"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { ActionBar } from "@/components/ActionBar";
import { Button } from "@/components/ui/button";
import { MessageSquare, LayoutList, X, ChevronRight } from "lucide-react";
import type { ViewDirective, ViewMode, ActionDefinition, LayoutHint } from "@/lib/viewProtocol";
import { resolveMode, resolveLayout } from "@/lib/viewProtocol";

// ── Surface Renderer ──────────────────────────────────────────
// Queue-first. Chat is a drawer, not a permanent column.
// Queue owns the full canvas in queue-dominant mode.

interface ViewRendererProps {
  directive: ViewDirective;
  onAction: (action: ActionDefinition) => void;

  queueSlot: React.ReactNode;
  chatSlot: React.ReactNode;
  agentStripSlot: React.ReactNode;

  focusSlot?: React.ReactNode;
  analysisSlot?: React.ReactNode;
  composeSlot?: React.ReactNode;
  reviewSlot?: React.ReactNode;
}

export function ViewRenderer({
  directive,
  onAction,
  queueSlot,
  chatSlot,
  agentStripSlot,
  focusSlot,
  analysisSlot,
  composeSlot,
  reviewSlot,
}: ViewRendererProps) {
  const mode = useMemo(() => resolveMode(directive), [directive]);
  const layout = useMemo(
    () => resolveLayout(mode, directive.layout),
    [mode, directive.layout]
  );
  const actions = directive.actions;

  // Chat drawer state — closed by default in queue mode
  const [chatOpen, setChatOpen] = useState(false);

  // Mobile: toggle between primary and chat
  const [mobileView, setMobileView] = useState<"primary" | "chat">("primary");

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full relative">
      {/* ── Canvas ─────────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0">

        {/* ══════════════════════════════════════════════════
            QUEUE-DOMINANT — Queue owns the full canvas.
            Chat is a slide-over drawer, NOT a permanent column.
           ══════════════════════════════════════════════════ */}
        {layout.canvas === "queue-dominant" && (
          <>
            {/* Queue — full width */}
            <div className="flex-1 flex flex-col bg-[#0a0a0a]">
              {/* Agent strip + chat toggle */}
              <div className="flex items-center justify-between px-4 py-2 border-b border-[#1a1a1a]">
                <div className="flex-1">{agentStripSlot}</div>
                <Button
                  variant="ghost"
                  size="sm"
                  className={cn(
                    "h-7 text-xs gap-1.5 ml-3",
                    chatOpen ? "text-indigo-400" : "text-muted-foreground"
                  )}
                  onClick={() => setChatOpen(!chatOpen)}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Chat</span>
                </Button>
              </div>

              {/* Queue content — full width on desktop and mobile */}
              <div className="flex-1 overflow-y-auto p-4 lg:p-6">
                {queueSlot}
              </div>
            </div>

            {/* Chat drawer — slides in from right on desktop, bottom on mobile */}
            {chatOpen && (
              <>
                {/* Desktop: right drawer */}
                <div className="hidden lg:flex flex-col w-96 border-l border-[#1a1a1a] bg-[#0a0a0a] animate-in slide-in-from-right duration-200">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-[#1a1a1a]">
                    <span className="text-xs font-medium text-muted-foreground">Chat</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setChatOpen(false)}>
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  {chatSlot}
                </div>

                {/* Mobile: full-screen overlay */}
                <div className="flex lg:hidden fixed inset-0 z-40 flex-col bg-[#0a0a0a]">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-[#1a1a1a]">
                    <span className="text-xs font-medium text-muted-foreground">Chat</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setChatOpen(false)}>
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                  {chatSlot}
                </div>
              </>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════
            SPLIT — Entity + chat main, queue sidebar
           ══════════════════════════════════════════════════ */}
        {layout.canvas === "split" && (
          <>
            <div className="flex-1 flex flex-col min-w-0">
              {mode === "focus" && (focusSlot || <ModePlaceholder mode="focus" />)}
              {mode === "queue" && chatSlot}
            </div>

            {layout.feed !== "hidden" && (
              <aside className={cn(
                "hidden lg:flex border-l border-[#1a1a1a] bg-[#0a0a0a] flex-col transition-all duration-300",
                layout.feed === "minimized" ? "w-64" : "w-80",
              )}>
                <div className="p-3 border-b border-[#1a1a1a]">
                  {agentStripSlot}
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {queueSlot}
                </div>
              </aside>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════
            CANVAS-DOMINANT — Full width, no sidebar
           ══════════════════════════════════════════════════ */}
        {layout.canvas === "canvas-dominant" && (
          <div className="flex-1 flex flex-col min-w-0">
            {mode === "analysis" && (analysisSlot || <ModePlaceholder mode="analysis" />)}
            {mode === "review" && (reviewSlot || <ModePlaceholder mode="review" />)}
          </div>
        )}

        {/* ══════════════════════════════════════════════════
            COMPOSE-DOMINANT — Editor + chat sidebar
           ══════════════════════════════════════════════════ */}
        {layout.canvas === "compose-dominant" && (
          <>
            <div className="hidden lg:flex flex-1 min-w-0">
              <div className="flex-1 flex flex-col min-w-0">
                {composeSlot || <ModePlaceholder mode="compose" />}
              </div>
              <div className="w-80 flex flex-col border-l border-[#1a1a1a] bg-[#0a0a0a]">
                {chatSlot}
              </div>
            </div>
            <div className="flex lg:hidden flex-1 flex-col min-h-0">
              {mobileView === "primary" ? (
                composeSlot || <ModePlaceholder mode="compose" />
              ) : (
                <div className="flex-1 flex flex-col bg-[#0a0a0a]">{chatSlot}</div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Mobile bottom bar (compose mode) ─────────────────── */}
      {layout.canvas === "compose-dominant" && (
        <div className="flex lg:hidden items-center border-t border-[#1a1a1a] bg-[#0f0f0f]">
          <button
            onClick={() => setMobileView("primary")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors",
              mobileView === "primary" ? "text-indigo-400 bg-indigo-500/10" : "text-muted-foreground"
            )}
          >
            <LayoutList className="w-4 h-4" />
            Editor
          </button>
          <button
            onClick={() => setMobileView("chat")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors",
              mobileView === "chat" ? "text-indigo-400 bg-indigo-500/10" : "text-muted-foreground"
            )}
          >
            <MessageSquare className="w-4 h-4" />
            Chat
          </button>
        </div>
      )}

      {/* ── Action Bar ────────────────────────────────────────── */}
      {actions.length > 0 && (
        <ActionBar actions={actions} onAction={onAction} />
      )}
    </div>
  );
}

function ModePlaceholder({ mode }: { mode: ViewMode }) {
  return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground bg-[#0a0a0a]">
      <div className="text-center">
        <p className="text-sm font-medium capitalize">{mode} mode</p>
        <p className="text-xs mt-1 text-[#525252]">Not yet implemented</p>
      </div>
    </div>
  );
}
