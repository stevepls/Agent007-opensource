"use client";

import { useState, useEffect } from "react";
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
  Activity,
  Loader2,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface FocusViewProps {
  entity: TypedEntity;
  chatSlot: React.ReactNode;
  onBack?: () => void;
  onAction?: (action: string, entity: TypedEntity) => void;
}

interface CommentData {
  user: string;
  text: string;
  date: string;
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
      <span className="text-xs text-muted-foreground ml-2 sm:ml-3 capitalize whitespace-nowrap">
        {status.replace(/_/g, " ")}
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

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function MetaItem({ icon, label, value, alert }: {
  icon: React.ReactNode; label: string; value: string; alert?: boolean;
}) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="text-zinc-500 flex-shrink-0">{icon}</span>
      <span className="text-xs text-muted-foreground flex-shrink-0">{label}</span>
      <span className={cn(
        "text-sm ml-auto truncate",
        alert ? "text-red-400 font-medium" : "text-foreground"
      )}>
        {value}
      </span>
    </div>
  );
}

// ── Focus Panel ───────────────────────────────────────────────

export function FocusView({ entity, chatSlot, onBack, onAction }: FocusViewProps) {
  const d = entity.data;
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [chatVisible, setChatVisible] = useState(false);
  const [comments, setComments] = useState<CommentData[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);

  const typeIcon = entity.type === "ticket"
    ? <Headphones className="w-5 h-5" />
    : <CheckSquare className="w-5 h-5" />;

  const slaStatus = d.priority_score?.sla_status || "no_sla";
  const isUrgent = slaStatus === "breaching" || slaStatus === "breached";

  const fire = (action: string) => onAction?.(action, entity);

  // Fetch latest comments/activity for this entity
  useEffect(() => {
    if (!entity.source?.system || !d.source_id) return;

    setCommentsLoading(true);
    // Try to fetch task details which include comments
    fetch(`/api/orchestrator/api/cache/stats`) // Lightweight check that orchestrator is up
      .then(() => {
        // Fetch the actual task with comments via the queue proxy
        const source = entity.source?.system;
        if (source === "clickup") {
          return fetch(`/api/queue?limit=1`).then(r => r.json()).then(() => {
            // Comments would come from a dedicated endpoint
            // For now, use the entity's existing data
            if (d.comments && Array.isArray(d.comments)) {
              setComments(d.comments.slice(-5));
            }
          });
        }
      })
      .catch(() => {})
      .finally(() => setCommentsLoading(false));

    // Also set comments from entity data if available
    if (d.comments && Array.isArray(d.comments)) {
      setComments(d.comments.slice(-5));
    }
  }, [entity.id]);

  return (
    <div className="flex flex-col h-full">
      {/* ── Focus Panel — owns the canvas ────────────────── */}
      <div className="bg-[#0a0a0a] flex-1 flex flex-col overflow-y-auto">

        {/* Back + source row */}
        <div className="flex items-center gap-2 px-3 sm:px-5 pt-3 sm:pt-4 pb-2 flex-wrap">
          {onBack && (
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-foreground" onClick={onBack}>
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          <span className="text-muted-foreground flex-shrink-0">{typeIcon}</span>
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
               className="ml-auto text-muted-foreground hover:text-indigo-400 transition-colors flex-shrink-0">
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
        </div>

        {/* Title — responsive sizing */}
        <h1 className="text-lg sm:text-xl font-semibold text-foreground px-3 sm:px-5 pb-3 sm:pb-4 leading-snug">
          {d.title || d.name || d.subject || entity.id}
        </h1>

        {/* Status pipeline */}
        {d.status && (
          <div className="px-3 sm:px-5 pb-3 sm:pb-4">
            <StatusPipeline status={d.status} />
          </div>
        )}

        {/* Metadata grid — 1 col mobile, 2 col tablet, 4 col desktop */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-2 sm:gap-y-3 px-3 sm:px-5 pb-4 sm:pb-5">
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

        {/* Actions — wrap on mobile */}
        <div className="flex items-center gap-2 px-3 sm:px-5 pb-4 sm:pb-5 flex-wrap">
          <Button size="sm" className="h-8 sm:h-9 text-xs gap-1.5 sm:gap-2 bg-indigo-600 hover:bg-indigo-500 text-white"
            onClick={() => fire(d.assignee ? "message_assignee" : "assign")}>
            {d.assignee ? <Send className="w-3.5 h-3.5" /> : <UserPlus className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{d.assignee ? `Message ${d.assignee}` : "Assign"}</span>
            <span className="sm:hidden">{d.assignee ? "Message" : "Assign"}</span>
          </Button>
          <Button variant="outline" size="sm" className="h-8 sm:h-9 text-xs gap-1.5 border-[#333] text-zinc-300"
            onClick={() => fire("subtasks")}>
            <ListPlus className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Break down</span>
            <span className="sm:hidden">Split</span>
          </Button>
          <Button variant="outline" size="sm" className="h-8 sm:h-9 text-xs gap-1.5 border-[#333] text-zinc-300"
            onClick={() => fire("branch")}>
            <GitBranch className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Create branch</span>
            <span className="sm:hidden">Branch</span>
          </Button>
          <Button variant="outline" size="sm" className="h-8 sm:h-9 text-xs gap-1.5 border-[#333] text-zinc-300"
            onClick={() => fire("snooze")}>
            <Pause className="w-3.5 h-3.5" />
            Snooze
          </Button>
          <Button variant="outline" size="sm" className="h-8 sm:h-9 text-xs gap-1.5 border-[#333] text-zinc-300"
            onClick={() => fire("comment")}>
            <MessageSquare className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Comment</span>
          </Button>
        </div>

        {/* Description */}
        {(d.description || d.body) && (
          <div className="px-3 sm:px-5 pb-4">
            <button onClick={() => setDetailsOpen(!detailsOpen)}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors mb-2">
              {detailsOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              Description
            </button>
            {detailsOpen && (
              <p className="text-sm text-zinc-400 whitespace-pre-wrap leading-relaxed max-h-48 sm:max-h-64 overflow-y-auto">
                {d.description || d.body}
              </p>
            )}
          </div>
        )}

        {/* ── Latest Activity / Comments ──────────────────── */}
        <div className="px-3 sm:px-5 pb-5 border-t border-[#1a1a1a] pt-4">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-zinc-500" />
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Latest Activity
            </span>
            {commentsLoading && <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />}
          </div>

          {comments.length > 0 ? (
            <div className="space-y-3">
              {comments.map((c, i) => (
                <div key={i} className="flex gap-3">
                  <div className="w-6 h-6 rounded-full bg-[#1a1a1a] flex items-center justify-center flex-shrink-0 mt-0.5">
                    <User className="w-3 h-3 text-zinc-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-foreground">{c.user || "Unknown"}</span>
                      <span className="text-xs text-muted-foreground">{c.date ? timeAgo(c.date) : ""}</span>
                    </div>
                    <p className="text-sm text-zinc-400 mt-0.5 whitespace-pre-wrap break-words">
                      {(c.text || "").slice(0, 300)}{(c.text || "").length > 300 ? "…" : ""}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              {commentsLoading ? "Loading activity…" : "No recent activity"}
            </p>
          )}
        </div>
      </div>

      {/* ── Chat — collapsible bottom strip ────────────── */}
      <div className="flex-shrink-0 border-t border-[#1a1a1a]">
        <button
          onClick={() => setChatVisible(!chatVisible)}
          className="w-full flex items-center gap-2 px-3 sm:px-5 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors bg-[#0f0f0f]"
        >
          <MessageSquare className="w-3.5 h-3.5" />
          {chatVisible ? "Hide chat" : "Chat with Orchestrator"}
          {chatVisible ? <ChevronDown className="w-3 h-3 ml-auto" /> : <ChevronUp className="w-3 h-3 ml-auto" />}
        </button>
        {chatVisible && (
          <div className="h-48 sm:h-64 overflow-hidden bg-[#0a0a0a]">
            {chatSlot}
          </div>
        )}
      </div>
    </div>
  );
}
