"""
Queue Manager — Core Manager

Owns:
- Ingesting normalized items from sources (via queue_aggregator)
- Computing priority scores
- Maintaining the ordered queue
- Tracking acknowledgment state
- Emitting promotion events when thresholds are crossed

Does NOT own:
- Long-form reasoning
- Drafting
- Mode-specific UI decisions
- Rich summaries

That stays with the Orchestrator.
"""

import logging
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Callable

from queue.models import QueueItem, Severity, SourceType, AckState, NotificationState
from queue.scoring import compute_score, compute_severity
from queue.policies import (
    PriorityPolicy,
    PromotionPolicy,
    is_working_hours,
    is_quiet_hours,
)
from queue.snapshots import QueueSnapshot
from queue.promotions import PromotionEvent, create_promotion_event

logger = logging.getLogger("queue_manager")

# State persistence
DATA_DIR = Path(__file__).parent.parent / "data" / "queue"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
SNAPSHOT_FILE = DATA_DIR / "latest_snapshot.json"


class QueueManager:
    """
    Central queue manager. Rule-based, deterministic, fast.

    Usage:
        qm = get_queue_manager()
        qm.refresh()                    # Pull fresh data from sources
        snapshot = qm.get_snapshot()     # Get current ordered queue
        events = qm.get_pending_promotions()  # Check for promotions
        qm.acknowledge(item_id, "queue_open")  # Mark item as seen
    """

    _instance: Optional["QueueManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._items: Dict[str, QueueItem] = {}      # id → QueueItem
        self._previous_scores: Dict[str, float] = {} # id → last score
        self._snapshot: Optional[QueueSnapshot] = None
        self._snapshot_version: int = 0
        self._pending_promotions: List[PromotionEvent] = []
        self._listeners: List[Callable] = []

        # Load persisted state
        self._load_state()

    # ── Ingestion ─────────────────────────────────────────────

    def refresh(self) -> QueueSnapshot:
        """
        Pull fresh data from the queue_aggregator, score everything,
        and build a new snapshot.
        """
        start = time.time()

        # Get raw items from the existing queue_aggregator
        try:
            from services.queue_aggregator import get_queue_aggregator
            qa = get_queue_aggregator()
            qa.force_refresh()
            raw_items = qa.get_prioritized(limit=200)
        except Exception as e:
            logger.warning(f"Failed to refresh from queue_aggregator: {e}")
            raw_items = []

        # Convert to QueueItems, preserving existing state
        for raw in raw_items:
            item_id = raw.id

            # Preserve existing ack/notification state if we've seen this item before
            existing = self._items.get(item_id)

            qi = QueueItem(
                id=item_id,
                source=SourceType(raw.source) if raw.source in [s.value for s in SourceType] else SourceType.CLICKUP,
                source_id=raw.source_id,
                source_url=raw.source_url,
                title=raw.title,
                project_name=raw.project_name,
                item_type=raw.task_type.value if hasattr(raw.task_type, 'value') else str(raw.task_type),
                sla_tier=raw.sla_tier.value if hasattr(raw.sla_tier, 'value') else str(raw.sla_tier),
                sla_deadline_at=raw.priority_score.sla_deadline if raw.priority_score else None,
                created_at=raw.created_at if hasattr(raw, 'created_at') else None,
                updated_at=raw.updated_at if hasattr(raw, 'updated_at') else None,
                last_activity_at=raw.updated_at if hasattr(raw, 'updated_at') else None,
                assignee=raw.assignee,
                status=raw.status,
                tags=raw.tags if hasattr(raw, 'tags') else [],
                client_facing=raw.sla_tier.value in ("gold", "silver") if hasattr(raw.sla_tier, 'value') else False,
                open_url=raw.source_url,
            )

            # Preserve state from previous cycle
            if existing:
                qi.ack_state = existing.ack_state
                qi.notification = existing.notification

            # Compute severity
            qi.severity = compute_severity(qi)
            qi.notification.severity = qi.severity
            qi.notification.acknowledgment_required = qi.severity in (Severity.HIGH, Severity.CRITICAL)
            qi.notification.call_eligible = qi.severity == Severity.CRITICAL

            # Compute score
            breakdown = compute_score(qi)

            # Apply policy adjustments
            breakdown.total += PriorityPolicy.apply_time_adjustments(qi)
            breakdown.total += PriorityPolicy.apply_snooze_penalty(qi)
            breakdown.total += PriorityPolicy.apply_ack_decay(qi)
            breakdown.total = round(min(max(breakdown.total, 0), 100), 2)

            qi.score = breakdown.total
            qi.score_breakdown = breakdown
            qi.score_computed_at = datetime.now(timezone.utc).isoformat()

            # Recommended mode
            qi.recommended_mode = PromotionPolicy.recommended_mode(qi)

            # Check for promotion
            previous_score = self._previous_scores.get(item_id)
            promotion = PromotionPolicy.should_promote(qi, previous_score)
            if promotion:
                event = create_promotion_event(qi, promotion, previous_score)
                self._pending_promotions.append(event)
                qi.promotion_eligible = True
                logger.info(f"Promotion: {promotion} for {qi.title[:50]} (score={qi.score})")

            # Track score for next cycle
            self._previous_scores[item_id] = qi.score
            self._items[item_id] = qi

        # Build snapshot
        sorted_items = sorted(self._items.values(), key=lambda x: x.score, reverse=True)

        # Filter out resolved items
        active_items = [i for i in sorted_items if i.ack_state != AckState.RESOLVED]

        self._snapshot_version += 1
        elapsed_ms = (time.time() - start) * 1000

        self._snapshot = QueueSnapshot(
            items=active_items,
            total=len(active_items),
            critical_count=sum(1 for i in active_items if i.severity == Severity.CRITICAL),
            high_count=sum(1 for i in active_items if i.severity == Severity.HIGH),
            unacked_count=sum(1 for i in active_items if i.ack_state == AckState.UNACKED),
            by_project={},
            by_severity={},
            by_source={},
            version=self._snapshot_version,
            compute_time_ms=elapsed_ms,
        )

        # Compute groupings
        for item in active_items:
            proj = item.project_name or "Unknown"
            self._snapshot.by_project[proj] = self._snapshot.by_project.get(proj, 0) + 1
            sev = item.severity.value
            self._snapshot.by_severity[sev] = self._snapshot.by_severity.get(sev, 0) + 1
            src = item.source.value
            self._snapshot.by_source[src] = self._snapshot.by_source.get(src, 0) + 1

        # Set promoted item (highest-scoring promotion)
        if self._pending_promotions:
            top_promo = max(self._pending_promotions, key=lambda p: p.score)
            promo_item = self._items.get(top_promo.item_id)
            if promo_item:
                self._snapshot.promoted_item = promo_item
                self._snapshot.promoted_reason = top_promo.reason

        # Persist
        self._save_state()

        logger.info(
            f"Queue refreshed: {len(active_items)} items, "
            f"{self._snapshot.critical_count} critical, "
            f"{self._snapshot.unacked_count} unacked, "
            f"{len(self._pending_promotions)} promotions, "
            f"{elapsed_ms:.0f}ms"
        )

        return self._snapshot

    # ── Queries ───────────────────────────────────────────────

    def get_snapshot(self) -> QueueSnapshot:
        """Get the current queue snapshot. Refreshes if stale (>2 min)."""
        if self._snapshot is None:
            return self.refresh()
        return self._snapshot

    def get_item(self, item_id: str) -> Optional[QueueItem]:
        """Get a specific item by ID."""
        return self._items.get(item_id)

    def get_pending_promotions(self) -> List[PromotionEvent]:
        """Get and clear pending promotion events."""
        events = list(self._pending_promotions)
        self._pending_promotions.clear()
        return events

    # ── Acknowledgment ────────────────────────────────────────

    def acknowledge(self, item_id: str, ack_type: str, via: str = "dashboard") -> bool:
        """
        Mark an item as acknowledged. Stops escalation.

        ack_type: "queue_open", "action", "snooze", "dismiss", "resolved"
        via: "dashboard", "slack", "email", "text", "voice"
        """
        item = self._items.get(item_id)
        if not item:
            return False

        now = datetime.now(timezone.utc).isoformat()

        if ack_type == "snooze":
            item.ack_state = AckState.SNOOZED
            item.notification.snoozed = True
            item.notification.snooze_count += 1
            item.notification.escalation_paused = True
        elif ack_type == "resolved":
            item.ack_state = AckState.RESOLVED
            item.notification.acknowledged = True
        elif ack_type == "action":
            item.ack_state = AckState.ACTING
            item.notification.acknowledged = True
        else:
            item.ack_state = AckState.OPENED
            item.notification.acknowledged = True

        item.notification.acknowledged_at = now
        item.notification.acknowledged_by = ack_type
        item.notification.acknowledged_via = via
        item.notification.escalation_paused = True

        self._save_state()
        logger.info(f"Acknowledged {item_id}: {ack_type} via {via}")
        return True

    def snooze(self, item_id: str, until: str) -> bool:
        """Snooze an item until a specific time."""
        item = self._items.get(item_id)
        if not item:
            return False

        item.notification.snoozed = True
        item.notification.snoozed_until = until
        item.notification.escalation_paused = True
        item.notification.escalation_paused_until = until
        return self.acknowledge(item_id, "snooze")

    # ── Persistence ───────────────────────────────────────────

    def _save_state(self):
        """Persist ack/notification state to disk."""
        state = {}
        for item_id, item in self._items.items():
            state[item_id] = {
                "ack_state": item.ack_state.value,
                "notification": {
                    "acknowledged": item.notification.acknowledged,
                    "acknowledged_at": item.notification.acknowledged_at,
                    "acknowledged_by": item.notification.acknowledged_by,
                    "escalation_stage": item.notification.escalation_stage,
                    "channels_attempted": item.notification.channels_attempted,
                    "last_notified_at": item.notification.last_notified_at,
                    "snoozed": item.notification.snoozed,
                    "snoozed_until": item.notification.snoozed_until,
                    "snooze_count": item.notification.snooze_count,
                },
            }

        try:
            STATE_FILE.write_text(json.dumps(state, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save queue state: {e}")

    def _load_state(self):
        """Load persisted ack/notification state."""
        if not STATE_FILE.exists():
            return
        try:
            state = json.loads(STATE_FILE.read_text())
            for item_id, data in state.items():
                if item_id in self._items:
                    item = self._items[item_id]
                    item.ack_state = AckState(data.get("ack_state", "unacked"))
                    n = data.get("notification", {})
                    item.notification.acknowledged = n.get("acknowledged", False)
                    item.notification.acknowledged_at = n.get("acknowledged_at")
                    item.notification.acknowledged_by = n.get("acknowledged_by")
                    item.notification.escalation_stage = n.get("escalation_stage", 0)
                    item.notification.channels_attempted = n.get("channels_attempted", [])
                    item.notification.last_notified_at = n.get("last_notified_at")
                    item.notification.snoozed = n.get("snoozed", False)
                    item.notification.snoozed_until = n.get("snoozed_until")
                    item.notification.snooze_count = n.get("snooze_count", 0)
            # Also store state for items not yet refreshed
            self._persisted_state = state
        except Exception as e:
            logger.warning(f"Failed to load queue state: {e}")


# ── Singleton ─────────────────────────────────────────────────

_manager: Optional[QueueManager] = None


def get_queue_manager() -> QueueManager:
    global _manager
    if _manager is None:
        _manager = QueueManager()
    return _manager
