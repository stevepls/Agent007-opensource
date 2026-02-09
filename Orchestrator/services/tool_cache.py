"""
In-memory TTL Cache for Tool Results

Reduces API round-trips by caching read-only tool results.
Cache is keyed on (tool_name, frozen_sorted_args).
Each tool has a configurable TTL. All responses carry freshness metadata.
"""

import time
import threading
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime


class CacheEntry:
    """A single cached tool result."""

    __slots__ = ("tool_name", "arguments", "result", "cached_at", "ttl_seconds")

    def __init__(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any],
                 cached_at: float, ttl_seconds: int):
        self.tool_name = tool_name
        self.arguments = arguments
        self.result = result
        self.cached_at = cached_at
        self.ttl_seconds = ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.cached_at

    @property
    def is_expired(self) -> bool:
        return self.age_seconds > self.ttl_seconds

    def freshness_meta(self) -> Dict[str, Any]:
        age = self.age_seconds
        return {
            "source": "cache",
            "cached_at": datetime.fromtimestamp(self.cached_at).isoformat(),
            "age_seconds": round(age, 1),
            "ttl_seconds": self.ttl_seconds,
            "freshness_label": self._human_age(age),
        }

    @staticmethod
    def _human_age(age: float) -> str:
        if age < 60:
            return f"cached {int(age)}s ago"
        elif age < 3600:
            return f"cached {int(age / 60)}m ago"
        return f"cached {age / 3600:.1f}h ago"


# Default TTLs per tool (seconds). Override via CACHE_TTL_<TOOL_NAME> env vars.
DEFAULT_TTL_CONFIG: Dict[str, int] = {
    # Slow-changing reference data (10-15 min)
    "harvest_list_projects":      900,
    "clickup_list_spaces":        900,
    "clickup_browse_workspace":   900,

    # Moderate data (3-5 min)
    "calendar_get_events":        300,
    "clickup_list_tasks":         180,
    "zendesk_list_tickets":       180,
    "docs_list_files":            300,

    # Frequently changing (1-2 min)
    "harvest_get_time_entries":   120,
    "harvest_status":              60,
    "gmail_get_unread_count":      90,
    "gmail_search":               120,
    "slack_get_recent_messages":   60,
    "slack_search_messages":       60,
    "notification_fetch_all":     120,
    "notification_search":        120,
    "airtable_get_tickets":       180,
    "airtable_search_ticket":     120,
}

# Tools that must NEVER be cached (write operations / side effects)
WRITE_TOOLS = frozenset({
    "harvest_log_time", "harvest_start_timer", "harvest_stop_timer",
    "clickup_create_task", "clickup_update_task", "clickup_add_comment",
    "zendesk_create_ticket",
    "slack_post_message", "slack_reply_to_thread", "slack_send_dm",
    "gmail_create_draft",
    "sheets_update_range", "sheets_append_rows",
    "memory_remember",
    "run_dev_task",
    "asana_pull_to_clickup",
    "generate_timesheet", "generate_draft_invoice",
})

# After a write succeeds, invalidate these read caches
INVALIDATION_MAP: Dict[str, List[str]] = {
    "harvest_log_time": ["harvest_get_time_entries", "harvest_status"],
    "harvest_start_timer": ["harvest_status", "harvest_get_time_entries"],
    "harvest_stop_timer": ["harvest_status", "harvest_get_time_entries"],
    "clickup_create_task": ["clickup_list_tasks"],
    "clickup_update_task": ["clickup_list_tasks"],
    "zendesk_create_ticket": ["zendesk_list_tickets"],
    "sheets_update_range": ["sheets_read_range"],
    "sheets_append_rows": ["sheets_read_range"],
}


class ToolCache:
    """Thread-safe in-memory TTL cache for tool results."""

    _instance: Optional["ToolCache"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._ttl_config = self._load_ttl_config()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def _load_ttl_config(self) -> Dict[str, int]:
        config = dict(DEFAULT_TTL_CONFIG)
        for tool_name in list(config):
            env_key = f"CACHE_TTL_{tool_name.upper()}"
            env_val = os.getenv(env_key)
            if env_val and env_val.isdigit():
                config[tool_name] = int(env_val)
        return config

    @staticmethod
    def _make_key(tool_name: str, arguments: Dict[str, Any]) -> str:
        sorted_args = json.dumps(arguments, sort_keys=True, default=str)
        return f"{tool_name}:{sorted_args}"

    def is_cacheable(self, tool_name: str) -> bool:
        if tool_name in WRITE_TOOLS:
            return False
        return tool_name in self._ttl_config

    def get(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached result if fresh. Returns None on miss/expired."""
        if not self.is_cacheable(tool_name):
            return None

        key = self._make_key(tool_name, arguments)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.is_expired:
                del self._cache[key]
                self._evictions += 1
                self._misses += 1
                return None
            self._hits += 1
            result = dict(entry.result)
            result["_cache_meta"] = entry.freshness_meta()
            return result

    def put(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any]):
        """Store a result in cache. Skips errors and non-cacheable tools."""
        if not self.is_cacheable(tool_name):
            return
        if "error" in result:
            return

        key = self._make_key(tool_name, arguments)
        ttl = self._ttl_config.get(tool_name, 0)

        with self._lock:
            self._cache[key] = CacheEntry(
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                cached_at=time.time(),
                ttl_seconds=ttl,
            )

    def invalidate(self, tool_name: str = None):
        """Invalidate cache entries. If tool_name given, only that tool."""
        with self._lock:
            if tool_name:
                to_delete = [k for k in self._cache if k.startswith(f"{tool_name}:")]
                for k in to_delete:
                    del self._cache[k]
                    self._evictions += 1
            else:
                self._evictions += len(self._cache)
                self._cache.clear()

    def invalidate_after_write(self, write_tool_name: str):
        """Invalidate read caches related to a write tool."""
        targets = INVALIDATION_MAP.get(write_tool_name, [])
        for target in targets:
            self.invalidate(target)

    def get_all_for_tool(self, tool_name: str) -> List[Dict[str, Any]]:
        """Return all non-expired cached results for a tool (any arguments)."""
        results = []
        prefix = f"{tool_name}:"
        with self._lock:
            expired_keys = []
            for key, entry in self._cache.items():
                if not key.startswith(prefix):
                    continue
                if entry.is_expired:
                    expired_keys.append(key)
                    continue
                result = dict(entry.result)
                result["_cache_meta"] = entry.freshness_meta()
                results.append(result)
            for k in expired_keys:
                del self._cache[k]
                self._evictions += 1
        return results

    def get_cached_tool_names(self) -> List[str]:
        """Return names of all tools that currently have cached data."""
        names = set()
        with self._lock:
            for key, entry in self._cache.items():
                if not entry.is_expired:
                    names.add(key.split(":")[0])
        return sorted(names)

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "entries": len(self._cache),
                "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "N/A",
            }


def get_tool_cache() -> ToolCache:
    return ToolCache()


def make_live_meta() -> Dict[str, Any]:
    """Create freshness metadata for a live (non-cached) result."""
    return {
        "source": "live",
        "cached_at": datetime.now().isoformat(),
        "age_seconds": 0,
        "ttl_seconds": 0,
        "freshness_label": "live data",
    }
