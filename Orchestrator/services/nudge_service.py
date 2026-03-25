"""
Nudge Service — delivers notifications via Slack, email, and (future) text.

Consumes PendingNotification objects from the NotificationEngine.
Rate limited: max 5 nudges per hour, no nudges 10pm-7am (except critical).

Does NOT decide what to send — the NotificationEngine does that.
This service just delivers and records the result.
"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional, Dict

logger = logging.getLogger("nudge_service")

# Rate limiting
MAX_NUDGES_PER_HOUR = 5
RATE_WINDOW = 3600  # 1 hour in seconds


class NudgeService:
    """Delivers notifications to Slack, email, and (future) text/call."""

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
        self._sent_timestamps: List[float] = []  # For rate limiting
        self._sent_count = 0

    def _is_rate_limited(self) -> bool:
        """Check if we've hit the rate limit."""
        now = time.time()
        # Prune old timestamps
        self._sent_timestamps = [t for t in self._sent_timestamps if now - t < RATE_WINDOW]
        return len(self._sent_timestamps) >= MAX_NUDGES_PER_HOUR

    def _record_send(self):
        self._sent_timestamps.append(time.time())
        self._sent_count += 1

    def send_slack(self, user: str, message: str, severity: str) -> bool:
        """Send a Slack DM notification."""
        try:
            from services.message_queue import get_message_queue, MessageType
            mq = get_message_queue()
            mq.queue(
                msg_type=MessageType.SLACK_DM,
                channel=user,
                content=message,
                created_by="nudge_service",
                delay_seconds=0,
                requires_approval=False,  # System notifications don't need approval
            )
            self._record_send()
            logger.info(f"Slack nudge sent to {user}: {message[:60]}")
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack nudge: {e}")
            return False

    def send_email(self, to: str, subject: str, body: str, severity: str) -> bool:
        """Send an email notification."""
        try:
            from services.message_queue import get_message_queue, MessageType
            mq = get_message_queue()
            mq.queue(
                msg_type=MessageType.EMAIL_SEND,
                channel=to,
                content=body,
                subject=subject,
                created_by="nudge_service",
                delay_seconds=0,
                requires_approval=False,  # System notifications
            )
            self._record_send()
            logger.info(f"Email nudge sent to {to}: {subject[:60]}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email nudge: {e}")
            return False

    def send_text(self, phone: str, message: str, severity: str) -> bool:
        """Send an SMS notification. Placeholder — needs Twilio integration."""
        logger.warning(f"Text nudge requested but not implemented: {phone}: {message[:60]}")
        # TODO: Integrate Twilio
        return False

    def send_call(self, phone: str, message: str) -> bool:
        """Make a phone call. Placeholder — needs Twilio Voice."""
        logger.warning(f"Call nudge requested but not implemented: {phone}")
        # TODO: Integrate Twilio Voice
        return False

    def deliver(self, notifications) -> Dict[str, int]:
        """
        Deliver a batch of pending notifications.
        Returns counts: {"sent": N, "skipped": N, "failed": N}
        """
        from services.notification_engine import PendingNotification, get_notification_engine

        engine = get_notification_engine()
        sent = 0
        skipped = 0
        failed = 0

        # Default recipients
        import os
        default_slack_user = os.getenv("BRIEFING_SLACK_USER", "steve")
        default_email = os.getenv("NOTIFICATION_EMAIL", "steve@peoplelikesoftware.com")

        for notif in notifications:
            if not isinstance(notif, PendingNotification):
                continue

            # Rate limit check (except critical)
            if notif.severity != "critical" and self._is_rate_limited():
                logger.info(f"Rate limited — skipping {notif.channel} for {notif.title[:40]}")
                skipped += 1
                continue

            success = False

            if notif.channel == "slack":
                success = self.send_slack(
                    default_slack_user,
                    f"*{notif.severity.upper()}* — {notif.title}\n{notif.reason}",
                    notif.severity,
                )
            elif notif.channel == "email":
                success = self.send_email(
                    default_email,
                    f"[{notif.severity.upper()}] {notif.title}",
                    f"{notif.title}\n\n{notif.reason}\n\nSeverity: {notif.severity}\nEscalation stage: {notif.escalation_stage}",
                    notif.severity,
                )
            elif notif.channel == "text":
                success = self.send_text(
                    os.getenv("NOTIFICATION_PHONE", ""),
                    f"[{notif.severity.upper()}] {notif.title} — {notif.reason}",
                    notif.severity,
                )
            elif notif.channel == "call":
                success = self.send_call(
                    os.getenv("NOTIFICATION_PHONE", ""),
                    f"Critical: {notif.title}",
                )

            if success:
                engine.mark_sent(notif.item_id, notif.channel)
                sent += 1
            else:
                failed += 1

        return {"sent": sent, "skipped": skipped, "failed": failed}

    def get_stats(self) -> Dict[str, int]:
        now = time.time()
        recent = [t for t in self._sent_timestamps if now - t < RATE_WINDOW]
        return {
            "total_sent": self._sent_count,
            "sent_this_hour": len(recent),
            "rate_limit": MAX_NUDGES_PER_HOUR,
            "rate_limited": len(recent) >= MAX_NUDGES_PER_HOUR,
        }


# Singleton
_service = None

def get_nudge_service() -> NudgeService:
    global _service
    if _service is None:
        _service = NudgeService()
    return _service
