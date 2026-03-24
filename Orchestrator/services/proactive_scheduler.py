"""
Proactive Agent Scheduler

Runs background agents on a schedule and feeds their results into the
BriefingEngine so the orchestrator can brief Steve on what happened.

Agents:
- ScaffoldingAgent: every 15 min — processes "Pending AI Scaffolding" tasks
- TicketManager: every 10 min — scans for duplicate/related tickets

Follows the same daemon-thread pattern as PrefetchScheduler.
"""

import json
import logging
import os
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("proactive_scheduler")

# Persist results to disk so briefing engine can read them
DATA_DIR = Path(__file__).parent.parent / "data" / "proactive"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AgentResult:
    """Result from a proactive agent run."""
    agent: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items_processed: int = 0
    items_found: int = 0
    summary: str = ""
    details: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "timestamp": self.timestamp,
            "items_processed": self.items_processed,
            "items_found": self.items_found,
            "summary": self.summary,
            "details": self.details,
            "error": self.error,
        }


def _run_scaffolding_agent() -> AgentResult:
    """Run the scaffolding agent for all configured projects."""
    from agents.scaffolding.agent import ScaffoldingAgent, ScaffoldingConfig
    from agents.scaffolding.config import PROJECT_CONFIGS

    result = AgentResult(agent="scaffolding")
    all_task_results = []

    for project_key in PROJECT_CONFIGS:
        try:
            config = ScaffoldingConfig.from_project_key(project_key)
            agent = ScaffoldingAgent(config)
            task_results = agent.run()

            for tr in task_results:
                all_task_results.append({
                    "project": project_key,
                    "task_id": tr.task_id,
                    "task_name": tr.task_name,
                    "status": tr.status,
                    "branch": getattr(tr, "branch_name", None),
                    "error": tr.error,
                })
        except Exception as e:
            logger.error(f"Scaffolding agent failed for {project_key}: {e}")
            all_task_results.append({
                "project": project_key,
                "error": str(e),
            })

    result.items_processed = len(all_task_results)
    result.items_found = sum(1 for r in all_task_results if r.get("status") == "success")
    result.details = all_task_results

    if result.items_found > 0:
        result.summary = f"Scaffolded {result.items_found} task(s) across {len(PROJECT_CONFIGS)} project(s)"
    elif result.items_processed > 0:
        result.summary = f"Checked {len(PROJECT_CONFIGS)} project(s), no pending scaffolding tasks"
    else:
        result.summary = "No projects to check"

    return result


def _run_ticket_scan() -> AgentResult:
    """Run the ticket manager to scan for duplicates and stale tickets."""
    from agents.ticket_manager import get_ticket_manager

    result = AgentResult(agent="ticket_manager")

    try:
        tm = get_ticket_manager()
        # Fetch recent tickets from both ClickUp and Zendesk
        recent = tm.fetch_recent_tickets(days_back=7)
        result.items_processed = len(recent)

        if not recent:
            result.summary = "No recent tickets to scan"
            return result

        # Group by subject similarity — check each ticket against the rest
        duplicates_found = []
        seen_ids = set()

        for i, ticket in enumerate(recent):
            if ticket["id"] in seen_ids:
                continue

            # Compare against remaining tickets
            for j in range(i + 1, len(recent)):
                other = recent[j]
                if other["id"] in seen_ids:
                    continue

                try:
                    analysis = tm.analyze_with_llm(
                        ticket,
                        [other],
                    )
                    if analysis.is_duplicate:
                        duplicates_found.append({
                            "ticket_a": {
                                "id": ticket["id"],
                                "type": ticket["type"],
                                "subject": ticket["subject"],
                            },
                            "ticket_b": {
                                "id": other["id"],
                                "type": other["type"],
                                "subject": other["subject"],
                            },
                            "confidence": analysis.duplicate_confidence.value
                                if analysis.duplicate_confidence else "unknown",
                            "reason": analysis.reasoning,
                        })
                        seen_ids.add(other["id"])
                except Exception as e:
                    logger.warning(f"Duplicate check failed: {e}")
                    continue

        result.items_found = len(duplicates_found)
        result.details = duplicates_found

        if duplicates_found:
            result.summary = f"Found {len(duplicates_found)} potential duplicate ticket pair(s) in {len(recent)} recent tickets"
        else:
            result.summary = f"Scanned {len(recent)} recent tickets — no duplicates found"

    except Exception as e:
        result.error = str(e)
        result.summary = f"Ticket scan failed: {e}"
        logger.error(f"Ticket scan error: {e}\n{traceback.format_exc()}")

    return result


def _save_result(result: AgentResult):
    """Persist result to disk and push to briefing engine."""
    # Save to disk
    result_file = DATA_DIR / f"{result.agent}_latest.json"
    result_file.write_text(json.dumps(result.to_dict(), indent=2))

    # Also append to history (keep last 50 runs per agent)
    history_file = DATA_DIR / f"{result.agent}_history.json"
    try:
        history = json.loads(history_file.read_text()) if history_file.exists() else []
    except (json.JSONDecodeError, OSError):
        history = []
    history.append(result.to_dict())
    history = history[-50:]  # Keep last 50
    history_file.write_text(json.dumps(history, indent=2))

    # Push to briefing engine
    _push_to_briefing(result)


def _push_to_briefing(result: AgentResult):
    """Convert agent result into BriefingItems for the orchestrator."""
    try:
        from services.briefing import (
            get_briefing_engine,
            BriefingItem,
            Priority,
            ItemType,
        )
        engine = get_briefing_engine()

        if result.error:
            engine._cached_items.append(BriefingItem(
                id=f"proactive-{result.agent}-error-{int(time.time())}",
                type=ItemType.ALERT,
                priority=Priority.HIGH,
                title=f"{result.agent.replace('_', ' ').title()} Agent Error",
                description=result.error,
                source=f"proactive/{result.agent}",
            ))
            return

        # Scaffolding results
        if result.agent == "scaffolding" and result.items_found > 0:
            for detail in result.details:
                if detail.get("status") == "success":
                    engine._cached_items.append(BriefingItem(
                        id=f"scaffolding-{detail.get('task_id', 'unknown')}",
                        type=ItemType.UPDATE,
                        priority=Priority.MEDIUM,
                        title=f"Scaffolded: {detail.get('task_name', 'Unknown task')}",
                        description=f"Branch `{detail.get('branch', '?')}` created for {detail.get('project', '?')}. Task moved to To Do.",
                        source="proactive/scaffolding",
                        metadata=detail,
                    ))

        # Ticket manager duplicate results
        if result.agent == "ticket_manager" and result.items_found > 0:
            engine._cached_items.append(BriefingItem(
                id=f"ticket-duplicates-{int(time.time())}",
                type=ItemType.ALERT,
                priority=Priority.HIGH if result.items_found >= 3 else Priority.MEDIUM,
                title=f"{result.items_found} Potential Duplicate Ticket(s)",
                description="\n".join(
                    f"• {d['ticket_a']['subject']} ↔ {d['ticket_b']['subject']} ({d.get('confidence', '?')})"
                    for d in result.details[:5]
                ),
                source="proactive/ticket_manager",
                metadata={"duplicates": result.details},
            ))

        # Force cache refresh so next briefing picks these up
        engine._last_refresh = None

    except Exception as e:
        logger.warning(f"Failed to push {result.agent} result to briefing: {e}")


@dataclass
class ProactiveJob:
    """A scheduled proactive agent job."""
    name: str
    runner: Callable[[], AgentResult]
    interval_seconds: int
    last_run: float = 0.0
    enabled: bool = True
    last_result: Optional[AgentResult] = field(default=None, repr=False)


DEFAULT_PROACTIVE_JOBS = [
    ProactiveJob(
        name="scaffolding",
        runner=_run_scaffolding_agent,
        interval_seconds=int(os.getenv("PROACTIVE_SCAFFOLDING_INTERVAL", "900")),  # 15 min
    ),
    ProactiveJob(
        name="ticket_scan",
        runner=_run_ticket_scan,
        interval_seconds=int(os.getenv("PROACTIVE_TICKET_SCAN_INTERVAL", "600")),  # 10 min
    ),
]


class ProactiveScheduler:
    """Background scheduler for proactive agent jobs."""

    _instance: Optional["ProactiveScheduler"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._jobs: List[ProactiveJob] = self._load_jobs()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def _load_jobs(self) -> List[ProactiveJob]:
        jobs = list(DEFAULT_PROACTIVE_JOBS)
        for job in jobs:
            # Disable: PROACTIVE_DISABLE_SCAFFOLDING=1
            disable_key = f"PROACTIVE_DISABLE_{job.name.upper()}"
            if os.getenv(disable_key, "").strip() in ("1", "true", "yes"):
                job.enabled = False
                logger.info(f"Proactive job '{job.name}' disabled via {disable_key}")
        return jobs

    def start(self):
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="proactive-scheduler"
        )
        self._thread.start()
        self._running = True
        enabled = [j.name for j in self._jobs if j.enabled]
        print(f"[INFO] Proactive scheduler started — agents: {', '.join(enabled)}")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._running = False
        print("[INFO] Proactive scheduler stopped")

    def _run_loop(self):
        # Wait for app startup
        time.sleep(15)

        while not self._stop_event.is_set():
            now = time.time()

            for job in self._jobs:
                if not job.enabled:
                    continue
                if (now - job.last_run) < job.interval_seconds:
                    continue

                logger.info(f"Running proactive job: {job.name}")
                try:
                    result = job.runner()
                    job.last_result = result
                    job.last_run = now
                    _save_result(result)

                    if result.error:
                        logger.error(f"Proactive job '{job.name}' errored: {result.error}")
                    else:
                        logger.info(f"Proactive job '{job.name}' done: {result.summary}")

                except Exception as e:
                    logger.error(f"Proactive job '{job.name}' crashed: {e}\n{traceback.format_exc()}")
                    job.last_run = now  # Don't retry immediately on crash
                    _save_result(AgentResult(
                        agent=job.name,
                        error=str(e),
                        summary=f"Job crashed: {e}",
                    ))

            # Check every 60 seconds
            self._stop_event.wait(timeout=60)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "jobs": [
                {
                    "name": j.name,
                    "interval": j.interval_seconds,
                    "last_run": round(j.last_run, 1) if j.last_run > 0 else None,
                    "age": round(time.time() - j.last_run, 1) if j.last_run > 0 else None,
                    "enabled": j.enabled,
                    "last_summary": j.last_result.summary if j.last_result else None,
                }
                for j in self._jobs
            ],
        }

    def get_latest_results(self) -> Dict[str, Any]:
        """Get latest results from all agents for briefing."""
        results = {}
        for job in self._jobs:
            result_file = DATA_DIR / f"{job.name}_latest.json"
            if result_file.exists():
                try:
                    results[job.name] = json.loads(result_file.read_text())
                except (json.JSONDecodeError, OSError):
                    pass
        return results


_scheduler: Optional[ProactiveScheduler] = None


def get_proactive_scheduler() -> ProactiveScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ProactiveScheduler()
    return _scheduler
