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
import { Progress } from "@/components/ui/progress";
import {
  type AgentUpdate,
  type StatusCard,
  type ApprovalRequest,
  type OrchestratorResponse,
  type ProgressEvent,
  type StructuredData,
} from "@/lib/utils";
import { Menu, X, Zap, Plus, Trash2, PanelRightOpen, PanelRightClose } from "lucide-react";
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

      // Mark the active queue item as addressed
      if (activeQueueItemRef.current) {
        setDismissedQueueIds(prev => {
          const next = new Set(prev);
          next.add(activeQueueItemRef.current!);
          return next;
        });
        setActiveQueueItemId(null);
      }
    },
  });

  // Persist messages whenever they change
  useEffect(() => {
    if (isLoaded && messages.length > 0) {
      saveMessages(messages);
    }
  }, [messages, isLoaded, saveMessages]);

  // Auto-brief on new/empty chat
  const autoBriefedRef = useRef(false);
  useEffect(() => {
    if (isLoaded && messages.length === 0 && !isLoading && !autoBriefedRef.current) {
      autoBriefedRef.current = true;
      // Small delay to let the UI settle
      const timer = setTimeout(() => {
        setInput("Brief me on what needs my attention right now. Start with the most urgent items.");
        const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
        setTimeout(() => handleSubmit(fakeEvent), 150);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isLoaded, messages.length, isLoading, setInput, handleSubmit]);

  // Auto-cycle: after finishing one item, prompt for the next
  const prevDismissedCountRef = useRef(0);
  useEffect(() => {
    const currentCount = dismissedQueueIds.size;
    const justDismissed = currentCount > prevDismissedCountRef.current;
    prevDismissedCountRef.current = currentCount;

    // Only trigger when a new item was just dismissed AND we're not loading
    if (justDismissed && !isLoading && messages.length > 0) {
      const timer = setTimeout(() => {
        setInput("What's next? Brief me on the next most urgent item.");
        const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
        setTimeout(() => handleSubmit(fakeEvent), 150);
      }, 2000); // 2s pause between items so Steve can read the response
      return () => clearTimeout(timer);
    }
  }, [dismissedQueueIds.size, isLoading, messages.length, setInput, handleSubmit]);

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

    // Build a prompt for the orchestrator to address this item
    let prompt = "";
    if (item.kind === "briefing" || item.type) {
      // Briefing item
      prompt = `Address this briefing item: "${item.title || item.data?.title}"\n\n${item.description || item.data?.description || ""}`;
    } else {
      // Queue item
      const q = item.data || item;
      prompt = `Review and brief me on this task: "${q.title}" (${q.project_name}, ${q.source} ${q.source_id})${q.source_url ? `\nLink: ${q.source_url}` : ""}`;
    }

    setInput(prompt);
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    setTimeout(() => handleSubmit(fakeEvent), 100);
  }, [setInput, handleSubmit]);

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
    };
    const label = labels[agentName] || agentName.replace(/_/g, " ") + " agent";
    setInput(`What has the ${label} been doing? Show me its latest results and any items that need my attention.`);
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    setTimeout(() => handleSubmit(fakeEvent), 150);
  }, [setInput, handleSubmit]);

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
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center animate-pulse">
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
          bg-card/50 backdrop-blur-xl border-r border-border
        `}
      >
        <div className="flex flex-col h-full p-4">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-4 mt-2">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold gradient-text">Agent007</h1>
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
                    className="text-[10px] px-1 py-0.5 rounded bg-background/50 border border-border cursor-pointer hover:bg-accent/50 transition-colors"
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

          {/* Agent List */}
          <AgentList agents={agents} onAgentClick={handleQuickAction} />
        </div>
      </aside>

      {/* Main Content - Chat */}
      <main className="flex-1 flex flex-col min-w-0 h-full">
        {/* Top bar with right panel toggle */}
        <div className="flex items-center justify-end px-4 py-2 border-b border-border bg-card/30">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setRightPanelOpen(!rightPanelOpen)}
            title={rightPanelOpen ? "Hide panel" : "Show panel"}
          >
            {rightPanelOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </Button>
        </div>

        {/* Chat Messages */}
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

        {/* Chat Input */}
        <div className="border-t border-border bg-card/30 backdrop-blur-xl">
          <ChatInput
            input={input}
            handleInputChange={handleInputChange}
            handleSubmit={handleSubmit}
            isLoading={isLoading}
            onAttachmentsChange={setAttachments}
            onCancel={handleCancel}
          />
        </div>
      </main>

      {/* Right Panel */}
      <aside
        className={`
          ${rightPanelOpen ? "flex" : "hidden"} flex-col w-80 border-l border-border bg-card/30 backdrop-blur-xl
          transition-all duration-300
        `}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
          <h2 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Priority Feed
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <AgentStrip onAgentFocus={handleAgentFocus} />
          <QueueView
            activeItemId={activeQueueItemId}
            onItemSelect={handleQueueItemSelect}
            onCreateTask={handleCreateTask}
            onBreakdown={handleBreakdown}
            dismissedIds={dismissedQueueIds}
          />
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
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
