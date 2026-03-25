"""
Notification Agent — checks queue items for notification triggers
and delivers pending notifications via the nudge service.

Runs every 5 minutes as a proactive agent.

Flow:
1. Get all queue items from the queue aggregator
2. For each item, compute severity and track in the notification engine
3. Check for pending notifications (items that need escalation)
4. Deliver via the nudge service
5. Report results
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("notification_agent")


def run_notification_agent() -> dict:
    """Check for notification triggers and deliver pending notifications."""
    try:
        from services.queue_aggregator import get_queue_aggregator
        from services.notification_engine import get_notification_engine, NotificationSeverity
        from services.nudge_service import get_nudge_service
        from services.sla import SLAStatus

        engine = get_notification_engine()
        nudge = get_nudge_service()

        # Get current queue items
        qa = get_queue_aggregator()
        items = qa.get_prioritized(limit=100)

        tracked = 0
        for item in items:
            if item.status == "done":
                continue

            # Compute notification severity from SLA status
            sla_status = item.priority_score.sla_status
            if sla_status == SLAStatus.BREACHED:
                severity = NotificationSeverity.CRITICAL
                reason = f"SLA breached: {item.title} ({item.project_name})"
            elif sla_status == SLAStatus.BREACHING:
                severity = NotificationSeverity.HIGH
                reason = f"SLA breaching: {item.title} ({item.project_name})"
            elif sla_status == SLAStatus.APPROACHING:
                severity = NotificationSeverity.ATTENTION
                reason = f"SLA approaching: {item.title} ({item.project_name})"
            else:
                # Only track high-score items
                if item.priority_score.score >= 50:
                    severity = NotificationSeverity.ATTENTION
                    reason = f"High priority (score {item.priority_score.score}): {item.title}"
                else:
                    continue  # Don't track low-priority items

            engine.track(item.id, item.title, severity, reason)
            tracked += 1

        # Check for pending notifications
        pending = engine.get_pending()

        # Deliver
        results = {"sent": 0, "skipped": 0, "failed": 0}
        if pending:
            results = nudge.deliver(pending)

        summary_parts = [f"Tracked {tracked} items"]
        if pending:
            summary_parts.append(f"{len(pending)} pending notifications")
        if results["sent"]:
            summary_parts.append(f"{results['sent']} sent")
        if results["skipped"]:
            summary_parts.append(f"{results['skipped']} rate-limited")

        return {
            "agent": "notification_agent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": tracked,
            "items_found": len(pending),
            "summary": "; ".join(summary_parts) if summary_parts else "No notifications needed",
            "details": [n.__dict__ for n in pending[:10]] if pending else [],
            "error": None,
        }
    except Exception as e:
        logger.exception("Notification agent failed")
        return {
            "agent": "notification_agent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
