"""
Queue Actions API — returns context-specific recommended actions for top queue items.

Called by the dashboard on page load. Uses the queue aggregator + project registry
to compute smart actions without an LLM call (fast, deterministic).
"""

import logging
from typing import Dict, List, Any
from fastapi import APIRouter

logger = logging.getLogger("queue_actions")

router = APIRouter(prefix="/api/queue", tags=["queue-actions"])


def _compute_actions(item: Dict[str, Any]) -> List[Dict[str, str]]:
    """Compute recommended actions for a single queue item."""
    actions = []
    status = (item.get("status") or "").lower().replace(" ", "_")
    assignee = item.get("assignee")
    source = item.get("source", "")
    task_type = item.get("task_type", "")
    sla_status = item.get("priority_score", {}).get("sla_status", "no_sla")
    description = item.get("description", "") or ""

    # ── Primary action based on state ──────────────────────

    if not assignee:
        actions.append({"id": "assign", "label": "Assign", "style": "primary",
                        "reason": "No one is assigned to this item"})

    if source == "zendesk":
        actions.append({"id": "reply_customer", "label": "Reply to customer", "style": "primary",
                        "reason": "Zendesk ticket — customer may be waiting"})

    if sla_status in ("breaching", "breached"):
        actions.append({"id": "escalate", "label": "Escalate", "style": "primary",
                        "reason": f"SLA {sla_status} — needs immediate attention"})

    # ── Status-based actions ───────────────────────────────

    if status in ("open", "to_do", "to do"):
        if assignee:
            actions.append({"id": "ping_dev", "label": f"Ping {assignee.split(' ')[0]}",
                            "style": "secondary", "reason": "Task is open but not started"})
        actions.append({"id": "start", "label": "Move to In Progress", "style": "secondary",
                        "reason": "Ready to start work"})

    if status in ("in_progress", "in progress"):
        actions.append({"id": "check_status", "label": "Check status", "style": "secondary",
                        "reason": "In progress — may need a status update"})
        if assignee:
            actions.append({"id": "ping_dev", "label": f"Ask {assignee.split(' ')[0]} for update",
                            "style": "secondary", "reason": "Get progress update from developer"})

    if status in ("review", "in_review", "in review", "internal_review", "internal review"):
        actions.append({"id": "review", "label": "Review now", "style": "primary",
                        "reason": "Waiting for your review"})
        actions.append({"id": "approve", "label": "Approve", "style": "secondary",
                        "reason": "If review looks good"})
        actions.append({"id": "request_changes", "label": "Request changes", "style": "secondary",
                        "reason": "If changes are needed"})

    if status in ("pending_ai_scaffolding", "pending ai scaffolding"):
        actions.append({"id": "scaffold", "label": "Run scaffolder", "style": "secondary",
                        "reason": "Queued for AI scaffolding"})

    # ── Type-based actions ─────────────────────────────────

    if task_type in ("critical_bug", "bug"):
        if not any(a["id"] == "escalate" for a in actions):
            actions.append({"id": "investigate", "label": "Investigate", "style": "secondary",
                            "reason": f"Bug report — needs investigation"})

    if task_type == "feature_request":
        actions.append({"id": "break_down", "label": "Break into subtasks", "style": "secondary",
                        "reason": "Feature request — may need decomposition"})

    if task_type == "question":
        actions.append({"id": "answer", "label": "Draft response", "style": "primary",
                        "reason": "Question — needs a response"})

    # ── Content-based actions ──────────────────────────────

    if description and len(description) < 50:
        actions.append({"id": "add_detail", "label": "Add details", "style": "secondary",
                        "reason": "Description is very short — may need more context"})

    # ── Always available ───────────────────────────────────

    actions.append({"id": "focus", "label": "Focus", "style": "ghost",
                    "reason": "Open full detail view"})
    actions.append({"id": "snooze", "label": "Snooze", "style": "ghost",
                    "reason": "Defer for later"})

    # Deduplicate and limit
    seen = set()
    unique = []
    for a in actions:
        if a["id"] not in seen:
            seen.add(a["id"])
            unique.append(a)
    return unique[:5]  # Max 5 actions per item


@router.get("/actions")
async def get_queue_actions(limit: int = 10):
    """Get recommended actions for the top queue items."""
    try:
        from services.queue_aggregator import get_queue_aggregator
        qa = get_queue_aggregator()
        items = qa.get_prioritized(limit=limit)

        result = {}
        for item in items:
            item_dict = item.to_dict()
            result[item.id] = {
                "title": item.title,
                "actions": _compute_actions(item_dict),
            }

        return {"items": result, "count": len(result)}
    except Exception as e:
        logger.exception("Failed to compute queue actions")
        return {"items": {}, "count": 0, "error": str(e)}
