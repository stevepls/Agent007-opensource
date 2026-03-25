"use client";

import { EntityCard } from "@/components/EntityCard";
import type { TypedEntity } from "@/lib/viewProtocol";

interface FocusViewProps {
  entity: TypedEntity;
  chatSlot: React.ReactNode;
}

export function FocusView({ entity, chatSlot }: FocusViewProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Entity card — pinned at top */}
      <div className="border-b border-[#262626] bg-[#0a0a0a] p-4">
        <EntityCard entity={entity} />
      </div>

      {/* Chat — fills remaining space, contextual to the entity */}
      <div className="flex-1 overflow-hidden">
        {chatSlot}
      </div>
    </div>
  );
}
