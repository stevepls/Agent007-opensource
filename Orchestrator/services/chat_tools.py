"""
Chat Tools for Claude

This module provides the tool interface for the Chat API.
Uses the unified ToolRegistry for all tool implementations.

For adding new tools, see services/tool_registry.py
"""

from typing import Dict, Any, List

from services.tool_registry import (
    get_registry,
    execute_tool,
    get_tool_definitions,
)


# ============================================================================
# Exports for backwards compatibility
# ============================================================================

def get_tool_defs() -> List[Dict[str, Any]]:
    """Get tool definitions for Claude API."""
    return get_tool_definitions()


# Alias
TOOL_DEFINITIONS = get_tool_definitions()


def execute(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name."""
    return execute_tool(name, arguments)


# ============================================================================
# Direct Access to Common Tools (for backwards compatibility)
# ============================================================================

def gmail_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    return execute_tool("gmail_search", {"query": query, "max_results": max_results})

def gmail_get_unread_count() -> Dict[str, Any]:
    return execute_tool("gmail_get_unread_count", {})

def calendar_get_events(**kwargs) -> Dict[str, Any]:
    return execute_tool("calendar_get_events", kwargs)

def harvest_get_time_entries(date: str = None) -> Dict[str, Any]:
    return execute_tool("harvest_get_time_entries", {"date": date} if date else {})

def harvest_log_time(**kwargs) -> Dict[str, Any]:
    return execute_tool("harvest_log_time", kwargs)

def harvest_list_projects() -> Dict[str, Any]:
    return execute_tool("harvest_list_projects", {})

def slack_search_messages(query: str, channel: str = None) -> Dict[str, Any]:
    return execute_tool("slack_search_messages", {"query": query, "channel": channel})

def slack_get_recent_messages(channel: str, limit: int = 10) -> Dict[str, Any]:
    return execute_tool("slack_get_recent_messages", {"channel": channel, "limit": limit})

def clickup_list_tasks(**kwargs) -> Dict[str, Any]:
    return execute_tool("clickup_list_tasks", kwargs)

def clickup_create_task(**kwargs) -> Dict[str, Any]:
    return execute_tool("clickup_create_task", kwargs)

def clickup_update_task(**kwargs) -> Dict[str, Any]:
    return execute_tool("clickup_update_task", kwargs)

def clickup_get_task(task_id: str) -> Dict[str, Any]:
    return execute_tool("clickup_get_task", {"task_id": task_id})

def clickup_add_comment(task_id: str, comment: str) -> Dict[str, Any]:
    return execute_tool("clickup_add_comment", {"task_id": task_id, "comment": comment})

def clickup_list_spaces() -> Dict[str, Any]:
    return execute_tool("clickup_list_spaces", {})

def memory_remember(category: str, key: str, value: str) -> Dict[str, Any]:
    return execute_tool("memory_remember", {"category": category, "key": key, "value": value})

def memory_recall(query: str) -> Dict[str, Any]:
    return execute_tool("memory_recall", {"query": query})

def run_dev_task(**kwargs) -> Dict[str, Any]:
    return execute_tool("run_dev_task", kwargs)

def get_agent_status() -> Dict[str, Any]:
    return execute_tool("get_agent_status", {})
