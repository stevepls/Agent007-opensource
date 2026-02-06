"""
Tests for ProgressTracker — thread-safe progress event streaming.

Run with: pytest tests/test_progress_tracker.py -v
"""

import os
import sys
import queue
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.progress_tracker import (
    ProgressTracker,
    register_tracker,
    unregister_tracker,
    get_tracker,
)


class TestProgressTracker(unittest.TestCase):
    """Tests for ProgressTracker."""

    def test_emit_basic(self):
        tracker = ProgressTracker("test-session")
        tracker.emit("tool_start", agent="Orchestrator", tool="harvest_status")
        event = tracker.progress_queue.get_nowait()
        self.assertEqual(event["type"], "tool_start")
        self.assertEqual(event["agent"], "Orchestrator")
        self.assertEqual(event["tool"], "harvest_status")
        self.assertIn("timestamp", event)

    def test_emit_cache_source(self):
        tracker = ProgressTracker("test-session")
        tracker.emit("tool_done", tool="harvest_status", cache_source="cache")
        event = tracker.progress_queue.get_nowait()
        self.assertEqual(event["cache_source"], "cache")

    def test_emit_no_cache_source_omits_key(self):
        tracker = ProgressTracker("test-session")
        tracker.emit("tool_done", tool="harvest_status")
        event = tracker.progress_queue.get_nowait()
        self.assertNotIn("cache_source", event)

    def test_emit_live_cache_source(self):
        tracker = ProgressTracker("test-session")
        tracker.emit("tool_done", tool="harvest_log_time", cache_source="live")
        event = tracker.progress_queue.get_nowait()
        self.assertEqual(event["cache_source"], "live")

    def test_cancel(self):
        tracker = ProgressTracker("test-session")
        self.assertFalse(tracker.is_cancelled)
        tracker.cancel()
        self.assertTrue(tracker.is_cancelled)

    def test_finish_sends_sentinel(self):
        tracker = ProgressTracker("test-session")
        tracker.finish()
        event = tracker.progress_queue.get_nowait()
        self.assertIsNone(event)

    def test_timestamp_relative(self):
        tracker = ProgressTracker("test-session")
        tracker.emit("thinking", message="test")
        event = tracker.progress_queue.get_nowait()
        self.assertGreaterEqual(event["timestamp"], 0)
        self.assertLess(event["timestamp"], 5)  # Should be less than 5s

    def test_queue_ordering(self):
        tracker = ProgressTracker("test-session")
        tracker.emit("tool_start", tool="a")
        tracker.emit("tool_done", tool="a")
        tracker.emit("tool_start", tool="b")
        e1 = tracker.progress_queue.get_nowait()
        e2 = tracker.progress_queue.get_nowait()
        e3 = tracker.progress_queue.get_nowait()
        self.assertEqual(e1["type"], "tool_start")
        self.assertEqual(e1["tool"], "a")
        self.assertEqual(e2["type"], "tool_done")
        self.assertEqual(e3["tool"], "b")

    def test_thread_safe_emit(self):
        """Multiple threads emitting should not raise."""
        tracker = ProgressTracker("test-session")
        errors = []

        def emitter(n):
            try:
                for i in range(20):
                    tracker.emit("tool_start", tool=f"tool_{n}_{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emitter, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        # Should have 100 events total
        count = 0
        while not tracker.progress_queue.empty():
            tracker.progress_queue.get_nowait()
            count += 1
        self.assertEqual(count, 100)


class TestTrackerRegistry(unittest.TestCase):
    """Tests for the module-level tracker registry."""

    def setUp(self):
        # Clean registry
        from services.progress_tracker import _active_trackers
        _active_trackers.clear()

    def test_register_and_get(self):
        tracker = ProgressTracker("session-1")
        register_tracker("session-1", tracker)
        retrieved = get_tracker("session-1")
        self.assertIs(retrieved, tracker)

    def test_get_nonexistent(self):
        self.assertIsNone(get_tracker("nonexistent"))

    def test_unregister(self):
        tracker = ProgressTracker("session-1")
        register_tracker("session-1", tracker)
        unregister_tracker("session-1")
        self.assertIsNone(get_tracker("session-1"))

    def test_unregister_nonexistent(self):
        # Should not raise
        unregister_tracker("nonexistent")

    def test_multiple_sessions(self):
        t1 = ProgressTracker("s1")
        t2 = ProgressTracker("s2")
        register_tracker("s1", t1)
        register_tracker("s2", t2)
        self.assertIs(get_tracker("s1"), t1)
        self.assertIs(get_tracker("s2"), t2)


if __name__ == "__main__":
    unittest.main()
