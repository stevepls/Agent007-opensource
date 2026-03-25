"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { ActionBar } from "@/components/ActionBar";
import type { ViewDirective, ViewMode, ActionDefinition, LayoutHint } from "@/lib/viewProtocol";
import { resolveMode, resolveLayout } from "@/lib/viewProtocol";

// ── Surface Renderer ──────────────────────────────────────────
// Queue-first: queue dominates by default.
// Chat is a secondary control layer, not the canvas owner.
// Modes are work states, not tabs.

interface ViewRendererProps {
  directive: ViewDirective;
  onAction: (action: ActionDefinition) => void;

  // Core slots — always available.
  queueSlot: React.ReactNode;     // The priority feed — queue IS the product
  chatSlot: React.ReactNode;      // Chat — secondary, for steering/narration
  agentStripSlot: React.ReactNode;

  // Mode-specific slots — render when their mode is active.
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

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full">
      {/* ── Canvas ─────────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0">

        {/* ── Queue-Dominant Layout ─────────────────────────── */}
        {layout.canvas === "queue-dominant" && (
          <>
            {/* Chat — narrow left column for steering */}
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
          </>
        )}

        {/* ── Split Layout (focus mode) ─────────────────────── */}
        {layout.canvas === "split" && (
          <>
            {/* Entity + chat — main area */}
            <div className="flex-1 flex flex-col min-w-0">
              {mode === "focus" && (focusSlot || <ModePlaceholder mode="focus" />)}
              {mode === "queue" && chatSlot}
            </div>

            {/* Queue sidebar — minimized */}
            {layout.feed !== "hidden" && (
              <aside className={cn(
                "border-l border-[#262626] bg-[#0f0f0f] flex flex-col transition-all duration-300",
                layout.feed === "minimized" ? "w-64" : "w-80",
              )}>
                <div className="p-3 border-b border-[#262626]">
                  {agentStripSlot}
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                  {queueSlot}
                </div>
              </aside>
            )}
          </>
        )}

        {/* ── Canvas-Dominant (analysis, review) ────────────── */}
        {layout.canvas === "canvas-dominant" && (
          <div className="flex-1 flex flex-col min-w-0">
            {mode === "analysis" && (analysisSlot || <ModePlaceholder mode="analysis" />)}
            {mode === "review" && (reviewSlot || <ModePlaceholder mode="review" />)}
            {/* Chat available as a collapsible bottom panel */}
          </div>
        )}

        {/* ── Compose-Dominant ──────────────────────────────── */}
        {layout.canvas === "compose-dominant" && (
          <div className="flex-1 flex min-w-0">
            {/* Editor — main area */}
            <div className="flex-1 flex flex-col min-w-0">
              {composeSlot || <ModePlaceholder mode="compose" />}
            </div>
            {/* Chat sidebar for refinement */}
            <div className="w-80 flex flex-col border-l border-[#262626] bg-[#0a0a0a]">
              {chatSlot}
            </div>
          </div>
        )}
      </div>

      {/* ── Action Bar ────────────────────────────────────────── */}
      {actions.length > 0 && (
        <ActionBar actions={actions} onAction={onAction} />
      )}
    </div>
  );
}

// Placeholder for modes not yet implemented
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
