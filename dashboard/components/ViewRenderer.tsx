"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { ActionBar } from "@/components/ActionBar";
import { Button } from "@/components/ui/button";
import { MessageSquare, LayoutList, X } from "lucide-react";
import type { ViewDirective, ViewMode, ActionDefinition, LayoutHint } from "@/lib/viewProtocol";
import { resolveMode, resolveLayout } from "@/lib/viewProtocol";

// ── Surface Renderer ──────────────────────────────────────────
// Queue-first. Responsive. Chat is secondary on all screen sizes.
//
// Mobile (<lg): single column, bottom toggle for chat/queue swap
// Desktop (lg+): side-by-side panels per layout mode

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

  // Mobile: toggle between queue and chat views
  const [mobileView, setMobileView] = useState<"queue" | "chat">("queue");

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full">
      {/* ── Canvas ─────────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0">

        {/* ══════════════════════════════════════════════════════
            QUEUE-DOMINANT LAYOUT
            Desktop: chat left (narrow) + queue center
            Mobile: queue or chat (toggled), one at a time
           ══════════════════════════════════════════════════════ */}
        {layout.canvas === "queue-dominant" && (
          <>
            {/* Desktop: side-by-side */}
            <div className="hidden lg:flex flex-1 min-h-0">
              {/* Chat — narrow left */}
              <div className="w-80 flex flex-col border-r border-[#262626] bg-[#0a0a0a]">
                {chatSlot}
              </div>
              {/* Queue — main surface */}
              <div className="flex-1 flex flex-col bg-[#0a0a0a]">
                <div className="px-4 py-2.5 border-b border-[#262626]">
                  {agentStripSlot}
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                  {queueSlot}
                </div>
              </div>
            </div>

            {/* Mobile: one panel at a time */}
            <div className="flex lg:hidden flex-1 flex-col min-h-0">
              {mobileView === "queue" ? (
                <div className="flex-1 flex flex-col bg-[#0a0a0a]">
                  <div className="px-3 py-2 border-b border-[#262626]">
                    {agentStripSlot}
                  </div>
                  <div className="flex-1 overflow-y-auto p-3">
                    {queueSlot}
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex flex-col bg-[#0a0a0a]">
                  {chatSlot}
                </div>
              )}
            </div>
          </>
        )}

        {/* ══════════════════════════════════════════════════════
            SPLIT LAYOUT (focus mode)
            Desktop: entity+chat main + queue sidebar
            Mobile: entity+chat stacked, no sidebar
           ══════════════════════════════════════════════════════ */}
        {layout.canvas === "split" && (
          <>
            {/* Main area — entity + chat */}
            <div className="flex-1 flex flex-col min-w-0">
              {mode === "focus" && (focusSlot || <ModePlaceholder mode="focus" />)}
              {mode === "queue" && chatSlot}
            </div>

            {/* Queue sidebar — desktop only, minimized */}
            {layout.feed !== "hidden" && (
              <aside className={cn(
                "hidden lg:flex border-l border-[#262626] bg-[#0f0f0f] flex-col transition-all duration-300",
                layout.feed === "minimized" ? "w-64" : "w-80",
              )}>
                <div className="p-3 border-b border-[#262626]">
                  {agentStripSlot}
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {queueSlot}
                </div>
              </aside>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════════
            CANVAS-DOMINANT (analysis, review)
            Full width on all devices.
           ══════════════════════════════════════════════════════ */}
        {layout.canvas === "canvas-dominant" && (
          <div className="flex-1 flex flex-col min-w-0">
            {mode === "analysis" && (analysisSlot || <ModePlaceholder mode="analysis" />)}
            {mode === "review" && (reviewSlot || <ModePlaceholder mode="review" />)}
          </div>
        )}

        {/* ══════════════════════════════════════════════════════
            COMPOSE-DOMINANT
            Desktop: editor + chat sidebar
            Mobile: editor full, chat via toggle
           ══════════════════════════════════════════════════════ */}
        {layout.canvas === "compose-dominant" && (
          <>
            {/* Desktop */}
            <div className="hidden lg:flex flex-1 min-w-0">
              <div className="flex-1 flex flex-col min-w-0">
                {composeSlot || <ModePlaceholder mode="compose" />}
              </div>
              <div className="w-80 flex flex-col border-l border-[#262626] bg-[#0a0a0a]">
                {chatSlot}
              </div>
            </div>
            {/* Mobile */}
            <div className="flex lg:hidden flex-1 flex-col min-h-0">
              {mobileView === "queue" ? (
                <div className="flex-1 flex flex-col">
                  {composeSlot || <ModePlaceholder mode="compose" />}
                </div>
              ) : (
                <div className="flex-1 flex flex-col bg-[#0a0a0a]">
                  {chatSlot}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Mobile Toggle Bar ──────────────────────────────────── */}
      {(layout.canvas === "queue-dominant" || layout.canvas === "compose-dominant") && (
        <div className="flex lg:hidden items-center border-t border-[#262626] bg-[#0f0f0f]">
          <button
            onClick={() => setMobileView("queue")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors",
              mobileView === "queue"
                ? "text-indigo-400 bg-indigo-500/10"
                : "text-muted-foreground"
            )}
          >
            <LayoutList className="w-4 h-4" />
            {layout.canvas === "compose-dominant" ? "Editor" : "Queue"}
          </button>
          <button
            onClick={() => setMobileView("chat")}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium transition-colors",
              mobileView === "chat"
                ? "text-indigo-400 bg-indigo-500/10"
                : "text-muted-foreground"
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
