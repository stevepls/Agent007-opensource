"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { ActionBar } from "@/components/ActionBar";
import type { ViewDirective, ViewMode, ActionDefinition, LayoutHint } from "@/lib/viewProtocol";
import { resolveMode, resolveLayout, EMPTY_DIRECTIVE } from "@/lib/viewProtocol";

interface ViewRendererProps {
  directive: ViewDirective;
  onAction: (action: ActionDefinition) => void;

  // Existing components passed through — we compose, not replace.
  chatSlot: React.ReactNode;
  feedSlot: React.ReactNode;
  agentStripSlot: React.ReactNode;

  // Future mode components (optional — renders placeholder if not provided)
  focusSlot?: React.ReactNode;
  analysisSlot?: React.ReactNode;
  composeSlot?: React.ReactNode;
  reviewSlot?: React.ReactNode;
}

export function ViewRenderer({
  directive,
  onAction,
  chatSlot,
  feedSlot,
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
      {/* ── Canvas ──────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0">
        {/* Main area */}
        <div className={cn(
          "flex flex-col min-w-0",
          layout.feed === "visible" ? "flex-1" : "w-full",
        )}>
          {/* Mode-specific content */}
          {mode === "queue" && chatSlot}
          {mode === "focus" && (focusSlot || <ModePlaceholder mode="focus" />)}
          {mode === "analysis" && (analysisSlot || <ModePlaceholder mode="analysis" />)}
          {mode === "compose" && (composeSlot || <ModePlaceholder mode="compose" />)}
          {mode === "review" && (reviewSlot || <ModePlaceholder mode="review" />)}
        </div>

        {/* Feed panel — visibility controlled by layout */}
        {layout.feed !== "hidden" && (
          <aside className={cn(
            "border-l border-[#262626] bg-[#0f0f0f] flex flex-col transition-all duration-300",
            layout.feed === "visible" ? "w-80" : "w-64",
          )}>
            <div className="flex-1 overflow-y-auto p-4">
              {agentStripSlot}
              {feedSlot}
            </div>
          </aside>
        )}
      </div>

      {/* ── Action Bar ─────────────────────────────────── */}
      {actions.length > 0 && (
        <ActionBar actions={actions} onAction={onAction} />
      )}
    </div>
  );
}

// Placeholder for modes not yet implemented
function ModePlaceholder({ mode }: { mode: ViewMode }) {
  return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground">
      <div className="text-center">
        <p className="text-sm font-medium">{mode} mode</p>
        <p className="text-xs mt-1">Not yet implemented</p>
      </div>
    </div>
  );
}
