"""
Time Tracking Agent

Runs when the orchestrator task queue goes idle.  Checks for unlogged
Hubstaff time entries and syncs them to Harvest — but ONLY for projects
that have an explicit Hubstaff↔Harvest name mapping.

Entries from unmapped Hubstaff projects are silently skipped so we never
randomly assign time to the wrong Harvest project.

The agent is intentionally lightweight — it reads from Hubstaff, cross-
references Harvest, and logs any gaps.  It does NOT run through CrewAI
(no LLM calls) to keep cost at zero.
"""

import os
import json
import logging
import threading
import time as _time
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("time_tracker")

# Minimum seconds between runs (avoid hammering APIs on rapid queue churn)
MIN_RUN_INTERVAL = int(os.getenv("TIME_TRACKER_INTERVAL", "300"))  # 5 min default

# Minimum match score for Hubstaff→Harvest project name similarity
PROJECT_MATCH_THRESHOLD = float(os.getenv("TIME_TRACKER_MATCH_THRESHOLD", "0.65"))

# Path to explicit overrides file (JSON: {"hubstaff_project_id": "harvest_project_name", ...})
MAPPING_OVERRIDES_PATH = Path(__file__).parent.parent.parent / "data" / "time_tracker" / "project_mappings.json"


def _load_overrides() -> Dict[int, str]:
    """Load manual hubstaff_project_id → harvest_project_name overrides."""
    if MAPPING_OVERRIDES_PATH.exists():
        try:
            raw = json.loads(MAPPING_OVERRIDES_PATH.read_text())
            return {int(k): v for k, v in raw.items()}
        except Exception as e:
            logger.warning(f"TimeTrackingAgent: failed to load overrides: {e}")
    return {}


class TimeTrackingAgent:
    """Sync Hubstaff tracked time → Harvest when the queue is idle.

    Only syncs time for Hubstaff projects that have a direct mapping to a
    Harvest project (by name match or explicit override).  Unmapped projects
    are logged at DEBUG level and skipped.
    """

    def __init__(self):
        self._last_run: float = 0.0
        self._lock = threading.Lock()
        self._hubstaff = None
        self._harvest_configured = False
        self._harvest_projects: Optional[Dict[str, int]] = None  # name_lower → project_id
        self._overrides: Dict[int, str] = _load_overrides()
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
    # Harvest project discovery
    # ------------------------------------------------------------------

    def _get_harvest_projects(self) -> Dict[str, int]:
        """Fetch available Harvest projects, cached for the lifetime of this run.

        Returns dict of lowercase_name → harvest_project_id.
        """
        if self._harvest_projects is not None:
            return self._harvest_projects

        self._harvest_projects = {}
        if not self._harvest_configured:
            return self._harvest_projects

        try:
            from services.tool_registry import get_registry

            result = get_registry().execute("harvest_list_projects", {})
            if isinstance(result, dict):
                for p in result.get("projects", []):
                    name = p.get("name", "")
                    self._harvest_projects[name.lower()] = p["id"]
        except Exception as e:
            logger.debug(f"TimeTrackingAgent: Harvest project list failed: {e}")

        return self._harvest_projects

    def _match_hubstaff_to_harvest(
        self, hubstaff_project_id: Optional[int], hubstaff_project_name: str,
    ) -> Optional[str]:
        """Find a matching Harvest project name for a Hubstaff project.

        Returns the exact Harvest project name (as it appears in Harvest) or
        None if no confident mapping exists.

        Matching order:
        1. Explicit override in data/time_tracker/project_mappings.json
        2. Fuzzy name match above PROJECT_MATCH_THRESHOLD
        """
        # 1. Check explicit overrides
        if hubstaff_project_id and hubstaff_project_id in self._overrides:
            return self._overrides[hubstaff_project_id]

        harvest_projects = self._get_harvest_projects()
        if not harvest_projects:
            return None

        # Normalise the Hubstaff name: take the part before " / " (project group)
        hs_name = hubstaff_project_name.split("/")[0].strip().lower()

        # 2. Exact substring match first
        for h_name_lower, _h_id in harvest_projects.items():
            if hs_name in h_name_lower or h_name_lower in hs_name:
                # Return the original-case name
                return self._harvest_project_original_name(h_name_lower)

        # 3. Fuzzy match
        best_score = 0.0
        best_name: Optional[str] = None
        for h_name_lower in harvest_projects:
            score = SequenceMatcher(None, hs_name, h_name_lower).ratio()
            if score > best_score:
                best_score = score
                best_name = h_name_lower

        if best_score >= PROJECT_MATCH_THRESHOLD and best_name:
            return self._harvest_project_original_name(best_name)

        return None

    def _harvest_project_original_name(self, lower_name: str) -> str:
        """Recover original-case Harvest project name from our lowercase key."""
        # Re-fetch from the tool result to get original case
        try:
            from services.tool_registry import get_registry

            result = get_registry().execute("harvest_list_projects", {})
            if isinstance(result, dict):
                for p in result.get("projects", []):
                    if p.get("name", "").lower() == lower_name:
                        return p["name"]
        except Exception:
            pass
        # Fallback: title-case the lowercase name
        return lower_name.title()

    # ------------------------------------------------------------------
    # Hubstaff project name lookup
    # ------------------------------------------------------------------

    def _get_hubstaff_project_names(self) -> Dict[int, str]:
        """Build hubstaff_project_id → name from the project mapper cache."""
        names: Dict[int, str] = {}
        try:
            from services.project_mapper import CACHE_FILE

            if CACHE_FILE.exists():
                data = json.loads(CACHE_FILE.read_text())
                for p in data.get("hubstaff_projects", []):
                    names[p["id"]] = p["name"]
        except Exception:
            pass
        return names

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _sync_check(self):
        """Compare today's Hubstaff entries against Harvest, per-project.

        Only entries whose Hubstaff project maps to a known Harvest project
        are synced.  Everything else is skipped.
        """
        user_id = os.getenv("HUBSTAFF_USER_ID")
        if not user_id:
            logger.debug("TimeTrackingAgent: HUBSTAFF_USER_ID not set, skipping")
            return
        user_id = int(user_id)

        today = date.today()

        # Invalidate cached Harvest projects each run
        self._harvest_projects = None

        hubstaff_entries = self._hubstaff.get_user_time_entries(
            user_id, start_date=today, end_date=today,
        )
        if not hubstaff_entries:
            logger.info("TimeTrackingAgent: no Hubstaff entries today")
            return

        hs_project_names = self._get_hubstaff_project_names()

        # Group Hubstaff hours by project
        hours_by_project: Dict[Optional[int], float] = defaultdict(float)
        notes_by_project: Dict[Optional[int], List[str]] = defaultdict(list)

        for entry in hubstaff_entries:
            pid = entry.project_id
            hours_by_project[pid] += entry.tracked / 3600
            if entry.note and entry.note not in notes_by_project[pid]:
                notes_by_project[pid].append(entry.note)

        # Get Harvest hours for today (per project)
        harvest_hours_by_project = self._get_harvest_hours_by_project(today)

        synced = 0
        skipped = 0

        for hs_pid, hs_hours in hours_by_project.items():
            hs_hours = round(hs_hours, 2)
            hs_name = hs_project_names.get(hs_pid, "") if hs_pid else ""

            harvest_name = self._match_hubstaff_to_harvest(hs_pid, hs_name)

            if not harvest_name:
                logger.debug(
                    f"TimeTrackingAgent: skipping unmapped Hubstaff project "
                    f"{hs_pid} ({hs_name}), {hs_hours}h"
                )
                skipped += 1
                continue

            # Compare against what's already logged in Harvest for this project
            harvest_logged = harvest_hours_by_project.get(harvest_name.lower(), 0.0)
            gap = round(hs_hours - harvest_logged, 2)

            if gap < 0.25:
                logger.debug(
                    f"TimeTrackingAgent: {harvest_name} — "
                    f"Hubstaff {hs_hours}h, Harvest {harvest_logged}h, gap {gap}h (below threshold)"
                )
                continue

            # Log the gap
            notes = notes_by_project.get(hs_pid, [])
            note_str = "; ".join(notes[:5]) if notes else f"Hubstaff tracked ({hs_name})"

            self._log_to_harvest(
                harvest_project=harvest_name,
                hours=gap,
                note=f"[auto-sync] {note_str}",
                target_date=today,
            )
            synced += 1
            logger.info(
                f"TimeTrackingAgent: synced {gap}h to Harvest '{harvest_name}' "
                f"(Hubstaff '{hs_name}')"
            )

        logger.info(
            f"TimeTrackingAgent: done — {synced} projects synced, {skipped} skipped (no mapping)"
        )

    def _get_harvest_hours_by_project(self, target_date: date) -> Dict[str, float]:
        """Fetch Harvest hours grouped by project name (lowercase).

        Returns {project_name_lower: total_hours}.
        """
        result: Dict[str, float] = defaultdict(float)
        if not self._harvest_configured:
            return result

        try:
            from services.tool_registry import get_registry

            data = get_registry().execute(
                "harvest_get_time_entries",
                {"date": target_date.isoformat()},
            )
            if isinstance(data, dict):
                for entry in data.get("entries", []):
                    proj = entry.get("project", "").lower()
                    result[proj] += entry.get("hours", 0)
        except Exception as e:
            logger.debug(f"TimeTrackingAgent: Harvest entries query failed: {e}")

        return result

    def _log_to_harvest(
        self, harvest_project: str, hours: float, note: str, target_date: date,
    ):
        """Log hours to a specific Harvest project."""
        try:
            from services.tool_registry import get_registry

            result = get_registry().execute("harvest_log_time", {
                "project_name": harvest_project,
                "hours": hours,
                "notes": note,
                "date": target_date.isoformat(),
            })

            if isinstance(result, dict) and result.get("success"):
                logger.info(f"TimeTrackingAgent: logged {hours}h to '{harvest_project}'")
            else:
                logger.warning(f"TimeTrackingAgent: Harvest log failed for '{harvest_project}': {result}")
        except Exception as e:
            logger.warning(f"TimeTrackingAgent: harvest log error: {e}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_agent: Optional[TimeTrackingAgent] = None


def get_time_tracking_agent() -> TimeTrackingAgent:
    global _agent
    if _agent is None:
        _agent = TimeTrackingAgent()
    return _agent
