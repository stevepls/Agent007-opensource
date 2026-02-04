"use client";

// Must be first - polyfill for older browsers
import "@/lib/polyfills";

import { useState, useCallback, useEffect, useRef } from "react";
import { useChat } from "@ai-sdk/react";
import { motion, AnimatePresence } from "framer-motion";
import { AgentList } from "@/components/AgentList";
import { ChatMessages } from "@/components/ChatMessages";
import { ChatInput, type Attachment } from "@/components/ChatInput";
import { DynamicStatusCards } from "@/components/DynamicStatusCards";
import { DynamicApproveDialog } from "@/components/DynamicApproveDialog";
import { Progress } from "@/components/ui/progress";
import {
  type AgentUpdate,
  type StatusCard,
  type ApprovalRequest,
  type OrchestratorResponse,
} from "@/lib/utils";
import { Menu, X, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";

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
  // UI State
  const [agents, setAgents] = useState<AgentUpdate[]>(DEFAULT_AGENTS);
  const [statusCards, setStatusCards] = useState<StatusCard[]>(DEFAULT_CARDS);
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);
  const [globalProgress, setGlobalProgress] = useState<number | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [currentProvider, setCurrentProvider] = useState<string>("connecting");
  const [preferredProvider, setPreferredProvider] = useState<string>("auto");

  // Track processed updates to prevent duplicates
  const processedUpdatesRef = useRef<Set<string>>(new Set());

  // Chat with streaming
  const {
    messages,
    input,
    handleInputChange,
    handleSubmit,
    isLoading,
    error,
    setInput,
  } = useChat({
    api: "/api/agent",
    body: { attachments, preferredProvider },
    onResponse: (response) => {
      console.log("Stream started:", response.status);
      // Track which AI provider is being used
      const provider = response.headers.get("X-AI-Provider") || "unknown";
      setCurrentProvider(provider);
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
    },
  });

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
    // Send approval to backend
    await fetch("/api/agent/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: id, approved: true }),
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
  }, []);

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
          <div className="flex items-center gap-3 mb-8 mt-2">
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
                    onChange={(e) => setPreferredProvider(e.target.value)}
                    className="text-[10px] px-1 py-0.5 rounded bg-background/50 border border-border cursor-pointer hover:bg-accent/50 transition-colors"
                    title="Select AI Provider"
                  >
                    <option value="auto">🔄 Auto</option>
                    <option value="orchestrator">🔵 Tools</option>
                    <option value="openai">🟢 GPT-4</option>
                    <option value="claude">🟣 Claude</option>
                  </select>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                    currentProvider === "orchestrator" ? "bg-blue-500/20 text-blue-400" :
                    currentProvider === "claude" ? "bg-purple-500/20 text-purple-400" :
                    currentProvider === "openai" ? "bg-green-500/20 text-green-400" :
                    currentProvider === "connecting" ? "bg-yellow-500/20 text-yellow-400 animate-pulse" :
                    "bg-gray-500/20 text-gray-400"
                  }`}>
                    {currentProvider === "orchestrator" ? "●" :
                     currentProvider === "claude" ? "●" :
                     currentProvider === "openai" ? "●" :
                     currentProvider === "connecting" ? "◌" : "○"}
                  </span>
                </div>
              </div>
            </div>
          </div>

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
        {/* Chat Messages */}
        <div className="flex-1 overflow-hidden">
          <ChatMessages
            messages={messages}
            isLoading={isLoading}
            onAttachmentsChange={setAttachments}
            error={error}
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
          />
        </div>
      </main>

      {/* Right Panel - Status Cards */}
      <aside
        className={`
          hidden xl:flex flex-col w-80 border-l border-border bg-card/30 backdrop-blur-xl
          transition-all duration-300
          ${rightPanelOpen ? "translate-x-0" : "translate-x-full"}
        `}
      >
        <div className="p-4 border-b border-border">
          <h2 className="font-semibold text-sm text-muted-foreground uppercase tracking-wider">
            Live Status
          </h2>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <DynamicStatusCards
            cards={statusCards}
            onAction={handleQuickAction}
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
