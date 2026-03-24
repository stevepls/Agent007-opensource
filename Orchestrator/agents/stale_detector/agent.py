"""Stale Detector Agent — finds tasks/tickets that have gone stale relative to SLA."""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("stale_detector")

# Staleness thresholds by SLA tier (days without update)
STALE_THRESHOLDS = {
    "gold": 2,
    "silver": 5,
    "bronze": 7,
    "internal": 14,
}


def run_stale_detector() -> dict:
    """Scan queue items for staleness relative to their SLA tier."""
    try:
        from services.queue_aggregator import get_queue_aggregator

        qa = get_queue_aggregator()
        qa.force_refresh()
        all_items = qa.get_prioritized(limit=200)

        now = datetime.now(timezone.utc)
        stale_items = []

        for item in all_items:
            if item.status == "done":
                continue

            threshold_days = STALE_THRESHOLDS.get(item.sla_tier.value, 7)
            threshold = timedelta(days=threshold_days)

            age = now - item.updated_at
            if age > threshold:
                stale_items.append({
                    "id": item.id,
                    "title": item.title,
                    "project": item.project_name,
                    "sla_tier": item.sla_tier.value,
                    "days_stale": round(age.total_seconds() / 86400, 1),
                    "threshold_days": threshold_days,
                    "source": item.source,
                    "source_url": item.source_url,
                    "assignee": item.assignee,
                })

        # Sort by staleness (most stale first)
        stale_items.sort(key=lambda x: x["days_stale"], reverse=True)

        return {
            "agent": "stale_detector",
            "timestamp": now.isoformat(),
            "items_processed": len(all_items),
            "items_found": len(stale_items),
            "summary": f"{len(stale_items)} stale items found" if stale_items else "No stale items",
            "details": stale_items[:20],  # Top 20 most stale
            "error": None,
        }
    except Exception as e:
        logger.exception("Stale detector failed")
        return {
            "agent": "stale_detector",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
