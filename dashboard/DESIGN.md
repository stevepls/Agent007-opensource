# Agent007 Design System

> Last updated: 2026-03-25

## Product Definition

Agent007 is a **queue-first, context-orchestrated anything interface** for operational work. The user should not need to context-switch into other windows, tabs, or apps. The Orchestrator pulls work from multiple systems, manages context, and shifts the main canvas into the right mode so the user can act.

This is NOT primarily a chat app. This is NOT a static dashboard. It is a **work surface** whose layout is shaped by context, work type, urgency, and intent.

## Design Philosophy

### Core Principles

1. **Queue is root.** The queue is the home state, the default surface, and the return state. Everything else is a temporary mode that the Orchestrator enters and exits. When there's nothing focused, the queue dominates.

2. **Chat is secondary.** Chat is for steering, clarification, narration, and override. It is NOT the primary container for diffs, charts, tables, data, or approval flows. Chat lives in a narrow panel — the work surface owns the canvas.

3. **Context drives the surface.** The Orchestrator sends typed business objects (tasks, tickets, PRs, emails, metrics). The dashboard decides how to render them. The surface reshapes based on what the user is doing, not based on what tab they clicked.

4. **Color means something or it's not there.** Red = breach/danger. Amber = warning/attention. Green = healthy/success. Blue = info/interactive. Indigo = accent/focus. Everything else is neutral gray. No decorative color.

5. **Content speaks, chrome whispers.** Titles are readable (text-sm minimum). Metadata is secondary. Borders are subtle. Surfaces are solid. The data is the hero.

6. **Every card is a command center.** A card should tell you what's happening, who's on it, how urgent it is, and what to do next — all at a glance.

7. **External systems are renderable contexts, not destinations.** GitHub, Zendesk, ClickUp, Gmail, Slack, Harvest — their data renders inside this surface. The user stays here.

6. **Keyboard-first, mouse-friendly.** Power users navigate with j/k/Enter/s. Casual users click. Both paths feel natural.

---

## Color Palette

### Base (Neutral)

All backgrounds and text use pure neutral grays — zero color saturation. No blue tint, no warm tint. Clean.

| Token | Hex | HSL | Usage |
|---|---|---|---|
| `--background` | `#0a0a0a` | `0 0% 4%` | Page background |
| `--surface` | `#141414` | `0 0% 8%` | Card/panel surfaces |
| `--elevated` | `#1a1a1a` | `0 0% 10%` | Raised surfaces, hover states |
| `--border` | `#262626` | `0 0% 15%` | Default borders |
| `--border-hover` | `#333333` | `0 0% 20%` | Border on hover/focus |

### Text

| Token | Hex | Usage |
|---|---|---|
| `--foreground` | `#fafafa` | Primary text — titles, important content |
| `--text-secondary` | `#a1a1a1` | Secondary text — descriptions, metadata labels |
| `--text-tertiary` | `#636363` | Tertiary — timestamps, counts, subtle info |
| `--text-muted` | `#525252` | Muted — disabled states, placeholder text |

### Accent (Interactive)

One accent color for all interactive elements. Not two, not three. One.

| Token | Hex | Usage |
|---|---|---|
| `--primary` / `--accent` | `#6366f1` (indigo-500) | Buttons, links, focus rings, active states |
| `--accent-hover` | `#818cf8` (indigo-400) | Hover state for interactive elements |
| `--accent-muted` | `rgba(99,102,241,0.15)` | Background behind accent elements |

### Semantic (Status Only)

These colors are **never decorative**. They communicate system state.

| Token | Hex | Meaning |
|---|---|---|
| `--destructive` | `#ef4444` | SLA breach, errors, critical alerts, destructive actions |
| `--warning` | `#f59e0b` | SLA approaching, attention needed, caution |
| `--success` | `#22c55e` | Within SLA, healthy, confirmed, completed |
| `--info` | `#3b82f6` | Informational, neutral status, in-progress |

### What We Removed

- Violet/fuchsia gradients on backgrounds — decorative, not meaningful
- Glass/blur effects — added visual noise without information
- Gradient text — made the logo flashy instead of professional
- Glow effects — "techy" aesthetic that didn't serve the content
- Blue-tinted backgrounds — the old `224 71% 4%` base had a blue cast that made neutrals feel cold

---

## Typography

### Scale

Only these sizes. No exceptions.

| Size | Class | Usage |
|---|---|---|
| 14px | `text-sm` | Card titles, primary content — the minimum "readable" size |
| 13px | `text-xs` | Metadata, badges, secondary labels |
| 12px | `text-[12px]` | Timestamps, counts, tertiary info |
| 11px | `text-[11px]` | Absolute minimum — action buttons, micro-labels |

**Banned:** `text-[9px]`, `text-[10px]` — too small to read comfortably.

### Weight

| Weight | Class | Usage |
|---|---|---|
| 600 | `font-semibold` | Card titles, section headers |
| 500 | `font-medium` | Labels, badges, button text |
| 400 | `font-normal` | Body text, descriptions |

### Font

- **Sans:** Inter — clean, neutral, excellent readability at small sizes
- **Mono:** JetBrains Mono — code, IDs, scores, timestamps

---

## Card Design

Cards are the primary unit of information. Each card is a self-contained view of one work item.

### Anatomy

```
┌─[left border: 3px, semantic color]──────────────────────────┐
│                                                              │
│  [icon]  Title of the work item                         [↗]  │
│          Project Badge · Source · Status · Age · SLA         │
│          ┌─────────┐ ┌──────────┐ ┌───────────┐            │
│          │ Discuss  │ │ Update   │ │ Subtasks  │            │
│          └─────────┘ └──────────┘ └───────────┘            │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Left Border (3px)

The thick left border is the primary urgency signal. Color from SLA status:
- `emerald-400` — Within SLA
- `yellow-400` — Approaching
- `orange-400` — Breaching
- `red-500` — Breached
- `zinc-600` — No SLA / internal

### Background Tint

Subtle, almost invisible tint that reinforces urgency:
- Breached: `bg-red-950/20`
- Breaching: `bg-orange-950/15`
- Approaching: `bg-yellow-950/10`
- Within SLA: default surface
- No SLA: default surface

### Type-Specific Icons

| Source/Type | Icon | Color |
|---|---|---|
| ClickUp task | `CheckSquare` | `text-blue-400` |
| Zendesk ticket | `Headphones` | `text-emerald-400` |
| GitHub PR | `GitPullRequest` | `text-purple-400` |
| Briefing: error | `AlertTriangle` | `text-red-400` |
| Briefing: insight | `Lightbulb` | `text-amber-400` |
| Briefing: approval | `Shield` | `text-blue-400` |
| Briefing: schema | `Database` | `text-cyan-400` |
| Briefing: message | `Mail` | `text-violet-400` |

### Card States

| State | Visual Treatment |
|---|---|
| Default | Surface background, subtle border |
| Focused (keyboard) | `ring-1 ring-indigo-500/50`, elevated background |
| Active (being discussed) | Indigo left border, `indigo-500/10` background, "Discussing..." badge |
| Hover | `border-[#333]`, elevated background |
| Dismissed | Slides left, fades out, removed from list |

### Information Density

Each card shows (in priority order):
1. **Urgency** — left border color (instant visual scan)
2. **Type** — icon (ClickUp/Zendesk/PR/briefing)
3. **Title** — `text-sm font-semibold`, truncated to 60 chars
4. **Project** — colored badge (deterministic color per project name)
5. **Source** — "CU" / "ZD" / "GH" badge
6. **Status** — current workflow status
7. **Age** — how long the item has existed
8. **SLA** — time remaining or breach status
9. **Assignee** — who's on it (or "Unassigned" flag)
10. **Actions** — always visible, not hover-only

---

## Layout

### Three-Panel Adaptive

```
┌────────┬──────────────────────┬────────────┐
│ Left   │ Main Canvas          │ Right      │
│ 256px  │ flex-1               │ 320px      │
│        │                      │ collapsible│
│ Nav    │ Adapts to context:   │            │
│ Agents │ • Chat (default)     │ Priority   │
│ Config │ • Diff viewer        │ Feed       │
│        │ • Chart/dashboard    │ Agent      │
│        │ • Kanban board       │ Strip      │
│        │ • Email composer     │            │
├────────┴──────────────────────┴────────────┤
│ Input bar                                   │
└─────────────────────────────────────────────┘
```

### Surface Hierarchy

| Layer | Background | Border | Usage |
|---|---|---|---|
| Canvas | `#0a0a0a` | none | Page background, main chat area |
| Panel | `#0f0f0f` | `#262626` | Sidebars, input area |
| Card | `#141414` | `#262626` | Feed cards, status cards |
| Elevated | `#1a1a1a` | `#333333` | Hover states, focused cards, dropdowns |

---

## Agent Strip

Background agents rendered as compact indicators — like colleagues at their desks in an open office.

```
┌──────────────────────────────────────────────┐
│ 🟢 Scaffold 2m · 🟡 Tickets 15m · 🟢 SLA 2m │
│ 🟡 Stale 45m · ⚫ PRs never · 🟢 Brief 2m   │
└──────────────────────────────────────────────┘
```

### Status Dots
- `emerald-400 + pulse` — ran in last 5 minutes (actively working)
- `amber-400` — ran within the last hour (recent)
- `zinc-500` — stale or never ran (idle)
- `zinc-600` — disabled

Click any agent → brings its latest work into the main chat.

---

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `j` / `↓` | Focus next item |
| `k` / `↑` | Focus previous item |
| `Enter` | Discuss focused item in chat |
| `s` | Skip / dismiss focused item |
| `t` | Create task from focused item |
| `b` | Break into subtasks |
| `?` | Toggle shortcuts panel |

---

## Adaptive UI Protocol (Future)

The Orchestrator can send view instructions as part of responses:

```json
{
  "view": {
    "type": "split",
    "panels": [
      {"component": "chart", "data": {...}},
      {"component": "feed", "minimized": true}
    ]
  }
}
```

### Component Registry (Planned)

| Component | Library | When to use |
|---|---|---|
| `chart` | Tremor / Recharts | Time data, KPIs, trends |
| `table` | @tanstack/react-table | Structured data, exports |
| `kanban` | Custom | Task triage, status pipeline |
| `diff` | Monaco Editor | Code review, PR diffs |
| `email` | Custom | Email compose/preview |
| `feed` | QueueView | Default Priority Feed |
| `chat` | ChatMessages | Default conversation |

The dashboard maintains a component registry. The Orchestrator references components by name. New components can be added without changing the protocol.

---

## Anti-Patterns (What NOT to Do)

1. **No decorative color.** If a color doesn't communicate state, it shouldn't be there.
2. **No glass/blur.** Solid surfaces only. Blur adds render cost and visual noise.
3. **No gradient backgrounds.** Gradients on surfaces look dated. Flat is modern.
4. **No text below 11px.** If it's too small to read comfortably, it shouldn't be displayed.
5. **No hover-only content.** If information or actions matter, they're always visible.
6. **No generic cards.** A PR card should look different from a ticket card from an email card.
7. **No text walls in chat.** If the response has structured data, render it as a table/chart/board — not as markdown in a bubble.
