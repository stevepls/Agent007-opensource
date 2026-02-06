import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes with clsx
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Agent status update from the orchestrator
 */
export interface AgentUpdate {
  id: string;
  name: string;
  status: "idle" | "active" | "busy" | "error" | "offline";
  priority?: number;
  current_task?: string;
}

/**
 * Status card for the dashboard
 */
export interface StatusCard {
  id: string;
  type: "info" | "success" | "warning" | "error" | "progress" | "metric";
  title: string;
  value?: string;
  description?: string;
  progress?: number;
  priority?: number;
  icon?: string;
  action?: { label: string; href?: string; onClick?: string };
}

/**
 * UI update instructions from the orchestrator
 */
export interface PriorityUI {
  cards?: StatusCard[];
  show_progress_bar?: boolean;
  progress?: number;
  highlight_agent?: string;
}

/**
 * Request for human approval
 */
export interface ApprovalRequest {
  id: string;
  type: "deploy" | "database" | "message" | "payment" | "critical";
  title: string;
  description: string;
  details?: Record<string, any>;
  timeout_seconds?: number;
  tool?: string;  // Tool name to execute when approved
  args?: Record<string, any>;  // Arguments for the tool
  preview?: string;  // Preview of what will happen
}

/**
 * Full response from the orchestrator API
 */
export interface OrchestratorResponse {
  text?: string;
  priority_ui?: PriorityUI;
  agents?: AgentUpdate[];
  status_cards?: StatusCard[];
  needs_approval?: ApprovalRequest;
}

/**
 * Progress event from CrewAI real-time streaming
 */
export interface ProgressEvent {
  type: "tool_start" | "tool_done" | "thinking" | "task_start" | "task_done";
  agent?: string;
  tool?: string;
  message?: string;
  output?: string;
  timestamp?: number;
}

/**
 * Parse JSON blocks from streaming text
 */
export function parseJsonFromText(text: string): {
  cleanText: string;
  jsonData: OrchestratorResponse | null;
} {
  // Look for ```json ... ``` blocks
  const jsonMatch = text.match(/```json\s*([\s\S]*?)\s*```/);
  
  if (jsonMatch) {
    try {
      const jsonData = JSON.parse(jsonMatch[1]) as OrchestratorResponse;
      const cleanText = text.replace(/```json\s*[\s\S]*?\s*```/, "").trim();
      return { cleanText, jsonData };
    } catch {
      return { cleanText: text, jsonData: null };
    }
  }
  
  return { cleanText: text, jsonData: null };
}

/**
 * Format relative time
 */
export function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, length: number): string {
  if (text.length <= length) return text;
  return text.slice(0, length - 3) + "...";
}
