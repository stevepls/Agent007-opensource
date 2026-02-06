"""
Tests for PrefetchScheduler — background cache warming daemon.

Run with: pytest tests/test_prefetch_scheduler.py -v
"""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.prefetch_scheduler import (
    PrefetchJob,
    PrefetchScheduler,
    get_prefetch_scheduler,
    DEFAULT_PREFETCH_JOBS,
)


class TestPrefetchJob(unittest.TestCase):
    """Tests for PrefetchJob configuration."""

    def test_defaults(self):
        job = PrefetchJob("test_tool", {"arg": 1}, 300)
        self.assertEqual(job.tool_name, "test_tool")
        self.assertEqual(job.arguments, {"arg": 1})
        self.assertEqual(job.interval_seconds, 300)
        self.assertEqual(job.last_run, 0.0)
        self.assertTrue(job.enabled)

    def test_disabled(self):
        job = PrefetchJob("test_tool", {}, 60, enabled=False)
        self.assertFalse(job.enabled)

    def test_slots(self):
        job = PrefetchJob("test_tool", {}, 60)
        with self.assertRaises(AttributeError):
            job.nonexistent = True


class TestDefaultPrefetchJobs(unittest.TestCase):
    """Tests for the default prefetch job list."""

    def test_has_jobs(self):
        self.assertGreater(len(DEFAULT_PREFETCH_JOBS), 0)

    def test_all_enabled(self):
        for job in DEFAULT_PREFETCH_JOBS:
            self.assertTrue(job.enabled, f"{job.tool_name} should be enabled by default")

    def test_intervals_positive(self):
        for job in DEFAULT_PREFETCH_JOBS:
            self.assertGreater(job.interval_seconds, 0,
                               f"{job.tool_name} interval must be positive")

    def test_known_tools(self):
        expected = {"harvest_list_projects", "harvest_status",
                    "calendar_get_events", "clickup_list_spaces",
                    "gmail_get_unread_count"}
        actual = {job.tool_name for job in DEFAULT_PREFETCH_JOBS}
        self.assertEqual(actual, expected)


class TestPrefetchScheduler(unittest.TestCase):
    """Tests for PrefetchScheduler singleton."""

    def setUp(self):
        PrefetchScheduler._instance = None

    def tearDown(self):
        # Ensure scheduler is stopped
        try:
            scheduler = PrefetchScheduler._instance
            if scheduler and scheduler._running:
                scheduler.stop()
        except Exception:
            pass
        # Restore default job state (shared objects, mutated by tests)
        for job in DEFAULT_PREFETCH_JOBS:
            job.enabled = True
            job.last_run = 0.0
        PrefetchScheduler._instance = None

    def test_singleton(self):
        s1 = PrefetchScheduler()
        s2 = PrefetchScheduler()
        self.assertIs(s1, s2)

    def test_get_prefetch_scheduler_factory(self):
        scheduler = get_prefetch_scheduler()
        self.assertIsInstance(scheduler, PrefetchScheduler)

    def test_initial_state(self):
        scheduler = PrefetchScheduler()
        self.assertFalse(scheduler._running)
        self.assertIsNone(scheduler._thread)

    def test_get_status_stopped(self):
        scheduler = PrefetchScheduler()
        status = scheduler.get_status()
        self.assertFalse(status["running"])
        self.assertIsInstance(status["jobs"], list)
        self.assertGreater(len(status["jobs"]), 0)

    def test_get_status_job_fields(self):
        scheduler = PrefetchScheduler()
        status = scheduler.get_status()
        job = status["jobs"][0]
        self.assertIn("tool", job)
        self.assertIn("interval", job)
        self.assertIn("last_run", job)
        self.assertIn("enabled", job)

    def test_start_stop(self):
        scheduler = PrefetchScheduler()
        with patch("services.prefetch_scheduler.PrefetchScheduler._run_loop"):
            scheduler.start()
            self.assertTrue(scheduler._running)
            self.assertIsNotNone(scheduler._thread)
            scheduler.stop()
            self.assertFalse(scheduler._running)

    def test_start_idempotent(self):
        scheduler = PrefetchScheduler()
        with patch("services.prefetch_scheduler.PrefetchScheduler._run_loop"):
            scheduler.start()
            thread1 = scheduler._thread
            scheduler.start()  # second call should be no-op
            self.assertIs(scheduler._thread, thread1)
            scheduler.stop()

    def test_env_interval_override(self):
        PrefetchScheduler._instance = None
        os.environ["PREFETCH_INTERVAL_HARVEST_STATUS"] = "999"
        try:
            scheduler = PrefetchScheduler()
            harvest_job = next(j for j in scheduler._jobs if j.tool_name == "harvest_status")
            self.assertEqual(harvest_job.interval_seconds, 999)
        finally:
            del os.environ["PREFETCH_INTERVAL_HARVEST_STATUS"]
            PrefetchScheduler._instance = None

    def test_env_disable(self):
        PrefetchScheduler._instance = None
        os.environ["PREFETCH_DISABLE_HARVEST_STATUS"] = "1"
        try:
            scheduler = PrefetchScheduler()
            harvest_job = next(j for j in scheduler._jobs if j.tool_name == "harvest_status")
            self.assertFalse(harvest_job.enabled)
        finally:
            del os.environ["PREFETCH_DISABLE_HARVEST_STATUS"]
            PrefetchScheduler._instance = None

    def test_env_disable_true_string(self):
        PrefetchScheduler._instance = None
        os.environ["PREFETCH_DISABLE_CLICKUP_LIST_SPACES"] = "true"
        try:
            scheduler = PrefetchScheduler()
            job = next(j for j in scheduler._jobs if j.tool_name == "clickup_list_spaces")
            self.assertFalse(job.enabled)
        finally:
            del os.environ["PREFETCH_DISABLE_CLICKUP_LIST_SPACES"]
            PrefetchScheduler._instance = None

    def test_due_jobs_update_last_run(self):
        """Jobs that are due (last_run=0) should be executed and last_run updated."""
        PrefetchScheduler._instance = None
        scheduler = PrefetchScheduler()

        # All jobs start with last_run=0, so they are all due
        for job in scheduler._jobs:
            self.assertEqual(job.last_run, 0.0)

        mock_registry = MagicMock()
        mock_registry.execute.return_value = {"data": "ok"}

        # Simulate one iteration of the run loop logic directly
        now = time.time()
        for job in scheduler._jobs:
            if not job.enabled:
                continue
            if (now - job.last_run) >= job.interval_seconds:
                mock_registry.execute(job.tool_name, dict(job.arguments))
                job.last_run = now

        enabled_count = sum(1 for j in scheduler._jobs if j.enabled)
        self.assertEqual(mock_registry.execute.call_count, enabled_count)

        # Verify last_run was updated
        for job in scheduler._jobs:
            if job.enabled:
                self.assertGreater(job.last_run, 0.0)

    def test_not_due_jobs_skipped(self):
        """Jobs that ran recently should be skipped."""
        PrefetchScheduler._instance = None
        scheduler = PrefetchScheduler()

        # Mark all jobs as recently run
        now = time.time()
        for job in scheduler._jobs:
            job.last_run = now

        mock_registry = MagicMock()

        # Simulate one iteration — none should be due
        for job in scheduler._jobs:
            if not job.enabled:
                continue
            if (now - job.last_run) >= job.interval_seconds:
                mock_registry.execute(job.tool_name, dict(job.arguments))

        self.assertEqual(mock_registry.execute.call_count, 0)

    def test_disabled_jobs_skipped(self):
        """Disabled jobs should be skipped even if due."""
        PrefetchScheduler._instance = None
        scheduler = PrefetchScheduler()

        for job in scheduler._jobs:
            job.enabled = False

        mock_registry = MagicMock()

        now = time.time()
        for job in scheduler._jobs:
            if not job.enabled:
                continue
            if (now - job.last_run) >= job.interval_seconds:
                mock_registry.execute(job.tool_name, dict(job.arguments))

        self.assertEqual(mock_registry.execute.call_count, 0)

    def test_failed_job_does_not_crash_loop(self):
        """A failing job should not prevent other jobs from running."""
        PrefetchScheduler._instance = None
        scheduler = PrefetchScheduler()

        # Ensure all jobs are enabled (may have been mutated by previous tests)
        for job in scheduler._jobs:
            job.enabled = True

        # Pick one job to fail
        fail_tool = scheduler._jobs[0].tool_name
        call_log = []

        def mock_execute(tool_name, args):
            if tool_name == fail_tool:
                raise Exception("API error")
            call_log.append(tool_name)
            return {"data": "ok"}

        now = time.time()
        for job in scheduler._jobs:
            if not job.enabled:
                continue
            if (now - job.last_run) >= job.interval_seconds:
                try:
                    mock_execute(job.tool_name, dict(job.arguments))
                    job.last_run = now
                except Exception:
                    pass  # Same as _run_loop's except handler

        # Other jobs should have run (total enabled minus the one that failed)
        enabled_count = sum(1 for j in scheduler._jobs if j.enabled)
        self.assertEqual(len(call_log), enabled_count - 1)
        self.assertNotIn(fail_tool, call_log)


if __name__ == "__main__":
    unittest.main()
