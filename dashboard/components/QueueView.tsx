"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import {
  Loader2,
  ExternalLink,
  Filter,
  RefreshCw,
  AlertTriangle,
  Clock,
  MessageSquare,
  AlertCircle,
  Lightbulb,
  Shield,
  Database,
  Mail,
  CheckSquare,
  Headphones,
  ChevronDown,
  Keyboard,
  ListPlus,
  GitBranch,
  Sparkles,
  X,
  UserPlus,
  Send,
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
  onCreateTask?: (item: QueueItem | BriefingItemData) => void;
  onBreakdown?: (item: QueueItem | BriefingItemData) => void;
  dismissedIds?: Set<string>;
  activeProject?: string | null;
  onProjectSelect?: (project: string | null) => void;
}

/* ------------------------------------------------------------------ */
/*  SLA / urgency visual config                                        */
/* ------------------------------------------------------------------ */

const SLA_CONFIG: Record<
  string,
  { dot: string; label: string; labelColor: string }
> = {
  within_sla: {
    dot: "bg-emerald-400",
    label: "Within SLA",
    labelColor: "text-muted-foreground",
  },
  approaching: {
    dot: "bg-yellow-400",
    label: "Approaching",
    labelColor: "text-yellow-400",
  },
  breaching: {
    dot: "bg-orange-400",
    label: "Breaching",
    labelColor: "text-orange-400",
  },
  breached: {
    dot: "bg-red-500",
    label: "Breached",
    labelColor: "text-red-400",
  },
  no_sla: {
    dot: "bg-zinc-600",
    label: "",
    labelColor: "text-muted-foreground",
  },
};

/* ------------------------------------------------------------------ */
/*  Project badge colours — deterministic by name                      */
/* ------------------------------------------------------------------ */

const PROJECT_COLORS = [
  "border-[#333] text-zinc-400",
  "border-[#333] text-zinc-400",
  "border-[#333] text-zinc-400",
  "border-[#333] text-zinc-400",
  "border-[#333] text-zinc-400",
  "border-[#333] text-zinc-400",
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

/* ------------------------------------------------------------------ */
/*  Briefing-specific helpers                                          */
/* ------------------------------------------------------------------ */

/** Icon for briefing item types. */
function briefingTypeIcon(type: string) {
  const cls = "w-4 h-4 text-zinc-500";
  switch (type) {
    case "error":
      return <AlertTriangle className={cls} />;
    case "pending_approval":
      return <Shield className={cls} />;
    case "schema_change":
      return <Database className={cls} />;
    case "insight":
      return <Lightbulb className={cls} />;
    case "message":
      return <Mail className={cls} />;
    default:
      return <Sparkles className={cls} />;
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

/** Background tint for briefing items based on priority. */
function briefingBgTint(priority: number): string {
  switch (priority) {
    case 0:
      return "bg-red-950/20";
    case 1:
      return "bg-orange-950/15";
    case 2:
      return "bg-yellow-950/10";
    default:
      return "bg-zinc-900/40";
  }
}

/** Priority label for briefing items. */
function briefingPriorityLabel(priority: number): string {
  switch (priority) {
    case 0:
      return "CRITICAL";
    case 1:
      return "HIGH";
    case 2:
      return "MEDIUM";
    case 3:
      return "LOW";
    case 4:
    default:
      return "INFO";
  }
}

/** Priority label styling for briefing items. */
function briefingPriorityStyle(priority: number): string {
  switch (priority) {
    case 0:
      return "text-red-400 bg-red-500/15 border-red-500/30";
    case 1:
      return "text-orange-400 bg-orange-500/15 border-orange-500/30";
    case 2:
      return "text-yellow-400 bg-yellow-500/15 border-yellow-500/30";
    default:
      return "text-zinc-400 bg-zinc-500/15 border-zinc-500/30";
  }
}

/* ------------------------------------------------------------------ */
/*  Animation variants                                                 */
/* ------------------------------------------------------------------ */

const cardEnter = {
  initial: { opacity: 0, x: 20, scale: 0.98 },
  animate: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 400, damping: 30 },
  },
  exit: {
    opacity: 0,
    x: -100,
    height: 0,
    marginBottom: 0,
    paddingTop: 0,
    paddingBottom: 0,
    transition: { duration: 0.3, ease: "easeInOut" },
  },
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const MAX_VISIBLE = 10;

function QueueView({
  activeItemId,
  onItemSelect,
  onCreateTask,
  onBreakdown,
  dismissedIds,
  activeProject,
  onProjectSelect,
}: QueueViewProps) {
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [briefingItems, setBriefingItems] = useState<BriefingItemData[]>([]);
  const [summary, setSummary] = useState<QueueSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [showFilter, setShowFilter] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Use parent-controlled project scope, or internal state as fallback
  const filterProject = activeProject || "";
  const setFilterProject = (p: string) => {
    if (onProjectSelect) {
      onProjectSelect(p || null);
    }
  };

  // ── Client-side cache ─────────────────────────────────────
  // Stale-while-revalidate: show cached data immediately, fetch
  // fresh data in the background. Cache key includes project scope.
  const cacheRef = useRef<{
    key: string;
    queue: QueueItem[];
    briefing: BriefingItemData[];
    summary: QueueSummary | null;
    timestamp: number;
  } | null>(null);

  const CACHE_TTL = 30_000; // 30s — show cache, refetch in background
  const POLL_INTERVAL = 60_000; // 60s — poll for fresh data

  const fetchData = useCallback(async (background = false) => {
    const cacheKey = filterProject || "__all__";

    // If cache is fresh and this is a poll, skip
    if (background && cacheRef.current?.key === cacheKey) {
      const age = Date.now() - cacheRef.current.timestamp;
      if (age < CACHE_TTL) return;
    }

    try {
      const queueParams = new URLSearchParams();
      if (filterProject) queueParams.set("project", filterProject);
      queueParams.set("limit", "50");

      const [queueRes, briefingRes] = await Promise.allSettled([
        fetch(`/api/queue?${queueParams.toString()}`),
        fetch("/api/briefing?max_items=15"),
      ]);

      let newQueue: QueueItem[] | null = null;
      let newSummary: QueueSummary | null = null;
      let newBriefing: BriefingItemData[] | null = null;

      if (queueRes.status === "fulfilled" && queueRes.value.ok) {
        const data: QueueResponse = await queueRes.value.json();
        newQueue = data.items || [];
        newSummary = data.summary || null;
      }

      if (briefingRes.status === "fulfilled" && briefingRes.value.ok) {
        const data = await briefingRes.value.json();
        newBriefing = data.items || [];
      }

      // Update state
      if (newQueue !== null) setQueueItems(newQueue);
      if (newSummary !== null) setSummary(newSummary);
      if (newBriefing !== null) setBriefingItems(newBriefing);

      // Update cache
      cacheRef.current = {
        key: cacheKey,
        queue: newQueue ?? queueItems,
        briefing: newBriefing ?? briefingItems,
        summary: newSummary ?? summary,
        timestamp: Date.now(),
      };
    } catch {
      // Silently handle — stale cache still showing
    } finally {
      setLoading(false);
    }
  }, [activeProject]);

  // Initial load: use cache if available, fetch in background
  useEffect(() => {
    const cacheKey = filterProject || "__all__";
    if (cacheRef.current?.key === cacheKey) {
      // Show cached data immediately
      setQueueItems(cacheRef.current.queue);
      setBriefingItems(cacheRef.current.briefing);
      setSummary(cacheRef.current.summary);
      setLoading(false);
      // Refresh in background
      fetchData(true);
    } else {
      setLoading(true);
      fetchData();
    }

    const interval = setInterval(() => fetchData(true), POLL_INTERVAL);
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
  const projectNames = summary ? Object.keys(summary.by_project).sort() : [];

  // Triage progress
  const dismissed = dismissedIds ?? new Set<string>();
  const allCount = useMemo(() => {
    const allFeed: FeedItem[] = [
      ...queueItems.map((q): FeedItem => ({ kind: "queue", data: q })),
      ...briefingItems.map((b): FeedItem => ({ kind: "briefing", data: b })),
    ];
    return allFeed.length;
  }, [queueItems, briefingItems]);
  const reviewedCount = dismissed.size;
  const triagePercent = allCount > 0 ? Math.round((reviewedCount / allCount) * 100) : 0;

  // Keyboard navigation
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture keys if user is typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      switch (e.key) {
        case "j":
        case "ArrowDown":
          e.preventDefault();
          setFocusedIndex((prev) => {
            const next = prev + 1;
            return next >= visibleItems.length ? visibleItems.length - 1 : next;
          });
          break;
        case "k":
        case "ArrowUp":
          e.preventDefault();
          setFocusedIndex((prev) => {
            const next = prev - 1;
            return next < 0 ? 0 : next;
          });
          break;
        case "Enter":
          if (focusedIndex >= 0 && focusedIndex < visibleItems.length) {
            e.preventDefault();
            const item = visibleItems[focusedIndex];
            onItemSelect?.(item.data);
          }
          break;
        case "s":
          // Skip / dismiss focused item (move focus to next)
          if (focusedIndex >= 0 && focusedIndex < visibleItems.length) {
            e.preventDefault();
            // Dispatch a custom event or just move focus forward
            // The parent manages dismissedIds, so we select and let parent handle skip
            const item = visibleItems[focusedIndex];
            onItemSelect?.(item.data);
          }
          break;
        case "t":
          if (focusedIndex >= 0 && focusedIndex < visibleItems.length) {
            e.preventDefault();
            const item = visibleItems[focusedIndex];
            onCreateTask?.(item.data);
          }
          break;
        case "b":
          if (focusedIndex >= 0 && focusedIndex < visibleItems.length) {
            e.preventDefault();
            const item = visibleItems[focusedIndex];
            onBreakdown?.(item.data);
          }
          break;
        case "?":
          e.preventDefault();
          setShowShortcuts((v) => !v);
          break;
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [focusedIndex, visibleItems, onItemSelect, onCreateTask, onBreakdown]);

  // Reset focus when items change
  useEffect(() => {
    setFocusedIndex((prev) =>
      prev >= visibleItems.length ? Math.max(0, visibleItems.length - 1) : prev
    );
  }, [visibleItems.length]);

  // Scroll focused item into view
  useEffect(() => {
    if (focusedIndex < 0 || !containerRef.current) return;
    const cards = containerRef.current.querySelectorAll("[data-queue-card]");
    const card = cards[focusedIndex];
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [focusedIndex]);

  return (
    <div className="space-y-3" ref={containerRef}>
      {/* ---- Header ---- */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
            {filterProject ? `${filterProject}` : "Priority Feed"}
          </span>
          {filterProject && (
            <button
              onClick={() => setFilterProject("")}
              className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              title="Clear project filter"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {/* Summary badges */}
          {summary && summary.total > 0 && (
            <Badge
              variant="outline"
              className="text-[11px] py-0 px-1.5 bg-indigo-500/10 border-indigo-500/30 text-indigo-400"
            >
              {summary.total}
            </Badge>
          )}
          {summary && summary.breaching > 0 && (
            <Badge
              variant="outline"
              className="text-[11px] py-0 px-1.5 bg-red-500/10 border-red-500/30 text-red-400"
            >
              {summary.breaching} breaching
            </Badge>
          )}

          {/* Keyboard shortcuts toggle */}
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "h-6 w-6 text-muted-foreground hover:text-zinc-300",
              showShortcuts && "text-indigo-400"
            )}
            onClick={() => setShowShortcuts((v) => !v)}
            title="Keyboard shortcuts (?)"
          >
            <Keyboard className="w-3.5 h-3.5" />
          </Button>

          {/* Filter toggle */}
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "h-6 w-6 text-muted-foreground hover:text-zinc-300",
              showFilter && "text-indigo-400"
            )}
            onClick={() => setShowFilter((v) => !v)}
          >
            <Filter className="w-3.5 h-3.5" />
          </Button>

          {/* Refresh */}
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-muted-foreground hover:text-zinc-300"
            onClick={() => {
              setLoading(true);
              fetchData();
            }}
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* ---- Triage Progress Bar ---- */}
      {allCount > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">
              {reviewedCount} of {allCount} reviewed
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">
              {triagePercent}%
            </span>
          </div>
          <Progress
            value={triagePercent}
            className="h-1 bg-zinc-800"
            indicatorClassName="bg-indigo-500/70"
          />
        </div>
      )}

      {/* ---- Keyboard shortcuts panel ---- */}
      <AnimatePresence>
        {showShortcuts && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-3">
              <p className="text-[11px] font-medium text-zinc-400 mb-2 uppercase tracking-wide">
                Keyboard shortcuts
              </p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {[
                  ["j / \u2193", "Next item"],
                  ["k / \u2191", "Previous item"],
                  ["Enter", "Discuss"],
                  ["s", "Skip / dismiss"],
                  ["t", "Create task"],
                  ["b", "Break down"],
                  ["?", "Toggle shortcuts"],
                ].map(([key, label]) => (
                  <div key={key} className="flex items-center gap-2">
                    <kbd className="text-[11px] font-mono bg-zinc-800 border border-zinc-700 rounded px-1.5 py-0.5 text-zinc-300 min-w-[2rem] text-center">
                      {key}
                    </kbd>
                    <span className="text-[11px] text-muted-foreground">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Project filter dropdown ---- */}
      <AnimatePresence>
        {showFilter && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="flex flex-wrap gap-1.5 pb-1">
              <button
                onClick={() => setFilterProject("")}
                className={cn(
                  "text-[11px] px-2.5 py-1 rounded-full border transition-colors",
                  filterProject === ""
                    ? "bg-indigo-500/15 border-indigo-500/30 text-indigo-300"
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
                    "text-[11px] px-2.5 py-1 rounded-full border transition-colors",
                    filterProject === name
                      ? "bg-indigo-500/15 border-indigo-500/30 text-indigo-300"
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
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(summary.by_project).map(([name, count]) => (
            <Badge
              key={name}
              variant="outline"
              className={cn("text-[11px] py-0 px-1.5", projectColor(name))}
            >
              {name}: {count}
            </Badge>
          ))}
        </div>
      )}

      {/* ---- Item list ---- */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
          <span className="text-[11px] text-muted-foreground">Loading feed...</span>
        </div>
      ) : visibleItems.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <CheckSquare className="w-5 h-5 text-emerald-400/50" />
          <p className="text-xs text-muted-foreground/60 text-center">
            All clear. No items need attention.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <AnimatePresence mode="popLayout">
            {visibleItems.map((feedItem, index) => {
              const id = feedItemId(feedItem);
              const isActive = activeItemId === id;
              const isFocused = focusedIndex === index;

              if (feedItem.kind === "queue") {
                return (
                  <QueueCard
                    key={id}
                    item={feedItem.data}
                    isActive={isActive}
                    isFocused={isFocused}
                    index={index}
                    onItemSelect={onItemSelect}
                    onCreateTask={onCreateTask}
                    onBreakdown={onBreakdown}
                    onFocus={() => setFocusedIndex(index)}
                  />
                );
              }

              return (
                <BriefingCard
                  key={id}
                  item={feedItem.data}
                  isActive={isActive}
                  isFocused={isFocused}
                  index={index}
                  onItemSelect={onItemSelect}
                  onCreateTask={onCreateTask}
                  onBreakdown={onBreakdown}
                  onFocus={() => setFocusedIndex(index)}
                />
              );
            })}
          </AnimatePresence>

          {/* Remaining count */}
          {totalCount > MAX_VISIBLE && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center justify-center gap-1.5 py-2"
            >
              <ChevronDown className="w-3 h-3 text-muted-foreground/50" />
              <span className="text-[11px] text-muted-foreground/60">
                {totalCount - MAX_VISIBLE} more items below
              </span>
            </motion.div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Queue item card (ClickUp / Zendesk tasks)                          */
/* ------------------------------------------------------------------ */

function QueueCard({
  item,
  isActive,
  isFocused,
  index,
  onItemSelect,
  onCreateTask,
  onBreakdown,
  onFocus,
}: {
  item: QueueItem;
  isActive: boolean;
  isFocused: boolean;
  index: number;
  onItemSelect?: (item: QueueItem | BriefingItemData) => void;
  onCreateTask?: (item: QueueItem | BriefingItemData) => void;
  onBreakdown?: (item: QueueItem | BriefingItemData) => void;
  onFocus: () => void;
}) {
  const sla = SLA_CONFIG[item.priority_score?.sla_status] ?? SLA_CONFIG.no_sla;
  const SourceIcon = item.source === "clickup" ? CheckSquare : Headphones;

  return (
    <motion.div
      data-queue-card
      variants={cardEnter}
      initial="initial"
      animate="animate"
      exit="exit"
      layout
      onMouseEnter={onFocus}
    >
      <Card
        className={cn(
          "border border-[#1a1a1a] bg-[#141414] transition-all duration-200 cursor-pointer",
          // Hover
          "hover:border-[#333] hover:bg-[#1a1a1a]",
          // Active (being discussed)
          isActive && "border-indigo-500/50 bg-indigo-500/5 opacity-60",
          // Keyboard focused
          isFocused && !isActive && "ring-1 ring-indigo-500/40 bg-[#1a1a1a]",
        )}
        onClick={() => onItemSelect?.(item)}
      >
        <CardContent className="p-3">
          {/* Active discussing badge */}
          {isActive && (
            <div className="flex items-center gap-1.5 mb-2">
              <MessageSquare className="w-3 h-3 text-indigo-400" />
              <span className="text-[11px] text-indigo-400 font-medium">
                Discussing...
              </span>
            </div>
          )}

          {/* Title row */}
          <div className="flex items-start gap-2">
            <SourceIcon
              className={cn(
                "w-4 h-4 flex-shrink-0 mt-0.5",
                item.source === "clickup"
                  ? "text-blue-400"
                  : "text-emerald-400"
              )}
            />

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium truncate flex-1 text-zinc-100">
                  {item.title}
                </p>
                {item.source_url && (
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 text-muted-foreground/50 hover:text-indigo-400 transition-colors"
                    onClick={(e) => e.stopPropagation()}
                    title="Open in source"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>

              {/* Status + metadata row */}
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                {/* SLA dot */}
                <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", sla.dot)} title={sla.label} />

                {/* Status */}
                <span className="text-xs text-zinc-400 capitalize">
                  {(item.status || "").replace(/_/g, " ")}
                </span>

                <span className="text-[11px] text-muted-foreground/30">&middot;</span>

                {/* Project */}
                <span className="text-xs text-zinc-500">{item.project_name}</span>

                {/* Assignee */}
                {item.assignee && (
                  <>
                    <span className="text-[11px] text-muted-foreground/30">&middot;</span>
                    <span className="text-xs text-zinc-500">{item.assignee}</span>
                  </>
                )}
                {!item.assignee && (
                  <>
                    <span className="text-[11px] text-muted-foreground/30">&middot;</span>
                    <span className="text-xs text-red-400/70">Unassigned</span>
                  </>
                )}

                {/* Age */}
                <span className="text-xs text-muted-foreground/40 ml-auto">
                  {timeAgo(item.updated_at || item.created_at)}
                </span>
              </div>

              {/* Recommended actions — context-specific */}
              {!isActive && (
                <div className="flex items-center gap-1.5 mt-2">
                  {/* Primary action — context-dependent */}
                  {!item.assignee && (
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-indigo-400 hover:bg-indigo-500/10 gap-1"
                      onClick={(e) => { e.stopPropagation(); onCreateTask?.(item); }}>
                      <UserPlus className="w-3 h-3" />
                      Assign
                    </Button>
                  )}
                  {item.assignee && item.status === "open" && (
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-indigo-400 hover:bg-indigo-500/10 gap-1"
                      onClick={(e) => { e.stopPropagation(); onItemSelect?.(item); }}>
                      <Send className="w-3 h-3" />
                      Ping {item.assignee.split(" ")[0]}
                    </Button>
                  )}
                  {item.status === "in_progress" && (
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-zinc-400 hover:bg-zinc-800 gap-1"
                      onClick={(e) => { e.stopPropagation(); onItemSelect?.(item); }}>
                      <Clock className="w-3 h-3" />
                      Check status
                    </Button>
                  )}
                  {(item.status === "review" || item.status === "internal review" || item.status === "internal_review") && (
                    <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-emerald-400 hover:bg-emerald-500/10 gap-1"
                      onClick={(e) => { e.stopPropagation(); onItemSelect?.(item); }}>
                      <CheckSquare className="w-3 h-3" />
                      Review
                    </Button>
                  )}

                  {/* Secondary actions */}
                  <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 gap-1"
                    onClick={(e) => { e.stopPropagation(); onItemSelect?.(item); }}>
                    Focus
                  </Button>
                  <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 gap-1"
                    onClick={(e) => { e.stopPropagation(); onBreakdown?.(item); }}>
                    <GitBranch className="w-3 h-3" />
                    Split
                  </Button>
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/*  Briefing item card (insights, errors, approvals, etc.)             */
/* ------------------------------------------------------------------ */

function BriefingCard({
  item,
  isActive,
  isFocused,
  index,
  onItemSelect,
  onCreateTask,
  onBreakdown,
  onFocus,
}: {
  item: BriefingItemData;
  isActive: boolean;
  isFocused: boolean;
  index: number;
  onItemSelect?: (item: QueueItem | BriefingItemData) => void;
  onCreateTask?: (item: QueueItem | BriefingItemData) => void;
  onBreakdown?: (item: QueueItem | BriefingItemData) => void;
  onFocus: () => void;
}) {
  return (
    <motion.div
      data-queue-card
      variants={cardEnter}
      initial="initial"
      animate="animate"
      exit="exit"
      layout
      onMouseEnter={onFocus}
    >
      <Card
        className={cn(
          "border border-[#1a1a1a] bg-[#141414] transition-all duration-200 cursor-pointer",
          // Hover
          "hover:border-[#333] hover:bg-[#1a1a1a]",
          // Active
          isActive && "border-indigo-500/50 bg-indigo-500/5 opacity-60",
          // Keyboard focused
          isFocused && !isActive && "ring-1 ring-indigo-500/40 bg-[#1a1a1a]",
        )}
        onClick={() => onItemSelect?.(item)}
      >
        <CardContent className="p-3">
          {/* Active discussing badge */}
          {isActive && (
            <div className="flex items-center gap-1.5 mb-2">
              <MessageSquare className="w-3 h-3 text-indigo-400" />
              <span className="text-[11px] text-indigo-400 font-medium">
                Discussing...
              </span>
            </div>
          )}

          {/* Title row */}
          <div className="flex items-start gap-2">
            <div className="flex-shrink-0 mt-0.5">
              {briefingTypeIcon(item.type)}
            </div>

            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-zinc-100 leading-snug">
                {item.title}
              </p>

              {/* Metadata row */}
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                {/* Priority label badge */}
                <Badge
                  variant="outline"
                  className={cn(
                    "text-[11px] py-0 px-1.5 font-semibold uppercase tracking-wide",
                    briefingPriorityStyle(item.priority)
                  )}
                >
                  {briefingPriorityLabel(item.priority)}
                </Badge>

                <span className="text-[11px] text-muted-foreground/40">&middot;</span>

                {/* Source */}
                <span className="text-xs text-muted-foreground">
                  {item.source}
                </span>

                <span className="text-[11px] text-muted-foreground/40">&middot;</span>

                {/* Time ago */}
                <span className="text-[11px] text-muted-foreground/50">
                  {timeAgo(item.created_at)}
                </span>
              </div>

              {/* Description preview */}
              {item.description && (
                <p className="text-xs text-muted-foreground/60 mt-1.5 line-clamp-1">
                  {truncate(item.description, 100)}
                </p>
              )}

              {/* Action buttons — always visible, subtle */}
              {!isActive && (
                <div className="flex items-center gap-1.5 mt-2.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2.5 text-[11px] text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 gap-1.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      onItemSelect?.(item);
                    }}
                  >
                    <MessageSquare className="w-3 h-3" />
                    Discuss
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2.5 text-[11px] text-zinc-400 hover:text-emerald-300 hover:bg-emerald-500/10 gap-1.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCreateTask?.(item);
                    }}
                  >
                    <ListPlus className="w-3 h-3" />
                    Task
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2.5 text-[11px] text-zinc-400 hover:text-sky-300 hover:bg-sky-500/10 gap-1.5"
                    onClick={(e) => {
                      e.stopPropagation();
                      onBreakdown?.(item);
                    }}
                  >
                    <GitBranch className="w-3 h-3" />
                    Break down
                  </Button>
                </div>
              )}
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
