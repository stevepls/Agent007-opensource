"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { ApprovalRequest } from "@/lib/utils";
import {
  AlertTriangle,
  Rocket,
  Database,
  Mail,
  DollarSign,
  Shield,
  Clock,
} from "lucide-react";

interface DynamicApproveDialogProps {
  request: ApprovalRequest | null;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

const TYPE_CONFIG: Record<
  ApprovalRequest["type"],
  { icon: React.ReactNode; color: string; label: string }
> = {
  deploy: {
    icon: <Rocket className="w-5 h-5" />,
    color: "text-violet-400",
    label: "Deployment",
  },
  database: {
    icon: <Database className="w-5 h-5" />,
    color: "text-cyan-400",
    label: "Database",
  },
  message: {
    icon: <Mail className="w-5 h-5" />,
    color: "text-blue-400",
    label: "Message",
  },
  payment: {
    icon: <DollarSign className="w-5 h-5" />,
    color: "text-emerald-400",
    label: "Payment",
  },
  critical: {
    icon: <Shield className="w-5 h-5" />,
    color: "text-red-400",
    label: "Critical",
  },
};

export function DynamicApproveDialog({
  request,
  onApprove,
  onReject,
}: DynamicApproveDialogProps) {
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  // Handle dialog state
  useEffect(() => {
    if (request) {
      setIsOpen(true);
      if (request.timeout_seconds) {
        setTimeRemaining(request.timeout_seconds);
      }
    } else {
      setIsOpen(false);
      setTimeRemaining(null);
    }
  }, [request]);

  // Countdown timer
  useEffect(() => {
    if (timeRemaining === null || timeRemaining <= 0) return;

    const timer = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev === null || prev <= 1) {
          // Auto-reject on timeout
          if (request) {
            onReject(request.id);
          }
          return null;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [timeRemaining, request, onReject]);

  if (!request) return null;

  const config = TYPE_CONFIG[request.type];
  const progressValue = request.timeout_seconds
    ? ((timeRemaining || 0) / request.timeout_seconds) * 100
    : 100;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onReject(request.id)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2">
            <div
              className={`w-10 h-10 rounded-xl bg-muted flex items-center justify-center ${config.color}`}
            >
              {config.icon}
            </div>
            <div>
              <Badge
                variant={request.type === "critical" ? "error" : "warning"}
                className="mb-1"
              >
                {config.label} Approval
              </Badge>
              <DialogTitle className="text-lg">{request.title}</DialogTitle>
            </div>
          </div>
          <DialogDescription className="text-left">
            {request.description}
          </DialogDescription>
          
          {/* Show preview for actions like Slack messages */}
          {request.preview && (
            <div className="mt-4 p-3 rounded-lg bg-muted/50 border border-border">
              <p className="text-xs text-muted-foreground mb-2 font-semibold">Preview:</p>
              <pre className="text-sm whitespace-pre-wrap font-mono text-foreground">
                {request.preview}
              </pre>
            </div>
          )}
        </DialogHeader>

        {/* Details section */}
        {request.details && Object.keys(request.details).length > 0 && (
          <div className="my-4 p-3 rounded-lg bg-muted/50 space-y-2">
            {Object.entries(request.details).map(([key, value]) => (
              <div key={key} className="flex justify-between text-sm">
                <span className="text-muted-foreground capitalize">
                  {key.replace(/_/g, " ")}
                </span>
                <span className="font-medium">{String(value)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Timeout indicator */}
        {timeRemaining !== null && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2 text-muted-foreground">
                <Clock className="w-4 h-4" />
                <span>Time remaining</span>
              </div>
              <span
                className={`font-mono font-medium ${
                  timeRemaining <= 10 ? "text-red-400" : "text-amber-400"
                }`}
              >
                {Math.floor(timeRemaining / 60)}:
                {(timeRemaining % 60).toString().padStart(2, "0")}
              </span>
            </div>
            <Progress
              value={progressValue}
              className="h-1"
              indicatorClassName={
                timeRemaining <= 10 ? "bg-red-500" : "bg-amber-500"
              }
            />
          </div>
        )}

        {/* Warning for critical actions */}
        {request.type === "critical" && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20"
          >
            <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
            <p className="text-sm text-red-300">
              This is a critical action that may have significant consequences.
              Please review carefully before approving.
            </p>
          </motion.div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onReject(request.id)}
            className="flex-1 sm:flex-none"
          >
            Reject
          </Button>
          <Button
            variant={request.type === "critical" ? "destructive" : "default"}
            onClick={() => onApprove(request.id)}
            className="flex-1 sm:flex-none"
          >
            Approve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
