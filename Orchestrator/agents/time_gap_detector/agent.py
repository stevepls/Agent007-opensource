"""Time Gap Detector Agent — finds missing time entries and unsynced hours."""

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("time_gap_detector")

# Minimum expected hours per workday
MIN_HOURS_PER_DAY = 6


def run_time_gap_detector() -> dict:
    """Check the last 5 business days for time logging gaps."""
    try:
        from services.tool_registry import get_registry
        registry = get_registry()

        now = datetime.now(timezone.utc)
        gaps = []
        days_checked = 0

        # Check last 7 calendar days (covers ~5 business days)
        for days_ago in range(1, 8):
            day = now - timedelta(days=days_ago)
            # Skip weekends
            if day.weekday() >= 5:
                continue

            days_checked += 1
            date_str = day.strftime("%Y-%m-%d")

            try:
                result = registry.execute("harvest_get_time_entries", {
                    "from_date": date_str,
                    "to_date": date_str,
                }, skip_confirmation=True)

                entries = []
                if isinstance(result, dict):
                    entries = result.get("time_entries", result.get("entries", []))
                elif isinstance(result, list):
                    entries = result

                total_hours = sum(
                    float(e.get("hours", 0)) for e in entries
                )

                if total_hours < MIN_HOURS_PER_DAY:
                    gaps.append({
                        "date": date_str,
                        "day_name": day.strftime("%A"),
                        "hours_logged": round(total_hours, 2),
                        "expected": MIN_HOURS_PER_DAY,
                        "gap": round(MIN_HOURS_PER_DAY - total_hours, 2),
                        "entries_count": len(entries),
                    })
            except Exception as e:
                logger.warning(f"Failed to check {date_str}: {e}")

        # Also check for pending session time from the session timer
        pending_sessions = []
        try:
            from services.session_timer import get_session_timer
            timer = get_session_timer()
            if hasattr(timer, 'list_pending_time'):
                pending = timer.list_pending_time()
                if pending:
                    for p in pending:
                        pending_sessions.append({
                            "session_id": p.get("session_id", "?"),
                            "duration_minutes": p.get("duration_minutes", 0),
                            "project": p.get("project", "Unknown"),
                        })
        except Exception:
            pass

        details = gaps
        if pending_sessions:
            details = gaps + [{"pending_sessions": pending_sessions}]

        total_gap_hours = sum(g["gap"] for g in gaps)

        summary_parts = []
        if gaps:
            summary_parts.append(f"{len(gaps)} days with <{MIN_HOURS_PER_DAY}h logged ({total_gap_hours:.1f}h total gap)")
        if pending_sessions:
            summary_parts.append(f"{len(pending_sessions)} unlogged sessions")

        return {
            "agent": "time_gap_detector",
            "timestamp": now.isoformat(),
            "items_processed": days_checked,
            "items_found": len(gaps) + len(pending_sessions),
            "summary": "; ".join(summary_parts) if summary_parts else f"All {days_checked} days have {MIN_HOURS_PER_DAY}+ hours logged",
            "details": details,
            "error": None,
        }
    except Exception as e:
        logger.exception("Time gap detector failed")
        return {
            "agent": "time_gap_detector",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
