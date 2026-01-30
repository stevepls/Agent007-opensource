"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { StatusCard } from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle,
  Info,
  XCircle,
  TrendingUp,
  Clock,
  Ticket,
  Rocket,
  Database,
  ArrowRight,
  Sparkles,
} from "lucide-react";

interface DynamicStatusCardsProps {
  cards: StatusCard[];
  onAction?: (action: string) => void;
}

const TYPE_CONFIG: Record<
  StatusCard["type"],
  { icon: React.ReactNode; color: string; bgColor: string }
> = {
  info: {
    icon: <Info className="w-4 h-4" />,
    color: "text-blue-400",
    bgColor: "bg-blue-500/10 border-blue-500/20",
  },
  success: {
    icon: <CheckCircle className="w-4 h-4" />,
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/10 border-emerald-500/20",
  },
  warning: {
    icon: <AlertTriangle className="w-4 h-4" />,
    color: "text-amber-400",
    bgColor: "bg-amber-500/10 border-amber-500/20",
  },
  error: {
    icon: <XCircle className="w-4 h-4" />,
    color: "text-red-400",
    bgColor: "bg-red-500/10 border-red-500/20",
  },
  progress: {
    icon: <Rocket className="w-4 h-4" />,
    color: "text-violet-400",
    bgColor: "bg-violet-500/10 border-violet-500/20",
  },
  metric: {
    icon: <TrendingUp className="w-4 h-4" />,
    color: "text-cyan-400",
    bgColor: "bg-cyan-500/10 border-cyan-500/20",
  },
};

const ICON_MAP: Record<string, React.ReactNode> = {
  clock: <Clock className="w-4 h-4" />,
  ticket: <Ticket className="w-4 h-4" />,
  rocket: <Rocket className="w-4 h-4" />,
  database: <Database className="w-4 h-4" />,
  sparkles: <Sparkles className="w-4 h-4" />,
  trending: <TrendingUp className="w-4 h-4" />,
};

export function DynamicStatusCards({ cards, onAction }: DynamicStatusCardsProps) {
  // Sort by priority
  const sortedCards = [...cards].sort(
    (a, b) => (a.priority || 5) - (b.priority || 5)
  );

  return (
    <div className="space-y-3">
      <AnimatePresence mode="popLayout">
        {sortedCards.map((card, index) => {
          const config = TYPE_CONFIG[card.type];
          const customIcon = card.icon ? ICON_MAP[card.icon] : null;

          return (
            <motion.div
              key={card.id}
              layout
              initial={{ opacity: 0, y: 20, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95 }}
              transition={{
                delay: index * 0.05,
                duration: 0.3,
                layout: { duration: 0.2 },
              }}
            >
              <Card
                className={cn(
                  "overflow-hidden transition-all duration-300 hover:shadow-lg",
                  config.bgColor,
                  (card.priority || 5) <= 2 && "ring-1 ring-primary/30 glow"
                )}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={config.color}>
                        {customIcon || config.icon}
                      </span>
                      <CardTitle className="text-sm font-medium">
                        {card.title}
                      </CardTitle>
                    </div>
                    
                    {/* Priority badge */}
                    {(card.priority || 5) <= 2 && (
                      <Badge variant="active" className="text-[10px]">
                        Priority
                      </Badge>
                    )}
                  </div>
                </CardHeader>

                <CardContent className="pt-0">
                  {/* Value (for metrics) */}
                  {card.value !== undefined && (
                    <p className="text-2xl font-bold mb-1">{card.value}</p>
                  )}

                  {/* Description */}
                  {card.description && (
                    <p className="text-sm text-muted-foreground">
                      {card.description}
                    </p>
                  )}

                  {/* Progress bar */}
                  {card.type === "progress" && card.progress !== undefined && (
                    <div className="mt-3">
                      <Progress
                        value={card.progress}
                        className="h-1.5"
                        indicatorClassName="bg-violet-500"
                      />
                      <p className="text-xs text-muted-foreground mt-1 text-right">
                        {card.progress}%
                      </p>
                    </div>
                  )}

                  {/* Action button */}
                  {card.action && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-3 w-full justify-between text-xs"
                      onClick={() => {
                        if (card.action?.href) {
                          window.open(card.action.href, "_blank");
                        } else if (onAction && card.action?.onClick) {
                          onAction(card.action.onClick);
                        }
                      }}
                    >
                      {card.action.label}
                      <ArrowRight className="w-3 h-3" />
                    </Button>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Empty state */}
      {cards.length === 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-8 text-muted-foreground"
        >
          <Sparkles className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">No active status updates</p>
        </motion.div>
      )}
    </div>
  );
}
