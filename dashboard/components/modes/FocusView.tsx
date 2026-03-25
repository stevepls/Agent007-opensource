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
  Pause,
  UserPlus,
  Send,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface FocusViewProps {
  entity: TypedEntity;
  chatSlot: React.ReactNode;
  onBack?: () => void;
  onAction?: (action: string, entity: TypedEntity) => void;
}

const STATUS_STEPS = ["open", "in_progress", "review", "done"];

function StatusPipeline({ status }: { status: string }) {
  const normalized = status.toLowerCase().replace(/\s+/g, "_");
  const idx = STATUS_STEPS.indexOf(normalized);
  return (
    <div className="flex items-center gap-1">
      {STATUS_STEPS.map((step, i) => (
        <div key={step} className="flex-1">
          <div className={cn(
            "h-1.5 rounded-full",
            i < idx ? "bg-emerald-500/60" : i === idx ? "bg-indigo-500" : "bg-[#262626]"
          )} />
        </div>
      ))}
      <span className="text-xs text-muted-foreground ml-3 capitalize whitespace-nowrap">
        {status.replace(/_/g, " ")}
      </span>
    </div>
  );
}

export function FocusView({ entity, chatSlot, onBack, onAction }: FocusViewProps) {
  const d = entity.data;
  const [detailsOpen, setDetailsOpen] = useState(true); // Open by default — this is focus mode

  const typeIcon = entity.type === "ticket"
    ? <Headphones className="w-5 h-5" />
    : <CheckSquare className="w-5 h-5" />;

  const slaStatus = d.priority_score?.sla_status || "no_sla";
  const isUrgent = slaStatus === "breaching" || slaStatus === "breached";

  const fire = (action: string) => onAction?.(action, entity);

  return (
    <div className="flex flex-col h-full">
      {/* ── Focus Panel — takes at least half the screen ──── */}
      <div className="border-b border-[#1a1a1a] bg-[#0a0a0a] flex-shrink-0 min-h-[50vh] flex flex-col">

        {/* Back + source row */}
        <div className="flex items-center gap-2 px-5 pt-4 pb-2">
          {onBack && (
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground" onClick={onBack}>
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
            <a href={entity.source.url} target="_blank" rel="noopener noreferrer"
               className="ml-auto text-muted-foreground hover:text-indigo-400 transition-colors">
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
        </div>

        {/* Title */}
        <h1 className="text-xl font-semibold text-foreground px-5 pb-4 leading-snug">
          {d.title || d.name || d.subject || entity.id}
        </h1>

        {/* Status pipeline */}
        {d.status && (
          <div className="px-5 pb-4">
            <StatusPipeline status={d.status} />
          </div>
        )}

        {/* Metadata grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 px-5 pb-5">
          <MetaItem icon={<User className="w-3.5 h-3.5" />} label="Assignee"
            value={d.assignee || "Unassigned"} alert={!d.assignee} />
          <MetaItem icon={<Shield className="w-3.5 h-3.5" />} label="SLA"
            value={d.sla_tier ? `${d.sla_tier.toUpperCase()}${slaStatus !== "no_sla" ? ` · ${slaStatus.replace(/_/g, " ")}` : ""}` : "—"}
            alert={isUrgent} />
          {d.created_at && (
            <MetaItem icon={<Clock className="w-3.5 h-3.5" />} label="Age" value={formatAge(d.created_at)} />
          )}
          {d.due_date && (
            <MetaItem icon={<AlertTriangle className="w-3.5 h-3.5" />} label="Due"
              value={new Date(d.due_date).toLocaleDateString()} />
          )}
          {d.task_type && (
            <MetaItem icon={<CheckSquare className="w-3.5 h-3.5" />} label="Type"
              value={d.task_type.replace(/_/g, " ")} />
          )}
          {d.priority_score?.score != null && (
            <MetaItem icon={<AlertTriangle className="w-3.5 h-3.5" />} label="Score"
              value={String(d.priority_score.score)} />
          )}
        </div>

        {/* Actions — real buttons that do things */}
        <div className="flex items-center gap-2 px-5 pb-5 flex-wrap">
          <Button size="sm" className="h-9 text-xs gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
            onClick={() => fire(d.assignee ? "message_assignee" : "assign")}>
            {d.assignee ? <Send className="w-3.5 h-3.5" /> : <UserPlus className="w-3.5 h-3.5" />}
            {d.assignee ? `Message ${d.assignee}` : "Assign"}
          </Button>
          <Button variant="outline" size="sm" className="h-9 text-xs gap-2 border-[#333] text-zinc-300"
            onClick={() => fire("subtasks")}>
            <ListPlus className="w-3.5 h-3.5" />
            Break down
          </Button>
          <Button variant="outline" size="sm" className="h-9 text-xs gap-2 border-[#333] text-zinc-300"
            onClick={() => fire("branch")}>
            <GitBranch className="w-3.5 h-3.5" />
            Create branch
          </Button>
          <Button variant="outline" size="sm" className="h-9 text-xs gap-2 border-[#333] text-zinc-300"
            onClick={() => fire("snooze")}>
            <Pause className="w-3.5 h-3.5" />
            Snooze
          </Button>
          <Button variant="outline" size="sm" className="h-9 text-xs gap-2 border-[#333] text-zinc-300"
            onClick={() => fire("comment")}>
            <MessageSquare className="w-3.5 h-3.5" />
            Comment
          </Button>
        </div>

        {/* Description */}
        {(d.description || d.body) && (
          <div className="px-5 pb-5 flex-1">
            <button onClick={() => setDetailsOpen(!detailsOpen)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-2">
              {detailsOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              Description
            </button>
            {detailsOpen && (
              <p className="text-sm text-zinc-400 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                {d.description || d.body}
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Chat — secondary, reduced height ─────────────── */}
      <div className="h-48 lg:h-64 flex-shrink-0 overflow-hidden bg-[#0a0a0a] border-t border-[#1a1a1a]">
        {chatSlot}
      </div>
    </div>
  );
}

function MetaItem({ icon, label, value, alert }: {
  icon: React.ReactNode; label: string; value: string; alert?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-zinc-500">{icon}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={cn("text-sm ml-auto", alert ? "text-red-400 font-medium" : "text-foreground")}>
        {value}
      </span>
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
