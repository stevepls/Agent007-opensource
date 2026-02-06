"""
Tests for ToolCache — in-memory TTL cache for tool results.

Run with: pytest tests/test_tool_cache.py -v
"""

import os
import sys
import time
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tool_cache import (
    ToolCache,
    CacheEntry,
    get_tool_cache,
    make_live_meta,
    DEFAULT_TTL_CONFIG,
    WRITE_TOOLS,
    INVALIDATION_MAP,
)


class TestCacheEntry(unittest.TestCase):
    """Tests for CacheEntry data class."""

    def test_age_seconds(self):
        entry = CacheEntry("test_tool", {}, {"data": 1}, time.time() - 10, 60)
        self.assertAlmostEqual(entry.age_seconds, 10, delta=1)

    def test_is_expired_false(self):
        entry = CacheEntry("test_tool", {}, {"data": 1}, time.time(), 60)
        self.assertFalse(entry.is_expired)

    def test_is_expired_true(self):
        entry = CacheEntry("test_tool", {}, {"data": 1}, time.time() - 120, 60)
        self.assertTrue(entry.is_expired)

    def test_freshness_meta_structure(self):
        entry = CacheEntry("test_tool", {}, {"data": 1}, time.time() - 30, 300)
        meta = entry.freshness_meta()
        self.assertEqual(meta["source"], "cache")
        self.assertIn("cached_at", meta)
        self.assertAlmostEqual(meta["age_seconds"], 30, delta=2)
        self.assertEqual(meta["ttl_seconds"], 300)
        self.assertIn("cached", meta["freshness_label"])

    def test_human_age_seconds(self):
        self.assertIn("s ago", CacheEntry._human_age(30))

    def test_human_age_minutes(self):
        self.assertIn("m ago", CacheEntry._human_age(180))

    def test_human_age_hours(self):
        self.assertIn("h ago", CacheEntry._human_age(7200))


class TestToolCache(unittest.TestCase):
    """Tests for ToolCache singleton."""

    def setUp(self):
        """Reset the singleton for each test."""
        ToolCache._instance = None
        self.cache = ToolCache()

    def tearDown(self):
        ToolCache._instance = None

    def test_singleton(self):
        cache2 = ToolCache()
        self.assertIs(self.cache, cache2)

    def test_get_tool_cache_factory(self):
        cache = get_tool_cache()
        self.assertIsInstance(cache, ToolCache)

    def test_is_cacheable_read_tool(self):
        self.assertTrue(self.cache.is_cacheable("harvest_list_projects"))

    def test_is_cacheable_write_tool(self):
        self.assertFalse(self.cache.is_cacheable("harvest_log_time"))

    def test_is_cacheable_unknown_tool(self):
        self.assertFalse(self.cache.is_cacheable("nonexistent_tool"))

    def test_put_and_get(self):
        self.cache.put("harvest_list_projects", {}, {"projects": [1, 2, 3]})
        result = self.cache.get("harvest_list_projects", {})
        self.assertIsNotNone(result)
        self.assertEqual(result["projects"], [1, 2, 3])
        self.assertIn("_cache_meta", result)
        self.assertEqual(result["_cache_meta"]["source"], "cache")

    def test_get_miss(self):
        result = self.cache.get("harvest_list_projects", {})
        self.assertIsNone(result)

    def test_get_expired(self):
        self.cache.put("harvest_status", {}, {"hours": 5})
        # Force expiration by manipulating the cached entry
        key = self.cache._make_key("harvest_status", {})
        self.cache._cache[key].cached_at = time.time() - 9999
        result = self.cache.get("harvest_status", {})
        self.assertIsNone(result)

    def test_put_skips_write_tools(self):
        self.cache.put("harvest_log_time", {}, {"success": True})
        result = self.cache.get("harvest_log_time", {})
        self.assertIsNone(result)

    def test_put_skips_errors(self):
        self.cache.put("harvest_list_projects", {}, {"error": "API failed"})
        result = self.cache.get("harvest_list_projects", {})
        self.assertIsNone(result)

    def test_different_args_different_keys(self):
        self.cache.put("calendar_get_events", {"days_ahead": 1}, {"events": ["a"]})
        self.cache.put("calendar_get_events", {"days_ahead": 7}, {"events": ["a", "b", "c"]})
        r1 = self.cache.get("calendar_get_events", {"days_ahead": 1})
        r2 = self.cache.get("calendar_get_events", {"days_ahead": 7})
        self.assertEqual(len(r1["events"]), 1)
        self.assertEqual(len(r2["events"]), 3)

    def test_arg_order_independence(self):
        self.cache.put("calendar_get_events", {"a": 1, "b": 2}, {"data": "ok"})
        result = self.cache.get("calendar_get_events", {"b": 2, "a": 1})
        self.assertIsNotNone(result)

    def test_invalidate_specific_tool(self):
        self.cache.put("harvest_list_projects", {}, {"projects": []})
        self.cache.put("harvest_status", {}, {"hours": 0})
        self.cache.invalidate("harvest_list_projects")
        self.assertIsNone(self.cache.get("harvest_list_projects", {}))
        self.assertIsNotNone(self.cache.get("harvest_status", {}))

    def test_invalidate_all(self):
        self.cache.put("harvest_list_projects", {}, {"projects": []})
        self.cache.put("harvest_status", {}, {"hours": 0})
        self.cache.invalidate()
        self.assertIsNone(self.cache.get("harvest_list_projects", {}))
        self.assertIsNone(self.cache.get("harvest_status", {}))

    def test_invalidate_after_write(self):
        self.cache.put("harvest_get_time_entries", {}, {"entries": []})
        self.cache.put("harvest_status", {}, {"hours": 0})
        self.cache.invalidate_after_write("harvest_log_time")
        # Both should be invalidated per INVALIDATION_MAP
        self.assertIsNone(self.cache.get("harvest_get_time_entries", {}))
        self.assertIsNone(self.cache.get("harvest_status", {}))

    def test_invalidate_after_write_no_mapping(self):
        self.cache.put("harvest_list_projects", {}, {"projects": []})
        self.cache.invalidate_after_write("some_random_write")
        # Should not be affected
        self.assertIsNotNone(self.cache.get("harvest_list_projects", {}))

    def test_stats(self):
        self.cache.put("harvest_list_projects", {}, {"projects": []})
        self.cache.get("harvest_list_projects", {})  # hit
        self.cache.get("harvest_list_projects", {"arg": 1})  # miss
        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["entries"], 1)
        self.assertIn("hit_rate", stats)

    def test_stats_initial(self):
        stats = self.cache.get_stats()
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)
        self.assertEqual(stats["hit_rate"], "N/A")

    def test_thread_safety(self):
        """Concurrent puts and gets should not raise."""
        errors = []

        def writer():
            try:
                for i in range(50):
                    self.cache.put("harvest_list_projects", {"i": i}, {"data": i})
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(50):
                    self.cache.get("harvest_list_projects", {"i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_env_ttl_override(self):
        """CACHE_TTL_* env vars should override default TTLs."""
        ToolCache._instance = None
        os.environ["CACHE_TTL_HARVEST_LIST_PROJECTS"] = "42"
        try:
            cache = ToolCache()
            self.assertEqual(cache._ttl_config["harvest_list_projects"], 42)
        finally:
            del os.environ["CACHE_TTL_HARVEST_LIST_PROJECTS"]
            ToolCache._instance = None


class TestMakeLiveMeta(unittest.TestCase):
    """Tests for the make_live_meta helper."""

    def test_structure(self):
        meta = make_live_meta()
        self.assertEqual(meta["source"], "live")
        self.assertEqual(meta["age_seconds"], 0)
        self.assertEqual(meta["freshness_label"], "live data")
        self.assertIn("cached_at", meta)


class TestConfigConstants(unittest.TestCase):
    """Tests for config constants."""

    def test_write_tools_are_frozenset(self):
        self.assertIsInstance(WRITE_TOOLS, frozenset)

    def test_write_tools_not_in_ttl_config(self):
        for tool in WRITE_TOOLS:
            self.assertNotIn(tool, DEFAULT_TTL_CONFIG,
                             f"Write tool {tool} should not have a TTL config")

    def test_invalidation_map_keys_are_write_tools(self):
        for key in INVALIDATION_MAP:
            self.assertIn(key, WRITE_TOOLS,
                          f"Invalidation map key {key} should be a write tool")

    def test_invalidation_map_values_are_read_tools(self):
        for key, targets in INVALIDATION_MAP.items():
            for target in targets:
                self.assertNotIn(target, WRITE_TOOLS,
                                 f"Invalidation target {target} should be a read tool")


if __name__ == "__main__":
    unittest.main()
