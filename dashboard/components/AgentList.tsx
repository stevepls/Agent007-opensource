"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { AgentUpdate } from "@/lib/utils";
import {
  Bot,
  Clock,
  Code2,
  Eye,
  Rocket,
  Ticket,
  Cpu,
  Database,
  Mail,
  GitBranch,
} from "lucide-react";

interface AgentListProps {
  agents: AgentUpdate[];
  onAgentClick?: (action: string) => void;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  orchestrator: <Cpu className="w-4 h-4" />,
  "time-logger": <Clock className="w-4 h-4" />,
  coder: <Code2 className="w-4 h-4" />,
  reviewer: <Eye className="w-4 h-4" />,
  deployer: <Rocket className="w-4 h-4" />,
  "ticket-manager": <Ticket className="w-4 h-4" />,
  database: <Database className="w-4 h-4" />,
  mailer: <Mail className="w-4 h-4" />,
  "version-control": <GitBranch className="w-4 h-4" />,
};

const STATUS_STYLES: Record<
  AgentUpdate["status"],
  { badge: "active" | "success" | "warning" | "error" | "secondary"; dot: string }
> = {
  active: { badge: "active", dot: "bg-green-500" },
  busy: { badge: "warning", dot: "bg-amber-500" },
  idle: { badge: "secondary", dot: "bg-slate-400" },
  error: { badge: "error", dot: "bg-red-500" },
  offline: { badge: "secondary", dot: "bg-slate-600" },
};

export function AgentList({ agents, onAgentClick }: AgentListProps) {
  // Sort by priority (lower = higher priority), then by status (active first)
  const sortedAgents = [...agents].sort((a, b) => {
    // Active agents first
    if (a.status === "active" && b.status !== "active") return -1;
    if (b.status === "active" && a.status !== "active") return 1;
    
    // Then by priority
    return (a.priority || 5) - (b.priority || 5);
  });

  const handleClick = (agent: AgentUpdate) => {
    if (onAgentClick) {
      onAgentClick(`Check status of ${agent.name}`);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-1">
      <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3 px-2">
        Agents
      </p>
      
      <AnimatePresence mode="popLayout">
        {sortedAgents.map((agent, index) => {
          const style = STATUS_STYLES[agent.status];
          const icon = AGENT_ICONS[agent.id] || <Bot className="w-4 h-4" />;

          return (
            <motion.div
              key={agent.id}
              layout
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ delay: index * 0.05, duration: 0.2 }}
            >
              <button
                onClick={() => handleClick(agent)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200",
                  "hover:bg-accent/50 group text-left",
                  agent.status === "active" && "bg-accent/30 glow"
                )}
              >
                {/* Icon */}
                <div
                  className={cn(
                    "w-8 h-8 rounded-lg flex items-center justify-center transition-colors",
                    agent.status === "active"
                      ? "bg-primary/20 text-primary"
                      : "bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary"
                  )}
                >
                  {icon}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">
                      {agent.name}
                    </span>
                    {/* Status dot */}
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full flex-shrink-0",
                        style.dot,
                        agent.status === "active" && "status-pulse"
                      )}
                    />
                  </div>
                  
                  {agent.current_task ? (
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {agent.current_task}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground/60 capitalize mt-0.5">
                      {agent.status}
                    </p>
                  )}
                </div>

                {/* Priority badge (only for high priority) */}
                {(agent.priority || 5) <= 2 && agent.status === "active" && (
                  <Badge variant="active" className="text-[10px] px-1.5">
                    High
                  </Badge>
                )}
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Quick actions */}
      <div className="pt-4 mt-4 border-t border-border">
        <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3 px-2">
          Quick Actions
        </p>
        <div className="space-y-1">
          {[
            { label: "Deploy latest", action: "deploy code to production" },
            { label: "Check tickets", action: "show open tickets" },
            { label: "Time summary", action: "show time logged today" },
          ].map((quick) => (
            <button
              key={quick.action}
              onClick={() => onAgentClick?.(quick.action)}
              className="w-full text-left px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent/50 rounded-lg transition-colors"
            >
              {quick.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
