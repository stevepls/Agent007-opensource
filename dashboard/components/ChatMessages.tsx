"use client";

import { useEffect, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Message } from "@ai-sdk/react";
import { cn, type OrchestratorResponse } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { User, Bot, AlertCircle, Sparkles } from "lucide-react";

interface ChatMessagesProps {
  messages: Message[];
  isLoading: boolean;
  error?: Error | null;
}

interface ParsedContent {
  text: string;
  json: OrchestratorResponse | null;
  codeBlocks: Array<{ language: string; code: string }>;
}

function parseMessageContent(content: string): ParsedContent {
  const result: ParsedContent = {
    text: content,
    json: null,
    codeBlocks: [],
  };

  // Extract JSON blocks
  const jsonMatch = content.match(/```json\n?([\s\S]*?)\n?```/);
  if (jsonMatch) {
    try {
      result.json = JSON.parse(jsonMatch[1]);
      result.text = content.replace(jsonMatch[0], "").trim();
    } catch {
      // Invalid JSON, keep as text
    }
  }

  // Extract code blocks
  const codeBlockRegex = /```(\w+)?\n?([\s\S]*?)\n?```/g;
  let match;
  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match[1] !== "json") {
      result.codeBlocks.push({
        language: match[1] || "plaintext",
        code: match[2].trim(),
      });
      result.text = result.text.replace(match[0], "").trim();
    }
  }

  return result;
}

function MessageContent({ content }: { content: string }) {
  const parsed = useMemo(() => parseMessageContent(content), [content]);

  return (
    <div className="space-y-3">
      {/* Main text */}
      {parsed.text && (
        <p className="whitespace-pre-wrap leading-relaxed">{parsed.text}</p>
      )}

      {/* Inline JSON preview (if it contains priority UI) */}
      {parsed.json?.priority_ui && (
        <Card className="p-3 bg-accent/30 border-primary/20">
          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
            <Sparkles className="w-3 h-3" />
            <span>UI Update</span>
          </div>
          
          {parsed.json.priority_ui.show_progress_bar && (
            <div className="mt-2">
              <Progress
                value={parsed.json.priority_ui.progress || 0}
                className="h-1.5"
              />
              <p className="text-xs text-muted-foreground mt-1">
                {parsed.json.priority_ui.progress || 0}% complete
              </p>
            </div>
          )}
          
          {parsed.json.priority_ui.cards?.map((card) => (
            <Badge
              key={card.id}
              variant={
                card.type === "success"
                  ? "success"
                  : card.type === "warning"
                  ? "warning"
                  : card.type === "error"
                  ? "error"
                  : "info"
              }
              className="mr-1 mt-1"
            >
              {card.title}
            </Badge>
          ))}
        </Card>
      )}

      {/* Code blocks */}
      {parsed.codeBlocks.map((block, i) => (
        <pre
          key={i}
          className="p-3 rounded-lg bg-muted/50 overflow-x-auto text-sm font-mono"
        >
          <code className={`language-${block.language}`}>{block.code}</code>
        </pre>
      ))}

      {/* Approval request indicator */}
      {parsed.json?.needs_approval && (
        <Card className="p-3 bg-amber-500/10 border-amber-500/30">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-500" />
            <span className="text-sm font-medium text-amber-400">
              Approval Required: {parsed.json.needs_approval.title}
            </span>
          </div>
        </Card>
      )}
    </div>
  );
}

export function ChatMessages({
  messages,
  isLoading,
  error,
}: ChatMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto px-4 py-6 space-y-6"
    >
      {/* Welcome message if no messages */}
      {messages.length === 0 && !isLoading && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col items-center justify-center h-full text-center max-w-md mx-auto"
        >
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center mb-6">
            <Bot className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-2xl font-bold mb-2">Welcome to Agent007</h2>
          <p className="text-muted-foreground mb-6">
            Your AI-powered command center. Ask me to deploy code, check
            tickets, log time, or manage your projects.
          </p>
          <div className="flex flex-wrap gap-2 justify-center">
            {["Deploy to production", "Show open tickets", "Time logged today"].map(
              (suggestion) => (
                <button
                  key={suggestion}
                  className="px-3 py-1.5 text-sm rounded-full border border-border hover:bg-accent/50 transition-colors"
                >
                  {suggestion}
                </button>
              )
            )}
          </div>
        </motion.div>
      )}

      {/* Messages */}
      <AnimatePresence mode="popLayout">
        {messages.map((message, index) => {
          const isUser = message.role === "user";

          return (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ delay: index * 0.02 }}
              className={cn(
                "flex gap-3",
                isUser ? "justify-end" : "justify-start"
              )}
            >
              {/* Avatar */}
              {!isUser && (
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center flex-shrink-0">
                  <Bot className="w-4 h-4 text-white" />
                </div>
              )}

              {/* Message bubble */}
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-3",
                  isUser
                    ? "bg-primary text-primary-foreground rounded-br-md"
                    : "bg-card border border-border rounded-bl-md"
                )}
              >
                <MessageContent content={message.content} />
              </div>

              {/* User avatar */}
              {isUser && (
                <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                  <User className="w-4 h-4" />
                </div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Loading indicator */}
      {isLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex gap-3"
        >
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center">
            <Bot className="w-4 h-4 text-white" />
          </div>
          <div className="bg-card border border-border rounded-2xl rounded-bl-md px-4 py-3">
            <div className="typing-indicator flex gap-1">
              <span className="w-2 h-2 rounded-full bg-muted-foreground" />
              <span className="w-2 h-2 rounded-full bg-muted-foreground" />
              <span className="w-2 h-2 rounded-full bg-muted-foreground" />
            </div>
          </div>
        </motion.div>
      )}

      {/* Error message */}
      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-destructive bg-destructive/10 px-4 py-3 rounded-lg"
        >
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{error.message}</span>
        </motion.div>
      )}
    </div>
  );
}
