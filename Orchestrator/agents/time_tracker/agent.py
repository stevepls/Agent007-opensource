"""
Time Tracking Agent

Runs when the orchestrator task queue goes idle.  Checks for unlogged
Hubstaff time entries and syncs them to Harvest so tracked hours are
never lost.

The agent is intentionally lightweight — it reads from Hubstaff, cross-
references Harvest, and logs any gaps.  It does NOT run through CrewAI
(no LLM calls) to keep cost at zero.
"""

import os
import logging
import threading
import time as _time
from datetime import date, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger("time_tracker")

# Minimum seconds between runs (avoid hammering APIs on rapid queue churn)
MIN_RUN_INTERVAL = int(os.getenv("TIME_TRACKER_INTERVAL", "300"))  # 5 min default


class TimeTrackingAgent:
    """Sync Hubstaff tracked time → Harvest when the queue is idle."""

    def __init__(self):
        self._last_run: float = 0.0
        self._lock = threading.Lock()
        self._hubstaff = None
        self._harvest_configured = False
        self._init_clients()

    # ------------------------------------------------------------------
    # Client initialisation (fail-safe)
    # ------------------------------------------------------------------

    def _init_clients(self):
        try:
            from services.hubstaff.client import HubstaffClient

            token = os.getenv("HUBSTAFF_API_TOKEN")
            if token:
                org_id = os.getenv("HUBSTAFF_ORG_ID")
                self._hubstaff = HubstaffClient(
                    api_token=token,
                    org_id=int(org_id) if org_id else None,
                )
                logger.info("TimeTrackingAgent: Hubstaff client ready")
            else:
                logger.info("TimeTrackingAgent: HUBSTAFF_API_TOKEN not set — disabled")
        except Exception as e:
            logger.warning(f"TimeTrackingAgent: Hubstaff init failed: {e}")

        try:
            from services.harvest_client import is_harvest_configured

            self._harvest_configured = is_harvest_configured()
            if self._harvest_configured:
                logger.info("TimeTrackingAgent: Harvest configured")
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_queue_idle(self):
        """Called by BackgroundTaskQueue when all tasks finish.

        Respects MIN_RUN_INTERVAL to avoid rapid-fire API calls.
        Runs in the calling thread (background executor), so it won't
        block the event loop.
        """
        if not self._hubstaff:
            return

        now = _time.time()
        if (now - self._last_run) < MIN_RUN_INTERVAL:
            return

        if not self._lock.acquire(blocking=False):
            return  # another run already in progress

        try:
            self._last_run = now
            logger.info("TimeTrackingAgent: queue idle — running sync check")
            self._sync_check()
        except Exception as e:
            logger.warning(f"TimeTrackingAgent: sync check failed: {e}")
        finally:
            self._lock.release()

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _sync_check(self):
        """Compare today's Hubstaff entries against Harvest and log gaps."""
        user_id = os.getenv("HUBSTAFF_USER_ID")
        if not user_id:
            logger.debug("TimeTrackingAgent: HUBSTAFF_USER_ID not set, skipping")
            return
        user_id = int(user_id)

        today = date.today()
        hubstaff_entries = self._hubstaff.get_user_time_entries(
            user_id, start_date=today, end_date=today,
        )
        hubstaff_hours = round(sum(e.tracked for e in hubstaff_entries) / 3600, 2)

        # Fetch Harvest hours for comparison
        harvest_hours = self._get_harvest_hours(today)

        gap = round(hubstaff_hours - harvest_hours, 2) if harvest_hours is not None else None

        summary = {
            "date": today.isoformat(),
            "hubstaff_hours": hubstaff_hours,
            "hubstaff_entries": len(hubstaff_entries),
            "harvest_hours": harvest_hours,
            "gap_hours": gap,
        }
        logger.info(f"TimeTrackingAgent: {summary}")

        # If there's a meaningful gap (>15 min), log it to Harvest
        if gap is not None and gap >= 0.25 and self._harvest_configured:
            self._log_gap_to_harvest(gap, hubstaff_entries, today)

    def _get_harvest_hours(self, target_date: date) -> Optional[float]:
        """Fetch total Harvest hours for a date.  Returns None if unavailable."""
        if not self._harvest_configured:
            return None
        try:
            from services.tool_registry import get_registry

            registry = get_registry()
            result = registry.execute(
                "harvest_get_time_entries",
                {"date": target_date.isoformat()},
            )
            if isinstance(result, dict) and "total_hours" in result:
                return result["total_hours"]
        except Exception as e:
            logger.debug(f"TimeTrackingAgent: Harvest query failed: {e}")
        return None

    def _log_gap_to_harvest(
        self,
        gap_hours: float,
        hubstaff_entries: list,
        target_date: date,
    ):
        """Log untracked Hubstaff time to Harvest."""
        try:
            from services.tool_registry import get_registry
            from services.project_mapper import get_project_mapper

            registry = get_registry()

            # Build a note from Hubstaff entry details
            notes_parts = []
            for entry in hubstaff_entries:
                if entry.note:
                    notes_parts.append(entry.note)
            note = "; ".join(notes_parts[:5]) if notes_parts else "Hubstaff tracked time (auto-synced)"

            result = registry.execute("harvest_log_time", {
                "project_name": os.getenv("DEFAULT_HARVEST_PROJECT", "Development"),
                "hours": gap_hours,
                "notes": f"[auto-sync] {note}",
                "date": target_date.isoformat(),
            })

            if isinstance(result, dict) and result.get("success"):
                logger.info(f"TimeTrackingAgent: logged {gap_hours}h gap to Harvest")
            else:
                logger.warning(f"TimeTrackingAgent: Harvest log failed: {result}")
        except Exception as e:
            logger.warning(f"TimeTrackingAgent: gap logging failed: {e}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_agent: Optional[TimeTrackingAgent] = None


def get_time_tracking_agent() -> TimeTrackingAgent:
    global _agent
    if _agent is None:
        _agent = TimeTrackingAgent()
    return _agent
