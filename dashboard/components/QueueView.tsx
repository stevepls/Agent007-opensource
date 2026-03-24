"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Loader2,
  ExternalLink,
  Filter,
  RefreshCw,
  AlertTriangle,
  Clock,
  CheckCircle2,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface PriorityScore {
  score: number;
  sla_status: "within_sla" | "approaching" | "breaching" | "breached" | "no_sla";
  sla_deadline: string | null;
  time_remaining: string | null;
  components: Record<string, number>;
}

interface QueueItem {
  id: string;
  source: "clickup" | "zendesk";
  source_id: string;
  source_url: string | null;
  project_name: string;
  title: string;
  status: string;
  assignee: string | null;
  priority_score: PriorityScore;
  task_type: string;
  sla_tier: string;
  created_at: string;
  updated_at: string;
  due_date: string | null;
  tags: string[];
}

interface QueueSummary {
  total: number;
  breaching: number;
  by_project: Record<string, number>;
  by_sla_status: Record<string, number>;
  by_source: Record<string, number>;
  last_refresh: string | null;
}

interface QueueResponse {
  items: QueueItem[];
  summary: QueueSummary;
}

/* ------------------------------------------------------------------ */
/*  SLA status config                                                  */
/* ------------------------------------------------------------------ */

const SLA_CONFIG: Record<
  string,
  { dot: string; label: string }
> = {
  within_sla: {
    dot: "bg-emerald-400",
    label: "Within SLA",
  },
  approaching: {
    dot: "bg-yellow-400",
    label: "Approaching",
  },
  breaching: {
    dot: "bg-orange-400",
    label: "Breaching",
  },
  breached: {
    dot: "bg-red-500",
    label: "Breached",
  },
  no_sla: {
    dot: "bg-zinc-500",
    label: "No SLA",
  },
};

/* ------------------------------------------------------------------ */
/*  Project badge colours — deterministic by name                      */
/* ------------------------------------------------------------------ */

const PROJECT_COLORS = [
  "bg-violet-500/15 border-violet-500/30 text-violet-400",
  "bg-sky-500/15 border-sky-500/30 text-sky-400",
  "bg-amber-500/15 border-amber-500/30 text-amber-400",
  "bg-rose-500/15 border-rose-500/30 text-rose-400",
  "bg-teal-500/15 border-teal-500/30 text-teal-400",
  "bg-fuchsia-500/15 border-fuchsia-500/30 text-fuchsia-400",
];

function projectColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return PROJECT_COLORS[Math.abs(hash) % PROJECT_COLORS.length];
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function truncate(str: string, len: number): string {
  if (str.length <= len) return str;
  return str.slice(0, len).trimEnd() + "\u2026";
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function QueueView() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [summary, setSummary] = useState<QueueSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterProject, setFilterProject] = useState<string>("");
  const [showFilter, setShowFilter] = useState(false);

  const fetchQueue = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterProject) params.set("project", filterProject);
      params.set("limit", "50");

      const res = await fetch(`/api/queue?${params.toString()}`);
      if (res.ok) {
        const data: QueueResponse = await res.json();
        setItems(data.items || []);
        setSummary(data.summary || null);
      }
    } catch {
      // Silently handle fetch errors
    } finally {
      setLoading(false);
    }
  }, [filterProject]);

  // Initial fetch + poll every 60 seconds
  useEffect(() => {
    setLoading(true);
    fetchQueue();
    const interval = setInterval(fetchQueue, 60_000);
    return () => clearInterval(interval);
  }, [fetchQueue]);

  // Derive project list for filter dropdown
  const projectNames = summary
    ? Object.keys(summary.by_project).sort()
    : [];

  return (
    <div className="space-y-3">
      {/* ---- Header ---- */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Work Queue
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Summary badges */}
          {summary && summary.total > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 bg-violet-500/10 border-violet-500/30 text-violet-400"
            >
              {summary.total} items
            </Badge>
          )}
          {summary && summary.breaching > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 bg-red-500/10 border-red-500/30 text-red-400"
            >
              {summary.breaching} breaching
            </Badge>
          )}

          {/* Filter toggle */}
          <Button
            variant="ghost"
            size="icon"
            className={cn("h-5 w-5", showFilter && "text-violet-400")}
            onClick={() => setShowFilter((v) => !v)}
          >
            <Filter className="w-3 h-3" />
          </Button>

          {/* Refresh */}
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={() => {
              setLoading(true);
              fetchQueue();
            }}
          >
            <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* ---- Project filter dropdown ---- */}
      <AnimatePresence>
        {showFilter && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="flex flex-wrap gap-1 pb-1">
              <button
                onClick={() => setFilterProject("")}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded-full border transition-colors",
                  filterProject === ""
                    ? "bg-violet-500/20 border-violet-500/40 text-violet-300"
                    : "border-zinc-700 text-muted-foreground hover:border-zinc-500"
                )}
              >
                All
              </button>
              {projectNames.map((name) => (
                <button
                  key={name}
                  onClick={() =>
                    setFilterProject(filterProject === name ? "" : name)
                  }
                  className={cn(
                    "text-[10px] px-2 py-0.5 rounded-full border transition-colors",
                    filterProject === name
                      ? "bg-violet-500/20 border-violet-500/40 text-violet-300"
                      : "border-zinc-700 text-muted-foreground hover:border-zinc-500"
                  )}
                >
                  {name}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- By-project summary ---- */}
      {summary && !filterProject && Object.keys(summary.by_project).length > 0 && (
        <div className="flex flex-wrap gap-1">
          {Object.entries(summary.by_project).map(([name, count]) => (
            <Badge
              key={name}
              variant="outline"
              className={cn("text-[10px] py-0 px-1.5", projectColor(name))}
            >
              {name}: {count}
            </Badge>
          ))}
        </div>
      )}

      {/* ---- Item list ---- */}
      {loading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground/50 text-center py-3">
          No work items in queue
        </p>
      ) : (
        <AnimatePresence mode="popLayout">
          {items.map((item) => {
            const sla =
              SLA_CONFIG[item.priority_score?.sla_status] ?? SLA_CONFIG.no_sla;

            return (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                layout
              >
                <Card className="border border-zinc-800 bg-zinc-900/50 transition-colors hover:border-zinc-700">
                  <CardContent className="p-2.5">
                    <div className="flex items-start gap-2">
                      {/* SLA dot */}
                      <div className="mt-1.5 flex-shrink-0">
                        <span
                          className={cn(
                            "block w-2 h-2 rounded-full",
                            sla.dot
                          )}
                          title={sla.label}
                        />
                      </div>

                      {/* Main content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          {/* Priority score badge */}
                          <span className="text-[10px] font-mono font-semibold text-violet-400 bg-violet-500/10 rounded px-1 py-0 leading-tight">
                            {item.priority_score?.score ?? "–"}
                          </span>

                          {/* Title */}
                          <p className="text-xs font-medium truncate flex-1">
                            {truncate(item.title, 60)}
                          </p>

                          {/* Source link */}
                          {item.source_url && (
                            <a
                              href={item.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-shrink-0 text-muted-foreground hover:text-violet-400 transition-colors"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>

                        {/* Metadata row */}
                        <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                          {/* Project badge */}
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[9px] py-0 px-1",
                              projectColor(item.project_name)
                            )}
                          >
                            {item.project_name}
                          </Badge>

                          {/* Source badge */}
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[9px] py-0 px-1 font-mono",
                              item.source === "clickup"
                                ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                                : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                            )}
                          >
                            {item.source === "clickup" ? "CU" : "ZD"}
                          </Badge>

                          {/* SLA status */}
                          <span className="text-[9px] text-muted-foreground">
                            {sla.label}
                          </span>

                          {/* Time remaining if approaching/breaching */}
                          {item.priority_score?.time_remaining &&
                            (item.priority_score.sla_status === "approaching" ||
                              item.priority_score.sla_status === "breaching") && (
                              <span className="text-[9px] text-orange-400 flex items-center gap-0.5">
                                <Clock className="w-2.5 h-2.5" />
                                {item.priority_score.time_remaining}
                              </span>
                            )}

                          {/* Created time */}
                          <span className="text-[9px] text-muted-foreground ml-auto">
                            {timeAgo(item.created_at)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </AnimatePresence>
      )}
    </div>
  );
}
