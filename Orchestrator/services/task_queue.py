"""
Background Task Queue — FIFO queue for concurrent CrewAI task execution.

Allows the orchestrator to accept new requests while previous tasks run in
background threads.  Completed results are reported to the user on their
next interaction (FIFO order).

Thread-local storage associates each worker thread with its own
ProgressTracker so the global CrewAI event bus can route events to the
correct task.
"""

import collections
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.progress_tracker import ProgressTracker


# ---------------------------------------------------------------------------
# Thread-local tracker (used by CrewAI event handlers)
# ---------------------------------------------------------------------------

_thread_local = threading.local()


def get_current_tracker() -> Optional[ProgressTracker]:
    """Return the ProgressTracker for the current worker thread, or None."""
    return getattr(_thread_local, "current_tracker", None)


def set_current_tracker(tracker: Optional[ProgressTracker]):
    """Associate a ProgressTracker with the current thread."""
    _thread_local.current_tracker = tracker


# ---------------------------------------------------------------------------
# BackgroundTask data structure
# ---------------------------------------------------------------------------

@dataclass
class BackgroundTask:
    id: str
    user_request: str
    context: Optional[str]
    session_id: str
    status: str = "queued"  # queued | running | completed | failed
    result: Optional[str] = None
    error: Optional[str] = None
    progress_events: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    reported: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_request": self.user_request[:200],
            "status": self.status,
            "result": self.result[:500] if self.result else None,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "reported": self.reported,
            "event_count": len(self.progress_events),
        }


# ---------------------------------------------------------------------------
# BackgroundTaskQueue singleton
# ---------------------------------------------------------------------------

class BackgroundTaskQueue:
    """Thread-safe singleton managing a FIFO queue of background CrewAI tasks."""

    _instance: Optional["BackgroundTaskQueue"] = None
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._tasks: Dict[str, BackgroundTask] = {}
                    inst._task_order: collections.deque = collections.deque()
                    inst._trackers: Dict[str, ProgressTracker] = {}
                    inst._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="crew-bg")
                    inst._lock = threading.Lock()
                    cls._instance = inst
        return cls._instance

    # -- public API ---------------------------------------------------------

    def submit(self, user_request: str, context: Optional[str], session_id: str) -> str:
        """Submit a new task to the background queue.  Returns task_id."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        task = BackgroundTask(
            id=task_id,
            user_request=user_request,
            context=context,
            session_id=session_id,
        )
        tracker = ProgressTracker(session_id)

        with self._lock:
            self._tasks[task_id] = task
            self._task_order.append(task_id)
            self._trackers[task_id] = tracker

        self._executor.submit(self._run_task, task, tracker)
        return task_id

    def get_task_tracker(self, task_id: str) -> Optional[ProgressTracker]:
        """Return the ProgressTracker for a given task."""
        with self._lock:
            return self._trackers.get(task_id)

    def get_unreported_updates(self) -> List[BackgroundTask]:
        """Return completed/failed tasks not yet reported, in FIFO order."""
        with self._lock:
            results = []
            for tid in self._task_order:
                task = self._tasks.get(tid)
                if task and task.status in ("completed", "failed") and not task.reported:
                    results.append(task)
            return results

    def mark_reported(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.reported = True

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[str] = None) -> List[BackgroundTask]:
        with self._lock:
            tasks = [self._tasks[tid] for tid in self._task_order if tid in self._tasks]
            if status:
                tasks = [t for t in tasks if t.status == status]
            return tasks

    def get_running_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == "running")

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running/queued task via its ProgressTracker."""
        with self._lock:
            tracker = self._trackers.get(task_id)
            task = self._tasks.get(task_id)
        if tracker and task and task.status in ("queued", "running"):
            tracker.cancel()
            return True
        return False

    def get_status(self) -> dict:
        with self._lock:
            counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0}
            for t in self._tasks.values():
                counts[t.status] = counts.get(t.status, 0) + 1
            return {
                "total": len(self._tasks),
                "unreported": sum(1 for t in self._tasks.values() if t.status in ("completed", "failed") and not t.reported),
                **counts,
            }

    def shutdown(self):
        """Gracefully shut down the thread pool."""
        self._executor.shutdown(wait=False)

    # -- internal -----------------------------------------------------------

    def _run_task(self, task: BackgroundTask, tracker: ProgressTracker):
        """Execute a single task in a background thread."""
        set_current_tracker(tracker)
        task.status = "running"
        task.started_at = time.time()

        try:
            from crews.orchestrator_crew import run_orchestrator_task

            result = run_orchestrator_task(
                task.user_request,
                task.context,
                task.session_id,
                progress_tracker=tracker,
            )

            if result.get("status") == "success":
                task.status = "completed"
                task.result = result.get("result", "")
            elif result.get("status") == "cancelled":
                task.status = "failed"
                task.error = "Cancelled by user"
            else:
                task.status = "failed"
                task.error = result.get("error", "Unknown error")

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
        finally:
            task.completed_at = time.time()
            # Drain remaining progress events for potential replay
            import queue as _q
            while True:
                try:
                    evt = tracker.progress_queue.get_nowait()
                    if evt is None:
                        break
                    task.progress_events.append(evt)
                except _q.Empty:
                    break
            set_current_tracker(None)


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------

def get_task_queue() -> BackgroundTaskQueue:
    """Return the singleton BackgroundTaskQueue."""
    return BackgroundTaskQueue()
