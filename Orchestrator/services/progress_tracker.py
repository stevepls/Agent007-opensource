"""
Progress Tracker for Real-Time Agent Activity Streaming

Thread-safe progress tracker using queue.Queue + threading.Event.
CrewAI event handlers push events to the queue, which the API stream drains.
"""

import queue
import threading
import time
from typing import Dict, Optional, Any

# Module-level registry of active trackers
_active_trackers: Dict[str, "ProgressTracker"] = {}
_registry_lock = threading.Lock()


class ProgressTracker:
    """Track progress of a CrewAI crew execution for real-time streaming."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.progress_queue: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self._started_at = time.time()

    def emit(self, event_type: str, agent: str = "", message: str = "", tool: str = "", output: str = "", cache_source: str = ""):
        """Push a progress event to the queue."""
        event = {
            "type": event_type,
            "agent": agent,
            "message": message,
            "tool": tool,
            "output": output,
            "timestamp": time.time() - self._started_at,
        }
        if cache_source:
            event["cache_source"] = cache_source
        self.progress_queue.put(event)

    def cancel(self):
        """Signal cancellation to the running crew."""
        self.cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def finish(self):
        """Send sentinel to indicate crew is done."""
        self.progress_queue.put(None)


def register_tracker(session_id: str, tracker: "ProgressTracker"):
    with _registry_lock:
        _active_trackers[session_id] = tracker


def unregister_tracker(session_id: str):
    with _registry_lock:
        _active_trackers.pop(session_id, None)


def get_tracker(session_id: str) -> Optional["ProgressTracker"]:
    with _registry_lock:
        return _active_trackers.get(session_id)
