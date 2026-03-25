"use client";

import { EntityCard } from "@/components/EntityCard";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface FocusViewProps {
  entity: TypedEntity;
  chatSlot: React.ReactNode;
  onBack?: () => void;
}

export function FocusView({ entity, chatSlot, onBack }: FocusViewProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Entity card — pinned at top */}
      <div className="border-b border-[#1a1a1a] bg-[#0a0a0a] p-4">
        <div className="flex items-center gap-3 mb-3">
          {onBack && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              onClick={onBack}
              title="Back to queue"
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Focus
          </span>
        </div>
        <EntityCard entity={entity} />
      </div>

      {/* Chat — fills remaining space, contextual to the entity */}
      <div className="flex-1 overflow-hidden">
        {chatSlot}
      </div>
    </div>
  );
}
