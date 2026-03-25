// ── View Protocol ─────────────────────────────────────────────
// Typed contract between Orchestrator and Dashboard.
// The Orchestrator sends ViewDirectives as SSE annotations.
// The Dashboard resolves the mode and renders accordingly.

export type ViewMode = "queue" | "focus" | "analysis" | "compose" | "review";

export interface ViewDirective {
  mode: ViewMode;
  primary_entity: TypedEntity | null;
  supporting_entities: TypedEntity[];
  actions: ActionDefinition[];
  agent_states: AgentState[];
  pending_approvals: ApprovalRequest[];
  layout: LayoutHint;
}

export type EntityType =
  | "task"
  | "ticket"
  | "pr"
  | "email_draft"
  | "time_entries"
  | "metrics"
  | "diff"
  | "table"
  | "thread";

export interface TypedEntity {
  type: EntityType;
  id: string;
  source?: {
    system: "clickup" | "zendesk" | "github" | "gmail" | "slack" | "harvest";
    url?: string;
  };
  data: Record<string, any>;
}

export interface ActionDefinition {
  id: string;
  label: string;
  style: "primary" | "secondary" | "ghost" | "destructive";
  key: string | null;
  requires_approval: boolean;
  tool: string | null;
  args: Record<string, any>;
}

export interface AgentState {
  name: string;
  status: "running" | "idle" | "error";
  last_run_age_seconds: number | null;
  last_summary: string | null;
}

export interface ApprovalRequest {
  id: string;
  type: string;
  title: string;
  description: string;
  details?: Record<string, any>;
  timeout_seconds?: number;
  tool?: string;
  args?: Record<string, any>;
  preview?: string;
}

export interface LayoutHint {
  canvas: "full" | "split" | "sidebar";
  emphasis: "entity" | "chat" | "balanced";
  feed: "visible" | "minimized" | "hidden";
}

// ── Defaults ──────────────────────────────────────────────────

export const DEFAULT_LAYOUT: LayoutHint = {
  canvas: "split",
  emphasis: "chat",
  feed: "visible",
};

export const EMPTY_DIRECTIVE: ViewDirective = {
  mode: "queue",
  primary_entity: null,
  supporting_entities: [],
  actions: [],
  agent_states: [],
  pending_approvals: [],
  layout: DEFAULT_LAYOUT,
};

// ── Mode Resolution ───────────────────────────────────────────
// Deterministic rules. The Orchestrator suggests a mode via the
// directive, but the dashboard validates it against the entity
// types present. This prevents the model from picking nonsensical
// modes.

const TYPE_TO_MODE: Partial<Record<EntityType, ViewMode>> = {
  time_entries: "analysis",
  metrics: "analysis",
  table: "analysis",
  email_draft: "compose",
  pr: "review",
  diff: "review",
};

export function resolveMode(directive: ViewDirective): ViewMode {
  const entity = directive.primary_entity;

  // Rule 1: No entity → queue mode. Always.
  if (!entity) return "queue";

  // Rule 2: Entity type forces mode (overrides suggestion).
  const forced = TYPE_TO_MODE[entity.type];
  if (forced) return forced;

  // Rule 3: Task/ticket → focus mode.
  if (entity.type === "task" || entity.type === "ticket") return "focus";

  // Rule 4: Thread → stay in queue with chat emphasis.
  if (entity.type === "thread") return "queue";

  // Rule 5: Trust the Orchestrator's suggestion.
  return directive.mode || "queue";
}

// ── Layout Resolution ─────────────────────────────────────────
// Given a resolved mode, determine the default layout if the
// Orchestrator didn't provide one.

export function resolveLayout(mode: ViewMode, hint?: LayoutHint): LayoutHint {
  if (hint && hint !== DEFAULT_LAYOUT) return hint;

  switch (mode) {
    case "queue":
      return { canvas: "split", emphasis: "chat", feed: "visible" };
    case "focus":
      return { canvas: "split", emphasis: "entity", feed: "minimized" };
    case "analysis":
      return { canvas: "full", emphasis: "entity", feed: "hidden" };
    case "compose":
      return { canvas: "full", emphasis: "entity", feed: "hidden" };
    case "review":
      return { canvas: "full", emphasis: "entity", feed: "hidden" };
    default:
      return DEFAULT_LAYOUT;
  }
}
