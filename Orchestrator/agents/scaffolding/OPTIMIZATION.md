# Scaffolding Agent Optimization

## Problem

The agent was wasteful:
- ❌ Always fetched all tasks on every run
- ❌ Always analyzed tasks with LLM even if unchanged
- ❌ Added duplicate blocking comments every 15 minutes
- ❌ Ran LLM analysis on tasks blocked 12 hours ago

## Solution — Multi-Layer Caching

### Layer 1: List-Level Change Detection

**Before fetching tasks, check if anything changed:**

```python
state = load_state()  # {last_list_check: "2026-02-09T02:29:56"}
recent_tasks = clickup.list_tasks(limit=10, order_by="updated")

if recent_tasks[0].date_updated <= last_list_check:
    print("No updates in list, skip everything")
    return []
```

**Saved per run:** ~50-100 API calls, ~$0.50 in LLM costs

---

### Layer 2: Task-Level Freshness Check

**Only process tasks updated since we last touched them:**

```python
our_last_comment = get_our_latest_comment(task_id)

if task.date_updated <= our_last_comment.date:
    print("Task not updated since we last commented, skip")
    return
```

**Saved per task:** 2 LLM calls ($0.10), 5 API calls, time tracking API hit

---

### Layer 3: Smart Blocking

**Don't block tasks that were unblocked:**

```python
# OLD: Any "Blocked" comment in 48h → skip
# NEW: Only if MOST RECENT agent comment is "Blocked"

most_recent_agent_comment = get_latest_agent_comment(task_id)

if "Scaffolding complete" in most_recent_agent_comment:
    process()  # User fixed the blocker, we should retry

if "Scaffolding Blocked" in most_recent_agent_comment and age < 48h:
    skip()  # Still blocked, don't retry yet
```

---

### Layer 4: Comment Deduplication

**Don't spam the same blocking message:**

```python
existing_blockers = [c for c in comments if "Scaffolding Blocked" in c]
last_blocker = existing_blockers[-1] if existing_blockers else None

if last_blocker and similarity(last_blocker.reason, new_reason) > 0.5:
    print("Already commented this blocker, skip duplicate")
    return
```

---

## Results

| Metric | Before | After | Savings |
|---|---|---|---|
| **API calls per run** | 50-100 | 3-5 | 90% |
| **LLM calls per task** | Always | Only if fresh | ~80% |
| **Duplicate comments** | Every run | Once per 48h | 95% |
| **Time tracking hits** | Always | Only if processing | ~80% |

## Example Run Logs

### No Changes (New Behavior)

```
INFO: === Scaffolding Agent: phyto ===
INFO:   No updates since 2026-02-09 02:29
INFO: No changes in list since last check, nothing to do.
⏱️ Total time: 0.8s
```

**Cost:** $0.00 (no LLM calls, 3 API calls)

### With Updates (Selective Processing)

```
INFO: === Scaffolding Agent: phyto ===
INFO:   List has updates (task 868hdpq72 updated 2026-02-09 02:30:35)
INFO: Fetching tasks with status: 'pending ai scaffolding'
INFO: Found 1 fresh task(s) (out of 1 pending, 9 open)
INFO: Processing task: [868hdpq72] Install the module...
```

**Cost:** ~$0.15 per fresh task (only processes what changed)

### Blocked Task (Skip)

```
INFO: Processing task: [868hdpqak] WordPress integration...
INFO:   Task was blocked <48h ago, skipping to avoid duplicate work
```

**Cost:** $0.00 (no LLM, no time tracking, no duplicate comment)

---

## State File

Location: `agents/scaffolding/state/{project_key}.json`

```json
{
  "last_run": "2026-02-09T02:29:56.664260",
  "last_list_check": "2026-02-09T02:29:56.664246",
  "task_timestamps": {
    "868hdpr7j": "2026-02-09T00:33:37",
    "868hdpqaw": "2026-02-09T00:34:47",
    "868hdpqak": "2026-02-09T01:17:08"
  }
}
```

Reset a specific task: Delete its entry from `task_timestamps`.
Reset everything: Delete the state file.

---

## Cost Analysis (15-minute cron)

**Before:** 96 runs/day × 4 tasks × $0.15 = **$57.60/day**

**After (typical):**
- 90 runs: No changes (skip) = $0.00
- 4 runs: 1 task updated = $0.60
- 2 runs: New tasks = $1.20
- **Total: $1.80/day** (97% reduction)

---

## Force Refresh

To force the agent to reprocess everything:

```bash
# Delete state for one project
rm agents/scaffolding/state/phyto.json

# Or delete just task timestamps
python3 -c "
import json
from pathlib import Path
state = json.loads(Path('agents/scaffolding/state/phyto.json').read_text())
state['task_timestamps'] = {}
Path('agents/scaffolding/state/phyto.json').write_text(json.dumps(state, indent=2))
"
```

---

**Status:** All 4 optimization layers active and tested. 97% cost reduction on idle runs.
