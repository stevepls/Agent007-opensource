import { NextRequest } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const CLAUDE_API_KEY = process.env.ANTHROPIC_API_KEY || "";
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";

// Track which provider is currently active
type AIProvider = "claude" | "openai" | "orchestrator" | "mock";

// ============================================================================
// GUARDRAILS - Safety and operational boundaries
// ============================================================================
const GUARDRAILS = {
  requiresApproval: [
    "deploy", "production", "delete", "remove", "drop", "truncate",
    "payment", "refund", "billing", "charge", "invoice",
    "user data", "pii", "credentials", "api key", "secret",
    "database migration", "schema change",
  ],
  forbidden: [
    "execute arbitrary code", "shell command without approval",
    "access other users' data", "bypass authentication",
    "disable security", "export all data",
  ],
  limits: {
    maxBulkOperations: 100,
    maxCostWithoutApproval: 50,
    maxTimeEstimateMinutes: 60,
  },
};

// ============================================================================
// AGENT DEFINITIONS
// ============================================================================
const AGENTS = {
  orchestrator: {
    id: "orchestrator",
    name: "Orchestrator",
    role: "Task Coordinator",
    goal: "Coordinate between agents and ensure tasks are completed efficiently",
    canDelegate: true,
    tools: ["delegate_task", "check_status", "request_approval"],
  },
  coder: {
    id: "coder",
    name: "Coder",
    role: "Software Developer",
    goal: "Write, review, and improve code quality",
    canDelegate: false,
    tools: ["read_file", "write_file", "search_code", "run_tests"],
  },
  reviewer: {
    id: "reviewer",
    name: "Reviewer",
    role: "Code Reviewer",
    goal: "Ensure code quality, security, and best practices",
    canDelegate: false,
    tools: ["read_file", "analyze_code", "check_security"],
  },
  ticketManager: {
    id: "ticket-manager",
    name: "Ticket Manager",
    role: "Support Coordinator",
    goal: "Manage tickets, prioritize issues, track resolution",
    canDelegate: false,
    tools: ["list_tickets", "create_ticket", "update_ticket", "search_tickets"],
  },
};

// ============================================================================
// ATTACHMENT HANDLING
// ============================================================================
interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  data?: string;
}

function processAttachments(attachments: Attachment[]): string {
  if (!attachments || attachments.length === 0) return "";
  
  let context = "\n\n📎 **Attachments:**\n";
  for (const att of attachments) {
    context += `- ${att.name} (${att.type})\n`;
    if (att.data && (att.type.includes("text") || att.type.includes("json"))) {
      try {
        const base64Data = att.data.split(",")[1] || att.data;
        const content = Buffer.from(base64Data, "base64").toString("utf-8");
        context += `\`\`\`\n${content.slice(0, 2000)}\n\`\`\`\n`;
      } catch { /* skip */ }
    }
  }
  return context;
}

// ============================================================================
// GUARDRAILS CHECK
// ============================================================================
function checkGuardrails(message: string): { allowed: boolean; reason?: string; requiresApproval?: boolean } {
  const lowerMessage = message.toLowerCase();
  
  for (const forbidden of GUARDRAILS.forbidden) {
    if (lowerMessage.includes(forbidden)) {
      return { allowed: false, reason: `Action not permitted: "${forbidden}" is blocked.` };
    }
  }
  
  for (const approval of GUARDRAILS.requiresApproval) {
    if (lowerMessage.includes(approval)) {
      return { allowed: true, requiresApproval: true };
    }
  }
  
  return { allowed: true };
}

// ============================================================================
// MAIN API HANDLER
// ============================================================================
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages, attachments = [], selectedAgent = "orchestrator", preferredProvider = "auto", sessionId = `session-${Date.now()}` } = body;

    if (!messages || messages.length === 0) {
      return new Response(JSON.stringify({ error: "No messages provided" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const lastMessage = messages[messages.length - 1];
    const guardrailCheck = checkGuardrails(lastMessage.content);

    if (!guardrailCheck.allowed) {
      return createProviderResponse("mock", `🚫 **Blocked**: ${guardrailCheck.reason}`);
    }

    const attachmentContext = processAttachments(attachments);
    const agent = AGENTS[selectedAgent as keyof typeof AGENTS] || AGENTS.orchestrator;

    // Provider selection based on user preference
    const orchestratorAvailable = await checkOrchestrator();
    
    // If user selected a specific provider, try that first
    if (preferredProvider !== "auto") {
      try {
        switch (preferredProvider) {
          case "orchestrator":
          case "orchestrator-claude":
            if (orchestratorAvailable) {
              return await callOrchestrator(messages, attachments, agent, "claude", sessionId);
            }
            throw new Error("Orchestrator not available");
          case "orchestrator-openai":
            if (orchestratorAvailable) {
              return await callOrchestrator(messages, attachments, agent, "openai", sessionId);
            }
            throw new Error("Orchestrator not available");
          case "claude":
            if (CLAUDE_API_KEY) {
              return await callClaude(messages, attachmentContext, agent);
            }
            throw new Error("Claude API key not configured");
          case "openai":
            if (OPENAI_API_KEY) {
              return await callOpenAI(messages, attachmentContext, agent);
            }
            throw new Error("OpenAI API key not configured");
        }
      } catch (error: any) {
        console.log(`Preferred provider ${preferredProvider} failed:`, error?.message);
        // Fall through to auto mode
      }
    }

    // Auto mode: Try providers in order: Orchestrator -> Claude -> OpenAI
    
    // 1. Try Orchestrator first (has tools access)
    if (orchestratorAvailable) {
      try {
        return await callOrchestrator(messages, attachments, agent, "auto", sessionId);
      } catch (error) {
        console.error("Orchestrator failed:", error);
      }
    }

    // 2. Try Claude
    if (CLAUDE_API_KEY) {
      try {
        return await callClaude(messages, attachmentContext, agent);
      } catch (error: any) {
        console.error("Claude failed:", error?.message || error);
      }
    }

    // 3. Try OpenAI
    if (OPENAI_API_KEY) {
      try {
        return await callOpenAI(messages, attachmentContext, agent);
      } catch (error: any) {
        console.error("OpenAI failed:", error?.message || error);
      }
    }

    // 4. Mock fallback
    return createProviderResponse("mock", 
      "⚠️ **No AI providers available**\n\n" +
      "Please configure one of:\n" +
      "- `ANTHROPIC_API_KEY` for Claude\n" +
      "- `OPENAI_API_KEY` for OpenAI\n" +
      "- Start the Orchestrator API on port 8502"
    );

  } catch (error) {
    console.error("Agent API error:", error);
    return new Response(JSON.stringify({ error: "Internal server error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}

// ============================================================================
// PROVIDER FUNCTIONS
// ============================================================================

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

function createProviderResponse(provider: AIProvider, text: string) {
  const encoder = new TextEncoder();
  const providerBadge = getProviderBadge(provider);
  const fullText = `${providerBadge}\n\n${text}`;
  
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(`0:${JSON.stringify(fullText)}\n`));
      controller.enqueue(encoder.encode(`d:{"finishReason":"stop","provider":"${provider}"}\n`));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
      "X-AI-Provider": provider,
    },
  });
}

function getProviderBadge(provider: AIProvider): string {
  switch (provider) {
    case "claude":
      return "🟣 **Claude**";
    case "openai":
      return "🟢 **GPT-4**";
    case "orchestrator":
      return "🔵 **Orchestrator** (Claude + Tools)";
    case "mock":
      return "⚪ **Offline**";
    default:
      return "";
  }
}

async function callOrchestrator(
  messages: Array<{ role: string; content: string }>,
  attachments: Attachment[],
  agent: typeof AGENTS[keyof typeof AGENTS],
  llmProvider: string = "auto",
  sessionId: string = ""
) {
  const response = await fetch(`${ORCHESTRATOR_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages,
      attachments,
      selected_agent: agent.id,
      stream: true,
      llm_provider: llmProvider,
      session_id: sessionId,
    }),
    signal: AbortSignal.timeout(300000), // 5 min - CrewAI crew can take a while
  });

  if (!response.ok) {
    throw new Error(`Orchestrator error: ${response.status}`);
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const providerBadge = getProviderBadge("orchestrator");
  let sentBadge = false;
  let lineBuffer = "";

  const transformStream = new TransformStream({
    transform(chunk, controller) {
      lineBuffer += decoder.decode(chunk, { stream: true });
      const lines = lineBuffer.split("\n");
      // Keep the last incomplete line in the buffer
      lineBuffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("PROGRESS:")) {
          // Parse progress event and emit as Vercel AI annotation (8: prefix)
          const progressJson = line.slice("PROGRESS:".length);
          controller.enqueue(encoder.encode(`8:${JSON.stringify([JSON.parse(progressJson)])}\n`));
        } else if (line.trim() && line.trim() !== " ") {
          // Regular text content
          if (!sentBadge) {
            controller.enqueue(encoder.encode(`0:${JSON.stringify(providerBadge + "\n\n")}\n`));
            sentBadge = true;
          }
          controller.enqueue(encoder.encode(`0:${JSON.stringify(line)}\n`));
        }
      }
    },
    flush(controller) {
      // Flush any remaining buffer
      if (lineBuffer.trim() && !lineBuffer.startsWith("PROGRESS:")) {
        if (!sentBadge) {
          controller.enqueue(encoder.encode(`0:${JSON.stringify(providerBadge + "\n\n")}\n`));
          sentBadge = true;
        }
        controller.enqueue(encoder.encode(`0:${JSON.stringify(lineBuffer)}\n`));
      }
      controller.enqueue(encoder.encode(`d:{"finishReason":"stop","provider":"orchestrator"}\n`));
    },
  });

  return new Response(response.body?.pipeThrough(transformStream), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
      "X-AI-Provider": "orchestrator",
    },
  });
}

async function callClaude(
  messages: Array<{ role: string; content: string }>,
  attachmentContext: string,
  agent: typeof AGENTS[keyof typeof AGENTS]
) {
  const systemPrompt = `You are Agent007, an AI assistant. You are currently operating as the ${agent.name} (${agent.role}).
Your goal: ${agent.goal}

Respond helpfully and concisely. If you need tools or integrations (like Google Drive, Gmail, etc.), 
mention that the Orchestrator backend is needed for those features.${attachmentContext}`;

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
    const errorText = await response.text();
    throw new Error(`Claude API error ${response.status}: ${errorText}`);
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const providerBadge = getProviderBadge("claude");
  let sentBadge = false;
  let buffer = "";

  const transformStream = new TransformStream({
    async transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") continue;

          try {
            const parsed = JSON.parse(data);
            if (parsed.type === "content_block_delta" && parsed.delta?.text) {
              if (!sentBadge) {
                controller.enqueue(encoder.encode(`0:${JSON.stringify(providerBadge + "\n\n")}\n`));
                sentBadge = true;
              }
              controller.enqueue(encoder.encode(`0:${JSON.stringify(parsed.delta.text)}\n`));
            }
          } catch { /* skip */ }
        }
      }
    },
    flush(controller) {
      controller.enqueue(encoder.encode(`d:{"finishReason":"stop","provider":"claude"}\n`));
    },
  });

  return new Response(response.body?.pipeThrough(transformStream), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
      "X-AI-Provider": "claude",
    },
  });
}

async function callOpenAI(
  messages: Array<{ role: string; content: string }>,
  attachmentContext: string,
  agent: typeof AGENTS[keyof typeof AGENTS]
) {
  const systemPrompt = `You are Agent007, an AI assistant. You are currently operating as the ${agent.name} (${agent.role}).
Your goal: ${agent.goal}

Respond helpfully and concisely. If you need tools or integrations (like Google Drive, Gmail, etc.), 
mention that the Orchestrator backend is needed for those features.${attachmentContext}`;

  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${OPENAI_API_KEY}`,
    },
    body: JSON.stringify({
      model: "gpt-4o",
      max_tokens: 4096,
      stream: true,
      messages: [
        { role: "system", content: systemPrompt },
        ...messages.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        })),
      ],
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenAI API error ${response.status}: ${errorText}`);
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const providerBadge = getProviderBadge("openai");
  let sentBadge = false;
  let buffer = "";

  const transformStream = new TransformStream({
    async transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") continue;

          try {
            const parsed = JSON.parse(data);
            const content = parsed.choices?.[0]?.delta?.content;
            if (content) {
              if (!sentBadge) {
                controller.enqueue(encoder.encode(`0:${JSON.stringify(providerBadge + "\n\n")}\n`));
                sentBadge = true;
              }
              controller.enqueue(encoder.encode(`0:${JSON.stringify(content)}\n`));
            }
          } catch { /* skip */ }
        }
      }
    },
    flush(controller) {
      controller.enqueue(encoder.encode(`d:{"finishReason":"stop","provider":"openai"}\n`));
    },
  });

  return new Response(response.body?.pipeThrough(transformStream), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "X-Vercel-AI-Data-Stream": "v1",
      "X-AI-Provider": "openai",
    },
  });
}
