"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  ListTodo,
  RefreshCw,
} from "lucide-react";

interface QueueTask {
  id: string;
  user_request: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: number;
  started_at?: number;
  completed_at?: number;
  error?: string;
}

interface QueueStatus {
  total: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
}

const STATUS_CONFIG: Record<
  string,
  { icon: React.ReactNode; color: string; bg: string; label: string }
> = {
  queued: {
    icon: <Clock className="w-3 h-3" />,
    color: "text-yellow-400",
    bg: "bg-yellow-500/10 border-yellow-500/30",
    label: "Queued",
  },
  running: {
    icon: <Loader2 className="w-3 h-3 animate-spin" />,
    color: "text-blue-400",
    bg: "bg-blue-500/10 border-blue-500/30",
    label: "Running",
  },
  completed: {
    icon: <CheckCircle className="w-3 h-3" />,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/30",
    label: "Done",
  },
  failed: {
    icon: <XCircle className="w-3 h-3" />,
    color: "text-red-400",
    bg: "bg-red-500/10 border-red-500/30",
    label: "Failed",
  },
};

function timeAgo(ts: number): string {
  const seconds = Math.floor(Date.now() / 1000 - ts);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

export function TaskQueue() {
  const [tasks, setTasks] = useState<QueueTask[]>([]);
  const [status, setStatus] = useState<QueueStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await fetch("/api/tasks");
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
        setStatus(data.status || null);
      }
    } catch {
      // Silently handle fetch errors
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch + poll every 3 seconds
  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  // Show only recent tasks (last 10)
  const recentTasks = tasks.slice(0, 10);
  const hasActive = tasks.some(
    (t) => t.status === "queued" || t.status === "running"
  );

  return (
    <div className="space-y-3">
      {/* Queue summary */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ListTodo className="w-4 h-4 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Task Queue
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {status && status.running > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 bg-blue-500/10 border-blue-500/30 text-blue-400"
            >
              {status.running} running
            </Badge>
          )}
          {status && status.queued > 0 && (
            <Badge
              variant="outline"
              className="text-[10px] py-0 px-1.5 bg-yellow-500/10 border-yellow-500/30 text-yellow-400"
            >
              {status.queued} queued
            </Badge>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-5 w-5"
            onClick={fetchTasks}
          >
            <RefreshCw
              className={cn("w-3 h-3", hasActive && "animate-spin")}
            />
          </Button>
        </div>
      </div>

      {/* Task list */}
      {loading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        </div>
      ) : recentTasks.length === 0 ? (
        <p className="text-xs text-muted-foreground/50 text-center py-3">
          No tasks in queue
        </p>
      ) : (
        <AnimatePresence mode="popLayout">
          {recentTasks.map((task) => {
            const cfg = STATUS_CONFIG[task.status] || STATUS_CONFIG.queued;
            return (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                layout
              >
                <Card
                  className={cn(
                    "border transition-colors",
                    cfg.bg
                  )}
                >
                  <CardContent className="p-2.5">
                    <div className="flex items-start gap-2">
                      <div className={cn("mt-0.5", cfg.color)}>
                        {cfg.icon}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium truncate">
                          {task.user_request}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge
                            variant="outline"
                            className={cn(
                              "text-[9px] py-0 px-1",
                              cfg.color
                            )}
                          >
                            {cfg.label}
                          </Badge>
                          <span className="text-[9px] text-muted-foreground">
                            {timeAgo(task.created_at)}
                          </span>
                          {task.error && (
                            <span
                              className="text-[9px] text-red-400 truncate max-w-[120px]"
                              title={task.error}
                            >
                              {task.error}
                            </span>
                          )}
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
