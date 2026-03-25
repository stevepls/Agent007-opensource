"""
Task Detail API — returns full task/ticket details with comments.

Called by the dashboard when a user focuses on a queue item.
Uses the tool registry to call clickup_get_task or zendesk_get_ticket.
Caches results for 5 minutes per task ID.
"""

import time
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter

logger = logging.getLogger("task_detail")

router = APIRouter(prefix="/api/task", tags=["task-detail"])

# Simple in-memory cache: task_id → (timestamp, data)
_cache: Dict[str, tuple] = {}
CACHE_TTL = 300  # 5 minutes


def _get_cached(task_id: str) -> Optional[Dict[str, Any]]:
    entry = _cache.get(task_id)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1]
    return None


def _set_cache(task_id: str, data: Dict[str, Any]):
    _cache[task_id] = (time.time(), data)
    # Prune old entries
    if len(_cache) > 200:
        cutoff = time.time() - CACHE_TTL
        expired = [k for k, v in _cache.items() if v[0] < cutoff]
        for k in expired:
            del _cache[k]


@router.get("/{source}/{source_id}")
async def get_task_detail(source: str, source_id: str):
    """Get full task/ticket details including description and comments."""
    cache_key = f"{source}:{source_id}"

    # Check cache
    cached = _get_cached(cache_key)
    if cached:
        return {"detail": cached, "cached": True}

    try:
        from services.tool_registry import get_registry
        registry = get_registry()

        if source == "clickup":
            result = registry.execute("clickup_get_task", {
                "task_id": source_id,
            }, skip_confirmation=True)

            task = result.get("task", result) if isinstance(result, dict) else {}

            # Extract comments if available
            comments = []
            try:
                comment_result = registry.execute("clickup_get_comments", {
                    "task_id": source_id,
                }, skip_confirmation=True)
                if isinstance(comment_result, list):
                    comments = [{"user": c.get("user", ""), "text": c.get("text", ""), "date": c.get("date", "")} for c in comment_result]
                elif isinstance(comment_result, dict):
                    raw = comment_result.get("comments", [])
                    comments = [{"user": c.get("user", ""), "text": c.get("text", ""), "date": c.get("date", "")} for c in raw]
            except Exception:
                pass

            # Extract assignees
            assignees = task.get("assignees", [])
            assignee_names = []
            for a in assignees:
                if isinstance(a, dict):
                    assignee_names.append(a.get("username") or a.get("email") or str(a.get("id", "")))
                else:
                    assignee_names.append(str(a))

            detail = {
                "source": "clickup",
                "source_id": source_id,
                "title": task.get("name", ""),
                "description": task.get("description", "") or task.get("text_content", "") or "",
                "status": task.get("status", {}).get("status", "") if isinstance(task.get("status"), dict) else str(task.get("status", "")),
                "assignees": assignee_names,
                "assignee": assignee_names[0] if assignee_names else None,
                "priority": task.get("priority", {}).get("priority", "") if isinstance(task.get("priority"), dict) else None,
                "due_date": task.get("due_date"),
                "date_created": task.get("date_created"),
                "date_updated": task.get("date_updated"),
                "url": task.get("url", f"https://app.clickup.com/t/{source_id}"),
                "tags": [t.get("name", "") if isinstance(t, dict) else str(t) for t in task.get("tags", [])],
                "custom_fields": task.get("custom_fields", {}),
                "comments": comments[-10:],  # Last 10 comments
            }

            _set_cache(cache_key, detail)
            return {"detail": detail, "cached": False}

        elif source == "zendesk":
            result = registry.execute("zendesk_get_ticket", {
                "ticket_id": source_id,
            }, skip_confirmation=True)

            ticket = result.get("ticket", result) if isinstance(result, dict) else {}

            # Get comments
            comments = []
            try:
                comment_result = registry.execute("zendesk_get_comments", {
                    "ticket_id": source_id,
                }, skip_confirmation=True)
                if isinstance(comment_result, list):
                    comments = [{"user": c.get("author", ""), "text": c.get("body", ""), "date": c.get("created_at", "")} for c in comment_result]
                elif isinstance(comment_result, dict):
                    raw = comment_result.get("comments", [])
                    comments = [{"user": c.get("author_id", ""), "text": c.get("body", ""), "date": c.get("created_at", "")} for c in raw]
            except Exception:
                pass

            detail = {
                "source": "zendesk",
                "source_id": source_id,
                "title": ticket.get("subject", ""),
                "description": ticket.get("description", "") or "",
                "status": ticket.get("status", ""),
                "assignee": str(ticket.get("assignee_id", "")) if ticket.get("assignee_id") else None,
                "assignees": [str(ticket.get("assignee_id"))] if ticket.get("assignee_id") else [],
                "priority": ticket.get("priority"),
                "due_date": ticket.get("due_at"),
                "date_created": ticket.get("created_at"),
                "date_updated": ticket.get("updated_at"),
                "url": ticket.get("url", ""),
                "tags": ticket.get("tags", []),
                "comments": comments[-10:],
            }

            _set_cache(cache_key, detail)
            return {"detail": detail, "cached": False}

        else:
            return {"error": f"Unknown source: {source}", "detail": None}

    except Exception as e:
        logger.exception(f"Failed to fetch detail for {source}/{source_id}")
        return {"error": str(e), "detail": None}
