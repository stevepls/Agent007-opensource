"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  CheckSquare,
  Headphones,
  GitPullRequest,
  Mail,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  User,
  Clock,
  Shield,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface EntityCardProps {
  entity: TypedEntity;
  className?: string;
}

const TYPE_CONFIG: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  task: { icon: <CheckSquare className="w-4 h-4" />, label: "Task", color: "text-blue-400" },
  ticket: { icon: <Headphones className="w-4 h-4" />, label: "Ticket", color: "text-emerald-400" },
  pr: { icon: <GitPullRequest className="w-4 h-4" />, label: "PR", color: "text-purple-400" },
  email_draft: { icon: <Mail className="w-4 h-4" />, label: "Email", color: "text-amber-400" },
};

const STATUS_STEPS = ["open", "in_progress", "review", "done"];
const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In Progress",
  review: "Review",
  done: "Done",
};

function StatusPipeline({ status }: { status: string }) {
  const normalized = status.toLowerCase().replace(/\s+/g, "_");
  const currentIndex = STATUS_STEPS.indexOf(normalized);

  return (
    <div className="flex items-center gap-1 mt-3 mb-3">
      {STATUS_STEPS.map((step, i) => {
        const isActive = i === currentIndex;
        const isPast = i < currentIndex;

        return (
          <div key={step} className="flex items-center gap-1 flex-1">
            <div className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              isPast ? "bg-emerald-500" : isActive ? "bg-indigo-500" : "bg-[#262626]",
            )} />
            {i < STATUS_STEPS.length - 1 && <div className="w-0.5" />}
          </div>
        );
      })}
    </div>
  );
}

export function EntityCard({ entity, className }: EntityCardProps) {
  const [expanded, setExpanded] = useState(false);
  const config = TYPE_CONFIG[entity.type] || { icon: <CheckSquare className="w-4 h-4" />, label: entity.type, color: "text-muted-foreground" };
  const d = entity.data;

  return (
    <div className={cn("bg-[#141414] border border-[#262626] rounded-lg p-4", className)}>
      {/* Header */}
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5", config.color)}>{config.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground truncate flex-1">
              {d.title || d.name || d.subject || entity.id}
            </h3>
            {entity.source?.url && (
              <a
                href={entity.source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-indigo-400 transition-colors flex-shrink-0"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="outline" className="text-[11px] py-0 px-1.5 border-[#333] text-muted-foreground">
              {config.label}
            </Badge>
            {d.project_name && (
              <Badge variant="outline" className="text-[11px] py-0 px-1.5 border-indigo-500/30 text-indigo-400">
                {d.project_name}
              </Badge>
            )}
            {entity.source?.system && (
              <span className="text-[11px] text-muted-foreground">
                {entity.source.system}:{d.source_id || entity.id}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Status pipeline */}
      {d.status && <StatusPipeline status={d.status} />}

      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 mt-2">
        {d.assignee && (
          <div className="flex items-center gap-1.5">
            <User className="w-3 h-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Assignee</span>
            <span className="text-xs text-foreground ml-auto">{d.assignee}</span>
          </div>
        )}
        {!d.assignee && (
          <div className="flex items-center gap-1.5">
            <User className="w-3 h-3 text-red-400" />
            <span className="text-xs text-red-400">Unassigned</span>
          </div>
        )}
        {d.sla_tier && (
          <div className="flex items-center gap-1.5">
            <Shield className="w-3 h-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">SLA</span>
            <span className={cn("text-xs ml-auto font-medium",
              d.priority_score?.sla_status === "breached" ? "text-red-400" :
              d.priority_score?.sla_status === "breaching" ? "text-orange-400" :
              d.priority_score?.sla_status === "approaching" ? "text-yellow-400" :
              "text-emerald-400"
            )}>
              {d.sla_tier.toUpperCase()} — {d.priority_score?.sla_status?.replace(/_/g, " ") || "N/A"}
            </span>
          </div>
        )}
        {d.created_at && (
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Age</span>
            <span className="text-xs text-foreground ml-auto">{formatAge(d.created_at)}</span>
          </div>
        )}
        {d.due_date && (
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Due</span>
            <span className="text-xs text-foreground ml-auto">{new Date(d.due_date).toLocaleDateString()}</span>
          </div>
        )}
      </div>

      {/* Description (expandable) */}
      {(d.description || d.body) && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "Hide details" : "Show details"}
          </button>
          {expanded && (
            <p className="text-xs text-muted-foreground mt-2 whitespace-pre-wrap leading-relaxed">
              {d.description || d.body}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function formatAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const hours = ms / 3600000;
  if (hours < 1) return "< 1h";
  if (hours < 24) return `${Math.floor(hours)}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}
