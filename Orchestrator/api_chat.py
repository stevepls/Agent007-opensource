"""
Chat API Endpoint for Orchestrator

Provides streaming chat endpoint that the Next.js dashboard connects to.
Supports structured JSON output for dynamic UI updates.

This module extends the main api.py with chat capabilities.
"""

import os
import json
import queue
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Try to import Anthropic for direct Claude access
# Try to import AI clients
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None

# Import services
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from services.schema_detector import get_schema_detector

# ============================================================================
# Configuration
# ============================================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Which LLM to use: "auto" (prefers OpenAI), "claude", "openai"
ORCHESTRATOR_LLM = os.getenv("ORCHESTRATOR_LLM", "auto")

from services.message_queue import get_message_queue
from services.memory import get_memory_service, MemoryService

# Import Harvest tools
try:
    from tools.harvest import get_status as get_harvest_status
except ImportError:
    get_harvest_status = None

try:
    from services.harvest_client import get_harvest_client, is_harvest_configured
    HARVEST_AVAILABLE = True
except ImportError:
    HARVEST_AVAILABLE = False
    get_harvest_client = lambda: None
    is_harvest_configured = lambda: False

router = APIRouter(prefix="/api", tags=["Chat"])


# ============================================================================
# Models
# ============================================================================

class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request from the dashboard."""
    messages: List[ChatMessage]
    session_id: Optional[str] = Field(None, description="Session ID for memory persistence")
    stream: bool = Field(True, description="Stream the response")
    llm_provider: Optional[str] = Field("auto", description="LLM provider: 'auto', 'claude', 'openai'")
    structured_output: bool = Field(True, description="Include UI JSON")


class UICard(BaseModel):
    """Status card for the dashboard."""
    id: str
    type: str  # info, success, warning, error, progress, metric
    title: str
    value: Optional[str] = None
    description: Optional[str] = None
    progress: Optional[int] = None
    priority: int = 5
    icon: Optional[str] = None


class PriorityUI(BaseModel):
    """UI update instructions."""
    cards: Optional[List[UICard]] = None
    show_progress_bar: Optional[bool] = None
    progress: Optional[int] = None
    highlight_agent: Optional[str] = None


class AgentStatus(BaseModel):
    """Agent status update."""
    id: str
    name: str
    status: str  # idle, active, busy, error, offline
    priority: int = 5
    current_task: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Request for human approval."""
    id: str
    type: str  # deploy, database, message, payment, critical
    title: str
    description: str
    details: Optional[Dict[str, Any]] = None
    timeout_seconds: int = 60


class ChatResponse(BaseModel):
    """Structured chat response."""
    text: Optional[str] = None
    priority_ui: Optional[PriorityUI] = None
    agents: Optional[List[AgentStatus]] = None
    status_cards: Optional[List[UICard]] = None
    needs_approval: Optional[ApprovalRequest] = None


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are Agent007, an AI assistant that helps Steve manage software development and business operations.

## Available Tools

You have tools to interact with these services - USE THEM when the user asks:

### Communication & Productivity
- **Gmail**: `gmail_search`, `gmail_get_unread_count` - Search emails, check inbox
- **Calendar**: `calendar_get_events` - View upcoming meetings and events
- **Slack**: `slack_search_messages`, `slack_get_recent_messages` - Read messages
- **Google Sheets**: `sheets_get_info`, `sheets_read_range`, `sheets_update_range`, `sheets_append_rows`, `sheets_find_value` - Read/write spreadsheets
- **Google Docs/Drive**: `docs_list_files`, `docs_search`, `docs_read_file`, `docs_get_file_info` - Access files

### Unified Notifications (Notion + Slack + Airtable)
- **Notification Hub**: `notification_fetch_all`, `notification_search` - Get/search all notifications
- **Notion**: `notion_get_updates` - Get Notion page updates from email notifications (no direct API)
- **Slack via Email**: `slack_get_updates` - Get Slack messages from email notifications
- **Airtable**: `airtable_get_tickets`, `airtable_search_ticket` - Direct access to Airtable tickets

### Time & Task Management
- **Harvest**: `harvest_log_time`, `harvest_get_time_entries`, `harvest_list_projects` - Track time
- **ClickUp**: `clickup_create_task`, `clickup_list_tasks`, `clickup_update_task`, `clickup_get_task`, `clickup_add_comment`, `clickup_list_spaces` - Manage tasks and tickets
- **Zendesk**: `zendesk_list_tickets`, `zendesk_get_ticket`, `zendesk_create_ticket` - Support tickets

### Utility
- **DateTime**: `get_current_datetime` - Get the current date, time, day of week, and timezone. ALWAYS call before time-sensitive operations.

### Memory & Context
- **Memory**: `memory_remember`, `memory_recall` - Store and retrieve context

### AI Agent Crews (for complex tasks)
- **Agents**: `run_dev_task`, `get_agent_status` - Dispatch work to AI crews
  - Use `run_dev_task` for code changes, file operations, or multi-step development work
  - The crew includes Manager (planning), Coder (implementation), Reviewer (code review)

## When to Use Tools

- "Show my emails" → `gmail_search`
- "What did I work on?" → `harvest_get_time_entries`
- "Log 2 hours" → `harvest_log_time`
- "Check Slack" → `slack_get_recent_messages` or `slack_get_updates`
- "Create a task" → `clickup_create_task`
- "Show my tasks" → `clickup_list_tasks`
- "What meetings?" → `calendar_get_events`
- "Remember that..." → `memory_remember`
- "Build a feature" / "Write code" / "Fix bug" → `run_dev_task` (delegates to AI crew)
- "What time is it?" / "What's today's date?" → `get_current_datetime`
- "What's happening in Notion?" → `notion_get_updates`
- "Show all notifications" → `notification_fetch_all`
- "Find notifications about payment" → `notification_search`
- "Show my Airtable tickets" → `airtable_get_tickets`
- "Find the payment plan ticket" → `airtable_search_ticket`
- "Tell me about yourself" / "What can you do?" / "What integrations?" → `memory_recall` (self-context is stored in memory)
- "What Harvest projects?" / "Project IDs?" → `memory_recall` (project mappings stored in memory)

## Self-Awareness

You have detailed knowledge about your own architecture, integrations, projects, governance rules, and known issues stored in your memory system. When asked about yourself or your capabilities, use `memory_recall` to retrieve this context rather than guessing.

## CRITICAL: Anti-Hallucination Rules

**NEVER make up data. NEVER assume tool results.**

When using tools:
1. ✅ ONLY report IDs, names, and data that appear in the ACTUAL tool response
2. ❌ NEVER fabricate task IDs, file IDs, or any identifiers
3. ✅ If a tool fails or returns truncated results, SAY SO explicitly
4. ✅ If you create multiple items, VERIFY them with a list/verify tool after
5. ❌ NEVER say "Created task X" unless you see the ID in the tool response
6. ✅ If unsure about data, ask for clarification instead of guessing

**If tool result is truncated or incomplete:**
- Say: "I created some tasks but the full list was truncated. Let me verify..."
- Use verification tools to get actual IDs
- DO NOT fill in gaps with assumed data

**Example - WRONG:**
"Created 20 tasks: task1 (ID: abc123), task2 (ID: abc124)..."
(when you only see task1's ID in the response)

**Example - CORRECT:**
"I attempted to create 20 tasks. I can confirm task1 was created (ID: abc123). 
Let me verify the others..."

## Response Style

- Be conversational and natural
- When you use a tool, summarize the results clearly
- Don't just dump raw data - interpret it for the user
- Keep responses concise
- ONLY state facts you can verify from tool responses

## Dashboard UI Updates

You can update the dashboard UI with JSON:

```json
{
  "priority_ui": {
    "cards": [{"id": "card-1", "type": "success", "title": "Done", "description": "Time logged"}]
  }
}
```

Card types: info, success, warning, error, progress, metric

## Important - ANTI-HALLUCINATION RULES

- Steve manages multiple projects (Forge Lab, Agent007, Nemesis, etc.)
- Always use tools to get REAL data - never guess or fabricate
- If a tool fails, explain the error and suggest fixes
- Use memory_remember to store important facts Steve tells you
- For complex development tasks, use run_dev_task to delegate to the AI crew

### Critical Rules (DO NOT VIOLATE):
1. **NEVER fabricate IDs** - task IDs, entry IDs, URLs must come from tool responses
2. **ALWAYS check verification** - After creating tasks/time entries, check if verification.verified is true
3. **Report failures honestly** - If verification fails, tell the user the action may not have completed
4. **Use listing tools to confirm** - After creating anything, use the appropriate list tool to verify
5. **No phantom data** - If harvest_get_time_entries returns 0 entries, report 0 entries (don't make up hours)
6. **Time logging must verify** - Only confirm time was logged if the tool returns success:true AND verification.verified:true"""


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Stream a chat response with structured UI updates.
    
    Connects to Claude API and streams the response while parsing
    for UI update JSON blocks. Persists conversation to memory.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    # Get the last user message
    last_message = request.messages[-1]
    if last_message.role != "user":
        raise HTTPException(status_code=400, detail="Last message must be from user")
    
    # Get or create session for memory persistence
    memory = get_memory_service()
    session_id = request.session_id
    if not session_id:
        session_id = memory.create_session()
    
    # Get relevant context from memory (before response, for injection)
    memory_context = memory.get_relevant_context(last_message.content, limit=5)
    
    # Note: Messages are persisted at the END of the response via persist_turn_context
    # This is more efficient than persisting before we have the full response
    
    # Provider selection: auto, claude, or openai
    provider = request.llm_provider or "auto"
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    # Determine which provider to use
    use_provider = None
    if provider == "claude" and claude_key and ANTHROPIC_AVAILABLE:
        use_provider = "claude"
    elif provider == "openai" and openai_key and OPENAI_AVAILABLE:
        use_provider = "openai"
    elif provider == "auto":
        # Auto: prefer Claude, fallback to OpenAI
        if claude_key and ANTHROPIC_AVAILABLE:
            use_provider = "claude"
        elif openai_key and OPENAI_AVAILABLE:
            use_provider = "openai"
    
    if use_provider == "claude":
        return StreamingResponse(
            stream_claude_response(request.messages, claude_key, session_id, memory_context),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id, "X-LLM-Provider": "claude"},
        )
    elif use_provider == "openai":
        return StreamingResponse(
            stream_openai_response(request.messages, openai_key, session_id, memory_context),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id, "X-LLM-Provider": "openai"},
        )
    else:
        # Fallback to mock response
        return StreamingResponse(
            stream_mock_response(last_message.content, session_id, memory_context),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id, "X-LLM-Provider": "mock"},
        )


@router.post("/cancel/{session_id}")
async def cancel_task(session_id: str):
    """Cancel a running crew task by session ID."""
    from services.task_queue import get_task_queue

    task_queue = get_task_queue()
    # Find tasks for this session that are still running
    for task in task_queue.list_tasks():
        if task.session_id == session_id and task.status in ("queued", "running"):
            task_queue.cancel_task(task.id)
            return {"success": True, "message": f"Cancellation requested for task {task.id}"}
    return {"success": False, "message": "No active task found for this session"}


# ── Complex tasks that REQUIRE CrewAI agents (multi-step / batch) ─────
# Only truly multi-step or batch operations that need agent orchestration.
# Single-tool ops (create one task, generate timesheet) go to orchestrator.
CREW_KEYWORDS = [
    "batch create", "create tasks",  # plural = batch
    "bulk", "migrate",
    "deploy", "run dev", "dev task",
    "write code", "fix bug", "implement", "refactor",
    "pull request",
    "tasks from", "doc to clickup", "google doc to",
    "create checklist",
]

# ── Domains that signal the orchestrator should use tools ─────────────
# Orchestrator handles single-tool and multi-tool requests directly via
# Claude API + native tool_use (up to 8 iterations).
TOOL_DOMAINS = [
    "email", "gmail", "unread", "inbox",
    "harvest", "hubstaff", "time entr", "time track", "hours", "timer",
    "log time", "log hours", "timesheet", "invoice",
    "clickup", "task", "ticket", "to do", "todo",
    "create task", "create a task", "create ticket", "update task",
    "create subtask", "assign task",
    "zendesk", "support ticket",
    "calendar", "meeting", "schedule", "event",
    "slack", "message", "channel",
    "notification", "notion", "airtable",
    "asana", "sync asana", "pull asana",
    "drive", "docs", "sheet", "spreadsheet", "file",
    "create doc", "create space", "create folder",
    "update sheet", "generate report",
    "remember", "recall", "memory",
    "comment", "reply", "send", "draft", "commit",
    "github", "pull request", "branch", "pr ", "repo",
    "build",
]


def _classify_request(message: str, memory_context: str = "") -> str:
    """Classify how to handle a request: 'direct', 'orchestrator', or 'crew'.

    - 'direct': simple chat, no tools needed
    - 'orchestrator': handle with Claude + native tool_use (most requests)
    - 'crew': complex multi-step tasks needing CrewAI agents

    Priority: crew keywords (batch/multi-step) > tool domains (single ops) > direct.
    """
    msg = message.lower().strip()

    # Complex/batch operations -> crew (checked first, but only for true multi-step)
    if any(kw in msg for kw in CREW_KEYWORDS):
        return "crew"

    # If the message mentions any tool domain -> orchestrator handles it directly
    if any(kw in msg for kw in TOOL_DOMAINS):
        return "orchestrator"

    # If memory has relevant context, Claude can answer directly
    if memory_context and len(memory_context) > 50:
        return "direct"

    # Short conversational messages — no tools needed
    if len(msg.split()) <= 12:
        return "direct"

    # Default: let the orchestrator decide (it has tools if it needs them)
    return "orchestrator"


# ── Structured data schemas for dashboard table rendering ──────────────
STRUCTURED_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "clickup_list_tasks": {
        "title": "Tasks",
        "columns": [
            {"key": "name", "label": "Task"},
            {"key": "status", "label": "Status"},
            {"key": "assignee", "label": "Assignee"},
            {"key": "due_date", "label": "Due"},
        ],
        "row_path": "tasks",
    },
    "harvest_get_time_entries": {
        "title": "Time Entries",
        "columns": [
            {"key": "project", "label": "Project"},
            {"key": "task", "label": "Task"},
            {"key": "hours", "label": "Hours"},
            {"key": "notes", "label": "Notes"},
        ],
        "row_path": "entries",
    },
    "hubstaff_get_time_entries": {
        "title": "Hubstaff Time",
        "columns": [
            {"key": "date", "label": "Date"},
            {"key": "project", "label": "Project"},
            {"key": "duration_hours", "label": "Hours"},
        ],
        "row_path": "entries",
    },
    "gmail_search": {
        "title": "Emails",
        "columns": [
            {"key": "from", "label": "From"},
            {"key": "subject", "label": "Subject"},
            {"key": "date", "label": "Date"},
            {"key": "snippet", "label": "Preview"},
        ],
        "row_path": "results",
    },
    "slack_get_dm_history": {
        "title": "Messages",
        "columns": [
            {"key": "user", "label": "From"},
            {"key": "text", "label": "Message"},
            {"key": "timestamp", "label": "Time"},
        ],
        "row_path": "messages",
    },
    "slack_list_dms": {
        "title": "DM Contacts",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "username", "label": "Username"},
            {"key": "title", "label": "Role"},
        ],
        "row_path": "dm_contacts",
    },
    "zendesk_list_tickets": {
        "title": "Tickets",
        "columns": [
            {"key": "subject", "label": "Subject"},
            {"key": "status", "label": "Status"},
            {"key": "priority", "label": "Priority"},
            {"key": "assignee", "label": "Assignee"},
        ],
        "row_path": "tickets",
    },
    "asana_list_my_tasks": {
        "title": "Asana Tasks",
        "columns": [
            {"key": "name", "label": "Task"},
            {"key": "due_on", "label": "Due"},
            {"key": "assignee_section", "label": "Section"},
        ],
        "row_path": "tasks",
    },
    "harvest_list_projects": {
        "title": "Projects",
        "columns": [
            {"key": "name", "label": "Project"},
            {"key": "client", "label": "Client"},
            {"key": "is_active", "label": "Active"},
        ],
        "row_path": "projects",
    },
    "drive_list_files": {
        "title": "Files",
        "columns": [
            {"key": "name", "label": "Name"},
            {"key": "mimeType", "label": "Type"},
            {"key": "modifiedTime", "label": "Modified"},
        ],
        "row_path": "files",
    },
    "clickup_get_comments": {
        "title": "Task Comments",
        "columns": [
            {"key": "user", "label": "Author"},
            {"key": "text", "label": "Comment"},
            {"key": "date", "label": "Date"},
        ],
        "row_path": "comments",
    },
    "github_list_prs": {
        "title": "Pull Requests",
        "columns": [
            {"key": "number", "label": "#"},
            {"key": "title", "label": "Title"},
            {"key": "author", "label": "Author"},
            {"key": "head", "label": "Branch"},
            {"key": "state", "label": "State"},
        ],
        "row_path": "prs",
    },
    "github_list_branches": {
        "title": "Branches",
        "columns": [
            {"key": "name", "label": "Branch"},
            {"key": "protected", "label": "Protected"},
        ],
        "row_path": "branches",
    },
    "github_get_branch_commits": {
        "title": "Commits",
        "columns": [
            {"key": "sha", "label": "SHA"},
            {"key": "message", "label": "Message"},
            {"key": "author", "label": "Author"},
            {"key": "date", "label": "Date"},
        ],
        "row_path": "commits",
    },
}


def _make_structured_data(tool_name: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract structured table data from a tool result for dashboard rendering."""
    schema = STRUCTURED_SCHEMAS.get(tool_name)
    if not schema or not isinstance(result, dict) or "error" in result:
        return None

    rows_raw = result.get(schema["row_path"], [])
    if not isinstance(rows_raw, list) or len(rows_raw) == 0:
        return None

    # Extract only the columns defined in the schema
    rows = []
    for item in rows_raw[:50]:  # Cap at 50 rows
        if not isinstance(item, dict):
            continue
        row = {}
        for col in schema["columns"]:
            val = item.get(col["key"], "")
            if isinstance(val, (dict, list)):
                val = json.dumps(val, default=str)
            row[col["key"]] = str(val)[:200] if val else ""
        rows.append(row)

    if not rows:
        return None

    return {
        "type": "structured_data",
        "title": schema["title"],
        "columns": schema["columns"],
        "rows": rows,
        "total": len(rows_raw),
    }


def _make_status_card(tool_name: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Generate a dashboard status card from a tool result."""
    if not isinstance(result, dict) or "error" in result:
        return None

    if tool_name == "gmail_get_unread_count":
        count = result.get("unread_count", 0)
        return {
            "id": "email-status",
            "type": "warning" if count > 50 else "info",
            "title": f"{count} Unread Emails",
            "description": "Inbox status",
        }
    elif tool_name == "gmail_search":
        count = result.get("count", 0)
        return {
            "id": "email-search",
            "type": "info",
            "title": f"{count} Emails Found",
            "description": "Search results",
        }
    elif tool_name in ("harvest_get_time_entries", "harvest_status"):
        hours = result.get("total_hours", 0)
        entries = len(result.get("entries", []))
        return {
            "id": "harvest-status",
            "type": "metric",
            "title": f"{hours:.1f}h Logged Today",
            "description": f"{entries} time entries",
        }
    elif tool_name == "harvest_log_time":
        if result.get("success"):
            return {
                "id": f"harvest-logged-{result.get('entry_id', '')}",
                "type": "success",
                "title": f"Logged {result.get('hours', 0)}h",
                "description": result.get("project", ""),
            }
    elif tool_name == "harvest_list_projects":
        count = result.get("count", 0)
        return {
            "id": "harvest-projects",
            "type": "info",
            "title": f"{count} Active Projects",
            "description": "Harvest projects",
        }
    elif tool_name == "calendar_get_events":
        events = result.get("events", result.get("upcoming", []))
        count = len(events) if isinstance(events, list) else result.get("count", 0)
        return {
            "id": "calendar-status",
            "type": "info",
            "title": f"{count} Upcoming Events",
            "description": "Calendar",
        }
    elif tool_name == "clickup_list_tasks":
        tasks = result.get("tasks", [])
        return {
            "id": "clickup-tasks",
            "type": "info",
            "title": f"{len(tasks)} Tasks",
            "description": "ClickUp",
        }
    elif tool_name == "zendesk_list_tickets":
        tickets = result.get("tickets", [])
        return {
            "id": "zendesk-tickets",
            "type": "info",
            "title": f"{len(tickets)} Tickets",
            "description": "Zendesk",
        }
    elif tool_name == "notification_fetch_all":
        notifs = result.get("notifications", [])
        return {
            "id": "notifications",
            "type": "info" if len(notifs) < 10 else "warning",
            "title": f"{len(notifs)} Notifications",
            "description": "All sources",
        }
    elif tool_name == "slack_get_recent_messages":
        msgs = result.get("messages", [])
        return {
            "id": "slack-messages",
            "type": "info",
            "title": f"{len(msgs)} Messages",
            "description": "Slack",
        }
    return None


async def _stream_direct_response(
    messages: List[ChatMessage],
    memory_context: str = "",
    session_id: str = None,
) -> AsyncGenerator[str, None]:
    """Answer simple questions directly via Claude API — no tools."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not ANTHROPIC_AVAILABLE:
        return

    memory = get_memory_service()
    user_request = messages[-1].content if messages else ""

    system = (
        "You are Agent007, a friendly AI assistant that helps Steve manage "
        "software development and business operations. Answer conversationally. "
        "Keep answers concise.\n\n"
        "You can help with:\n"
        "- Time tracking (Harvest)\n"
        "- Task management (ClickUp, Zendesk)\n"
        "- Communication (Gmail, Slack)\n"
        "- File management (Google Drive, Docs, Sheets)\n"
        "- Development tasks\n"
        "- General questions and conversation"
    )
    if memory_context:
        system += f"\n\nRelevant context from memory:\n{memory_context}"

    client = anthropic.Anthropic(api_key=api_key)
    api_messages = [
        {"role": m.role if m.role in ("user", "assistant") else "user", "content": m.content}
        for m in messages[-10:]
        if m.content and m.content.strip()
    ]
    if not api_messages:
        yield "How can I help you?"
        return

    try:
        with client.messages.stream(
            model=os.getenv("DEFAULT_MODEL", "claude-opus-4-20250514"),
            max_tokens=1024,
            system=system,
            messages=api_messages,
        ) as stream:
            full_response = ""
            for text in stream.text_stream:
                full_response += text
                yield text

        if session_id and full_response:
            memory.persist_turn_context(session_id, user_request, full_response)

    except Exception as e:
        yield f"\n\nError: {str(e)}"


async def _stream_orchestrator_response(
    messages: List[ChatMessage],
    memory_context: str = "",
    session_id: str = None,
) -> AsyncGenerator[str, None]:
    """Handle requests using Claude API with native tool_use.

    Multi-turn loop: Claude calls tools, we execute them via ToolRegistry
    (which handles caching + safety), feed results back, repeat until done.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not ANTHROPIC_AVAILABLE:
        yield "Error: Anthropic API not available\n"
        return

    from services.tool_registry import get_registry

    registry = get_registry()
    memory = get_memory_service()
    user_request = messages[-1].content if messages else ""
    tool_defs = registry.get_orchestrator_definitions()

    # System prompt
    system = SYSTEM_PROMPT
    if memory_context:
        system += f"\n\nRelevant context from memory:\n{memory_context}"

    # Build message history — filter empty content to avoid 400 errors
    api_messages = []
    for m in messages[-10:]:
        content = m.content
        if not content or not content.strip():
            continue
        role = m.role if m.role in ("user", "assistant") else "user"
        api_messages.append({"role": role, "content": content})

    if not api_messages:
        yield "How can I help you?"
        return

    # Ensure first message is from user
    if api_messages[0]["role"] == "assistant":
        api_messages = api_messages[1:]

    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("DEFAULT_MODEL", "claude-opus-4-20250514")
    full_response = ""
    tool_freshness = {}
    MAX_ITERATIONS = 8

    try:
        for iteration in range(MAX_ITERATIONS):
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tool_defs,
                messages=api_messages,
            )

            has_tool_use = False
            tool_results = []

            for block in response.content:
                if block.type == "text" and block.text:
                    full_response += block.text
                    # Each text block on its own line so PROGRESS lines stay separate
                    yield block.text + "\n"

                elif block.type == "tool_use":
                    has_tool_use = True
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    # Emit progress: tool starting
                    yield "PROGRESS:" + json.dumps({
                        "type": "tool_start",
                        "agent": "Orchestrator",
                        "tool": tool_name,
                        "message": f"Using {tool_name}...",
                    }) + "\n"

                    # Execute tool via registry (caching + safety built in)
                    tool_result = registry.execute(tool_name, tool_input)

                    # Handle confirmation-required tools
                    if isinstance(tool_result, dict) and tool_result.get("requires_confirmation"):
                        preview = tool_result.get("preview", "")
                        msg = tool_result.get("message", "")
                        confirmation_text = f"\n\n**{msg}**\n\n{preview}\n\nPlease confirm this action."
                        full_response += confirmation_text
                        yield confirmation_text
                        # Store pending action for follow-up
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps({"status": "awaiting_confirmation", "preview": preview}),
                        })
                        has_tool_use = False  # Stop the loop
                        break

                    # Track freshness
                    if isinstance(tool_result, dict):
                        cache_meta = tool_result.get("_cache_meta", {})
                        if cache_meta.get("source"):
                            tool_freshness[tool_name] = cache_meta["source"]

                    # Build a status card from tool result
                    status_card = _make_status_card(tool_name, tool_result)

                    # Emit progress: tool done
                    result_str = json.dumps(tool_result, default=str)
                    done_event: Dict[str, Any] = {
                        "type": "tool_done",
                        "agent": "Orchestrator",
                        "tool": tool_name,
                        "message": f"{tool_name} complete",
                        "cache_source": tool_freshness.get(tool_name, "live"),
                    }
                    if status_card:
                        done_event["status_card"] = status_card
                    yield "PROGRESS:" + json.dumps(done_event) + "\n"

                    # Emit structured data for dashboard table rendering
                    structured = _make_structured_data(tool_name, tool_result)
                    if structured:
                        yield "STRUCTURED:" + json.dumps(structured) + "\n"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_str,
                    })

            # If no tool calls or Claude said end_turn, we're done
            if not has_tool_use or response.stop_reason == "end_turn":
                break

            # Build messages for next iteration
            api_messages.append({"role": "assistant", "content": response.content})
            api_messages.append({"role": "user", "content": tool_results})

        # Emit freshness summary
        if tool_freshness:
            yield "FRESHNESS:" + json.dumps(tool_freshness) + "\n"

        # Persist to memory
        if session_id and full_response:
            memory.persist_turn_context(session_id, user_request, full_response)

    except anthropic.BadRequestError as e:
        print(f"[ERROR] Orchestrator API error: {e}")
        yield f"\n\nAPI Error: {str(e)}"
    except Exception as e:
        import traceback
        print(f"[ERROR] Orchestrator tool loop failed: {traceback.format_exc()}")
        yield f"\n\nError: {str(e)}"


async def stream_claude_response(
    messages: List[ChatMessage],
    api_key: str,
    session_id: str = None,
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """
    Stream response — fast path for simple questions, crew for tool tasks.

    Simple questions (greetings, chitchat, general knowledge) are answered
    directly via Claude API.  Requests that need tools (time tracking, tasks,
    email, etc.) go through the background CrewAI crew.

    Protocol lines (crew path only):
    - BACKGROUND_UPDATE:{json}  — completed task result
    - BACKGROUND_QUEUED:{json}  — new task acknowledged
    - PROGRESS:{json}           — real-time tool/agent activity
    - FRESHNESS:{json}          — data freshness summary
    """
    from services.task_queue import get_task_queue

    memory = get_memory_service()

    # Get the last user message
    user_request = messages[-1].content if messages else ""

    # Build context from conversation history
    context_parts = []
    if memory_context:
        context_parts.append(f"Previous context:\n{memory_context}")

    # Add conversation history (last 5 messages)
    for msg in messages[-5:]:
        if msg.role == "user":
            context_parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            context_parts.append(f"Assistant: {msg.content[:200]}...")

    context = "\n\n".join(context_parts) if context_parts else None

    task_queue = get_task_queue()

    # ── Phase 1: Report completed background tasks (FIFO) ─────────────
    for completed_task in task_queue.get_unreported_updates():
        update_payload = {
            "task_id": completed_task.id,
            "request": completed_task.user_request[:100],
            "status": completed_task.status,
            "result": completed_task.result[:500] if completed_task.result else None,
            "error": completed_task.error,
        }
        yield "BACKGROUND_UPDATE:" + json.dumps(update_payload) + "\n"
        task_queue.mark_reported(completed_task.id)

    # ── Route: direct (chat), orchestrator (tools), or crew (complex) ──
    route = _classify_request(user_request, memory_context)

    if route == "direct":
        async for chunk in _stream_direct_response(messages, memory_context, session_id=session_id):
            yield chunk
        return

    if route == "orchestrator":
        async for chunk in _stream_orchestrator_response(
            messages, memory_context, session_id=session_id
        ):
            yield chunk
        return

    # ── Phase 2: Submit tool request to background queue ──────────────
    task_id = task_queue.submit(user_request, context, session_id)
    queued_payload = {
        "task_id": task_id,
        "position": task_queue.get_running_count(),
        "request": user_request[:100],
    }
    yield "BACKGROUND_QUEUED:" + json.dumps(queued_payload) + "\n"

    yield "PROGRESS:" + json.dumps({"type": "thinking", "agent": "Orchestrator", "message": "Starting AI crew..."}) + "\n"

    # ── Phase 3: Stream progress for this task ────────────────────────
    tracker = task_queue.get_task_tracker(task_id)
    if not tracker:
        yield "Error: tracker not found for task\n"
        return

    tool_freshness: dict = {}

    try:
        # Drain progress events while task is running
        while True:
            bg_task = task_queue.get_task(task_id)
            task_done = bg_task and bg_task.status in ("completed", "failed")

            # Try to get progress events from the queue
            try:
                event = tracker.progress_queue.get_nowait()
                if event is None:
                    break  # Sentinel: crew finished
                if event.get("type") == "tool_done" and event.get("cache_source"):
                    tool_freshness[event["tool"]] = event["cache_source"]
                yield "PROGRESS:" + json.dumps(event) + "\n"
            except queue.Empty:
                if task_done:
                    break
                # Sleep briefly then send keepalive
                await asyncio.sleep(0.5)
                yield " "  # keepalive byte
                continue

        # Drain any remaining events
        while True:
            try:
                event = tracker.progress_queue.get_nowait()
                if event is None:
                    break
                if event.get("type") == "tool_done" and event.get("cache_source"):
                    tool_freshness[event["tool"]] = event["cache_source"]
                yield "PROGRESS:" + json.dumps(event) + "\n"
            except queue.Empty:
                break

        # Emit freshness summary
        if tool_freshness:
            yield "FRESHNESS:" + json.dumps(tool_freshness) + "\n"

        # Stream the result
        bg_task = task_queue.get_task(task_id)
        if bg_task and bg_task.status == "completed" and bg_task.result:
            response_text = bg_task.result

            # Stream the response (simulate streaming by chunking)
            words = response_text.split()
            chunk_size = 10
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i+chunk_size]) + " "
                yield chunk
                await asyncio.sleep(0.05)

            # Persist to memory
            if session_id and response_text:
                memory.persist_turn_context(session_id, user_request, response_text)

            # Mark reported since we streamed it live
            task_queue.mark_reported(task_id)

        elif bg_task and bg_task.status == "failed":
            error_msg = bg_task.error or "Unknown error"
            if "cancel" in error_msg.lower():
                yield "\n\n*Task cancelled.*\n"
            else:
                yield f"Error: {error_msg}\n\n"
                yield "Please try rephrasing your request or check the logs for details."
            task_queue.mark_reported(task_id)

        else:
            # Task still running — it will be reported on next request
            yield "Task is still running in the background. Results will be reported when ready.\n"

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] Orchestrator stream failed: {error_trace}")
        yield f"Error processing request: {str(e)}\n\n"
        yield "The AI crew encountered an error. Please try again or check the logs."



async def stream_openai_response(
    messages: List[ChatMessage],
    api_key: str,
    session_id: str = None,
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """
    Stream response using CrewAI Orchestrator Crew.

    All tasks are now routed through CrewAI agents (same as Claude).
    """
    async for chunk in stream_claude_response(messages, api_key, session_id, memory_context):
        yield chunk


async def stream_mock_response(
    user_message: str,
    session_id: str = None,
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """Generate a conversational response when Claude API is not available."""
    memory = get_memory_service()
    message_lower = user_message.lower()
    words = message_lower.split()
    
    # Get real system context
    context = await build_context()
    
    # Add memory context
    if memory_context:
        context = memory_context + "\n\n" + context
    
    # Analyze intent more naturally (strip punctuation for matching)
    import re
    clean_words = re.sub(r'[^\w\s]', '', message_lower).split()
    
    is_greeting = any(w in clean_words for w in ["hi", "hello", "hey", "yo", "sup", "hiya"])
    is_question = "?" in user_message or any(message_lower.startswith(w) for w in ["what", "how", "why", "when", "where", "who", "can", "could", "would", "is", "are", "do", "does"])
    is_thanks = any(w in clean_words for w in ["thanks", "thank", "thx", "ty", "appreciate"])
    wants_help = any(w in clean_words for w in ["help", "assist", "support"])
    
    # Build natural response
    response_text = ""
    json_data: Dict[str, Any] = {}
    
    # Handle greetings first (before keyword matching)
    if is_greeting:
        import random
        greetings = [
            "Hey! What can I help you with today?",
            "Hi there! Ready to help with deployments, time tracking, or anything else.",
            "Hello! I'm here - what do you need?",
        ]
        response_text = random.choice(greetings)
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]}
    
    elif is_thanks:
        thanks_responses = [
            "You're welcome! Let me know if you need anything else.",
            "No problem! I'm here if you need me.",
            "Anytime! 👍",
        ]
        import random
        response_text = random.choice(thanks_responses)
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "idle", "priority": 1}]}
    
    elif "deploy" in message_lower:
        response_text = "I'll initiate the deployment process. Let me run the pre-deployment checks first."
        json_data = {
            "priority_ui": {
                "show_progress_bar": True,
                "progress": 25,
                "cards": [
                    {
                        "id": "deploy-status",
                        "type": "progress",
                        "title": "Deployment",
                        "description": "Running pre-deployment checks...",
                        "progress": 25,
                        "priority": 1,
                    }
                ],
            },
            "agents": [
                {"id": "deployer", "name": "Deployer", "status": "active", "priority": 1, "current_task": "Running checks"}
            ],
            "needs_approval": {
                "id": f"deploy-{int(datetime.now().timestamp())}",
                "type": "deploy",
                "title": "Deploy to Production",
                "description": "All checks passed. Ready to deploy the latest code to production.",
                "details": {"branch": "main", "commit": "abc123", "environment": "production"},
                "timeout_seconds": 120,
            },
        }
        
    elif "ticket" in message_lower:
        response_text = "Here's a summary of your open tickets:"
        json_data = {
            "priority_ui": {
                "cards": [
                    {"id": "tickets-urgent", "type": "warning", "title": "3 Urgent Tickets", "description": "Require immediate attention", "priority": 1},
                    {"id": "tickets-normal", "type": "info", "title": "12 Open Tickets", "description": "Normal priority", "priority": 3},
                ]
            },
            "agents": [
                {"id": "ticket-manager", "name": "Ticket Manager", "status": "active", "current_task": "Fetching tickets"}
            ],
        }
        
    elif "time" in message_lower:
        # Try to get real Harvest data
        hours_today = 0.0
        hours_week = 0.0
        running_timer = None
        entries_count = 0
        harvest_configured = False
        
        if HARVEST_AVAILABLE and get_harvest_status:
            try:
                status = get_harvest_status()
                harvest_configured = status.get("configured", False)
                if harvest_configured:
                    hours_today = status.get("today_hours", 0)
                    entries_count = status.get("today_entries", 0)
                    running_timer = status.get("running_timer")
                    # Estimate week hours (today * days so far this week)
                    from datetime import date
                    days_this_week = date.today().weekday() + 1
                    hours_week = hours_today * days_this_week * 0.8  # rough estimate
            except Exception:
                pass
        
        if harvest_configured:
            response_text = f"Here's your time from Harvest:"
            timer_status = ""
            if running_timer:
                timer_notes = running_timer.get("notes", "")[:40]
                timer_status = f"\n\n⏱️ **Timer Running:** {timer_notes}..."
            
            response_text += f"\n\n• **Today:** {hours_today:.1f} hours ({entries_count} entries)"
            response_text += timer_status
            
            json_data = {
                "priority_ui": {
                    "cards": [
                        {"id": "time-today", "type": "metric", "title": "Hours Today", "value": f"{hours_today:.1f}", "description": f"{entries_count} time entries", "priority": 2, "icon": "clock"},
                    ]
                },
                "agents": [
                    {"id": "time-logger", "name": "Time Logger", "status": "active", "current_task": "Connected to Harvest"}
                ],
            }
            
            if running_timer:
                json_data["priority_ui"]["cards"].insert(0, {
                    "id": "timer-running", 
                    "type": "warning", 
                    "title": "Timer Running", 
                    "description": running_timer.get("notes", "")[:50],
                    "priority": 1, 
                    "icon": "clock"
                })
        else:
            response_text = "Harvest is not configured. To connect:\n\n"
            response_text += "1. Get your token from: https://id.getharvest.com/developers\n"
            response_text += "2. Set environment variables:\n"
            response_text += "   - `HARVEST_ACCESS_TOKEN`\n"
            response_text += "   - `HARVEST_ACCOUNT_ID`\n"
            response_text += "   - `HARVEST_DEFAULT_PROJECT_ID` (optional)\n"
            response_text += "   - `HARVEST_DEFAULT_TASK_ID` (optional)"
            
            json_data = {
                "priority_ui": {
                    "cards": [
                        {"id": "harvest-setup", "type": "warning", "title": "Harvest Not Configured", "description": "Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID", "priority": 1},
                    ]
                },
                "agents": [
                    {"id": "time-logger", "name": "Time Logger", "status": "error", "current_task": "Not configured"}
                ],
            }
        
    elif "schema" in message_lower or "database" in message_lower:
        detector = get_schema_detector()
        summary = detector.get_summary()
        
        response_text = f"I found {summary['total']} schema changes, {summary['unreviewed']} need review."
        json_data = {
            "priority_ui": {
                "cards": [
                    {"id": "schema-pending", "type": "warning" if summary['unreviewed'] > 0 else "success", 
                     "title": f"{summary['unreviewed']} Pending Reviews", 
                     "description": f"Across {len(summary.get('by_project', {}))} projects", 
                     "priority": 1 if summary['unreviewed'] > 0 else 5},
                ]
            },
            "agents": [
                {"id": "orchestrator", "name": "Orchestrator", "status": "active", "current_task": "Schema detection"}
            ],
        }
        
    elif wants_help:
        response_text = f"""Sure, I can help! Here's what I can do:

**🚀 Deployments** - "deploy to production", "run checks"
**🎫 Tickets** - "show open tickets", "create a ticket"
**⏱️ Time** - "log time", "start timer", "what did I work on today?"
**📊 Database** - "check schema changes", "any pending reviews?"
**💬 General** - Just ask naturally, I'll figure it out

{context}

What would you like to do?"""
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]}
    
    # Handle questions about the system
    elif "status" in message_lower or "what's" in message_lower or "how are" in message_lower:
        response_text = f"Here's the current system status:\n\n{context}\n\nEverything looks good. What would you like me to do?"
        json_data = {
            "priority_ui": {"cards": [{"id": "status-ok", "type": "success", "title": "Systems Operational", "description": "All services running", "priority": 3}]},
            "agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]
        }
    
    # Handle project/work related questions
    elif any(w in message_lower for w in ["project", "work", "doing", "task"]):
        response_text = f"""I'm tracking several things for you:

{context}

Want me to show details on any of these? Or tell me what you're working on and I can start a timer."""
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "current_task": "Monitoring"}]}
    
    # More conversational fallback
    else:
        # Try to extract what they might want
        if is_question:
            response_text = f"""Good question! I'm not 100% sure what you're asking about, but here's what I know:

{context}

Could you be more specific? For example:
- "How much time did I log today?"
- "Are there any pending schema reviews?"
- "Deploy the latest changes"
"""
        else:
            response_text = f"""Got it. Here's what I can see right now:

{context}

Just tell me what you'd like to do - deploy, track time, check tickets, or something else."""
        
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]}
    
    # Only include JSON if there's UI updates (not for simple conversations)
    if json_data.get("priority_ui") or json_data.get("needs_approval"):
        full_response = response_text + "\n\n```json\n" + json.dumps(json_data, indent=2) + "\n```"
    else:
        full_response = response_text
    
    # Stream more naturally (by sentence/phrase, not word)
    chunks = []
    current = ""
    for char in full_response:
        current += char
        if char in ".!?\n" and len(current) > 10:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    
    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.05)
    
    # Persist conversation turn efficiently (batched write + fact extraction)
    if session_id:
        memory.persist_turn_context(session_id, user_message, full_response)


async def build_context() -> str:
    """Build context from current system state."""
    import os
    context_parts = []
    
    # Connected integrations
    integrations = []
    if os.getenv("HARVEST_ACCESS_TOKEN"):
        integrations.append("Harvest (time tracking)")
    if os.getenv("ZENDESK_API_TOKEN"):
        integrations.append("Zendesk (tickets)")
    if os.getenv("CLICKUP_API_TOKEN"):
        integrations.append("ClickUp (tasks)")
    if os.getenv("AIRTABLE_PERSONAL_ACCESS_TOKEN"):
        integrations.append("Airtable (database)")
    if os.getenv("SLACK_BOT_TOKEN"):
        integrations.append("Slack (messages)")
    
    # Check Gmail
    gmail_token = os.path.expanduser("~/.config/agent007/google/token.json")
    if os.path.exists(gmail_token):
        integrations.append("Gmail (email)")
    
    if integrations:
        context_parts.append(f"Connected integrations: {', '.join(integrations)}")
    
    # Harvest status if available
    if HARVEST_AVAILABLE and get_harvest_status:
        try:
            status = get_harvest_status()
            if status.get("configured"):
                hours = status.get("today_hours", 0)
                entries = status.get("today_entries", 0)
                context_parts.append(f"Harvest: {hours:.1f}h logged today ({entries} entries)")
                if status.get("running_timer"):
                    context_parts.append(f"Active timer: {status['running_timer'].get('notes', 'running')[:40]}")
        except Exception:
            pass
    
    # Schema changes
    try:
        detector = get_schema_detector()
        summary = detector.get_summary()
        context_parts.append(f"Schema changes: {summary['total']} total, {summary['unreviewed']} pending review")
        context_parts.append(f"Monitored projects: {', '.join(summary.get('monitored_projects', []))}")
    except Exception:
        pass
    
    # Message queue
    try:
        queue = get_message_queue()
        pending = queue.list_pending()
        if pending:
            context_parts.append(f"Pending messages in queue: {len(pending)}")
    except Exception:
        pass
    
    context_parts.append(f"Current time: {datetime.now().isoformat()}")

    # Always inject system self-context from memory (full values, not truncated)
    try:
        from services.memory import get_memory_service, ContextEntry
        memory = get_memory_service()
        with memory._get_session() as db:
            entries = (
                db.query(ContextEntry)
                .filter_by(source="system")
                .order_by(ContextEntry.category, ContextEntry.key)
                .all()
            )
            if entries:
                context_parts.append("\n## Agent Self-Context")
                for e in entries:
                    context_parts.append(f"**{e.category}/{e.key}**: {e.value}")
    except Exception:
        pass

    return "\n".join(context_parts)


# ============================================================================
# Approval Endpoint
# ============================================================================

class ApprovalAction(BaseModel):
    """Approval action request."""
    approval_id: str
    approved: bool


@router.post("/approve")
async def process_approval(action: ApprovalAction):
    """Process an approval or rejection."""
    # In a real implementation, this would:
    # 1. Look up the pending action by ID
    # 2. Execute or cancel based on approval status
    # 3. Return the result
    
    return {
        "success": True,
        "approval_id": action.approval_id,
        "status": "approved" if action.approved else "rejected",
        "message": f"Action {'approved and executed' if action.approved else 'rejected'}",
    }


# ============================================================================
# Memory Endpoints
# ============================================================================

class ContextEntry(BaseModel):
    """A context/memory entry."""
    category: str
    key: str
    value: str
    source: str = "user"
    confidence: float = 1.0
    expires_in_days: Optional[int] = None


@router.get("/memory/stats")
async def get_memory_stats():
    """Get memory database statistics."""
    memory = get_memory_service()
    return memory.get_stats()


@router.get("/memory/sessions")
async def list_sessions(limit: int = 20):
    """List recent conversation sessions."""
    memory = get_memory_service()
    return {"sessions": memory.list_sessions(limit=limit)}


@router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details and conversation history."""
    memory = get_memory_service()
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    history = memory.get_conversation(session_id, limit=100)
    return {
        "session": session,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in history
        ],
    }


@router.get("/memory/context")
async def list_context(category: Optional[str] = None):
    """List stored context entries."""
    memory = get_memory_service()
    return {"entries": memory.list_context(category=category)}


@router.post("/memory/context")
async def add_context(entry: ContextEntry):
    """Add or update a context entry."""
    memory = get_memory_service()
    entry_id = memory.add_context(
        category=entry.category,
        key=entry.key,
        value=entry.value,
        source=entry.source,
        confidence=entry.confidence,
        expires_in_days=entry.expires_in_days,
    )
    return {"success": True, "id": entry_id}


@router.delete("/memory/context/{category}/{key}")
async def delete_context(category: str, key: str):
    """Delete a context entry."""
    memory = get_memory_service()
    deleted = memory.delete_context(category, key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Context entry not found")
    return {"success": True}


@router.get("/memory/search")
async def search_memory(q: str, limit: int = 10):
    """Search context entries."""
    memory = get_memory_service()
    results = memory.search_context(q, limit=limit)
    return {
        "results": [
            {
                "category": r.category,
                "key": r.key,
                "content": r.content,
                "relevance": r.relevance,
                "source": r.source,
            }
            for r in results
        ]
    }


@router.post("/memory/cleanup")
async def cleanup_memory():
    """Remove expired context entries."""
    memory = get_memory_service()
    removed = memory.cleanup_expired()
    return {"success": True, "removed": removed}


@router.get("/memory/export")
async def export_memory():
    """Export all context for backup."""
    memory = get_memory_service()
    return memory.export_context()


@router.post("/memory/import")
async def import_memory(data: Dict[str, Any]):
    """Import context from backup."""
    memory = get_memory_service()
    count = memory.import_context(data)
    return {"success": True, "imported": count}
