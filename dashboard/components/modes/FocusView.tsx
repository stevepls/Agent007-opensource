"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ExternalLink,
  CheckSquare,
  Headphones,
  User,
  Clock,
  Shield,
  GitBranch,
  MessageSquare,
  ListPlus,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface FocusViewProps {
  entity: TypedEntity;
  chatSlot: React.ReactNode;
  onBack?: () => void;
}

// ── Status Pipeline ───────────────────────────────────────────

const STATUS_STEPS = ["open", "in_progress", "review", "done"];

function StatusPipeline({ status }: { status: string }) {
  const normalized = status.toLowerCase().replace(/\s+/g, "_");
  const idx = STATUS_STEPS.indexOf(normalized);

  return (
    <div className="flex items-center gap-1">
      {STATUS_STEPS.map((step, i) => (
        <div key={step} className="flex items-center gap-1 flex-1">
          <div
            className={cn(
              "h-1 flex-1 rounded-full",
              i < idx ? "bg-emerald-500/60" : i === idx ? "bg-indigo-500" : "bg-[#262626]"
            )}
          />
        </div>
      ))}
      <span className="text-xs text-muted-foreground ml-2 capitalize">
        {status.replace(/_/g, " ")}
      </span>
    </div>
  );
}

// ── Focus Panel ───────────────────────────────────────────────

export function FocusView({ entity, chatSlot, onBack }: FocusViewProps) {
  const d = entity.data;
  const [detailsOpen, setDetailsOpen] = useState(false);

  const typeIcon =
    entity.type === "ticket" ? <Headphones className="w-5 h-5" /> : <CheckSquare className="w-5 h-5" />;

  const slaStatus = d.priority_score?.sla_status || "no_sla";
  const isUrgent = slaStatus === "breaching" || slaStatus === "breached";

  return (
    <div className="flex flex-col h-full">
      {/* ── Focus Panel — the primary work surface ─────────── */}
      <div className="border-b border-[#1a1a1a] bg-[#0a0a0a] flex-shrink-0">

        {/* Row 1: Back + Source */}
        <div className="flex items-center gap-2 px-5 pt-4 pb-2">
          {onBack && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              onClick={onBack}
            >
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          <span className="text-muted-foreground">{typeIcon}</span>
          <span className="text-xs text-muted-foreground">
            {entity.source?.system || entity.type} {d.source_id ? `#${d.source_id}` : ""}
          </span>
          {d.project_name && (
            <Badge variant="outline" className="text-xs py-0 px-2 border-[#333] text-zinc-400">
              {d.project_name}
            </Badge>
          )}
          {entity.source?.url && (
            <a
              href={entity.source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto text-muted-foreground hover:text-indigo-400 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
        </div>

        {/* Row 2: Title */}
        <h1 className="text-lg font-semibold text-foreground px-5 pb-3 leading-snug">
          {d.title || d.name || d.subject || entity.id}
        </h1>

        {/* Row 3: Status pipeline */}
        {d.status && (
          <div className="px-5 pb-3">
            <StatusPipeline status={d.status} />
          </div>
        )}

        {/* Row 4: Key metadata grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-2 px-5 pb-4">
          {/* Assignee */}
          <div className="flex items-center gap-2">
            <User className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-xs text-muted-foreground">Assignee</span>
            <span className={cn("text-sm ml-auto", d.assignee ? "text-foreground" : "text-red-400")}>
              {d.assignee || "Unassigned"}
            </span>
          </div>

          {/* SLA */}
          <div className="flex items-center gap-2">
            <Shield className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-xs text-muted-foreground">SLA</span>
            <span className={cn(
              "text-sm ml-auto",
              isUrgent ? "text-red-400 font-medium" : "text-foreground"
            )}>
              {d.sla_tier ? d.sla_tier.toUpperCase() : "—"}
              {slaStatus !== "no_sla" && ` · ${slaStatus.replace(/_/g, " ")}`}
            </span>
          </div>

          {/* Age */}
          {d.created_at && (
            <div className="flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-zinc-500" />
              <span className="text-xs text-muted-foreground">Age</span>
              <span className="text-sm text-foreground ml-auto">{formatAge(d.created_at)}</span>
            </div>
          )}

          {/* Due date */}
          {d.due_date && (
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-zinc-500" />
              <span className="text-xs text-muted-foreground">Due</span>
              <span className="text-sm text-foreground ml-auto">
                {new Date(d.due_date).toLocaleDateString()}
              </span>
            </div>
          )}
        </div>

        {/* Row 5: Recommended actions */}
        <div className="flex items-center gap-2 px-5 pb-4">
          <Button size="sm" className="h-8 text-xs gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white">
            <MessageSquare className="w-3.5 h-3.5" />
            {d.assignee ? "Message assignee" : "Assign"}
          </Button>
          <Button variant="ghost" size="sm" className="h-8 text-xs gap-1.5 text-muted-foreground">
            <ListPlus className="w-3.5 h-3.5" />
            Subtasks
          </Button>
          <Button variant="ghost" size="sm" className="h-8 text-xs gap-1.5 text-muted-foreground">
            <GitBranch className="w-3.5 h-3.5" />
            Branch
          </Button>
          <Button variant="ghost" size="sm" className="h-8 text-xs gap-1.5 text-muted-foreground">
            <Clock className="w-3.5 h-3.5" />
            Snooze
          </Button>
        </div>

        {/* Row 6: Expandable description */}
        {(d.description || d.body) && (
          <div className="px-5 pb-4">
            <button
              onClick={() => setDetailsOpen(!detailsOpen)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {detailsOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              {detailsOpen ? "Hide description" : "Show description"}
            </button>
            {detailsOpen && (
              <p className="text-sm text-zinc-400 mt-2 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                {d.description || d.body}
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Activity / Chat — secondary, below ────────────── */}
      <div className="flex-1 overflow-hidden bg-[#0a0a0a]">
        {chatSlot}
      </div>
    </div>
  );
}

function formatAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const hours = ms / 3600000;
  if (hours < 1) return "< 1h";
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d`;
  return `${Math.floor(days / 30)}mo`;
}
