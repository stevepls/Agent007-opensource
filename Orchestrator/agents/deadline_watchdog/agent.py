"""Deadline Watchdog — finds tasks approaching their SLA deadline with no recent activity."""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("deadline_watchdog")


def run_deadline_watchdog() -> dict:
    """Check queue items for approaching deadlines with no progress."""
    try:
        from services.queue_aggregator import get_queue_aggregator

        qa = get_queue_aggregator()
        qa.force_refresh()
        all_items = qa.get_prioritized(limit=200)

        now = datetime.now(timezone.utc)
        deadline_48h = now + timedelta(hours=48)
        approaching = []

        for item in all_items:
            if item.status == "done":
                continue

            deadline = item.priority_score.sla_deadline
            if deadline is None:
                continue

            # Check if deadline is within 48 hours
            if deadline <= deadline_48h:
                # Check if there's been recent activity (updated in last 24h)
                hours_since_update = (now - item.updated_at).total_seconds() / 3600
                hours_until_deadline = (deadline - now).total_seconds() / 3600

                approaching.append({
                    "id": item.id,
                    "title": item.title,
                    "project": item.project_name,
                    "sla_status": item.priority_score.sla_status.value,
                    "hours_until_deadline": round(max(hours_until_deadline, 0), 1),
                    "hours_since_update": round(hours_since_update, 1),
                    "stagnant": hours_since_update > 24,
                    "source": item.source,
                    "source_url": item.source_url,
                    "assignee": item.assignee,
                    "status": item.status,
                })

        # Sort by deadline proximity (most urgent first)
        approaching.sort(key=lambda x: x["hours_until_deadline"])

        stagnant_count = sum(1 for a in approaching if a["stagnant"])

        summary_parts = []
        if approaching:
            summary_parts.append(f"{len(approaching)} items due within 48h")
        if stagnant_count:
            summary_parts.append(f"{stagnant_count} with no activity in 24h")

        return {
            "agent": "deadline_watchdog",
            "timestamp": now.isoformat(),
            "items_processed": len(all_items),
            "items_found": len(approaching),
            "summary": "; ".join(summary_parts) if summary_parts else "No approaching deadlines",
            "details": approaching[:15],
            "error": None,
        }
    except Exception as e:
        logger.exception("Deadline watchdog failed")
        return {
            "agent": "deadline_watchdog",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
