"""
Queue Manager — Promotion Events

The Queue Manager emits promotion events when items cross thresholds.
The Orchestrator/Surface consumes these to decide mode shifts.

Promotions are:
- rare (only on threshold crossings)
- justified (include reason and score delta)
- visible (tracked and inspectable)
- dismissible (user can snooze or override)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from queue.models import QueueItem


@dataclass
class PromotionEvent:
    """A promotion event emitted by the Queue Manager."""

    event_type: str                         # PROMOTE_TO_FOCUS, PROMOTE_TO_BRIEFING, etc.
    item_id: str
    item_title: str
    project_name: Optional[str]

    # Why this promotion happened
    reason: str
    score: float
    previous_score: Optional[float]
    score_delta: Optional[float]

    # What the Orchestrator should consider doing
    recommended_mode: Optional[str]         # "focus", "review", "compose", "analysis"
    requires_acknowledgment: bool

    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event_type,
            "item_id": self.item_id,
            "item_title": self.item_title,
            "project_name": self.project_name,
            "reason": self.reason,
            "score": self.score,
            "previous_score": self.previous_score,
            "score_delta": self.score_delta,
            "recommended_mode": self.recommended_mode,
            "requires_acknowledgment": self.requires_acknowledgment,
            "timestamp": self.timestamp,
        }


def create_promotion_event(
    item: QueueItem,
    event_type: str,
    previous_score: Optional[float] = None,
) -> PromotionEvent:
    """Create a promotion event from a queue item."""
    delta = round(item.score - previous_score, 2) if previous_score is not None else None

    # Build reason string
    reasons = []
    if item.score_breakdown:
        if item.score_breakdown.severity >= 25:
            reasons.append(f"severity {item.severity.value}")
        if item.score_breakdown.urgency >= 15:
            reasons.append("deadline approaching")
        if item.score_breakdown.blocking >= 10:
            reasons.append("blocking other work")
        if item.score_breakdown.ack_penalty > 0:
            reasons.append("unacknowledged")
        if item.score_breakdown.staleness_penalty >= 6:
            reasons.append("stale")

    reason = "; ".join(reasons) if reasons else f"score={item.score}"

    return PromotionEvent(
        event_type=event_type,
        item_id=item.id,
        item_title=item.title,
        project_name=item.project_name,
        reason=reason,
        score=item.score,
        previous_score=previous_score,
        score_delta=delta,
        recommended_mode=item.recommended_mode,
        requires_acknowledgment=item.severity in ("high", "critical") if isinstance(item.severity, str) else item.severity.value in ("high", "critical"),
    )
