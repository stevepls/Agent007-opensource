"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
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
  MessageSquare,
  AlertCircle,
  Info,
  Zap,
  ShieldAlert,
  Bell,
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

interface BriefingItemData {
  id: string;
  type: string;
  priority: number;
  title: string;
  description: string;
  action_label: string | null;
  source: string;
  created_at: string;
  metadata: Record<string, any>;
}

type FeedItem =
  | { kind: "queue"; data: QueueItem }
  | { kind: "briefing"; data: BriefingItemData };

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

interface QueueViewProps {
  activeItemId?: string | null;
  onItemSelect?: (item: QueueItem | BriefingItemData) => void;
  dismissedIds?: Set<string>;
}

/* ------------------------------------------------------------------ */
/*  SLA status config                                                  */
/* ------------------------------------------------------------------ */

const SLA_CONFIG: Record<string, { dot: string; label: string }> = {
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

/** Normalize any feed item to a 0-100 urgency score for unified sorting. */
function feedItemScore(item: FeedItem): number {
  if (item.kind === "queue") {
    return item.data.priority_score?.score ?? 0;
  }
  // Briefing priority: 0=CRITICAL, 1=HIGH, 2=MEDIUM, 3=LOW, 4=INFO
  const map: Record<number, number> = { 0: 95, 1: 75, 2: 50, 3: 25, 4: 10 };
  return map[item.data.priority] ?? 10;
}

/** Unique string id for any feed item. */
function feedItemId(item: FeedItem): string {
  return item.kind === "queue" ? item.data.id : item.data.id;
}

/**
 * Smart selection: pick up to `max` items.
 * 1. One item per project (most urgent representative from each).
 * 2. Fill remaining slots with highest-priority items across all projects.
 * If more than `max` projects, take the `max` most urgent representatives.
 */
function smartSelect(items: FeedItem[], max: number): FeedItem[] {
  if (items.length <= max) return items;

  // Group by project. Briefing items use their `source` as the project key.
  const byProject = new Map<string, FeedItem[]>();
  for (const item of items) {
    const key =
      item.kind === "queue" ? item.data.project_name : `briefing:${item.data.source}`;
    const list = byProject.get(key) || [];
    list.push(item);
    byProject.set(key, list);
  }

  // Sort each project's items by score descending
  for (const list of byProject.values()) {
    list.sort((a, b) => feedItemScore(b) - feedItemScore(a));
  }

  // Pick one representative per project (most urgent)
  const reps: FeedItem[] = [];
  for (const list of byProject.values()) {
    reps.push(list[0]);
  }

  // Sort representatives by score descending
  reps.sort((a, b) => feedItemScore(b) - feedItemScore(a));

  // If more projects than max, take only the top `max` reps
  const selected = new Set<string>();
  const result: FeedItem[] = [];

  const repSlice = reps.slice(0, max);
  for (const rep of repSlice) {
    result.push(rep);
    selected.add(feedItemId(rep));
  }

  if (result.length >= max) {
    return result.slice(0, max);
  }

  // Fill remaining slots with highest-priority items not already selected
  const remaining = items
    .filter((item) => !selected.has(feedItemId(item)))
    .sort((a, b) => feedItemScore(b) - feedItemScore(a));

  for (const item of remaining) {
    if (result.length >= max) break;
    result.push(item);
  }

  // Final sort by score descending
  result.sort((a, b) => feedItemScore(b) - feedItemScore(a));
  return result;
}

/** Icon for briefing item types. */
function briefingTypeIcon(type: string) {
  switch (type) {
    case "error":
      return <AlertCircle className="w-3 h-3" />;
    case "pending_approval":
      return <CheckCircle2 className="w-3 h-3" />;
    case "schema_change":
      return <Zap className="w-3 h-3" />;
    case "insight":
      return <Info className="w-3 h-3" />;
    default:
      return <Bell className="w-3 h-3" />;
  }
}

/** Left border color for briefing items based on priority. */
function briefingBorderColor(priority: number): string {
  switch (priority) {
    case 0:
      return "border-l-red-500";
    case 1:
      return "border-l-orange-400";
    case 2:
      return "border-l-yellow-400";
    case 3:
      return "border-l-zinc-500";
    case 4:
    default:
      return "border-l-zinc-600";
  }
}

/** Priority label for briefing items. */
function briefingPriorityLabel(priority: number): string {
  switch (priority) {
    case 0:
      return "Critical";
    case 1:
      return "High";
    case 2:
      return "Medium";
    case 3:
      return "Low";
    case 4:
    default:
      return "Info";
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const MAX_VISIBLE = 10;

function QueueView({ activeItemId, onItemSelect, dismissedIds }: QueueViewProps) {
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [briefingItems, setBriefingItems] = useState<BriefingItemData[]>([]);
  const [summary, setSummary] = useState<QueueSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterProject, setFilterProject] = useState<string>("");
  const [showFilter, setShowFilter] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const queueParams = new URLSearchParams();
      if (filterProject) queueParams.set("project", filterProject);
      queueParams.set("limit", "50");

      const [queueRes, briefingRes] = await Promise.allSettled([
        fetch(`/api/queue?${queueParams.toString()}`),
        fetch("/api/briefing?max_items=15"),
      ]);

      // Process queue response
      if (queueRes.status === "fulfilled" && queueRes.value.ok) {
        const data: QueueResponse = await queueRes.value.json();
        setQueueItems(data.items || []);
        setSummary(data.summary || null);
      }

      // Process briefing response
      if (briefingRes.status === "fulfilled" && briefingRes.value.ok) {
        const data = await briefingRes.value.json();
        setBriefingItems(data.items || []);
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
    fetchData();
    const interval = setInterval(fetchData, 60_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Build merged, filtered, and selected feed
  const { visibleItems, totalCount } = useMemo(() => {
    // Merge into FeedItem[]
    const allFeed: FeedItem[] = [
      ...queueItems.map((q): FeedItem => ({ kind: "queue", data: q })),
      ...briefingItems.map((b): FeedItem => ({ kind: "briefing", data: b })),
    ];

    // Remove dismissed items
    const dismissed = dismissedIds ?? new Set<string>();
    const undismissed = allFeed.filter((item) => !dismissed.has(feedItemId(item)));

    // Sort by score descending
    undismissed.sort((a, b) => feedItemScore(b) - feedItemScore(a));

    const total = undismissed.length;
    const visible = smartSelect(undismissed, MAX_VISIBLE);

    return { visibleItems: visible, totalCount: total };
  }, [queueItems, briefingItems, dismissedIds]);

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
              fetchData();
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
      ) : visibleItems.length === 0 ? (
        <p className="text-xs text-muted-foreground/50 text-center py-3">
          No work items in queue
        </p>
      ) : (
        <AnimatePresence mode="popLayout">
          {visibleItems.map((feedItem) => {
            const id = feedItemId(feedItem);
            const isActive = activeItemId === id;

            if (feedItem.kind === "queue") {
              return (
                <QueueCard
                  key={id}
                  item={feedItem.data}
                  isActive={isActive}
                  onItemSelect={onItemSelect}
                />
              );
            }

            return (
              <BriefingCard
                key={id}
                item={feedItem.data}
                isActive={isActive}
                onItemSelect={onItemSelect}
              />
            );
          })}

          {/* Remaining count */}
          {totalCount > MAX_VISIBLE && (
            <motion.p
              key="__remaining"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-[11px] text-muted-foreground/60 text-center py-2"
            >
              and {totalCount - MAX_VISIBLE} more\u2026
            </motion.p>
          )}
        </AnimatePresence>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Queue item card                                                    */
/* ------------------------------------------------------------------ */

function QueueCard({
  item,
  isActive,
  onItemSelect,
}: {
  item: QueueItem;
  isActive: boolean;
  onItemSelect?: (item: QueueItem | BriefingItemData) => void;
}) {
  const sla = SLA_CONFIG[item.priority_score?.sla_status] ?? SLA_CONFIG.no_sla;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      layout
    >
      <Card
        className={cn(
          "border border-zinc-800 bg-zinc-900/50 transition-colors cursor-pointer group",
          isActive
            ? "border-l-2 border-l-violet-500 opacity-40"
            : "hover:border-zinc-700"
        )}
        onClick={() => onItemSelect?.(item)}
      >
        <CardContent className="p-2.5">
          {/* Active label */}
          {isActive && (
            <div className="flex items-center gap-1 mb-1.5">
              <MessageSquare className="w-2.5 h-2.5 text-violet-400" />
              <span className="text-[9px] text-violet-400 font-medium">
                Being discussed\u2026
              </span>
            </div>
          )}

          <div className="flex items-start gap-2">
            {/* SLA dot */}
            <div className="mt-1.5 flex-shrink-0">
              <span
                className={cn("block w-2 h-2 rounded-full", sla.dot)}
                title={sla.label}
              />
            </div>

            {/* Main content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                {/* Priority score badge */}
                <span className="text-[10px] font-mono font-semibold text-violet-400 bg-violet-500/10 rounded px-1 py-0 leading-tight">
                  {item.priority_score?.score ?? "\u2013"}
                </span>

                {/* Title */}
                <p className="text-xs font-medium truncate flex-1">
                  {truncate(item.title, 60)}
                </p>

                {/* Discuss hint on hover */}
                <span className="text-[9px] text-violet-400/0 group-hover:text-violet-400/70 transition-colors flex-shrink-0">
                  discuss
                </span>

                {/* Source link */}
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 text-muted-foreground hover:text-violet-400 transition-colors"
                    onClick={(e) => e.stopPropagation()}
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
}

/* ------------------------------------------------------------------ */
/*  Briefing item card                                                 */
/* ------------------------------------------------------------------ */

function BriefingCard({
  item,
  isActive,
  onItemSelect,
}: {
  item: BriefingItemData;
  isActive: boolean;
  onItemSelect?: (item: QueueItem | BriefingItemData) => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 10 }}
      layout
    >
      <Card
        className={cn(
          "border border-zinc-800 bg-zinc-900/30 transition-colors cursor-pointer group border-l-2",
          isActive
            ? "border-l-violet-500 opacity-40"
            : cn(briefingBorderColor(item.priority), "hover:border-zinc-700")
        )}
        onClick={() => onItemSelect?.(item)}
      >
        <CardContent className="p-2.5">
          {/* Active label */}
          {isActive && (
            <div className="flex items-center gap-1 mb-1.5">
              <MessageSquare className="w-2.5 h-2.5 text-violet-400" />
              <span className="text-[9px] text-violet-400 font-medium">
                Being discussed\u2026
              </span>
            </div>
          )}

          <div className="flex items-start gap-2">
            {/* Type icon */}
            <div className="mt-1 flex-shrink-0 text-muted-foreground">
              {briefingTypeIcon(item.type)}
            </div>

            {/* Main content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                {/* Priority label */}
                <span
                  className={cn(
                    "text-[10px] font-mono font-semibold rounded px-1 py-0 leading-tight",
                    item.priority === 0
                      ? "text-red-400 bg-red-500/10"
                      : item.priority === 1
                        ? "text-orange-400 bg-orange-500/10"
                        : item.priority === 2
                          ? "text-yellow-400 bg-yellow-500/10"
                          : "text-zinc-400 bg-zinc-500/10"
                  )}
                >
                  {briefingPriorityLabel(item.priority)}
                </span>

                {/* Title */}
                <p className="text-xs font-medium truncate flex-1">
                  {truncate(item.title, 60)}
                </p>

                {/* Discuss hint on hover */}
                <span className="text-[9px] text-violet-400/0 group-hover:text-violet-400/70 transition-colors flex-shrink-0">
                  discuss
                </span>
              </div>

              {/* Description preview */}
              {item.description && (
                <p className="text-[10px] text-muted-foreground/70 mt-0.5 truncate">
                  {truncate(item.description, 80)}
                </p>
              )}

              {/* Metadata row */}
              <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                {/* Source badge */}
                <Badge
                  variant="outline"
                  className="text-[9px] py-0 px-1 bg-indigo-500/10 border-indigo-500/30 text-indigo-400"
                >
                  {item.source}
                </Badge>

                {/* Type badge */}
                <Badge
                  variant="outline"
                  className="text-[9px] py-0 px-1 border-zinc-700 text-muted-foreground"
                >
                  {item.type.replace(/_/g, " ")}
                </Badge>

                {/* Action label if present */}
                {item.action_label && (
                  <span className="text-[9px] text-violet-400">
                    {item.action_label}
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
}

/* ------------------------------------------------------------------ */
/*  Exports                                                            */
/* ------------------------------------------------------------------ */

export { QueueView, type QueueItem, type BriefingItemData, type FeedItem };
