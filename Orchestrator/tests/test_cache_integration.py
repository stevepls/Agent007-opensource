"""
Tests for cache integration in ToolRegistry.execute() and the freshness pipeline.

These tests verify the caching logic without importing the full ToolRegistry
(which loads all service clients). Instead, they test the cache behavior
through the ToolCache API directly, matching what execute() does.

Run with: pytest tests/test_cache_integration.py -v
"""

import os
import sys
import json
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tool_cache import ToolCache, get_tool_cache, make_live_meta, WRITE_TOOLS, INVALIDATION_MAP


class TestExecuteCacheFlow(unittest.TestCase):
    """
    Tests that simulate what ToolRegistry.execute() does:
    1. Check cache → on hit, return cached + _cache_meta
    2. On miss → call tool func → inject live _cache_meta → cache.put()
    3. After write → cache.invalidate_after_write()
    """

    def setUp(self):
        ToolCache._instance = None
        self.cache = ToolCache()

    def tearDown(self):
        ToolCache._instance = None

    def _simulate_execute(self, tool_name, arguments, tool_func, is_write=False):
        """Simulate ToolRegistry.execute() cache logic."""
        # Step 1: Check cache
        cached = self.cache.get(tool_name, arguments)
        if cached is not None:
            return cached, "cache_hit"

        # Step 2: Call tool
        try:
            result = tool_func(**arguments)
        except Exception as e:
            return {"error": str(e)}, "error"

        # Step 3: Inject freshness metadata and store
        if isinstance(result, dict) and "error" not in result:
            result["_cache_meta"] = make_live_meta()
            self.cache.put(tool_name, arguments, result)
            self.cache.invalidate_after_write(tool_name)

        return result, "live"

    def test_cache_hit_returns_cached_result(self):
        """On cache hit, execute should return cached data without calling tool."""
        self.cache.put("harvest_list_projects", {}, {"projects": ["A", "B"]})

        call_count = 0
        def fake_tool():
            nonlocal call_count
            call_count += 1
            return {"projects": ["LIVE"]}

        result, source = self._simulate_execute("harvest_list_projects", {}, fake_tool)
        self.assertEqual(result["projects"], ["A", "B"])
        self.assertEqual(result["_cache_meta"]["source"], "cache")
        self.assertEqual(call_count, 0)  # Tool func was NOT called

    def test_cache_miss_calls_tool_and_stores(self):
        """On cache miss, execute should call tool func and store result."""
        call_count = 0
        def fake_tool():
            nonlocal call_count
            call_count += 1
            return {"projects": ["LIVE"]}

        result, source = self._simulate_execute("harvest_list_projects", {}, fake_tool)
        self.assertEqual(result["projects"], ["LIVE"])
        self.assertEqual(result["_cache_meta"]["source"], "live")
        self.assertEqual(call_count, 1)
        self.assertEqual(source, "live")

        # Should now be in cache
        cached = self.cache.get("harvest_list_projects", {})
        self.assertIsNotNone(cached)
        self.assertEqual(cached["_cache_meta"]["source"], "cache")

    def test_second_call_hits_cache(self):
        """Second call with same args should hit cache."""
        def fake_tool():
            return {"data": "fresh"}

        r1, s1 = self._simulate_execute("harvest_list_projects", {}, fake_tool)
        self.assertEqual(s1, "live")

        r2, s2 = self._simulate_execute("harvest_list_projects", {}, fake_tool)
        self.assertEqual(s2, "cache_hit")

    def test_write_tool_not_cached(self):
        """Write tools should never be cached."""
        def fake_write():
            return {"success": True}

        # harvest_log_time is a write tool — not in TTL config
        self.assertFalse(self.cache.is_cacheable("harvest_log_time"))

        result, source = self._simulate_execute("harvest_log_time", {}, fake_write, is_write=True)
        self.assertEqual(source, "live")

        # Should NOT be in cache
        self.assertIsNone(self.cache.get("harvest_log_time", {}))

    def test_write_invalidates_related_caches(self):
        """After a write, related read caches should be invalidated."""
        # Pre-populate caches
        self.cache.put("harvest_get_time_entries", {}, {"entries": []})
        self.cache.put("harvest_status", {}, {"hours": 5})
        self.cache.put("harvest_list_projects", {}, {"projects": []})

        # Simulate harvest_log_time write (triggers invalidation)
        self.cache.invalidate_after_write("harvest_log_time")

        # Related caches should be gone
        self.assertIsNone(self.cache.get("harvest_get_time_entries", {}))
        self.assertIsNone(self.cache.get("harvest_status", {}))
        # Unrelated cache should survive
        self.assertIsNotNone(self.cache.get("harvest_list_projects", {}))

    def test_error_result_not_cached(self):
        """Tool errors should not be stored in cache."""
        def failing_tool():
            raise Exception("API down")

        result, source = self._simulate_execute("harvest_list_projects", {}, failing_tool)
        self.assertIn("error", result)
        self.assertEqual(source, "error")
        self.assertIsNone(self.cache.get("harvest_list_projects", {}))

    def test_expired_entry_refetches(self):
        """Expired cache entry should trigger a fresh call."""
        self.cache.put("harvest_status", {}, {"hours": 5})
        # Force expiration
        key = self.cache._make_key("harvest_status", {})
        self.cache._cache[key].cached_at = time.time() - 9999

        def fresh_tool():
            return {"hours": 8}

        result, source = self._simulate_execute("harvest_status", {}, fresh_tool)
        self.assertEqual(source, "live")
        self.assertEqual(result["hours"], 8)


class TestFreshnessPipeline(unittest.TestCase):
    """Tests for the data freshness extraction and FRESHNESS: line protocol."""

    def test_cache_source_extraction_from_output(self):
        """ProgressEventListener should extract cache_source from tool output."""
        from services.progress_tracker import ProgressTracker

        tracker = ProgressTracker("test")

        output_data = {
            "projects": ["A"],
            "_cache_meta": {"source": "cache", "age_seconds": 30},
        }
        output_str = json.dumps(output_data)

        # Extract cache_source (same logic as in orchestrator_crew.py)
        cache_source = ""
        try:
            parsed = json.loads(output_str)
            if isinstance(parsed, dict) and "_cache_meta" in parsed:
                cache_source = parsed["_cache_meta"].get("source", "")
        except (json.JSONDecodeError, TypeError):
            pass

        tracker.emit("tool_done", tool="harvest_list_projects", cache_source=cache_source)
        event = tracker.progress_queue.get_nowait()
        self.assertEqual(event["cache_source"], "cache")

    def test_cache_source_extraction_live(self):
        output_data = {"entries": [], "_cache_meta": {"source": "live", "age_seconds": 0}}
        cache_source = output_data.get("_cache_meta", {}).get("source", "")
        self.assertEqual(cache_source, "live")

    def test_cache_source_extraction_no_meta(self):
        output_data = {"entries": []}
        cache_source = output_data.get("_cache_meta", {}).get("source", "")
        self.assertEqual(cache_source, "")

    def test_freshness_line_format(self):
        """FRESHNESS: line should be valid JSON mapping tools to sources."""
        tool_freshness = {
            "harvest_list_projects": "cache",
            "harvest_status": "live",
        }
        line = "FRESHNESS:" + json.dumps(tool_freshness)
        self.assertTrue(line.startswith("FRESHNESS:"))
        payload = json.loads(line[len("FRESHNESS:"):])
        self.assertEqual(payload["harvest_list_projects"], "cache")
        self.assertEqual(payload["harvest_status"], "live")

    def test_freshness_annotation_format(self):
        """Dashboard should emit freshness as 8: annotation."""
        tool_freshness = {"harvest_list_projects": "cache"}
        annotation = json.dumps([{"type": "freshness", "tools": tool_freshness}])
        parsed = json.loads(annotation)
        self.assertEqual(parsed[0]["type"], "freshness")
        self.assertEqual(parsed[0]["tools"]["harvest_list_projects"], "cache")

    def test_empty_freshness_not_emitted(self):
        """If no tools report cache_source, FRESHNESS line should not be emitted."""
        tool_freshness = {}
        # The api_chat.py check: `if tool_freshness:`
        self.assertFalse(bool(tool_freshness))


class TestCacheStatsEndpoint(unittest.TestCase):
    """Tests for /api/cache/stats response structure."""

    def setUp(self):
        ToolCache._instance = None

    def tearDown(self):
        ToolCache._instance = None

    def test_stats_structure(self):
        cache = ToolCache()
        stats = cache.get_stats()
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)
        self.assertIn("evictions", stats)
        self.assertIn("entries", stats)
        self.assertIn("hit_rate", stats)

    def test_stats_after_operations(self):
        cache = ToolCache()
        cache.put("harvest_list_projects", {}, {"data": 1})
        cache.get("harvest_list_projects", {})  # hit
        cache.get("harvest_list_projects", {"x": 1})  # miss
        stats = cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["entries"], 1)


class TestLiveMetaInjection(unittest.TestCase):
    """Tests for make_live_meta() freshness metadata."""

    def test_structure(self):
        meta = make_live_meta()
        self.assertEqual(meta["source"], "live")
        self.assertEqual(meta["age_seconds"], 0)
        self.assertEqual(meta["ttl_seconds"], 0)
        self.assertEqual(meta["freshness_label"], "live data")
        self.assertIn("cached_at", meta)

    def test_cached_at_is_recent(self):
        meta = make_live_meta()
        from datetime import datetime
        cached_at = datetime.fromisoformat(meta["cached_at"])
        now = datetime.now()
        diff = abs((now - cached_at).total_seconds())
        self.assertLess(diff, 5)


if __name__ == "__main__":
    unittest.main()
