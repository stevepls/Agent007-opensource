"use client";

import { useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActionDefinition } from "@/lib/viewProtocol";

interface ActionBarProps {
  actions: ActionDefinition[];
  onAction: (action: ActionDefinition) => void;
  className?: string;
}

export function ActionBar({ actions, onAction, className }: ActionBarProps) {
  // Keyboard shortcuts
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      for (const action of actions) {
        if (action.key && e.key.toLowerCase() === action.key.toLowerCase()) {
          e.preventDefault();
          onAction(action);
          return;
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [actions, onAction]);

  if (actions.length === 0) return null;

  return (
    <div className={cn("flex items-center gap-2 px-4 py-2 border-t border-[#262626] bg-[#0f0f0f]", className)}>
      {actions.map((action) => {
        const variant = action.style === "primary" ? "default"
          : action.style === "destructive" ? "destructive"
          : "ghost";

        return (
          <Button
            key={action.id}
            variant={variant}
            size="sm"
            className={cn(
              "text-xs h-7 gap-1.5",
              action.style === "primary" && "bg-indigo-600 hover:bg-indigo-500 text-white",
              action.style === "ghost" && "text-muted-foreground hover:text-foreground",
            )}
            onClick={() => onAction(action)}
          >
            {action.label}
            {action.key && (
              <kbd className="text-[10px] px-1 py-0.5 rounded bg-black/20 font-mono ml-1">
                {action.key.toUpperCase()}
              </kbd>
            )}
          </Button>
        );
      })}
    </div>
  );
}
