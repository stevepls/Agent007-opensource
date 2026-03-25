"""
Queue Manager — Priority & Promotion Policies

Deterministic rules for scoring adjustments and promotion decisions.
No LLM, no agents. Just rules.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from queue_manager.models import QueueItem, Severity, AckState


# ── Working Hours ─────────────────────────────────────────────

WORK_START_HOUR = 8     # 8 AM
WORK_END_HOUR = 20      # 8 PM
QUIET_START_HOUR = 22   # 10 PM
QUIET_END_HOUR = 7      # 7 AM


def is_working_hours(now: Optional[datetime] = None) -> bool:
    """Check if current time is within working hours (Mon-Fri 8AM-8PM)."""
    now = now or datetime.now()
    if now.weekday() >= 5:  # Saturday, Sunday
        return False
    return WORK_START_HOUR <= now.hour < WORK_END_HOUR


def is_quiet_hours(now: Optional[datetime] = None) -> bool:
    """Check if current time is quiet hours (10PM-7AM)."""
    now = now or datetime.now()
    return now.hour >= QUIET_START_HOUR or now.hour < QUIET_END_HOUR


# ── Promotion Thresholds ──────────────────────────────────────

# Score thresholds for promotion levels
PROMOTE_TO_FOCUS_THRESHOLD = 60        # Score >= 60 → suggest focus mode
PROMOTE_TO_BRIEFING_THRESHOLD = 40     # Score >= 40 → include in briefing
PROMOTE_TO_CRITICAL_ALERT = 80         # Score >= 80 → critical alert
PROMOTE_TO_REVIEW_THRESHOLD = 70       # Approval-type items at 70+ → review mode

# Score delta that triggers re-promotion
SCORE_DELTA_THRESHOLD = 20             # If score jumped 20+ since last compute, re-promote


class PriorityPolicy:
    """Rules for adjusting priority scores based on context."""

    @staticmethod
    def apply_time_adjustments(item: QueueItem) -> float:
        """Adjust score based on time of day and working hours."""
        adjustment = 0.0
        now = datetime.now()

        # During quiet hours, demote non-critical items
        if is_quiet_hours(now) and item.severity != Severity.CRITICAL:
            adjustment -= 10

        # Start of workday: boost items that accumulated overnight
        if 7 <= now.hour <= 9 and item.ack_state == AckState.UNACKED:
            adjustment += 5

        return adjustment

    @staticmethod
    def apply_snooze_penalty(item: QueueItem) -> float:
        """Items snoozed 3+ times get a severity bump."""
        if item.notification.snooze_count >= 3:
            return 10  # Bump score — something is being avoided
        return 0.0

    @staticmethod
    def apply_ack_decay(item: QueueItem) -> float:
        """Acknowledged items decay in score over time if no action taken."""
        if item.ack_state == AckState.OPENED and item.notification.acknowledged_at:
            try:
                ack_time = datetime.fromisoformat(item.notification.acknowledged_at)
                hours_since_ack = (datetime.now(timezone.utc) - ack_time).total_seconds() / 3600
                if hours_since_ack > 24:
                    return 5  # Re-bump: acknowledged but no action in 24h
            except (ValueError, TypeError):
                pass
        return 0.0


class PromotionPolicy:
    """Rules for when a queue item should interrupt or change mode."""

    @staticmethod
    def should_promote(item: QueueItem, previous_score: Optional[float] = None) -> Optional[str]:
        """
        Determine if an item should be promoted beyond its queue position.

        Returns promotion event type or None:
        - "PROMOTE_TO_FOCUS" — item should take over the canvas
        - "PROMOTE_TO_BRIEFING" — item should be in the next briefing
        - "PROMOTE_TO_REVIEW" — item needs a decision/approval
        - "PROMOTE_TO_CRITICAL_ALERT" — critical interrupt
        """
        score = item.score

        # Critical alert — highest priority
        if score >= PROMOTE_TO_CRITICAL_ALERT or item.severity == Severity.CRITICAL:
            return "PROMOTE_TO_CRITICAL_ALERT"

        # Review mode — approvals and decisions
        if score >= PROMOTE_TO_REVIEW_THRESHOLD and item.item_type in ("pr", "approval", "deploy"):
            return "PROMOTE_TO_REVIEW"

        # Focus mode — high-scoring items
        if score >= PROMOTE_TO_FOCUS_THRESHOLD:
            # Only promote if score jumped significantly (avoid constant re-promotion)
            if previous_score is not None and (score - previous_score) < SCORE_DELTA_THRESHOLD:
                return None  # Score didn't change enough
            return "PROMOTE_TO_FOCUS"

        # Briefing — medium-scoring items
        if score >= PROMOTE_TO_BRIEFING_THRESHOLD:
            return "PROMOTE_TO_BRIEFING"

        return None

    @staticmethod
    def recommended_mode(item: QueueItem) -> Optional[str]:
        """Suggest the best mode for this item if focused."""
        if item.item_type in ("pr", "diff"):
            return "review"
        if item.item_type in ("email", "email_draft"):
            return "compose"
        if item.item_type in ("metrics", "time_entries", "table"):
            return "analysis"
        if item.item_type in ("task", "ticket"):
            return "focus"
        return "focus"  # Default

    @staticmethod
    def should_return_to_queue(item: QueueItem) -> bool:
        """Check if the current focus should be released back to queue."""
        # Item resolved
        if item.ack_state == AckState.RESOLVED:
            return True
        # Item acknowledged and no longer high-scoring
        if item.ack_state in (AckState.OPENED, AckState.ACTING) and item.score < 30:
            return True
        return False


# ── Notification Channel Selection ────────────────────────────

def select_notification_channels(
    severity: Severity,
    working_hours: bool,
    quiet_hours: bool,
) -> List[str]:
    """
    Deterministic channel selection based on severity and time.
    Returns list of channels to notify on.
    """
    if severity == Severity.INFO:
        return ["email"]  # Or queue-only

    if severity == Severity.ATTENTION:
        if quiet_hours:
            return []  # Queue for morning
        return ["slack"]

    if severity == Severity.HIGH:
        if quiet_hours:
            # Check if SLA breach is imminent (< 4h)
            return ["email"]  # Will be escalated in morning
        return ["slack", "email"]  # Parallel

    if severity == Severity.CRITICAL:
        return ["text", "slack", "email"]  # All channels, ignore quiet hours

    return []


def next_escalation_delay(severity: Severity, stage: int) -> Optional[timedelta]:
    """
    How long to wait before escalating to the next stage.
    Returns None if no more escalation should happen.
    """
    escalation_table = {
        Severity.INFO: [],  # No escalation
        Severity.ATTENTION: [
            timedelta(hours=4),     # Stage 0→1: Slack → Email after 4h
            timedelta(hours=8),     # Stage 1→2: bump to HIGH
        ],
        Severity.HIGH: [
            timedelta(hours=2),     # Stage 0→1: Slack+Email → Text after 2h
            timedelta(hours=4),     # Stage 1→2: Text retry
            timedelta(hours=6),     # Stage 2→3: bump to CRITICAL
        ],
        Severity.CRITICAL: [
            timedelta(minutes=15),  # Stage 0→1: Text → Call after 15m
            timedelta(minutes=10),  # Stage 1→2: Call retry
            timedelta(minutes=10),  # Stage 2→3: Call retry
            timedelta(minutes=15),  # Stage 3→4: escalate to secondary
        ],
    }

    delays = escalation_table.get(severity, [])
    if stage < len(delays):
        return delays[stage]
    return None  # No more escalation
