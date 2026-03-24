"use client";

import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  Hammer,       // scaffolding
  Ticket,       // ticket_scan / ticket_manager
  Newspaper,    // daily_briefing
  GitPullRequest, // pr_scanner (future)
  Bot,          // generic fallback
  Loader2,
} from "lucide-react";

interface AgentJob {
  name: string;
  interval: number;
  last_run: number | null;    // unix timestamp
  age: number | null;         // seconds since last run
  enabled: boolean;
  last_summary: string | null;
}

interface AgentStripProps {
  onAgentFocus?: (agentName: string) => void;
}

const AGENT_CONFIG: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  scaffolding: {
    icon: <Hammer className="w-3.5 h-3.5" />,
    label: "Scaffold",
    color: "violet",
  },
  ticket_scan: {
    icon: <Ticket className="w-3.5 h-3.5" />,
    label: "Tickets",
    color: "sky",
  },
  daily_briefing: {
    icon: <Newspaper className="w-3.5 h-3.5" />,
    label: "Briefing",
    color: "amber",
  },
  pr_scanner: {
    icon: <GitPullRequest className="w-3.5 h-3.5" />,
    label: "PRs",
    color: "emerald",
  },
};

function getStatusColor(age: number | null, enabled: boolean): string {
  if (!enabled) return "text-zinc-600";
  if (age === null) return "text-zinc-500";
  if (age < 300) return "text-emerald-400";   // <5 min — just ran
  if (age < 3600) return "text-amber-400";    // <1 hour
  return "text-zinc-500";                      // stale
}

function getStatusDot(age: number | null, enabled: boolean): string {
  if (!enabled) return "bg-zinc-600";
  if (age === null) return "bg-zinc-500";
  if (age < 300) return "bg-emerald-400 animate-pulse";
  if (age < 3600) return "bg-amber-400";
  return "bg-zinc-500";
}

function formatAge(age: number | null): string {
  if (age === null) return "never";
  if (age < 60) return `${Math.floor(age)}s`;
  if (age < 3600) return `${Math.floor(age / 60)}m`;
  if (age < 86400) return `${Math.floor(age / 3600)}h`;
  return `${Math.floor(age / 86400)}d`;
}

export function AgentStrip({ onAgentFocus }: AgentStripProps) {
  const [agents, setAgents] = useState<AgentJob[]>([]);
  const [schedulerRunning, setSchedulerRunning] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/agents/status");
      if (res.ok) {
        const data = await res.json();
        setAgents(data.agents || []);
        setSchedulerRunning(data.scheduler_running);
      }
    } catch {
      // Silent
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30_000); // poll every 30s
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (agents.length === 0) {
    return null; // Don't render if no data yet
  }

  return (
    <div className="mb-3">
      {/* Header */}
      <div className="flex items-center gap-1.5 mb-2">
        <Bot className="w-3 h-3 text-muted-foreground" />
        <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
          Agents
        </span>
        {!schedulerRunning && (
          <span className="text-[10px] text-red-400 ml-auto">offline</span>
        )}
      </div>

      {/* Agent row */}
      <div className="flex gap-1.5 flex-wrap">
        {agents.map((agent) => {
          const config = AGENT_CONFIG[agent.name] || {
            icon: <Bot className="w-3.5 h-3.5" />,
            label: agent.name.replace(/_/g, " "),
            color: "zinc",
          };

          return (
            <button
              key={agent.name}
              onClick={() => onAgentFocus?.(agent.name)}
              title={agent.last_summary || `${config.label} — ${agent.enabled ? "enabled" : "disabled"}`}
              className={cn(
                "flex items-center gap-1.5 px-2 py-1.5 rounded-md border transition-all",
                "text-[11px] font-medium",
                "border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/80 hover:border-zinc-700",
                "cursor-pointer group"
              )}
            >
              {/* Status dot */}
              <span className={cn("w-1.5 h-1.5 rounded-full flex-shrink-0", getStatusDot(agent.age, agent.enabled))} />

              {/* Icon */}
              <span className={cn("flex-shrink-0", getStatusColor(agent.age, agent.enabled))}>
                {config.icon}
              </span>

              {/* Label + age */}
              <span className="text-zinc-400 group-hover:text-zinc-200 transition-colors">
                {config.label}
              </span>
              <span className={cn("text-[10px]", getStatusColor(agent.age, agent.enabled))}>
                {formatAge(agent.age)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
