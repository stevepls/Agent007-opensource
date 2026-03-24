"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  AlertTriangle,
  Calendar,
  CheckSquare,
  ChevronDown,
  ChevronUp,
  Clock,
  Code,
  Database,
  Lightbulb,
  Loader2,
  Mail,
  RefreshCw,
  Shield,
  Sparkles,
  X,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface BriefingItem {
  id: string;
  type: string;
  priority: number;
  title: string;
  description: string;
  action_label: string | null;
  action_callback: string | null;
  action_data: Record<string, any> | null;
  source: string;
  created_at: string;
  dismissed: boolean;
  metadata: Record<string, any>;
}

interface BriefingSummary {
  total_items: number;
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
  critical_count: number;
  high_count: number;
  needs_attention: boolean;
}

interface BriefingResponse {
  greeting: string;
  items: BriefingItem[];
  summary: BriefingSummary;
}

/* ------------------------------------------------------------------ */
/*  Config maps                                                        */
/* ------------------------------------------------------------------ */

const PRIORITY_COLORS: Record<number, { dot: string; ring: string }> = {
  0: { dot: "bg-red-500",    ring: "ring-red-500/40" },
  1: { dot: "bg-orange-500", ring: "ring-orange-500/40" },
  2: { dot: "bg-yellow-500", ring: "ring-yellow-500/40" },
  3: { dot: "bg-zinc-500",   ring: "ring-zinc-500/30" },
  4: { dot: "bg-zinc-600",   ring: "ring-zinc-600/20" },
};

const TYPE_ICONS: Record<string, React.ReactNode> = {
  schema_change:    <Database className="w-3 h-3" />,
  pending_approval: <Shield className="w-3 h-3" />,
  code_review:      <Code className="w-3 h-3" />,
  message_queue:    <Mail className="w-3 h-3" />,
  error:            <AlertTriangle className="w-3 h-3" />,
  todo:             <CheckSquare className="w-3 h-3" />,
  meeting:          <Calendar className="w-3 h-3" />,
  deadline:         <Clock className="w-3 h-3" />,
  insight:          <Lightbulb className="w-3 h-3" />,
  suggestion:       <Sparkles className="w-3 h-3" />,
};

const PRIORITY_LABEL: Record<number, string> = {
  0: "CRITICAL",
  1: "HIGH",
  2: "MEDIUM",
  3: "LOW",
  4: "INFO",
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function truncate(str: string, max: number): string {
  if (!str) return "";
  return str.length > max ? str.slice(0, max) + "\u2026" : str;
}

function timeAgo(iso: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(iso).getTime()) / 1000
  );
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function BriefingPanel() {
  const [data, setData] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set());

  /* Fetch briefing ------------------------------------------------- */

  const fetchBriefing = useCallback(async () => {
    try {
      const res = await fetch("/api/briefing");
      if (res.ok) {
        const json: BriefingResponse = await res.json();
        setData(json);
      }
    } catch {
      // Silently handle fetch errors
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBriefing();
    const interval = setInterval(fetchBriefing, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchBriefing]);

  /* Dismiss -------------------------------------------------------- */

  const dismissItem = useCallback(async (itemId: string) => {
    setDismissingIds((prev) => new Set(prev).add(itemId));
    try {
      await fetch("/api/briefing/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ item_id: itemId }),
      });
      setData((prev) => {
        if (!prev) return prev;
        const items = prev.items.filter((i) => i.id !== itemId);
        const critical_count = items.filter((i) => i.priority === 0).length;
        const high_count = items.filter((i) => i.priority === 1).length;
        return {
          ...prev,
          items,
          summary: {
            ...prev.summary,
            total_items: items.length,
            critical_count,
            high_count,
            needs_attention: critical_count > 0 || high_count > 0,
          },
        };
      });
    } catch {
      // Silently handle dismiss errors
    } finally {
      setDismissingIds((prev) => {
        const next = new Set(prev);
        next.delete(itemId);
        return next;
      });
    }
  }, []);

  /* Derived -------------------------------------------------------- */

  const items = data?.items.filter((i) => !i.dismissed) || [];
  const summary = data?.summary;
  const greeting = data?.greeting || "";

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="flex items-center gap-1.5 group"
        >
          {collapsed ? (
            <ChevronDown className="w-3.5 h-3.5 text-muted-foreground group-hover:text-foreground transition-colors" />
          ) : (
            <ChevronUp className="w-3.5 h-3.5 text-muted-foreground group-hover:text-foreground transition-colors" />
          )}
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider group-hover:text-foreground transition-colors">
            Briefing
          </span>
        </button>

        <div className="flex items-center gap-1.5">
          {summary && summary.critical_count > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 bg-red-500/10 border-red-500/30 text-red-400"
            >
              {summary.critical_count} critical
            </Badge>
          )}
          {summary && summary.high_count > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 bg-orange-500/10 border-orange-500/30 text-orange-400"
            >
              {summary.high_count} high
            </Badge>
          )}
          {summary && (
            <span className="text-[10px] text-muted-foreground">
              {summary.total_items} items
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={fetchBriefing}
          >
            <RefreshCw className={cn("w-3 h-3", loading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* Collapsible body */}
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            key="briefing-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-2">
              {/* Greeting */}
              {greeting && (
                <p className="text-xs text-muted-foreground italic px-0.5">
                  {greeting}
                </p>
              )}

              {/* Loading state */}
              {loading && items.length === 0 ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
              ) : items.length === 0 ? (
                /* Empty state */
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-6"
                >
                  <Sparkles className="w-6 h-6 mx-auto mb-1.5 text-muted-foreground/40" />
                  <p className="text-xs text-muted-foreground/60">
                    All clear — nothing needs attention
                  </p>
                </motion.div>
              ) : (
                /* Item list */
                <AnimatePresence mode="popLayout">
                  {items.map((item) => {
                    const prio = PRIORITY_COLORS[item.priority] || PRIORITY_COLORS[4];
                    const icon = TYPE_ICONS[item.type] || <Sparkles className="w-3 h-3" />;
                    const isExpanded = expandedId === item.id;
                    const isDismissing = dismissingIds.has(item.id);

                    return (
                      <motion.div
                        key={item.id}
                        layout
                        initial={{ opacity: 0, y: -8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, x: -20, height: 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        <Card
                          className={cn(
                            "border transition-colors",
                            item.priority <= 1 && `ring-1 ${prio.ring}`
                          )}
                        >
                          <CardContent className="p-2">
                            <div className="flex items-start gap-1.5">
                              {/* Priority dot */}
                              <div
                                className={cn(
                                  "w-2 h-2 rounded-full mt-1 shrink-0",
                                  prio.dot
                                )}
                                title={PRIORITY_LABEL[item.priority] || "INFO"}
                              />

                              {/* Type icon */}
                              <div className="text-muted-foreground mt-0.5 shrink-0">
                                {icon}
                              </div>

                              {/* Content */}
                              <div
                                className="flex-1 min-w-0 cursor-pointer"
                                onClick={() =>
                                  setExpandedId(isExpanded ? null : item.id)
                                }
                              >
                                <p className="text-xs font-medium truncate">
                                  {item.title}
                                </p>

                                {/* Description — always visible truncated, full on expand */}
                                <p
                                  className={cn(
                                    "text-[10px] text-muted-foreground mt-0.5",
                                    !isExpanded && "truncate"
                                  )}
                                  title={item.description}
                                >
                                  {isExpanded
                                    ? item.description
                                    : truncate(item.description, 80)}
                                </p>

                                {/* Meta row */}
                                <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                  <Badge
                                    variant="outline"
                                    className="text-[9px] py-0 px-1 text-muted-foreground"
                                  >
                                    {item.source}
                                  </Badge>
                                  <span className="text-[9px] text-muted-foreground/60">
                                    {timeAgo(item.created_at)}
                                  </span>
                                </div>

                                {/* Action button (expanded) */}
                                {isExpanded && item.action_label && (
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="mt-1.5 h-6 text-[10px] px-2 text-violet-400 hover:text-violet-300"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (item.action_callback) {
                                        // Fire callback to orchestrator
                                        fetch(item.action_callback, {
                                          method: "POST",
                                          headers: {
                                            "Content-Type": "application/json",
                                          },
                                          body: JSON.stringify(
                                            item.action_data || {}
                                          ),
                                        }).catch(() => {});
                                      }
                                    }}
                                  >
                                    {item.action_label}
                                  </Button>
                                )}
                              </div>

                              {/* Dismiss button */}
                              <button
                                className="text-muted-foreground/40 hover:text-muted-foreground transition-colors shrink-0 mt-0.5"
                                onClick={() => dismissItem(item.id)}
                                disabled={isDismissing}
                                title="Dismiss"
                              >
                                {isDismissing ? (
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                  <X className="w-3 h-3" />
                                )}
                              </button>
                            </div>
                          </CardContent>
                        </Card>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
