import { NextRequest } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const CLAUDE_API_KEY = process.env.ANTHROPIC_API_KEY || "";

/**
 * POST /api/agent
 * 
 * Proxies chat requests to the Orchestrator FastAPI backend.
 * Supports streaming responses with structured JSON for UI updates.
 * 
 * Expected request body (from Vercel AI SDK useChat):
 * {
 *   messages: [{ role: "user" | "assistant", content: string }]
 * }
 * 
 * Response: Streaming text with embedded JSON for UI instructions
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages } = body;

    if (!messages || !Array.isArray(messages)) {
      return new Response(
        JSON.stringify({ error: "Messages array required" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Get the last user message
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage || lastMessage.role !== "user") {
      return new Response(
        JSON.stringify({ error: "Last message must be from user" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Check if orchestrator is available
    const orchestratorAvailable = await checkOrchestrator();

    if (orchestratorAvailable) {
      // Forward to Orchestrator
      return await proxyToOrchestrator(messages);
    } else {
      // Fallback to direct Claude API with structured output
      return await callClaudeDirectly(messages);
    }
  } catch (error) {
    console.error("Agent API error:", error);
    return new Response(
      JSON.stringify({ error: "Internal server error" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}

/**
 * Check if orchestrator is running
 */
async function checkOrchestrator(): Promise<boolean> {
  try {
    const response = await fetch(`${ORCHESTRATOR_URL}/health`, {
      method: "GET",
      signal: AbortSignal.timeout(2000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Proxy request to Orchestrator FastAPI
 * Transforms plain text stream to Vercel AI SDK Data Stream Protocol
 */
async function proxyToOrchestrator(messages: Array<{ role: string; content: string }>) {
  const response = await fetch(`${ORCHESTRATOR_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messages,
      stream: true,
      structured_output: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`Orchestrator error: ${response.status}`);
  }

  // Transform plain text stream to Vercel AI SDK Data Stream Protocol
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  const transformStream = new TransformStream({
    transform(chunk, controller) {
      const text = decoder.decode(chunk, { stream: true });
      
      // Stream each chunk as it arrives, properly formatted
      if (text.trim()) {
        const escaped = JSON.stringify(text);
        controller.enqueue(encoder.encode(`0:${escaped}\n`));
      }
    },
    flush(controller) {
      controller.enqueue(encoder.encode(`d:{"finishReason":"stop"}\n`));
    },
  });

  return new Response(response.body?.pipeThrough(transformStream), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
    },
  });
}

/**
 * Direct Claude API call with structured output for UI
 * Fallback when orchestrator is not available
 */
async function callClaudeDirectly(messages: Array<{ role: string; content: string }>) {
  if (!CLAUDE_API_KEY) {
    return createMockResponse(messages);
  }

  const systemPrompt = `You are Agent007, an AI orchestrator that manages autonomous agents for development tasks.

When responding, you can include structured JSON to update the UI. Wrap JSON in code blocks:

\`\`\`json
{
  "text": "Human-readable response",
  "priority_ui": {
    "cards": [
      {"id": "card1", "type": "info", "title": "Status", "description": "Current status..."}
    ],
    "show_progress_bar": false
  },
  "agents": [
    {"id": "coder", "name": "Coder", "status": "active", "current_task": "Working on..."}
  ]
}
\`\`\`

Available card types: info, success, warning, error, progress, metric
Available agent statuses: idle, active, busy, error, offline

For approval requests, include:
\`\`\`json
{
  "needs_approval": {
    "id": "unique-id",
    "type": "deploy",
    "title": "Deploy to Production",
    "description": "This will deploy the latest code...",
    "timeout_seconds": 60
  }
}
\`\`\`

Respond naturally but include JSON when UI updates are needed.`;

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": CLAUDE_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 4096,
      stream: true,
      system: systemPrompt,
      messages: messages.map((m) => ({
        role: m.role === "user" ? "user" : "assistant",
        content: m.content,
      })),
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    console.error("Claude API error:", error);
    return createMockResponse(messages);
  }

  // Transform Claude's SSE stream to Vercel AI SDK Data Stream Protocol
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = "";

  const transformStream = new TransformStream({
    async transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || ""; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") {
            controller.enqueue(encoder.encode(`d:{"finishReason":"stop"}\n`));
            continue;
          }

          try {
            const parsed = JSON.parse(data);
            if (parsed.type === "content_block_delta" && parsed.delta?.text) {
              // Vercel AI SDK Data Stream Protocol: 0:"text"\n
              const escaped = JSON.stringify(parsed.delta.text);
              controller.enqueue(encoder.encode(`0:${escaped}\n`));
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
    },
    flush(controller) {
      // Process any remaining buffer
      if (buffer.trim()) {
        controller.enqueue(encoder.encode(`d:{"finishReason":"stop"}\n`));
      }
    },
  });

  return new Response(response.body?.pipeThrough(transformStream), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
    },
  });
}

/**
 * Create a mock response for demo/development
 * Uses Vercel AI SDK Data Stream Protocol: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
 */
function createMockResponse(messages: Array<{ role: string; content: string }>) {
  const lastMessage = messages[messages.length - 1]?.content.toLowerCase() || "";
  
  let responseText = "";
  let json: Record<string, unknown> = {};

  if (lastMessage.includes("deploy")) {
    responseText = "I'll initiate the deployment process. First, let me run the pre-deployment checks.";
    json = {
      priority_ui: {
        show_progress_bar: true,
        progress: 25,
        cards: [
          {
            id: "deploy-status",
            type: "progress",
            title: "Deployment",
            description: "Running pre-deployment checks...",
            progress: 25,
            priority: 1,
          },
        ],
      },
      agents: [
        { id: "deployer", name: "Deployer", status: "active", priority: 1, current_task: "Running checks" },
      ],
      needs_approval: {
        id: `deploy-${Date.now()}`,
        type: "deploy",
        title: "Deploy to Production",
        description: "All checks passed. Ready to deploy the latest code to production.",
        details: {
          branch: "main",
          commit: "a1b2c3d",
          environment: "production",
        },
        timeout_seconds: 120,
      },
    };
  } else if (lastMessage.includes("ticket")) {
    responseText = "Here's a summary of your open tickets:";
    json = {
      priority_ui: {
        cards: [
          {
            id: "tickets-urgent",
            type: "warning",
            title: "3 Urgent Tickets",
            description: "Require immediate attention",
            priority: 1,
            action: { label: "View Tickets", onClick: "show urgent tickets" },
          },
          {
            id: "tickets-normal",
            type: "info",
            title: "12 Open Tickets",
            description: "Normal priority",
            priority: 3,
          },
        ],
      },
      agents: [
        { id: "ticket-manager", name: "Ticket Manager", status: "active", current_task: "Fetching tickets" },
      ],
    };
  } else if (lastMessage.includes("time")) {
    responseText = "Here's your time summary for today:";
    json = {
      priority_ui: {
        cards: [
          {
            id: "time-today",
            type: "metric",
            title: "Hours Today",
            value: "6.5",
            description: "Across 3 projects",
            priority: 2,
            icon: "clock",
          },
          {
            id: "time-week",
            type: "metric",
            title: "Hours This Week",
            value: "28.5",
            description: "On track for 40h target",
            priority: 3,
            icon: "trending",
          },
        ],
      },
      agents: [
        { id: "time-logger", name: "Time Logger", status: "active", current_task: "Syncing time entries" },
      ],
    };
  } else {
    responseText = "I'm Agent007, your AI orchestrator. I can help you with:\n\n• **Deployments** - Deploy code, run checks, manage releases\n• **Tickets** - View, create, and manage support tickets\n• **Time Tracking** - Log time, view summaries, sync with Harvest\n• **Code Reviews** - Request reviews, check PR status\n• **Database** - Run queries (with approval), check schemas\n\nWhat would you like me to help with?";
    json = {
      agents: [
        { id: "orchestrator", name: "Orchestrator", status: "active", priority: 1 },
      ],
    };
  }

  // Combine text and JSON
  const fullResponse = responseText + "\n\n```json\n" + JSON.stringify(json, null, 2) + "\n```";

  // Create a streaming response using Vercel AI SDK Data Stream Protocol
  // Format: 0:"text chunk"\n (text part type = 0)
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      // Stream text chunks using data stream protocol
      // Split into sentences for natural streaming
      const chunks = fullResponse.match(/[^.!?\n]+[.!?\n]?|```[\s\S]*?```/g) || [fullResponse];
      
      for (const chunk of chunks) {
        if (chunk.trim()) {
          // Format: 0:"escaped text"\n
          const escaped = JSON.stringify(chunk);
          controller.enqueue(encoder.encode(`0:${escaped}\n`));
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
      }
      
      // End with finish message (type d = done with finish reason)
      controller.enqueue(encoder.encode(`d:{"finishReason":"stop"}\n`));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
    },
  });
}

/**
 * POST /api/agent/approve
 * Handle approval/rejection of pending requests
 */
export async function PUT(request: NextRequest) {
  return handleApproval(request);
}

async function handleApproval(request: NextRequest) {
  try {
    const body = await request.json();
    const { approval_id, approved } = body;

    // Forward to orchestrator if available
    const orchestratorAvailable = await checkOrchestrator();
    
    if (orchestratorAvailable) {
      const response = await fetch(`${ORCHESTRATOR_URL}/api/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval_id, approved }),
      });
      
      return new Response(response.body, {
        status: response.status,
        headers: { "Content-Type": "application/json" },
      });
    }

    // Mock response
    return new Response(
      JSON.stringify({
        success: true,
        approval_id,
        status: approved ? "approved" : "rejected",
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (error) {
    return new Response(
      JSON.stringify({ error: "Failed to process approval" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
