// ── Surface Orchestration Protocol ────────────────────────────
//
// Typed contract between Orchestrator and Dashboard.
//
// Core principle: QUEUE IS ROOT. Chat is secondary.
// The Orchestrator manages context and mode transitions.
// The Dashboard renders the surface state, not a chat transcript.
//
// The Orchestrator sends a SurfaceResponse as an SSE annotation.
// The Dashboard resolves the mode deterministically and renders.
// ──────────────────────────────────────────────────────────────

// ── Modes ─────────────────────────────────────────────────────
// These are work states, not tabs. The Orchestrator enters and
// exits them. Queue is always the return state.

export type ViewMode = "queue" | "focus" | "review" | "analysis" | "compose";

// ── Top-Level Surface Response ────────────────────────────────

export interface SurfaceResponse {
  /** Current work mode. Queue is default/home. */
  mode: ViewMode;

  /** Layout hint — how to divide the canvas. */
  layout?: LayoutHint;

  /** The primary work item on screen. Null = queue mode. */
  primary_entity: TypedEntity | null;

  /** Context around the primary entity (related tasks, thread, etc.) */
  supporting_entities: TypedEntity[];

  /** Queue state — always available, visibility controlled by mode. */
  queue?: QueueState;

  /** Surface cards — status indicators, metrics, alerts. */
  cards: SurfaceCard[];

  /** What the user can do next. Rendered as action bar. */
  actions: ActionDefinition[];

  /** Pending approval requests that block progress. */
  approvals: ApprovalRequest[];

  /** Background agent states. Feeds the Agent Strip. */
  agent_states: AgentState[];

  /** Chat context — secondary, for steering/narration. */
  chat?: ChatHint;

  /** Rendering hint for the primary entity. */
  view_hints?: ViewHint;

  /** Mobile-specific hints. */
  mobile_hints?: MobileHint;

  /** Voice interface hints. */
  voice_hints?: VoiceHint;
}

// ── Entity Types ──────────────────────────────────────────────

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
  /** Discriminator — dashboard picks the renderer from this. */
  type: EntityType;

  /** Stable ID for deduplication and state tracking. */
  id: string;

  /** Source system for linking out. */
  source?: {
    system: "clickup" | "zendesk" | "github" | "gmail" | "slack" | "harvest";
    url?: string;
  };

  /** The actual payload. Shape depends on type. */
  data: Record<string, any>;
}

// ── Actions ───────────────────────────────────────────────────

export interface ActionDefinition {
  /** Unique key. */
  id: string;

  /** Display label. */
  label: string;

  /** Visual weight. */
  style: "primary" | "secondary" | "ghost" | "destructive";

  /** Keyboard shortcut (single key). Null = no shortcut. */
  key: string | null;

  /** If true, action shows confirmation before executing. */
  requires_approval: boolean;

  /** Tool to call when executed. Null = send label as chat message. */
  tool: string | null;
  args: Record<string, any>;
}

// ── Supporting Types ──────────────────────────────────────────

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

export interface SurfaceCard {
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

export interface QueueState {
  total: number;
  breaching: number;
  by_project: Record<string, number>;
}

export interface ChatHint {
  /** Short summary of what the Orchestrator just did. */
  summary?: string;

  /** Placeholder text for the input field. */
  input_placeholder?: string;

  /** Whether chat should be visible in this mode. */
  visible: boolean;
}

export interface ViewHint {
  /** Suggested renderer component for the primary entity. */
  component?: "feed" | "diff" | "chart" | "table" | "email" | "form" | "detail";

  /** Whether this entity should be the visual emphasis or supporting. */
  emphasis?: "primary" | "supporting";
}

export interface MobileHint {
  /** What to show as the primary action button on mobile. */
  primary_action?: string;

  /** What the bottom sheet should contain. */
  bottom_sheet?: "queue" | "details" | "actions";
}

export interface VoiceHint {
  /** Spoken summary of the current surface state. */
  summary?: string;

  /** Available voice commands. */
  available_commands?: string[];

  /** Whether the next action requires verbal confirmation. */
  requires_confirmation?: boolean;
}

// ── Layout ────────────────────────────────────────────────────

export interface LayoutHint {
  /** How to arrange the canvas. */
  canvas: "queue-dominant" | "split" | "canvas-dominant" | "compose-dominant";

  /** What takes visual emphasis. */
  emphasis: "queue" | "entity" | "chat" | "balanced";

  /** Queue/feed panel visibility. */
  feed: "visible" | "minimized" | "hidden";
}

// ── Defaults ──────────────────────────────────────────────────

export const DEFAULT_LAYOUT: LayoutHint = {
  canvas: "queue-dominant",
  emphasis: "queue",
  feed: "visible",
};

export const EMPTY_SURFACE: SurfaceResponse = {
  mode: "queue",
  primary_entity: null,
  supporting_entities: [],
  cards: [],
  actions: [],
  approvals: [],
  agent_states: [],
  chat: { visible: true, input_placeholder: "Ask anything..." },
  layout: DEFAULT_LAYOUT,
};

// ── Backward Compatibility ────────────────────────────────────
// The old ViewDirective type was the V1 contract. SurfaceResponse
// is the V2. Keep the alias so existing page.tsx imports work.

export type ViewDirective = SurfaceResponse;
export const EMPTY_DIRECTIVE = EMPTY_SURFACE;

// ── Mode Resolution ───────────────────────────────────────────
// Deterministic rules. The Orchestrator suggests a mode, but the
// dashboard validates it against the entity types present.
// The model CANNOT arbitrarily pick modes.

const TYPE_TO_MODE: Partial<Record<EntityType, ViewMode>> = {
  time_entries: "analysis",
  metrics: "analysis",
  table: "analysis",
  email_draft: "compose",
  pr: "review",
  diff: "review",
};

export function resolveMode(surface: SurfaceResponse): ViewMode {
  const entity = surface.primary_entity;

  // Rule 1: No entity → queue. Always. Queue is root.
  if (!entity) return "queue";

  // Rule 2: Pending approvals → review mode (decisions block progress).
  if (surface.approvals && surface.approvals.length > 0) return "review";

  // Rule 3: Entity type forces mode (overrides suggestion).
  const forced = TYPE_TO_MODE[entity.type];
  if (forced) return forced;

  // Rule 4: Task/ticket → focus mode.
  if (entity.type === "task" || entity.type === "ticket") return "focus";

  // Rule 5: Thread → queue with chat visible.
  if (entity.type === "thread") return "queue";

  // Rule 6: Trust the Orchestrator's suggestion.
  return surface.mode || "queue";
}

// ── Layout Resolution ─────────────────────────────────────────
// Given a resolved mode, determine the layout.
// Queue-first: queue is always the dominant default.

export function resolveLayout(mode: ViewMode, hint?: LayoutHint): LayoutHint {
  // If the Orchestrator provided a non-default hint, use it.
  if (hint && hint !== DEFAULT_LAYOUT) return hint;

  switch (mode) {
    case "queue":
      // Queue dominates. Chat is available but secondary.
      return { canvas: "queue-dominant", emphasis: "queue", feed: "visible" };
    case "focus":
      // Entity takes the canvas. Queue minimizes to "Next up" strip.
      return { canvas: "split", emphasis: "entity", feed: "minimized" };
    case "analysis":
      // Data takes the full canvas. Queue hidden.
      return { canvas: "canvas-dominant", emphasis: "entity", feed: "hidden" };
    case "compose":
      // Editor takes the canvas. Queue hidden.
      return { canvas: "compose-dominant", emphasis: "entity", feed: "hidden" };
    case "review":
      // Decision surface. Queue hidden.
      return { canvas: "canvas-dominant", emphasis: "entity", feed: "hidden" };
    default:
      return DEFAULT_LAYOUT;
  }
}

// ── Return-to-Queue Rules ─────────────────────────────────────
// The dashboard should return to queue mode when:

export function shouldReturnToQueue(surface: SurfaceResponse): boolean {
  // No primary entity and no pending approvals → queue
  if (!surface.primary_entity && (!surface.approvals || surface.approvals.length === 0)) {
    return true;
  }
  return false;
}
