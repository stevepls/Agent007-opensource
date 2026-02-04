"use client";

import { useEffect, useState, useCallback } from "react";
import { type Message } from "@ai-sdk/react";

const STORAGE_KEY = "agent007_chat_history";
const SESSION_KEY = "agent007_session_id";
const MAX_MESSAGES = 100; // Keep last 100 messages

interface PersistedChatData {
  sessionId: string;
  messages: Message[];
  updatedAt: number;
}

/**
 * Generate a unique session ID
 */
function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
}

/**
 * Get or create a persistent session ID
 */
export function getSessionId(): string {
  if (typeof window === "undefined") return generateSessionId();
  
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = generateSessionId();
    localStorage.setItem(SESSION_KEY, sessionId);
  }
  return sessionId;
}

/**
 * Hook to persist chat messages across page refreshes
 */
export function usePersistedChat() {
  const [sessionId, setSessionId] = useState<string>("");
  const [initialMessages, setInitialMessages] = useState<Message[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);

  // Load messages from localStorage on mount
  useEffect(() => {
    if (typeof window === "undefined") return;

    const sid = getSessionId();
    setSessionId(sid);

    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const data: PersistedChatData = JSON.parse(stored);
        
        // Check if it's the same session (or within 24 hours)
        const isRecent = Date.now() - data.updatedAt < 24 * 60 * 60 * 1000;
        
        if (isRecent && data.messages.length > 0) {
          // Restore messages
          setInitialMessages(data.messages);
          console.log(`[Chat] Restored ${data.messages.length} messages from session`);
        }
      }
    } catch (e) {
      console.error("[Chat] Failed to load persisted messages:", e);
    }

    setIsLoaded(true);
  }, []);

  // Save messages to localStorage
  const saveMessages = useCallback((messages: Message[]) => {
    if (typeof window === "undefined" || !sessionId) return;

    try {
      // Keep only the last MAX_MESSAGES
      const trimmedMessages = messages.slice(-MAX_MESSAGES);
      
      const data: PersistedChatData = {
        sessionId,
        messages: trimmedMessages,
        updatedAt: Date.now(),
      };
      
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
      console.error("[Chat] Failed to save messages:", e);
    }
  }, [sessionId]);

  // Clear chat history
  const clearHistory = useCallback(() => {
    if (typeof window === "undefined") return;

    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(SESSION_KEY);
    
    // Generate new session
    const newSessionId = generateSessionId();
    localStorage.setItem(SESSION_KEY, newSessionId);
    setSessionId(newSessionId);
    setInitialMessages([]);
    
    console.log("[Chat] History cleared, new session:", newSessionId);
  }, []);

  return {
    sessionId,
    initialMessages,
    isLoaded,
    saveMessages,
    clearHistory,
  };
}

/**
 * Hook to sync with Orchestrator's memory service
 */
export function useChatMemorySync(sessionId: string) {
  // Sync session with orchestrator memory on mount
  useEffect(() => {
    if (!sessionId) return;

    // Notify orchestrator about session
    fetch("/api/agent/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId, action: "resume" }),
    }).catch(() => {
      // Orchestrator might not be available, that's fine
    });
  }, [sessionId]);
}
