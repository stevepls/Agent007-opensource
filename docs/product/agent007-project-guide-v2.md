# Agent007 — Project Guide v2

> Queue-first, context-orchestrated anything interface

This guide assumes queue is the default mode and the orchestrator manages context so the user rarely has to open another tab, window, or app. The product should optimize for throughput, clarity, and low-effort decisions. Most interactions should be visual: swipe, tap, click, approve, defer, inspect, or open focus mode.

---

## 1. Product Direction

Agent007 should be treated as a **queue-first, context-orchestrated anything interface** for operational work. The interface should bring work from multiple systems into one surface and shift modes only when that reduces effort.

### What This Means

- Queue is the root state and home screen.
- Focus, review, analysis, and compose are temporary takeovers, not equal tabs.
- Chat and voice are steering tools and fallback paths, not the primary workflow.
- The orchestrator should recommend likely next actions so the user mostly chooses instead of prompting.
- The product should reduce both physical context switching and cognitive context switching.

### Decision Hierarchy

1. Visual queue actions first
2. Recommended options second
3. Voice/chat third

---

## 2. Queue-First UI Model

The main canvas should be thought of as an active work surface, not a permanent transcript area. Queue dominates by default. Other modes take over only when a task or recommendation warrants it.

### Desktop Layout

- **Left rail:** Identity, navigation, settings, compact mode indicators, optional agent presence.
- **Center canvas:** Active mode renderer. Queue by default; focus, review, analysis, or compose when promoted.
- **Right rail:** Contextual secondary content. Queue details, approvals, related context, or supporting recommendations.

### Mobile Layout

- Use one primary region at a time. Do not preserve a 3-column desktop mental model on mobile.
- Queue remains default. Focus, review, analysis, and compose become takeover screens or bottom-sheet flows.
- Primary actions must be thumb-friendly and always visible in the lower half of the screen.

### Interaction Patterns

- **Swipe right:** Accept / approve / proceed.
- **Swipe left:** Dismiss / defer / not now.
- **Swipe up or tap:** Open focus mode.
- **Long press:** Alternate actions and rationale.
- **Keyboard parity** for power users: next, previous, approve, defer, open, compose.

---

## 3. Voice Strategy

Voice should improve throughput and hands-free control, but it should not become the primary way to grind through work. The best voice implementation is a queue-aware control plane layered on top of the visual surface.

### Voice Principles

- Voice is secondary to visual action, but always available.
- Voice should be stateful. Commands like `next`, `skip`, `approve`, `draft`, and `show more` should work without re-explaining context.
- High-risk actions require confirmation. Low-risk navigation and filtering should feel immediate.
- Voice outputs should be concise, speakable summaries, not readouts of the entire UI.

### Recommended Voice Commands for V1

| Command | Action | Risk |
|---|---|---|
| next | Move to next queue item | Low |
| skip | Dismiss current item | Low |
| approve | Execute primary recommended action | Medium |
| defer | Snooze item for later | Low |
| details / show more | Open focus mode on current item | Low |
| draft | Enter compose mode for current item | Medium |
| send | Execute send action | High (confirm) |
| go back / queue | Return to queue mode | Low |

### Confirmation Tiers

- **Low-risk:** Navigate, filter, summarize, open, show, next, previous.
- **Medium-risk:** Assign, snooze, draft, route, re-rank, mark reviewed.
- **High-risk:** Send, merge, close, approve with side effects, notify client, delete.

### Voice Implementation

- Push-to-talk first. Do not start with always-listening.
- Return `voice_summary`, `voice_actions`, and `requires_confirmation` in the surface response.
- Support terse follow-up commands tied to current selection and current mode.
- Keep a visible transcript chip or toast for trust, correction, and undo.
- Let voice trigger the same action system as taps, swipes, and keyboard shortcuts.

---

## 4. Surface Orchestration Protocol

Replace the weaker idea of an "adaptive view protocol" with a stronger **surface orchestration protocol**. The orchestrator should return surface state, not just chat plus extras.

### Mode Definitions

| Mode | Purpose |
|---|---|
| **Queue** | Default root state. Ranked work, recommended actions, and fast triage. |
| **Focus** | One item dominates the canvas with essential context and next actions. |
| **Review** | Diffs, approvals, decisions, and binary judgments dominate the canvas. |
| **Analysis** | Charts, tables, trends, and comparisons replace transcript-first rendering. |
| **Compose** | Drafting and sending a reply, update, note, or structured response. |

### Decision Rules for V1

- **Stay in queue** if no item is explicitly selected and no blocking action requires takeover.
- **Enter focus** when the user selects an item or the orchestrator promotes one with high confidence.
- **Enter review** when the next action is an approval, diff inspection, or decision with side effects.
- **Enter analysis** when the requested output is primarily tabular, metric-heavy, or trend-oriented.
- **Enter compose** when the next meaningful step is drafting or sending communication.
- **Return to queue** after completion, dismissal, or when no dominant task remains.

---

## 5. Implementation Direction

Build on the existing repo direction instead of rewriting it. The next step is to formalize queue-first surface orchestration and evolve the current structured response model around it.

### What to Change First

1. Make queue the official root mode in the dashboard shell.
2. Evolve the current chat-centric response into a top-level surface response.
3. Keep existing cards, agent status, and approval models, but make them children of surface state.
4. Make the main canvas mode-driven instead of transcript-driven.
5. Keep chat mounted as a supporting layer for steering and clarification.

### What NOT to Add Yet

- Do not add CopilotKit as a foundation yet.
- Do not add React Flow before the mode system and surface contract are stable.
- Do not overbuild generative UI or chart renderers before decision rules are solid.
- Do not add more agents just to make the product feel more advanced.
- Do not regress into a permanent chat-center layout.

### Suggested Repo Location

- `docs/product/Agent007_Project_Guide_v2.docx` — canonical document
- `docs/product/agent007-project-guide-v2.md` — markdown companion for diffs

### Next 5 Coding Sessions

1. **Session 1:** Introduce SurfaceResponse, add mode at the top level, and keep legacy compatibility.
2. **Session 2:** Make queue the default root renderer and move chat into a supporting role.
3. **Session 3:** Implement focus and compose takeovers with consistent action chips and approval handling.
4. **Session 4:** Implement analysis and review renderers with deterministic activation rules.
5. **Session 5:** Add queue-aware voice controls, confirmation tiers, and speakable summaries.
