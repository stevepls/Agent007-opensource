"""
Unified Work Queue Aggregator

Pulls work items from ClickUp and Zendesk via the tool registry, applies
SLA priority scoring from the SLA module, resolves project context from the
project registry, and returns a single sorted list.

This is a *read-only view* — it does not create or mutate data in any
external system.

Usage:
    from services.queue_aggregator import get_queue_aggregator

    queue = get_queue_aggregator()
    top_items = queue.get_prioritized(limit=20)
    breaching = queue.get_breaching()
    summary = queue.get_summary()
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from services.sla import (
    SLAStatus,
    SLATier,
    TaskType,
    PriorityScore,
    calculate_priority_score,
    classify_task_type,
    get_sla_status,
)
from services.project_context.project_registry import (
    ProjectConfig,
    get_project_registry,
)
from services.tool_registry import get_registry as get_tool_registry

logger = logging.getLogger("queue_aggregator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLICKUP_STATUS_MAP: Dict[str, str] = {
    "to do": "open",
    "open": "open",
    "in progress": "in_progress",
    "in review": "review",
    "review": "review",
    "complete": "done",
    "closed": "done",
    "done": "done",
}

ZENDESK_STATUS_MAP: Dict[str, str] = {
    "new": "open",
    "open": "open",
    "pending": "pending",
    "hold": "pending",
    "solved": "done",
    "closed": "done",
}

# Similarity threshold for cross-system deduplication
_DEDUP_SIMILARITY_THRESHOLD = 0.85

# Default cache TTL in seconds
_DEFAULT_CACHE_TTL = 120


# ---------------------------------------------------------------------------
# WorkItem
# ---------------------------------------------------------------------------

@dataclass
class WorkItem:
    """A normalised work item from any external system."""

    id: str                                # "clickup-{id}" or "zendesk-{id}"
    source: str                            # "clickup" or "zendesk"
    source_id: str                         # Original ID in the source system
    source_url: Optional[str]              # Deep link into the source system
    project_name: str                      # Resolved from project registry
    title: str
    status: str                            # Normalised status
    assignee: Optional[str]
    priority_score: PriorityScore          # Composite score from SLA module
    task_type: TaskType                    # Classified task type
    sla_tier: SLATier                      # From project registry
    created_at: datetime
    updated_at: datetime
    due_date: Optional[datetime]
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for JSON responses."""
        return {
            "id": self.id,
            "source": self.source,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "project_name": self.project_name,
            "title": self.title,
            "status": self.status,
            "assignee": self.assignee,
            "priority_score": {
                "score": self.priority_score.score,
                "sla_status": self.priority_score.sla_status.value,
                "sla_deadline": (
                    self.priority_score.sla_deadline.isoformat()
                    if self.priority_score.sla_deadline
                    else None
                ),
                "time_remaining": (
                    str(self.priority_score.time_remaining)
                    if self.priority_score.time_remaining is not None
                    else None
                ),
                "components": self.priority_score.components,
            },
            "task_type": self.task_type.value,
            "sla_tier": self.sla_tier.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_clickup_ts(value: Any) -> Optional[datetime]:
    """Parse a ClickUp millisecond-epoch timestamp into a tz-aware datetime."""
    if value is None:
        return None
    try:
        ts_ms = int(value)
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 date string (Zendesk format) into a tz-aware datetime."""
    if value is None:
        return None
    try:
        s = str(value)
        # Python 3.10 doesn't handle trailing 'Z' in fromisoformat
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _resolve_sla_tier(tier_str: str) -> SLATier:
    """Convert a string SLA tier from ProjectConfig to the SLATier enum."""
    mapping = {
        "gold": SLATier.GOLD,
        "silver": SLATier.SILVER,
        "bronze": SLATier.BRONZE,
        "internal": SLATier.INTERNAL,
    }
    return mapping.get(tier_str.lower().strip(), SLATier.BRONZE)


def _normalise_clickup_status(raw: str) -> str:
    return CLICKUP_STATUS_MAP.get(raw.lower().strip(), raw.lower().strip())


def _normalise_zendesk_status(raw: str) -> str:
    return ZENDESK_STATUS_MAP.get(raw.lower().strip(), raw.lower().strip())


def _titles_similar(a: str, b: str) -> bool:
    """Return True when two titles are similar enough to be duplicates."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= _DEDUP_SIMILARITY_THRESHOLD


# ---------------------------------------------------------------------------
# QueueAggregator
# ---------------------------------------------------------------------------

class QueueAggregator:
    """Aggregates work items from ClickUp and Zendesk into a unified prioritised queue."""

    def __init__(self) -> None:
        self._cache: List[WorkItem] = []
        self._last_refresh: Optional[datetime] = None
        self._cache_ttl: int = _DEFAULT_CACHE_TTL  # seconds

    # -- data fetching ------------------------------------------------------

    def refresh(self) -> None:
        """Pull fresh data from all sources and rebuild the cache."""
        items: List[WorkItem] = []

        try:
            project_registry = get_project_registry()
        except Exception:
            logger.warning("Project registry unavailable — returning empty queue")
            self._cache = []
            self._last_refresh = datetime.now(timezone.utc)
            return

        try:
            tool_registry = get_tool_registry()
        except Exception:
            logger.warning("Tool registry unavailable — returning empty queue")
            self._cache = []
            self._last_refresh = datetime.now(timezone.utc)
            return

        # -- ClickUp -------------------------------------------------------
        active_projects = project_registry.get_all_projects(active_only=True)

        for project in active_projects:
            if not project.clickup_list_id:
                continue
            try:
                result = tool_registry.execute(
                    "clickup_list_tasks",
                    {"list_id": project.clickup_list_id, "include_closed": False},
                    skip_confirmation=True,
                )
                if isinstance(result, dict) and "error" in result:
                    logger.warning(
                        "ClickUp error for project %s (list %s): %s",
                        project.name,
                        project.clickup_list_id,
                        result["error"],
                    )
                    continue

                tasks = []
                if isinstance(result, dict):
                    tasks = result.get("tasks", [])
                elif isinstance(result, list):
                    tasks = result

                for task in tasks:
                    item = self._clickup_task_to_work_item(task, project)
                    if item is not None:
                        items.append(item)
            except Exception:
                logger.exception(
                    "Failed to fetch ClickUp tasks for project %s", project.name
                )

        # -- Zendesk --------------------------------------------------------
        try:
            result = tool_registry.execute(
                "zendesk_list_tickets",
                {"status": "open", "limit": 50},
                skip_confirmation=True,
            )
            if isinstance(result, dict) and "error" in result:
                logger.warning("Zendesk error: %s", result["error"])
            else:
                tickets = []
                if isinstance(result, dict):
                    tickets = result.get("tickets", [])
                elif isinstance(result, list):
                    tickets = result

                for ticket in tickets:
                    item = self._zendesk_ticket_to_work_item(ticket, project_registry)
                    if item is not None:
                        items.append(item)
        except Exception:
            logger.exception("Failed to fetch Zendesk tickets")

        # -- Deduplicate & sort ---------------------------------------------
        items = self._deduplicate(items)
        items.sort(key=lambda w: w.priority_score.score, reverse=True)

        self._cache = items
        self._last_refresh = datetime.now(timezone.utc)

    def force_refresh(self) -> None:
        """Force an immediate refresh, ignoring cache TTL."""
        self.refresh()

    # -- conversion helpers -------------------------------------------------

    def _clickup_task_to_work_item(
        self, task: Dict[str, Any], project: ProjectConfig
    ) -> Optional[WorkItem]:
        """Convert a raw ClickUp task dict into a WorkItem."""
        try:
            task_id = str(task.get("id", ""))
            title = task.get("name", "Untitled")

            # Dates
            created_at = _parse_clickup_ts(task.get("date_created"))
            updated_at = _parse_clickup_ts(task.get("date_updated"))
            due_date = _parse_clickup_ts(task.get("due_date"))

            if created_at is None:
                created_at = datetime.now(timezone.utc)
            if updated_at is None:
                updated_at = created_at

            # Status
            raw_status = task.get("status", {})
            if isinstance(raw_status, dict):
                status_str = raw_status.get("status", "open")
            else:
                status_str = str(raw_status)
            status = _normalise_clickup_status(status_str)

            # Assignee
            assignees = task.get("assignees") or []
            assignee = None
            if assignees:
                first = assignees[0]
                if isinstance(first, dict):
                    assignee = first.get("username") or first.get("email")
                else:
                    assignee = str(first)

            # Tags
            raw_tags = task.get("tags") or []
            tags: List[str] = []
            for t in raw_tags:
                if isinstance(t, dict):
                    tags.append(t.get("name", ""))
                else:
                    tags.append(str(t))

            # SLA
            sla_tier = _resolve_sla_tier(project.sla_tier)
            task_type = classify_task_type(title, tags=tags)
            priority = calculate_priority_score(
                sla_tier=sla_tier,
                task_type=task_type,
                created_at=created_at,
                due_date=due_date,
            )

            return WorkItem(
                id=f"clickup-{task_id}",
                source="clickup",
                source_id=task_id,
                source_url=f"https://app.clickup.com/t/{task_id}",
                project_name=project.name,
                title=title,
                status=status,
                assignee=assignee,
                priority_score=priority,
                task_type=task_type,
                sla_tier=sla_tier,
                created_at=created_at,
                updated_at=updated_at,
                due_date=due_date,
                tags=tags,
            )
        except Exception:
            logger.exception("Error converting ClickUp task %s", task.get("id"))
            return None

    def _zendesk_ticket_to_work_item(
        self, ticket: Dict[str, Any], project_registry: Any
    ) -> Optional[WorkItem]:
        """Convert a raw Zendesk ticket dict into a WorkItem."""
        try:
            ticket_id = str(ticket.get("id", ""))
            title = ticket.get("subject", "Untitled")

            # Dates
            created_at = _parse_iso_dt(ticket.get("created_at"))
            updated_at = _parse_iso_dt(ticket.get("updated_at"))
            due_date = _parse_iso_dt(ticket.get("due_at"))

            if created_at is None:
                created_at = datetime.now(timezone.utc)
            if updated_at is None:
                updated_at = created_at

            # Status
            status = _normalise_zendesk_status(ticket.get("status", "open"))

            # Assignee
            assignee_id = ticket.get("assignee_id")
            assignee = str(assignee_id) if assignee_id else None

            # Tags
            tags: List[str] = list(ticket.get("tags") or [])

            # Resolve project from tags
            project: Optional[ProjectConfig] = None
            for tag in tags:
                project = project_registry.get_by_zendesk_tag(tag)
                if project is not None:
                    break

            project_name = project.name if project else "Unknown"
            sla_tier_str = project.sla_tier if project else "bronze"
            sla_tier = _resolve_sla_tier(sla_tier_str)

            task_type = classify_task_type(title, tags=tags)
            priority = calculate_priority_score(
                sla_tier=sla_tier,
                task_type=task_type,
                created_at=created_at,
                due_date=due_date,
            )

            subdomain = os.getenv("ZENDESK_SUBDOMAIN", "collegewise")

            return WorkItem(
                id=f"zendesk-{ticket_id}",
                source="zendesk",
                source_id=ticket_id,
                source_url=f"https://{subdomain}.zendesk.com/agent/tickets/{ticket_id}",
                project_name=project_name,
                title=title,
                status=status,
                assignee=assignee,
                priority_score=priority,
                task_type=task_type,
                sla_tier=sla_tier,
                created_at=created_at,
                updated_at=updated_at,
                due_date=due_date,
                tags=tags,
            )
        except Exception:
            logger.exception("Error converting Zendesk ticket %s", ticket.get("id"))
            return None

    # -- deduplication ------------------------------------------------------

    def _deduplicate(self, items: List[WorkItem]) -> List[WorkItem]:
        """Remove cross-system duplicates.

        If a ClickUp task and Zendesk ticket represent the same work
        (matched by title similarity or cross-reference tags), keep the
        one updated most recently and merge tags from both.
        """
        clickup_items = [i for i in items if i.source == "clickup"]
        zendesk_items = [i for i in items if i.source == "zendesk"]

        merged_zendesk_ids: set = set()

        for cu_item in clickup_items:
            for zd_item in zendesk_items:
                if zd_item.id in merged_zendesk_ids:
                    continue

                is_dup = False
                # Check title similarity
                if _titles_similar(cu_item.title, zd_item.title):
                    is_dup = True
                # Check cross-reference in tags (e.g., "clickup-123" tag on a Zendesk ticket)
                elif any(cu_item.source_id in t for t in zd_item.tags):
                    is_dup = True
                elif any(zd_item.source_id in t for t in cu_item.tags):
                    is_dup = True

                if is_dup:
                    merged_zendesk_ids.add(zd_item.id)
                    # Merge tags from the duplicate into the surviving item
                    keeper = cu_item if cu_item.updated_at >= zd_item.updated_at else zd_item
                    donor = zd_item if keeper is cu_item else cu_item
                    merged_tags = list(dict.fromkeys(keeper.tags + donor.tags))
                    keeper.tags = merged_tags
                    break

        # Return clickup items + non-merged zendesk items
        result = list(clickup_items)
        result.extend(i for i in zendesk_items if i.id not in merged_zendesk_ids)
        return result

    # -- cache management ---------------------------------------------------

    def _is_cache_fresh(self) -> bool:
        if self._last_refresh is None:
            return False
        age = (datetime.now(timezone.utc) - self._last_refresh).total_seconds()
        return age < self._cache_ttl

    def _ensure_fresh(self) -> None:
        """Refresh data if the cache is stale."""
        if not self._is_cache_fresh():
            self.refresh()

    # -- public getters -----------------------------------------------------

    def get_prioritized(self, limit: int = 50) -> List[WorkItem]:
        """All items sorted by priority score (highest first). Uses cache if fresh."""
        self._ensure_fresh()
        return self._cache[:limit]

    def get_by_project(self, project_name: str) -> List[WorkItem]:
        """Items for a specific project, sorted by priority."""
        self._ensure_fresh()
        name_lower = project_name.lower().strip()
        return [
            item for item in self._cache
            if item.project_name.lower() == name_lower
        ]

    def get_breaching(self) -> List[WorkItem]:
        """Items that are breaching or have breached SLA."""
        self._ensure_fresh()
        return [
            item for item in self._cache
            if item.priority_score.sla_status in (SLAStatus.BREACHING, SLAStatus.BREACHED)
        ]

    def get_next(self) -> Optional[WorkItem]:
        """Single highest-priority actionable item.

        Skips items with 'done' status since those are not actionable.
        """
        self._ensure_fresh()
        for item in self._cache:
            if item.status != "done":
                return item
        return None

    def get_summary(self) -> Dict[str, Any]:
        """Summary stats: total, by_project, by_sla_status, by_source."""
        self._ensure_fresh()

        by_project: Dict[str, int] = {}
        by_sla_status: Dict[str, int] = {}
        by_source: Dict[str, int] = {}

        for item in self._cache:
            by_project[item.project_name] = by_project.get(item.project_name, 0) + 1
            status_key = item.priority_score.sla_status.value
            by_sla_status[status_key] = by_sla_status.get(status_key, 0) + 1
            by_source[item.source] = by_source.get(item.source, 0) + 1

        breaching_count = sum(
            1 for item in self._cache
            if item.priority_score.sla_status in (SLAStatus.BREACHING, SLAStatus.BREACHED)
        )

        return {
            "total": len(self._cache),
            "breaching": breaching_count,
            "by_project": by_project,
            "by_sla_status": by_sla_status,
            "by_source": by_source,
            "last_refresh": (
                self._last_refresh.isoformat() if self._last_refresh else None
            ),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_aggregator: Optional[QueueAggregator] = None


def get_queue_aggregator() -> QueueAggregator:
    """Get the global QueueAggregator singleton."""
    global _aggregator
    if _aggregator is None:
        _aggregator = QueueAggregator()
    return _aggregator
