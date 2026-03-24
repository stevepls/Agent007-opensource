"""SLA Monitor Agent — detects and escalates SLA breaches."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("sla_monitor")


def run_sla_monitor() -> dict:
    """Check all queue items for SLA status and escalate breaches."""
    try:
        from services.queue_aggregator import get_queue_aggregator

        qa = get_queue_aggregator()
        qa.force_refresh()

        breaching = qa.get_breaching()
        summary = qa.get_summary()
        total = summary.get("total", 0)

        details = []
        for item in breaching:
            details.append({
                "id": item.id,
                "title": item.title,
                "project": item.project_name,
                "sla_status": item.priority_score.sla_status.value,
                "score": item.priority_score.score,
                "source": item.source,
                "source_url": item.source_url,
            })

        return {
            "agent": "sla_monitor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": total,
            "items_found": len(breaching),
            "summary": f"{len(breaching)} SLA breaches out of {total} items" if breaching else f"All {total} items within SLA",
            "details": details,
            "error": None,
        }
    except Exception as e:
        logger.exception("SLA monitor failed")
        return {
            "agent": "sla_monitor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
