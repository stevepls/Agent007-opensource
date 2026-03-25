"""
Notification Engine — severity-based, acknowledgment-aware escalation.

Rules:
- Email: informational, record-keeping
- Slack: important, needs timely attention during work hours
- Text: urgent, fast acknowledgment required
- Call: critical only, failed escalation
- Acknowledgment stops escalation
- Working hours respected (except critical)

This engine does NOT send notifications itself. It computes what should
be sent and when. The nudge_service handles actual delivery.
"""

import logging
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger("notification_engine")

DATA_DIR = Path(__file__).parent.parent / "data" / "notifications"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"


# ── Severity ──────────────────────────────────────────────────

class NotificationSeverity:
    INFO = "info"
    ATTENTION = "attention"
    HIGH = "high"
    CRITICAL = "critical"


# ── Working Hours ─────────────────────────────────────────────

WORK_START = 8
WORK_END = 20
QUIET_START = 22
QUIET_END = 7


def is_working_hours(now=None):
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    return WORK_START <= now.hour < WORK_END


def is_quiet_hours(now=None):
    now = now or datetime.now()
    return now.hour >= QUIET_START or now.hour < QUIET_END


# ── Channel Selection ─────────────────────────────────────────

def select_channels(severity: str, working: bool, quiet: bool) -> List[str]:
    if severity == NotificationSeverity.INFO:
        return ["email"]
    if severity == NotificationSeverity.ATTENTION:
        if quiet:
            return []  # Queue for morning
        return ["slack"]
    if severity == NotificationSeverity.HIGH:
        if quiet:
            return ["email"]  # Morning Slack will follow
        return ["slack", "email"]
    if severity == NotificationSeverity.CRITICAL:
        return ["text", "slack", "email"]  # Ignore quiet hours
    return []


# ── Escalation Delays ─────────────────────────────────────────

ESCALATION_DELAYS = {
    NotificationSeverity.INFO: [],
    NotificationSeverity.ATTENTION: [
        timedelta(hours=4),   # Stage 0→1: Email follow-up
        timedelta(hours=8),   # Stage 1→2: Bump to HIGH
    ],
    NotificationSeverity.HIGH: [
        timedelta(hours=2),   # Stage 0→1: Text
        timedelta(hours=4),   # Stage 1→2: Text retry
        timedelta(hours=6),   # Stage 2→3: Bump to CRITICAL
    ],
    NotificationSeverity.CRITICAL: [
        timedelta(minutes=15),  # Stage 0→1: Call
        timedelta(minutes=10),  # Stage 1→2: Call retry
        timedelta(minutes=10),  # Stage 2→3: Call retry
        timedelta(minutes=15),  # Stage 3→4: Secondary contact
    ],
}


def next_escalation_delay(severity: str, stage: int) -> Optional[timedelta]:
    delays = ESCALATION_DELAYS.get(severity, [])
    return delays[stage] if stage < len(delays) else None


# ── Notification Item State ───────────────────────────────────

@dataclass
class NotificationItem:
    item_id: str
    title: str
    severity: str = NotificationSeverity.INFO
    severity_reason: str = ""

    # Acknowledgment
    ack_required: bool = False
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    acknowledged_via: Optional[str] = None

    # Escalation
    escalation_stage: int = 0
    channels_attempted: List[str] = field(default_factory=list)
    last_notified_at: Optional[str] = None
    last_notified_channel: Optional[str] = None
    next_escalation_at: Optional[str] = None
    escalation_paused: bool = False

    # Snooze
    snoozed: bool = False
    snoozed_until: Optional[str] = None
    snooze_count: int = 0

    # Log
    events: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "severity": self.severity,
            "ack_required": self.ack_required,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at,
            "escalation_stage": self.escalation_stage,
            "channels_attempted": self.channels_attempted,
            "last_notified_at": self.last_notified_at,
            "next_escalation_at": self.next_escalation_at,
            "escalation_paused": self.escalation_paused,
            "snoozed": self.snoozed,
            "snoozed_until": self.snoozed_until,
            "snooze_count": self.snooze_count,
            "events": self.events[-20:],
        }


# ── Pending Notification (what the nudge service should send) ─

@dataclass
class PendingNotification:
    item_id: str
    title: str
    severity: str
    channel: str  # "slack", "email", "text", "call"
    message: str
    escalation_stage: int
    reason: str


# ── Notification Engine ───────────────────────────────────────

class NotificationEngine:
    """Computes what notifications should be sent and when."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._items: Dict[str, NotificationItem] = {}
        self._load_state()

    def track(self, item_id: str, title: str, severity: str, reason: str = "") -> NotificationItem:
        """Start tracking a notification item or update its severity."""
        if item_id in self._items:
            item = self._items[item_id]
            if severity != item.severity:
                item.severity = severity
                item.severity_reason = reason
                item.events.append({
                    "type": "severity_change",
                    "severity": severity,
                    "reason": reason,
                    "at": datetime.now(timezone.utc).isoformat(),
                })
            return item

        item = NotificationItem(
            item_id=item_id,
            title=title,
            severity=severity,
            severity_reason=reason,
            ack_required=severity in (NotificationSeverity.HIGH, NotificationSeverity.CRITICAL),
        )
        item.events.append({
            "type": "created",
            "severity": severity,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._items[item_id] = item
        return item

    def acknowledge(self, item_id: str, by: str = "user", via: str = "dashboard") -> bool:
        """Mark item as acknowledged. Stops escalation."""
        item = self._items.get(item_id)
        if not item:
            return False

        item.acknowledged = True
        item.acknowledged_at = datetime.now(timezone.utc).isoformat()
        item.acknowledged_by = by
        item.acknowledged_via = via
        item.escalation_paused = True
        item.events.append({
            "type": "acknowledged",
            "by": by,
            "via": via,
            "at": item.acknowledged_at,
        })
        self._save_state()
        return True

    def snooze(self, item_id: str, until: str) -> bool:
        """Snooze an item. Pauses escalation until the time."""
        item = self._items.get(item_id)
        if not item:
            return False

        item.snoozed = True
        item.snoozed_until = until
        item.snooze_count += 1
        item.escalation_paused = True
        item.events.append({
            "type": "snoozed",
            "until": until,
            "count": item.snooze_count,
            "at": datetime.now(timezone.utc).isoformat(),
        })

        # Bump severity if snoozed 3+ times
        if item.snooze_count >= 3 and item.severity == NotificationSeverity.ATTENTION:
            item.severity = NotificationSeverity.HIGH
            item.events.append({
                "type": "severity_bump",
                "reason": f"snoozed {item.snooze_count} times",
                "at": datetime.now(timezone.utc).isoformat(),
            })

        self._save_state()
        return True

    def get_pending(self) -> List[PendingNotification]:
        """
        Check all tracked items and return notifications that should be sent NOW.
        This is called by the nudge service on a schedule.
        """
        now = datetime.now(timezone.utc)
        working = is_working_hours()
        quiet = is_quiet_hours()
        pending = []

        for item in self._items.values():
            # Skip acknowledged
            if item.acknowledged:
                continue

            # Skip paused (unless snooze expired)
            if item.escalation_paused:
                if item.snoozed and item.snoozed_until:
                    try:
                        snooze_end = datetime.fromisoformat(item.snoozed_until)
                        if now < snooze_end:
                            continue
                        # Snooze expired — resume
                        item.escalation_paused = False
                        item.snoozed = False
                    except (ValueError, TypeError):
                        continue
                else:
                    continue

            # Check if it's time for next escalation
            if item.next_escalation_at:
                try:
                    next_time = datetime.fromisoformat(item.next_escalation_at)
                    if now < next_time:
                        continue
                except (ValueError, TypeError):
                    pass

            # Determine channels
            if item.last_notified_at is None:
                # First notification
                channels = select_channels(item.severity, working, quiet)
            else:
                # Escalation — determine next channel based on stage
                stage = item.escalation_stage
                if item.severity == NotificationSeverity.ATTENTION and stage >= 1:
                    channels = ["email"]
                elif item.severity == NotificationSeverity.HIGH and stage >= 1:
                    channels = ["text"]
                elif item.severity == NotificationSeverity.CRITICAL and stage >= 1:
                    channels = ["call"]
                else:
                    channels = select_channels(item.severity, working, quiet)

            for channel in channels:
                if channel in item.channels_attempted and item.escalation_stage == 0:
                    continue  # Already sent on this channel at this stage

                pending.append(PendingNotification(
                    item_id=item.item_id,
                    title=item.title,
                    severity=item.severity,
                    channel=channel,
                    message=f"[{item.severity.upper()}] {item.title}",
                    escalation_stage=item.escalation_stage,
                    reason=item.severity_reason or f"Stage {item.escalation_stage} escalation",
                ))

        return pending

    def mark_sent(self, item_id: str, channel: str):
        """Record that a notification was sent."""
        item = self._items.get(item_id)
        if not item:
            return

        now = datetime.now(timezone.utc).isoformat()
        item.last_notified_at = now
        item.last_notified_channel = channel
        if channel not in item.channels_attempted:
            item.channels_attempted.append(channel)

        item.events.append({
            "type": "sent",
            "channel": channel,
            "stage": item.escalation_stage,
            "at": now,
        })

        # Set next escalation time
        delay = next_escalation_delay(item.severity, item.escalation_stage)
        if delay:
            next_time = datetime.now(timezone.utc) + delay
            item.next_escalation_at = next_time.isoformat()
            item.escalation_stage += 1
        else:
            item.next_escalation_at = None  # No more escalation

        self._save_state()

    def get_status(self) -> Dict[str, Any]:
        """Summary for health/status endpoints."""
        total = len(self._items)
        unacked = sum(1 for i in self._items.values() if not i.acknowledged)
        by_severity = {}
        for i in self._items.values():
            by_severity[i.severity] = by_severity.get(i.severity, 0) + 1

        return {
            "total_tracked": total,
            "unacknowledged": unacked,
            "by_severity": by_severity,
        }

    # ── Persistence ───────────────────────────────────────

    def _save_state(self):
        try:
            data = {k: v.to_dict() for k, v in self._items.items()}
            STATE_FILE.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save notification state: {e}")

    def _load_state(self):
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text())
            for item_id, d in data.items():
                item = NotificationItem(
                    item_id=d.get("item_id", item_id),
                    title=d.get("title", ""),
                    severity=d.get("severity", NotificationSeverity.INFO),
                )
                item.ack_required = d.get("ack_required", False)
                item.acknowledged = d.get("acknowledged", False)
                item.acknowledged_at = d.get("acknowledged_at")
                item.escalation_stage = d.get("escalation_stage", 0)
                item.channels_attempted = d.get("channels_attempted", [])
                item.last_notified_at = d.get("last_notified_at")
                item.next_escalation_at = d.get("next_escalation_at")
                item.escalation_paused = d.get("escalation_paused", False)
                item.snoozed = d.get("snoozed", False)
                item.snoozed_until = d.get("snoozed_until")
                item.snooze_count = d.get("snooze_count", 0)
                item.events = d.get("events", [])
                self._items[item_id] = item
        except Exception as e:
            logger.warning(f"Failed to load notification state: {e}")


# Singleton
_engine = None

def get_notification_engine() -> NotificationEngine:
    global _engine
    if _engine is None:
        _engine = NotificationEngine()
    return _engine
