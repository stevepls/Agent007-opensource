"use client";

// Must be first - polyfill for older browsers
import "@/lib/polyfills";

import { useState, useCallback, useEffect, useRef } from "react";
import { useChat } from "@ai-sdk/react";
import { motion, AnimatePresence } from "framer-motion";
import { AgentList } from "@/components/AgentList";
import { ChatMessages } from "@/components/ChatMessages";
import { ChatInput, type Attachment } from "@/components/ChatInput";
import { TaskQueue } from "@/components/TaskQueue";
import { QueueView } from "@/components/QueueView";
import { AgentStrip } from "@/components/AgentStrip";
import { DynamicApproveDialog } from "@/components/DynamicApproveDialog";
import { ViewRenderer } from "@/components/ViewRenderer";
import { FocusView } from "@/components/modes/FocusView";
import { ComposeView } from "@/components/modes/ComposeView";
import { AnalysisView } from "@/components/modes/AnalysisView";
import { ReviewView } from "@/components/modes/ReviewView";
import { Progress } from "@/components/ui/progress";
import {
  type AgentUpdate,
  type StatusCard,
  type ApprovalRequest,
  type OrchestratorResponse,
  type ProgressEvent,
  type StructuredData,
} from "@/lib/utils";
import {
  type ViewDirective,
  type ActionDefinition,
  EMPTY_DIRECTIVE,
} from "@/lib/viewProtocol";
import { Menu, X, Zap, Plus, Trash2, PanelRightOpen, PanelRightClose, Settings } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { usePersistedChat, useChatMemorySync } from "@/lib/usePersistedChat";

// Default agents
const DEFAULT_AGENTS: AgentUpdate[] = [
  { id: "orchestrator", name: "Orchestrator", status: "active", priority: 1 },
  { id: "time-logger", name: "Time Logger", status: "idle", priority: 5 },
  { id: "coder", name: "Coder", status: "idle", priority: 4 },
  { id: "reviewer", name: "Reviewer", status: "idle", priority: 4 },
  { id: "deployer", name: "Deployer", status: "idle", priority: 3 },
  { id: "ticket-manager", name: "Ticket Manager", status: "idle", priority: 5 },
];

// Default status cards
const DEFAULT_CARDS: StatusCard[] = [
  {
    id: "welcome",
    type: "info",
    title: "Welcome",
    description: "Agent007 is ready. Ask me anything.",
    priority: 1,
  },
];

export default function Dashboard() {
  // Chat persistence
  const { sessionId, initialMessages, isLoaded, saveMessages, clearHistory } = usePersistedChat();
  useChatMemorySync(sessionId);

  // UI State
  const [agents, setAgents] = useState<AgentUpdate[]>(DEFAULT_AGENTS);
  const [statusCards, setStatusCards] = useState<StatusCard[]>(DEFAULT_CARDS);
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);
  const [globalProgress, setGlobalProgress] = useState<number | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  // Queue/briefing cycling state
  const [activeQueueItemId, setActiveQueueItemId] = useState<string | null>(null);
  const [dismissedQueueIds, setDismissedQueueIds] = useState<Set<string>>(new Set());
  const activeQueueItemRef = useRef<string | null>(null);

  // Adaptive view protocol
  const [viewDirective, setViewDirective] = useState<ViewDirective>(EMPTY_DIRECTIVE);

  // Project scope — filters queue and constrains orchestrator context
  const [activeProject, setActiveProject] = useState<string | null>(null);
  type Provider = "auto" | "orchestrator" | "orchestrator-claude" | "orchestrator-openai" | "claude" | "openai";
  const [currentProvider, setCurrentProvider] = useState<string>("connecting");
  const [preferredProvider, setPreferredProvider] = useState<Provider>("auto");

  // Real-time activity tracking
  const [currentActivity, setCurrentActivity] = useState<string>("");
  const [activityLog, setActivityLog] = useState<string[]>([]);
  const [structuredBlocks, setStructuredBlocks] = useState<StructuredData[]>([]);

  // Track processed updates to prevent duplicates
  const processedUpdatesRef = useRef<Set<string>>(new Set());

  // Keep ref in sync with active queue item state
  useEffect(() => { activeQueueItemRef.current = activeQueueItemId; }, [activeQueueItemId]);

  // Chat with streaming
  const {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
    error,
    setInput,
    setMessages,
    stop,
    data,
  } = useChat({
    api: "/api/agent",
    id: sessionId || undefined, // Use session ID for chat identity
    initialMessages: initialMessages,
    body: { attachments, preferredProvider, sessionId },
    onResponse: (response) => {
      console.log("Stream started:", response.status);
      // Track which AI provider is being used
      const provider = response.headers.get("X-AI-Provider") || "unknown";
      setCurrentProvider(provider);
      // Clear structured blocks from previous response
      setStructuredBlocks([]);
    },
    onFinish: (message) => {
      // Only parse UI updates ONCE when streaming is complete
      try {
        const jsonMatch = message.content.match(/```json\n?([\s\S]*?)\n?```/);
        if (jsonMatch) {
          const parsed: OrchestratorResponse = JSON.parse(jsonMatch[1]);
          applyUIUpdates(parsed);
        }
      } catch {
        // Not valid JSON, that's fine
      }

      // Mark the active queue item as addressed and return to queue
      if (activeQueueItemRef.current) {
        setDismissedQueueIds(prev => {
          const next = new Set(prev);
          next.add(activeQueueItemRef.current!);
          return next;
        });
        setActiveQueueItemId(null);
        // Return to queue mode
        setViewDirective(EMPTY_DIRECTIVE);
      }
    },
  });

  // Persist messages whenever they change
  useEffect(() => {
    if (isLoaded && messages.length > 0) {
      saveMessages(messages);
    }
  }, [messages, isLoaded, saveMessages]);

  // Auto-brief ref kept for potential future use
  const autoBriefedRef = useRef(false);
  // Queue IS the brief. No auto-chat-prompt needed.
  // The user scans, taps, and acts from the queue directly.

  // Track dismissed count for potential future use
  const prevDismissedCountRef = useRef(0);
  useEffect(() => {
    prevDismissedCountRef.current = dismissedQueueIds.size;
  }, [dismissedQueueIds.size]);

  // Process real-time progress events from annotations
  const lastDataLengthRef = useRef(0);
  useEffect(() => {
    if (!data || data.length === 0) return;
    // Only process new events since last check
    const newEvents = data.slice(lastDataLengthRef.current);
    lastDataLengthRef.current = data.length;

    for (const item of newEvents) {
      // Data items from 2: protocol arrive as plain objects after SDK spreads them
      const event: Record<string, any> = (Array.isArray(item) ? item[0] : item) as any;
      if (!event?.type) continue;

      switch (event.type) {
        case "tool_start":
          setCurrentActivity(`Using ${event.tool || "tool"}...`);
          setActivityLog((prev) => [...prev.slice(-9), `🔧 Using ${event.tool || "tool"}...`]);
          if (event.agent) {
            setAgents((prev) =>
              prev.map((a) =>
                a.name.toLowerCase().includes(event.agent!.toLowerCase().split(" ")[0])
                  ? { ...a, status: "busy" as const, current_task: `Using ${event.tool || "tool"}` }
                  : a
              )
            );
          }
          break;
        case "tool_done":
          setCurrentActivity("");
          setActivityLog((prev) => [...prev.slice(-9), `✅ ${event.tool || "tool"} complete`]);
          // Auto-update status cards from tool results
          if (event.status_card) {
            const card = event.status_card as StatusCard;
            setStatusCards((prev) => {
              const filtered = prev.filter((c) => c.id !== card.id);
              return [card, ...filtered];
            });
          }
          break;
        case "thinking":
          setCurrentActivity(event.message || "Thinking...");
          setActivityLog((prev) => [...prev.slice(-9), `💭 ${event.message || "Thinking..."}`]);
          if (event.agent) {
            setAgents((prev) =>
              prev.map((a) =>
                a.name.toLowerCase().includes(event.agent!.toLowerCase().split(" ")[0])
                  ? { ...a, status: "active" as const, current_task: "Thinking..." }
                  : a
              )
            );
          }
          break;
        case "task_start":
          setActivityLog((prev) => [...prev.slice(-9), `▶ ${event.message || "Task started"}`]);
          break;
        case "task_done":
          setCurrentActivity("");
          setActivityLog((prev) => [...prev.slice(-9), `✅ ${event.message || "Task complete"}`]);
          setAgents((prev) =>
            prev.map((a) =>
              a.status === "busy" || a.status === "active"
                ? { ...a, status: "idle" as const, current_task: undefined }
                : a
            )
          );
          break;
        case "background_queued":
          setCurrentActivity(`Queued: ${event.request || "task"}...`);
          setActivityLog((prev) => [...prev.slice(-9), `📋 Task queued: ${event.request || ""}`]);
          break;
        case "background_update":
          setActivityLog((prev) => [...prev.slice(-9), `📬 Update: ${event.request || ""} — ${event.status}`]);
          break;
        case "structured_data":
          setStructuredBlocks((prev) => [...prev, event as unknown as StructuredData]);
          break;
        case "view":
          // Adaptive view protocol — Orchestrator sends a ViewDirective
          setViewDirective(event as unknown as ViewDirective);
          break;
      }
    }
  }, [data]);

  // Reset activity when loading stops
  useEffect(() => {
    if (!isLoading) {
      setCurrentActivity("");
      setActivityLog([]);
      // Reset all agents to idle when done
      setAgents((prev) =>
        prev.map((a) =>
          a.status === "busy" ? { ...a, status: "idle" as const, current_task: undefined } : a
        )
      );
    }
  }, [isLoading]);

  // Cancel handler
  const handleCancel = useCallback(async () => {
    stop();
    setCurrentActivity("");
    // Reset agents to idle
    setAgents((prev) =>
      prev.map((a) => ({ ...a, status: "idle" as const, current_task: undefined }))
    );
    // Tell the backend to cancel
    try {
      await fetch("/api/agent/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId }),
      });
    } catch {
      // Best-effort cancel
    }
  }, [stop, sessionId]);

  // Handle new chat
  const handleNewChat = useCallback(() => {
    clearHistory();
    setMessages([]);
    setStatusCards(DEFAULT_CARDS);
    setAgents(DEFAULT_AGENTS);
    setGlobalProgress(null);
    setPendingApproval(null);
    processedUpdatesRef.current.clear();
    autoBriefedRef.current = false; // Re-trigger auto-brief on new chat
    setDismissedQueueIds(new Set());
    setActiveQueueItemId(null);
    setViewDirective(EMPTY_DIRECTIVE); // Return to queue
    setActiveProject(null);
  }, [clearHistory, setMessages]);

  // Apply UI updates from orchestrator (with deduplication)
  const applyUIUpdates = useCallback((response: OrchestratorResponse) => {
    // Create a hash of the response to prevent duplicate processing
    const responseHash = JSON.stringify(response);
    if (processedUpdatesRef.current.has(responseHash)) {
      return; // Already processed this exact update
    }
    processedUpdatesRef.current.add(responseHash);
    
    // Limit the set size to prevent memory leak
    if (processedUpdatesRef.current.size > 100) {
      const entries = Array.from(processedUpdatesRef.current);
      processedUpdatesRef.current = new Set(entries.slice(-50));
    }

    // Update agents
    if (response.agents) {
      setAgents((prev) => {
        const updated = [...prev];
        for (const agentUpdate of response.agents!) {
          const idx = updated.findIndex((a) => a.id === agentUpdate.id);
          if (idx >= 0) {
            updated[idx] = { ...updated[idx], ...agentUpdate };
          } else {
            updated.push(agentUpdate);
          }
        }
        return updated.sort((a, b) => (a.priority || 5) - (b.priority || 5));
      });
    }

    // Update status cards - REPLACE instead of merge to prevent accumulation
    if (response.status_cards) {
      setStatusCards(response.status_cards.sort((a, b) => (a.priority || 5) - (b.priority || 5)));
    }

    // Handle priority UI
    if (response.priority_ui) {
      const ui = response.priority_ui;

      if (ui.cards) {
        // Replace cards from this response, keeping others
        setStatusCards((prev) => {
          const newCardIds = new Set(ui.cards!.map((c) => c.id));
          const keptCards = prev.filter((c) => !newCardIds.has(c.id));
          return [...ui.cards!, ...keptCards].sort((a, b) => (a.priority || 5) - (b.priority || 5));
        });
      }

      if (ui.show_progress_bar && ui.progress !== undefined) {
        setGlobalProgress(ui.progress);
      } else if (ui.show_progress_bar === false) {
        setGlobalProgress(null);
      }

      if (ui.highlight_agent) {
        setAgents((prev) =>
          prev.map((a) =>
            a.id === ui.highlight_agent
              ? { ...a, status: "active", priority: 0 }
              : a
          )
        );
      }
    }

    // Handle approval request
    if (response.needs_approval) {
      setPendingApproval(response.needs_approval);
    }
  }, []);

  // Handle approval
  const handleApprove = useCallback(async (id: string) => {
    // Send approval to backend with tool info
    const approvalPayload: any = {
      approval_id: id,
      approved: true,
    };
    
    // Include tool name and arguments if available
    if (pendingApproval?.tool) {
      approvalPayload.tool_name = pendingApproval.tool;
      approvalPayload.arguments = pendingApproval.args || {};
    }
    
    await fetch("/api/agent/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(approvalPayload),
    });
    setPendingApproval(null);
    setStatusCards((prev) => [
      {
        id: `approved-${id}`,
        type: "success",
        title: "Approved",
        description: "Action has been approved and is being executed.",
        priority: 0,
      },
      ...prev,
    ]);
  }, [pendingApproval]);

  // Handle rejection
  const handleReject = useCallback(async (id: string) => {
    await fetch("/api/agent/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: id, approved: false }),
    });
    setPendingApproval(null);
  }, []);

  // Quick actions
  const handleQuickAction = useCallback(
    (action: string) => {
      setInput(action);
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setTimeout(() => handleSubmit(fakeEvent), 100);
    },
    [setInput, handleSubmit]
  );

  // Handle queue/briefing item selection — sends it to chat for discussion
  const handleQueueItemSelect = useCallback((item: any) => {
    const itemId = item.id || item.data?.id;
    setActiveQueueItemId(itemId);

    // Build a TypedEntity and switch to focus mode
    const isQueue = !item.type && !item.kind?.includes("briefing");
    const q = item.data || item;

    if (isQueue && q.source) {
      // Queue item → real entity in focus mode
      const entity = {
        type: (q.source === "zendesk" ? "ticket" : "task") as any,
        id: itemId,
        source: {
          system: q.source as any,
          url: q.source_url || undefined,
        },
        data: {
          title: q.title,
          project_name: q.project_name,
          source_id: q.source_id,
          status: q.status,
          assignee: q.assignee,
          sla_tier: q.sla_tier,
          task_type: q.task_type,
          priority_score: q.priority_score,
          created_at: q.created_at,
          updated_at: q.updated_at,
          due_date: q.due_date,
          tags: q.tags,
          description: q.description || "",
        },
      };

      setViewDirective({
        ...EMPTY_DIRECTIVE,
        mode: "focus",
        primary_entity: entity,
        layout: { canvas: "split", emphasis: "entity", feed: "minimized" },
        chat: { visible: true, input_placeholder: `Ask about ${q.title}...` },
      });

      // No auto-chat prompt. The entity card IS the interaction.
      // Chat is available if the user wants to ask something.
    } else {
      // Briefing item → focus with entity data from briefing
      const briefingEntity = {
        type: "task" as any,
        id: itemId,
        data: {
          title: item.title || q.title || "",
          description: item.description || q.description || "",
          source: item.source || q.source || "",
          priority: item.priority,
        },
      };

      setViewDirective({
        ...EMPTY_DIRECTIVE,
        mode: "focus",
        primary_entity: briefingEntity,
        layout: { canvas: "split", emphasis: "entity", feed: "minimized" },
        chat: { visible: true, input_placeholder: "Ask about this item..." },
      });
    }
  }, []);

  // Handle "Create Task" from a queue/briefing item
  const handleCreateTask = useCallback((item: any) => {
    const title = item.title || "";
    const desc = item.description || "";
    const project = item.project_name || "";
    const source = item.source_url ? `\nSource: ${item.source_url}` : "";

    let prompt = "";
    if (project) {
      prompt = `Create a ClickUp task in the ${project} project:\nTitle: ${title}\nDescription: ${desc}${source}\n\nUse the appropriate ClickUp list for this project.`;
    } else {
      prompt = `Create a ClickUp task from this briefing item:\nTitle: ${title}\nDescription: ${desc}\n\nPick the most appropriate project and list based on the content.`;
    }

    setInput(prompt);
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    setTimeout(() => handleSubmit(fakeEvent), 100);
  }, [setInput, handleSubmit]);

  // Handle "Break into Subtasks" from a queue/briefing item
  const handleBreakdown = useCallback((item: any) => {
    const title = item.title || "";
    const desc = item.description || "";
    const project = item.project_name || "";
    const sourceId = item.source_id || "";
    const source = item.source || "";

    let prompt = "";
    if (source === "clickup" && sourceId) {
      prompt = `Break down this ClickUp task into subtasks:\nTask: "${title}" (ID: ${sourceId}, Project: ${project})\n${desc ? `Context: ${desc}\n` : ""}\nAnalyze what needs to be done and create 3-5 actionable subtasks in ClickUp under this task.`;
    } else {
      prompt = `Break down this item into actionable subtasks:\nItem: "${title}"\n${desc ? `Context: ${desc}\n` : ""}${project ? `Project: ${project}\n` : ""}\nAnalyze what needs to be done and create 3-5 actionable ClickUp tasks for this work.`;
    }

    setInput(prompt);
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    setTimeout(() => handleSubmit(fakeEvent), 100);
  }, [setInput, handleSubmit]);

  // Handle send from compose mode
  const handleComposeSend = useCallback((data: { to: string; subject: string; body: string; html?: string }) => {
    // Send via chat — the Orchestrator will use the Gmail tool
    const htmlFlag = data.html ? " (HTML email)" : "";
    setInput(`Send this email${htmlFlag}:\nTo: ${data.to}\nSubject: ${data.subject}\n\n${data.body}`);
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    setTimeout(() => handleSubmit(fakeEvent), 100);
    // Return to queue after sending
    setViewDirective(EMPTY_DIRECTIVE);
  }, [setInput, handleSubmit]);

  // Handle discard from compose mode
  const handleComposeDiscard = useCallback(() => {
    setViewDirective(EMPTY_DIRECTIVE);
    setActiveQueueItemId(null);
  }, []);

  // Handle PR approve from review mode
  const handleReviewApprove = useCallback(() => {
    const entity = viewDirective.primary_entity;
    if (entity) {
      setInput(`Approve PR #${entity.data.number || entity.id} in ${entity.data.repo || "the repo"}. Post an approval review on GitHub.`);
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setTimeout(() => handleSubmit(fakeEvent), 100);
    }
    setViewDirective(EMPTY_DIRECTIVE);
    setActiveQueueItemId(null);
  }, [viewDirective, setInput, handleSubmit]);

  // Handle request changes from review mode
  const handleReviewRequestChanges = useCallback((comment: string) => {
    const entity = viewDirective.primary_entity;
    if (entity) {
      setInput(`Request changes on PR #${entity.data.number || entity.id} in ${entity.data.repo || "the repo"} with this comment: "${comment}"`);
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setTimeout(() => handleSubmit(fakeEvent), 100);
    }
    setViewDirective(EMPTY_DIRECTIVE);
  }, [viewDirective, setInput, handleSubmit]);

  // Handle PR comment from review mode
  const handleReviewComment = useCallback((comment: string) => {
    const entity = viewDirective.primary_entity;
    if (entity) {
      setInput(`Add a comment to PR #${entity.data.number || entity.id}: "${comment}"`);
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setTimeout(() => handleSubmit(fakeEvent), 100);
    }
  }, [viewDirective, setInput, handleSubmit]);

  // Handle agent focus — bring agent's work into the chat
  const handleAgentFocus = useCallback((agentName: string) => {
    const labels: Record<string, string> = {
      scaffolding: "scaffolding agent",
      ticket_scan: "ticket manager agent",
      daily_briefing: "daily briefing agent",
      pr_scanner: "PR scanner agent",
      sla_monitor: "SLA monitor agent",
      stale_detector: "stale task detector agent",
      time_gap_detector: "time gap detector agent",
      comms_gap_detector: "client communication gap detector agent",
      deadline_watchdog: "deadline watchdog agent",
      cx_agent: "customer experience agent",
      ticket_review: "ticket review agent",
    };
    const label = labels[agentName] || agentName.replace(/_/g, " ") + " agent";

    // Enter focus mode with the agent as the primary entity
    setViewDirective({
      ...EMPTY_DIRECTIVE,
      mode: "focus",
      primary_entity: {
        type: "task",
        id: `agent-${agentName}`,
        data: {
          title: label.charAt(0).toUpperCase() + label.slice(1),
          description: `Background agent — click "Chat with Orchestrator" below to ask about its latest work.`,
          status: "running",
          project_name: "Agent007",
          source_id: agentName,
        },
      },
      layout: { canvas: "split", emphasis: "entity", feed: "minimized" },
      chat: { visible: true, input_placeholder: `Ask about the ${label}...` },
    });

    // Also send the query to chat so it auto-loads results
    setInput(`What has the ${label} been doing? Show me its latest results and any items that need my attention.`);
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    setTimeout(() => handleSubmit(fakeEvent), 200);
  }, [setInput, handleSubmit]);

  // Handle view protocol actions
  const handleViewAction = useCallback((action: ActionDefinition) => {
    if (action.tool) {
      // Action mapped to a tool — send as chat prompt
      const prompt = `Execute: ${action.label} (tool: ${action.tool}, args: ${JSON.stringify(action.args)})`;
      setInput(prompt);
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setTimeout(() => handleSubmit(fakeEvent), 100);
    } else {
      // No tool — treat label as a chat command
      setInput(action.label);
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setTimeout(() => handleSubmit(fakeEvent), 100);
    }
  }, [setInput, handleSubmit]);

  // Reset view directive on new chat
  const resetView = useCallback(() => {
    setViewDirective(EMPTY_DIRECTIVE);
  }, []);

  // Simulate real-time updates (demo)
  useEffect(() => {
    const interval = setInterval(() => {
      // Subtle status updates
      setAgents((prev) =>
        prev.map((a) => ({
          ...a,
          status: a.id === "orchestrator" ? "active" : a.status,
        }))
      );
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Don't render chat until persistence is loaded
  if (!isLoaded) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-indigo-500 flex items-center justify-center animate-pulse">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <p className="text-sm text-muted-foreground">Loading chat history...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile menu button */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed top-4 left-4 z-50 lg:hidden"
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
      >
        {mobileMenuOpen ? <X /> : <Menu />}
      </Button>

      {/* Left Sidebar - Agents */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-40 w-64 transform transition-transform duration-300 ease-in-out
          lg:relative lg:translate-x-0
          ${mobileMenuOpen ? "translate-x-0" : "-translate-x-full"}
          bg-[#0f0f0f] border-r border-[#262626]
        `}
      >
        <div className="flex flex-col h-full p-4">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-4 mt-2">
            <div className="w-10 h-10 rounded-xl bg-indigo-500 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg text-foreground font-bold">Agent007</h1>
              <div className="flex items-center gap-2">
                <p className="text-xs text-muted-foreground">Command Center</p>
                <div className="flex items-center gap-1">
                  <select
                    value={preferredProvider}
                    onChange={(e) => {
                      const value = e.target.value as Provider;
                      // Validate value before setting
                      if (["auto", "orchestrator", "orchestrator-claude", "orchestrator-openai", "claude", "openai"].includes(value)) {
                        setPreferredProvider(value);
                      }
                    }}
                    className="text-[10px] px-1 py-0.5 rounded bg-zinc-900 border border-border cursor-pointer hover:bg-accent/50 transition-colors"
                    title="Select AI Provider"
                  >
                    <option value="auto">🔄 Auto</option>
                    <option value="orchestrator-claude">🔵 Orchestrator (Claude)</option>
                    <option value="orchestrator-openai">🟠 Orchestrator (GPT-4)</option>
                    <option value="claude">🟣 Claude Direct</option>
                    <option value="openai">🟢 GPT-4 Direct</option>
                  </select>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    currentProvider === "orchestrator" || currentProvider === "orchestrator-claude" ? "bg-blue-500/20 text-blue-400" :
                    currentProvider === "orchestrator-openai" ? "bg-orange-500/20 text-orange-400" :
                    currentProvider === "claude" ? "bg-purple-500/20 text-purple-400" :
                    currentProvider === "openai" ? "bg-green-500/20 text-green-400" :
                    currentProvider === "connecting" ? "bg-yellow-500/20 text-yellow-400 animate-pulse" :
                    "bg-gray-500/20 text-gray-400"
                  }`}>
                    {currentProvider === "orchestrator" || currentProvider === "orchestrator-claude" ? "●" :
                     currentProvider === "orchestrator-openai" ? "●" :
                     currentProvider === "claude" ? "●" :
                     currentProvider === "openai" ? "●" :
                     currentProvider === "connecting" ? "◌" : "○"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* New Chat / Clear History */}
          <div className="flex gap-2 mb-4">
            <Button
              variant="outline"
              size="sm"
              className="flex-1 text-xs"
              onClick={handleNewChat}
            >
              <Plus className="w-3 h-3 mr-1" />
              New Chat
            </Button>
            {messages.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground hover:text-destructive"
                onClick={handleNewChat}
                title="Clear history"
              >
                <Trash2 className="w-3 h-3" />
              </Button>
            )}
          </div>

          {/* Session indicator */}
          {messages.length > 0 && (
            <p className="text-[10px] text-muted-foreground/50 mb-4 truncate" title={sessionId}>
              Session: {sessionId.slice(-8)}
            </p>
          )}

          {/* Global progress bar */}
          <AnimatePresence>
            {globalProgress !== null && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mb-4"
              >
                <p className="text-xs text-muted-foreground mb-2">
                  Task Progress
                </p>
                <Progress value={globalProgress} className="h-2" />
                <p className="text-xs text-right text-muted-foreground mt-1">
                  {globalProgress}%
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Settings link */}
          <Link href="/settings" className="flex items-center gap-2 px-2 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-[#1a1a1a] transition-colors mb-2">
            <Settings className="w-3.5 h-3.5" />
            Settings
          </Link>

          {/* Agent List */}
          <AgentList agents={agents} onAgentClick={handleQuickAction} />
        </div>
      </aside>

      {/* Main Content — Adaptive View */}
      <main className="flex-1 flex flex-col min-w-0 h-full">
        <ViewRenderer
          directive={viewDirective}
          onAction={handleViewAction}

          chatSlot={
            <div className="flex flex-col h-full">
              <div className="flex-1 overflow-hidden">
                <ChatMessages
                  messages={messages}
                  isLoading={isLoading}
                  error={error}
                  currentActivity={currentActivity}
                  activityLog={activityLog}
                  structuredBlocks={structuredBlocks}
                />
              </div>
              <div className="bg-[#0f0f0f] border-t border-[#262626]">
                <ChatInput
                  input={input}
                  handleInputChange={handleInputChange}
                  handleSubmit={handleSubmit}
                  isLoading={isLoading}
                  onAttachmentsChange={setAttachments}
                  onCancel={handleCancel}
                />
              </div>
            </div>
          }

          queueSlot={
            <QueueView
              activeItemId={activeQueueItemId}
              onItemSelect={handleQueueItemSelect}
              onCreateTask={handleCreateTask}
              onBreakdown={handleBreakdown}
              onDiscuss={(item: any) => {
                // Open chat drawer with contextual prompt — stay in queue mode
                const q = item.data || item;
                setInput(`Tell me about "${q.title || item.title}" (${q.project_name || ""}, ${q.source || ""} ${q.source_id || ""}). What's the current status and what should I do?`);
                // ViewRenderer exposes chat drawer via a ref or state — for now
                // we trigger it by setting a view hint
                setViewDirective({
                  ...viewDirective,
                  mode: "queue",
                  chat: { visible: true, input_placeholder: `Discussing ${q.title || item.title}...` },
                });
              }}
              dismissedIds={dismissedQueueIds}
              activeProject={activeProject}
              onProjectSelect={setActiveProject}
            />
          }

          agentStripSlot={<AgentStrip onAgentFocus={handleAgentFocus} />}

          focusSlot={
            viewDirective.primary_entity ? (
              <FocusView
                entity={viewDirective.primary_entity}
                onBack={() => {
                  setViewDirective(EMPTY_DIRECTIVE);
                  setActiveQueueItemId(null);
                }}
                onAction={(action, entity) => {
                  const d = entity.data;

                  // Handle inline actions with parameters
                  if (action.startsWith("add_comment:")) {
                    const text = action.slice("add_comment:".length);
                    const prompt = `Add this comment to ${entity.source?.system} ${d.source_id} ("${d.title}"):\n\n${text}`;
                    setInput(prompt);
                    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
                    setTimeout(() => handleSubmit(fakeEvent), 100);
                    return;
                  }
                  if (action.startsWith("snooze:")) {
                    const duration = action.slice("snooze:".length);
                    const prompt = `Snooze "${d.title}" (${entity.source?.system} ${d.source_id}) for ${duration}. Update the due date and add a comment noting it's been deferred.`;
                    setInput(prompt);
                    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
                    setTimeout(() => handleSubmit(fakeEvent), 100);
                    return;
                  }
                  if (action.startsWith("create_branch:")) {
                    const branch = action.slice("create_branch:".length);
                    const prompt = `Create branch "${branch}" for "${d.title}" (${d.project_name}, ${entity.source?.system} ${d.source_id}) and push it to GitHub.`;
                    setInput(prompt);
                    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
                    setTimeout(() => handleSubmit(fakeEvent), 100);
                    return;
                  }

                  const prompts: Record<string, string> = {
                    assign: `Assign task "${d.title}" (${d.project_name}, ${entity.source?.system} ${d.source_id}) to the most appropriate team member.`,
                    message_assignee: `Send a Slack message to ${d.assignee} asking for a status update on "${d.title}" (${d.project_name}).`,
                    subtasks: `Break down "${d.title}" (${d.project_name}, ${entity.source?.system} ${d.source_id}) into 3-5 actionable subtasks in ClickUp.`,
                    branch: `Create a feature branch for "${d.title}" (${d.project_name}, ${entity.source?.system} ${d.source_id}) and push it to GitHub.`,
                    snooze: `Snooze "${d.title}" for 24 hours. Add a comment that it's been deferred.`,
                  };
                  const prompt = prompts[action] || `Take action "${action}" on "${d.title}"`;
                  setInput(prompt);
                  const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
                  setTimeout(() => handleSubmit(fakeEvent), 100);
                }}
                chatSlot={
                  <div className="flex flex-col h-full">
                    <div className="flex-1 overflow-hidden">
                      <ChatMessages
                        messages={messages}
                        isLoading={isLoading}
                        error={error}
                        currentActivity={currentActivity}
                        activityLog={activityLog}
                        structuredBlocks={structuredBlocks}
                      />
                    </div>
                    <div className="bg-[#0f0f0f] border-t border-[#262626]">
                      <ChatInput
                        input={input}
                        handleInputChange={handleInputChange}
                        handleSubmit={handleSubmit}
                        isLoading={isLoading}
                        onAttachmentsChange={setAttachments}
                        onCancel={handleCancel}
                      />
                    </div>
                  </div>
                }
              />
            ) : undefined
          }

          composeSlot={
            viewDirective.primary_entity?.type === "email_draft" ? (
              <ComposeView
                entity={viewDirective.primary_entity}
                onSend={handleComposeSend}
                onDiscard={handleComposeDiscard}
                onBack={() => {
                  setViewDirective(EMPTY_DIRECTIVE);
                  setActiveQueueItemId(null);
                }}
              />
            ) : undefined
          }

          analysisSlot={
            viewDirective.primary_entity && ["table", "time_entries", "metrics"].includes(viewDirective.primary_entity.type) ? (
              <AnalysisView
                entity={viewDirective.primary_entity}
                onBack={() => {
                  setViewDirective(EMPTY_DIRECTIVE);
                  setActiveQueueItemId(null);
                }}
              />
            ) : undefined
          }

          reviewSlot={
            viewDirective.primary_entity && ["pr", "diff"].includes(viewDirective.primary_entity.type) ? (
              <ReviewView
                entity={viewDirective.primary_entity}
                onApprove={handleReviewApprove}
                onRequestChanges={handleReviewRequestChanges}
                onComment={handleReviewComment}
                onBack={() => {
                  setViewDirective(EMPTY_DIRECTIVE);
                  setActiveQueueItemId(null);
                }}
              />
            ) : undefined
          }
        />
      </main>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-30 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Approval Dialog */}
      <DynamicApproveDialog
        request={pendingApproval}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}
