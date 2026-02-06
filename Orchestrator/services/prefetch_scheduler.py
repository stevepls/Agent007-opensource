"""
Background Prefetch Scheduler

Periodically calls configured read-only tools to warm the ToolCache.
Runs as a daemon thread, started from FastAPI lifespan.
"""

import time
import threading
import os
from typing import Dict, Any, List, Optional


class PrefetchJob:
    """A single prefetch job configuration."""

    __slots__ = ("tool_name", "arguments", "interval_seconds", "last_run", "enabled")

    def __init__(self, tool_name: str, arguments: Dict[str, Any], interval_seconds: int, enabled: bool = True):
        self.tool_name = tool_name
        self.arguments = arguments
        self.interval_seconds = interval_seconds
        self.last_run: float = 0.0
        self.enabled = enabled


# Default prefetch jobs — configurable via env vars
DEFAULT_PREFETCH_JOBS = [
    PrefetchJob("harvest_list_projects", {},                       interval_seconds=900),
    PrefetchJob("harvest_status",        {},                       interval_seconds=120),
    PrefetchJob("calendar_get_events",   {"days_ahead": 2},        interval_seconds=300),
    PrefetchJob("clickup_list_spaces",   {},                       interval_seconds=900),
    PrefetchJob("gmail_get_unread_count", {},                      interval_seconds=120),
]


class PrefetchScheduler:
    """Background scheduler for cache warming."""

    _instance: Optional["PrefetchScheduler"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._jobs: List[PrefetchJob] = self._load_jobs()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def _load_jobs(self) -> List[PrefetchJob]:
        jobs = list(DEFAULT_PREFETCH_JOBS)
        for job in jobs:
            # Override interval: PREFETCH_INTERVAL_HARVEST_LIST_PROJECTS=600
            env_key = f"PREFETCH_INTERVAL_{job.tool_name.upper()}"
            env_val = os.getenv(env_key)
            if env_val and env_val.isdigit():
                job.interval_seconds = int(env_val)
            # Disable: PREFETCH_DISABLE_HARVEST_LIST_PROJECTS=1
            disable_key = f"PREFETCH_DISABLE_{job.tool_name.upper()}"
            if os.getenv(disable_key, "").strip() in ("1", "true", "yes"):
                job.enabled = False
        return jobs

    def start(self):
        if self._running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="prefetch-scheduler")
        self._thread.start()
        self._running = True
        print("[INFO] Prefetch scheduler started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        print("[INFO] Prefetch scheduler stopped")

    def _run_loop(self):
        from services.tool_registry import get_registry

        # Initial delay for app startup
        time.sleep(5)

        while not self._stop_event.is_set():
            now = time.time()

            for job in self._jobs:
                if not job.enabled:
                    continue
                if (now - job.last_run) >= job.interval_seconds:
                    try:
                        registry = get_registry()
                        registry.execute(job.tool_name, dict(job.arguments))
                        job.last_run = now
                    except Exception as e:
                        print(f"[WARN] Prefetch failed for {job.tool_name}: {e}")

            # Check every 30 seconds
            self._stop_event.wait(timeout=30)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "jobs": [
                {
                    "tool": j.tool_name,
                    "interval": j.interval_seconds,
                    "last_run": round(j.last_run, 1) if j.last_run > 0 else None,
                    "age": round(time.time() - j.last_run, 1) if j.last_run > 0 else None,
                    "enabled": j.enabled,
                }
                for j in self._jobs
            ],
        }


def get_prefetch_scheduler() -> PrefetchScheduler:
    return PrefetchScheduler()
