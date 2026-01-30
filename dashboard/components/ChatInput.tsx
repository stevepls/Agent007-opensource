"use client";

import { useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send, Mic, Paperclip, Loader2 } from "lucide-react";

interface ChatInputProps {
  input: string;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  isLoading: boolean;
}

export function ChatInput({
  input,
  handleInputChange,
  handleSubmit,
  isLoading,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      handleInputChange(e);
      
      // Auto-resize
      const textarea = e.target;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    },
    [handleInputChange]
  );

  // Handle keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (input.trim() && !isLoading) {
          const form = e.currentTarget.form;
          if (form) {
            form.requestSubmit();
          }
        }
      }
    },
    [input, isLoading]
  );

  // Focus input on mount
  const focusInput = useCallback(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <form onSubmit={handleSubmit} className="p-4">
      <div className="relative flex items-end gap-2 max-w-4xl mx-auto">
        {/* Main input container */}
        <div className="flex-1 relative">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask Agent007 anything..."
            disabled={isLoading}
            className="min-h-[52px] max-h-[200px] pr-24 resize-none bg-muted/50 border-muted-foreground/20 focus:border-primary/50 rounded-xl"
            rows={1}
          />

          {/* Inline action buttons */}
          <div className="absolute right-2 bottom-2 flex items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              disabled={isLoading}
            >
              <Paperclip className="w-4 h-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              disabled={isLoading}
            >
              <Mic className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Send button */}
        <motion.div whileTap={{ scale: 0.95 }}>
          <Button
            type="submit"
            size="icon"
            className="h-[52px] w-[52px] rounded-xl bg-primary hover:bg-primary/90 shadow-lg shadow-primary/25"
            disabled={!input.trim() || isLoading}
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </Button>
        </motion.div>
      </div>

      {/* Keyboard hint */}
      <p className="text-center text-xs text-muted-foreground mt-2">
        Press <kbd className="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono">Enter</kbd> to send,{" "}
        <kbd className="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono">Shift + Enter</kbd> for new line
      </p>
    </form>
  );
}
