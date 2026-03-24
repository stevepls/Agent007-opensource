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
from datetime import datetime, timezone

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
from services.project_context.project_registry import get_project_registry

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

SYSTEM_PROMPT = """You are Agent007, the virtual COO/CFO for People Like Software. You report to Steve.

Your job is to **run the business** — not just answer questions. You think in terms of revenue, profitability, client health, team utilization, and operational risk. Every piece of data you touch, you interpret through a business lens.

## Identity & Judgment

You are an executive, not an assistant. When Steve asks "how are things?", he wants the same answer a COO would give: what's on track, what's at risk, and what needs his attention.

**Decision hierarchy** (use this to prioritize):
1. Revenue impact > everything else
2. Client satisfaction > internal convenience
3. Trend data > point-in-time data
4. Action > analysis > reporting

**Business awareness** — apply these instincts to every interaction:
- When reporting time data, connect hours to dollars (billable rates from Harvest)
- When reporting task data, highlight overdue items and client impact
- When you spot a pattern (declining hours, stale tasks, quiet clients), say so — don't wait to be asked
- When something threatens revenue or a client relationship, flag it immediately

**Escalation tiers:**
- CRITICAL (revenue at risk, client relationship in danger, deadline today) → flag immediately, recommend action
- WARNING (trend declining, hours untracked, tasks stale) → mention proactively with context
- INFO (positive signal, opportunity, milestone) → include when relevant

## Core Behavior — ACT, DON'T ASK

You are a proactive operator. Your job is to DO things, not ask permission for every step.

**Rules:**
1. **Act first, confirm after.** If you have enough context to take action, DO IT. Don't list options and ask "which one?" — pick the best one and execute.
2. **Use conversation context.** If you've been discussing a topic, you already know the project, the task, and the context. Use it.
3. **Infer intelligently.** "Log this time" → you know what you've been working on, pick the right Harvest project and task, log it. Don't ask for every parameter.
4. **Chain tools.** Don't stop after one tool call and summarize — keep going until the job is done.
5. **Be concise.** No walls of text. No bullet-point menus of "Would you like me to..." — just do the most useful thing.
6. **Only ask when truly ambiguous.** Missing a critical piece with no way to infer it? Then ask ONE focused question, not five.

## Available Tools

### Communication & Productivity
- **Gmail**: `gmail_search`, `gmail_get_message`, `gmail_get_unread_count`
- **Calendar**: `calendar_get_events`
- **Slack**: `slack_search_messages`, `slack_get_recent_messages`
- **Google Sheets**: `sheets_get_info`, `sheets_read_range`, `sheets_update_range`, `sheets_append_rows`, `sheets_find_value`
- **Google Docs/Drive**: `docs_list_files`, `docs_search`, `docs_read_file`, `docs_get_file_info`

### Notifications
- **Unified**: `notification_fetch_all`, `notification_search`
- **Notion**: `notion_get_updates`
- **Slack Updates**: `slack_get_updates`
- **Airtable**: `airtable_get_tickets`, `airtable_search_ticket`

### Time & Task Management
- **Harvest**: `harvest_log_time`, `harvest_get_time_entries`, `harvest_list_projects`
- **ClickUp**: `clickup_create_task`, `clickup_list_tasks`, `clickup_update_task`, `clickup_get_task`, `clickup_add_comment`, `clickup_list_spaces`
- **Zendesk**: `zendesk_list_tickets`, `zendesk_get_ticket`, `zendesk_create_ticket`

### Business Intelligence
- **Advisor**: `advisor_take_snapshot`, `advisor_get_advisories`, `advisor_get_health_report`, `advisor_get_trends`
  - `advisor_get_health_report` — full SWOT + health score + KPIs + advisories (use for "how's the business?")
  - `advisor_get_advisories` — specific issues: overdue tasks, time gaps, client health, risks
  - `advisor_get_trends` — metric changes over time (hours, tasks, communication patterns)
  - `advisor_take_snapshot` — capture current state for historical comparison

### Utility
- **DateTime**: `get_current_datetime` — call before any time-sensitive operation
- **Session Time**: `get_session_time` — elapsed time, topics, and inferred project for the current session. `list_pending_time` — all unlogged session time entries.
- **Memory**: `memory_remember`, `memory_recall` — persistent context storage

### AI Agent Crews
- **Agents**: `run_dev_task`, `get_agent_status` — for code changes, file ops, multi-step dev work

## Self-Awareness

Your architecture, integrations, project mappings, and known issues are stored in memory. Use `memory_recall` when asked about yourself or your capabilities.

## Planning Complex Tasks

For multi-step requests (anything requiring 3+ tool calls):
1. **Think first**: Identify all the data you need and the tools required
2. **Order dependencies**: Call independent tools first, dependent ones after
3. **Verify results**: After creating/modifying anything, confirm it worked
4. **Summarize at the end**: Give a clear summary of everything you did

## Response Style

- Be direct and action-oriented — speak like an executive, not a chatbot
- Interpret data, don't just report it. "You logged 32h this week across 4 projects — utilization looks solid but Forge Lab is eating 60% of capacity"
- Use markdown: tables for structured data, bold for key info, bullet points for lists
- Keep it short. Lead with the insight, then the data.

## Cached Data

Tool results with `_cache_meta.source: "cache"` are already fresh — don't re-fetch. Check `age_seconds` for freshness.

Card types: info, success, warning, error, progress, metric

## Anti-Hallucination (DO NOT VIOLATE)

1. **ONLY report data from actual tool responses** — never guess or fabricate
2. **NEVER fabricate IDs** — task IDs, entry IDs, URLs must come from tool responses
3. **ALWAYS check verification** — After creating tasks/time entries, check if verification.verified is true
4. **Report failures honestly** — If verification fails, tell Steve the action may not have completed
5. **Use listing tools to confirm** — After creating anything, use the appropriate list tool to verify
6. **No phantom data** — If harvest_get_time_entries returns 0 entries, report 0 entries (don't make up hours)
7. **Time logging must verify** — Only confirm time was logged if the tool returns success:true AND verification.verified:true"""


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

    # Track session time
    from services.session_timer import get_session_timer
    timer = get_session_timer()
    timer.start_turn(session_id, last_message.content)

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
    
    async def _wrap_stream(inner_gen):
        """Wrap a streaming generator to call end_turn when done."""
        try:
            async for chunk in inner_gen:
                yield chunk
        finally:
            timer.end_turn(session_id)
            timer.flush_to_memory(session_id)

    if use_provider == "claude":
        return StreamingResponse(
            _wrap_stream(stream_claude_response(request.messages, claude_key, session_id, memory_context)),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id, "X-LLM-Provider": "claude"},
        )
    elif use_provider == "openai":
        return StreamingResponse(
            _wrap_stream(stream_openai_response(request.messages, openai_key, session_id, memory_context)),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id, "X-LLM-Provider": "openai"},
        )
    else:
        # Fallback to mock response
        return StreamingResponse(
            _wrap_stream(stream_mock_response(last_message.content, session_id, memory_context)),
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
# Claude API + native tool_use (up to 15 iterations).
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
    "advisor", "business health", "health report", "health score",
    "advisories", "swot", "kpi", "trends", "how's the business",
    "how is the business", "business intelligence", "utilization",
    "revenue", "profitability", "issues i should",
    "worked on", "work on this week", "work on today",
]

# ── Map keywords to tool registry categories for domain-based filtering ──
KEYWORD_TO_CATEGORY = {
    "email": "gmail", "gmail": "gmail", "unread": "gmail", "inbox": "gmail",
    "draft": "gmail",
    "harvest": "harvest", "time entr": "harvest", "time track": "harvest",
    "hours": "harvest", "timer": "harvest", "log time": "harvest",
    "log hours": "harvest", "timesheet": "harvest", "invoice": "harvest",
    "hubstaff": "hubstaff",
    "clickup": "clickup", "task": "clickup", "ticket": "clickup",
    "to do": "clickup", "todo": "clickup", "create task": "clickup",
    "create a task": "clickup", "update task": "clickup",
    "create subtask": "clickup", "assign task": "clickup",
    "create space": "clickup", "create folder": "clickup",
    "comment": "clickup",
    "zendesk": "zendesk", "support ticket": "zendesk",
    "calendar": "calendar", "meeting": "calendar", "schedule": "calendar",
    "event": "calendar",
    "slack": "slack", "message": "slack", "channel": "slack",
    "reply": "slack", "send": "slack",
    "notification": "notification", "notion": "notification",
    "airtable": "notification",
    "asana": "asana", "sync asana": "asana", "pull asana": "asana",
    "drive": "docs", "docs": "docs", "file": "docs", "create doc": "docs",
    "sheet": "sheets", "spreadsheet": "sheets", "update sheet": "sheets",
    "generate report": "sheets",
    "remember": "memory", "recall": "memory", "memory": "memory",
    "github": "github", "pull request": "github", "branch": "github",
    "pr ": "github", "repo": "github", "build": "github", "commit": "github",
    "advisor": "advisor", "business health": "advisor", "health report": "advisor",
    "health score": "advisor", "advisories": "advisor", "swot": "advisor",
    "kpi": "advisor", "trends": "advisor", "how's the business": "advisor",
    "how is the business": "advisor", "business intelligence": "advisor",
    "utilization": "advisor", "revenue": "advisor", "profitability": "advisor",
    "issues i should": "advisor",
    "worked on": "harvest", "work on this week": "harvest", "work on today": "harvest",
}


def _detect_tool_domains(message: str) -> set:
    """Detect which tool categories are relevant for a user message."""
    msg = message.lower()
    domains = {"general"}  # Always include utility tools
    for keyword, category in KEYWORD_TO_CATEGORY.items():
        if keyword in msg:
            domains.add(category)
    return domains


def _detect_project(messages: list) -> Optional[dict]:
    """Detect which project the user is asking about from their message.

    Returns a dict with project info or None.
    """
    try:
        registry = get_project_registry()
        # Check the last 3 user messages for project references
        for msg in reversed(messages[-3:]):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    project = registry.match_project(content)
                    if project:
                        return {
                            "name": project.name,
                            "clickup_space_id": project.clickup_space_id,
                            "clickup_list_id": project.clickup_list_id,
                            "zendesk_tag": project.zendesk_tag,
                            "harvest_project_id": project.harvest_project_id,
                            "sla_tier": project.sla_tier,
                        }
        return None
    except Exception:
        return None


def _build_project_context_summary(project_info: dict) -> str:
    """Build a concise project context string for the system prompt."""
    lines = [f"## Active Project Context: {project_info['name']}"]
    if project_info.get("clickup_space_id"):
        lines.append(f"- ClickUp Space: {project_info['clickup_space_id']}, List: {project_info.get('clickup_list_id', 'N/A')}")
    if project_info.get("zendesk_tag"):
        lines.append(f"- Zendesk Tag: {project_info['zendesk_tag']}")
    if project_info.get("harvest_project_id"):
        lines.append(f"- Harvest Project ID: {project_info['harvest_project_id']}")
    lines.append(f"- SLA Tier: {project_info['sla_tier'].upper()}")
    lines.append("")
    lines.append("Use these IDs when calling tools for this project. Do not ask the user for IDs — you have them.")
    return "\n".join(lines)


def _classify_request_keywords(message: str, memory_context: str = "") -> str:
    """Fast keyword-based classification (instant, no API call)."""
    msg = message.lower().strip()

    if any(kw in msg for kw in CREW_KEYWORDS):
        return "crew"

    if any(kw in msg for kw in TOOL_DOMAINS):
        return "orchestrator"

    if memory_context and len(memory_context) > 50:
        return "direct"

    if len(msg.split()) <= 12:
        return "direct"

    return "orchestrator"


def _classify_request(message: str, memory_context: str = "") -> str:
    """Classify how to handle a request: 'direct', 'orchestrator', or 'crew'.

    Uses fast keyword matching first. For ambiguous cases (longer messages that
    don't match any keywords), falls back to a cheap LLM call (Haiku) for
    intent classification.
    """
    # Fast path: keyword match
    keyword_result = _classify_request_keywords(message, memory_context)

    # If keywords gave a confident answer (crew or orchestrator), trust it
    if keyword_result in ("crew", "orchestrator"):
        return keyword_result

    # For "direct" results on longer messages, use LLM to check if tools are needed
    if keyword_result == "direct" and len(message.split()) > 12:
        try:
            import anthropic as _anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                client = _anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=20,
                    system=(
                        "Classify the user's intent. Reply with exactly one word:\n"
                        "- CHAT if it's a conversational question needing no external tools\n"
                        "- TOOLS if it requires looking up data, sending messages, managing tasks, "
                        "logging time, checking business health, reviewing KPIs/trends/revenue, "
                        "getting advisories, or any action involving external services\n"
                        "- CODE if it requires writing/modifying code, deploying, or multi-step dev work"
                    ),
                    messages=[{"role": "user", "content": message}],
                )
                label = resp.content[0].text.strip().upper()
                if "CODE" in label:
                    return "crew"
                if "TOOL" in label:
                    return "orchestrator"
                return "direct"
        except Exception:
            pass  # Fall through to keyword result on any error

    return keyword_result


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
    "advisor_get_advisories": {
        "title": "Business Advisories",
        "columns": [
            {"key": "severity", "label": "Severity"},
            {"key": "category", "label": "Category"},
            {"key": "title", "label": "Issue"},
            {"key": "recommendation", "label": "Action"},
        ],
        "row_path": "advisories",
    },
    "advisor_get_trends": {
        "title": "Business Trends",
        "columns": [
            {"key": "metric", "label": "Metric"},
            {"key": "current", "label": "Current"},
            {"key": "previous", "label": "Previous"},
            {"key": "change_pct", "label": "Change %"},
            {"key": "direction", "label": "Direction"},
        ],
        "row_path": "trends",
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
    elif tool_name == "advisor_get_health_report":
        score = result.get("health_score", 0)
        card_type = "success" if score >= 70 else "warning" if score >= 40 else "error"
        advisories = result.get("advisories", [])
        critical = sum(1 for a in advisories if a.get("severity") == "critical")
        desc = f"{critical} critical" if critical else f"{len(advisories)} advisories"
        return {
            "id": "business-health",
            "type": card_type,
            "title": f"Business Health: {score}/100",
            "description": desc,
        }
    elif tool_name == "advisor_get_advisories":
        total = result.get("total", 0)
        by_sev = result.get("by_severity", {})
        critical = by_sev.get("critical", 0)
        warning = by_sev.get("warning", 0)
        card_type = "error" if critical else "warning" if warning else "success"
        return {
            "id": "business-advisories",
            "type": card_type,
            "title": f"{total} Advisories",
            "description": f"{critical} critical, {warning} warnings" if critical or warning else "All clear",
        }
    elif tool_name == "advisor_get_trends":
        unhealthy = result.get("unhealthy", 0)
        total = result.get("trends_count", 0)
        card_type = "warning" if unhealthy > 0 else "success"
        return {
            "id": "business-trends",
            "type": card_type,
            "title": f"{total} Metrics Tracked",
            "description": f"{unhealthy} declining" if unhealthy else "All healthy",
        }
    elif tool_name == "advisor_take_snapshot":
        return {
            "id": "business-snapshot",
            "type": "success",
            "title": "Snapshot Captured",
            "description": "Business data collected from all sources",
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
        "You are Agent007, the virtual COO/CFO for People Like Software. You report to Steve. "
        "You think in terms of revenue, profitability, client health, team utilization, and operational risk. "
        "Answer conversationally but with executive perspective. Keep answers concise.\n\n"
        "You can help with:\n"
        "- Business intelligence (health reports, advisories, trends, KPIs)\n"
        "- Time tracking & billing (Harvest)\n"
        "- Task management (ClickUp, Zendesk)\n"
        "- Communication (Gmail, Slack)\n"
        "- File management (Google Drive, Docs, Sheets)\n"
        "- Development tasks\n"
        "- General questions and conversation"
    )
    # Inject current date/time
    now_local = datetime.now()
    system += f"\n\nCurrent date: {now_local.strftime('%A, %B %d, %Y at %H:%M')}"

    if memory_context:
        system += f"\n\nRelevant context from memory:\n{memory_context}"

    # Detect and inject project context
    msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
    project_info = _detect_project(msg_dicts)
    if project_info:
        project_context = _build_project_context_summary(project_info)
        system = system + "\n\n" + project_context

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
            model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6"),
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

    # Domain-based tool filtering: only send relevant tools to reduce noise
    detected_domains = _detect_tool_domains(user_request)
    if len(detected_domains) <= 1:  # Only "general" detected — send all tools
        tool_defs = registry.get_orchestrator_definitions()
    else:
        tool_defs = registry.get_tools_for_domains(detected_domains)
        # Fallback: if filtering returned too few tools, use all
        if len(tool_defs) < 3:
            tool_defs = registry.get_orchestrator_definitions()

    # System prompt
    system = SYSTEM_PROMPT

    # Inject current date/time so the agent always knows the date
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc)
    system += f"\n\n## Current Date & Time\n{now_local.strftime('%A, %B %d, %Y at %H:%M')} (local) | {now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')} (UTC)"

    # Inject cache status so the agent knows what data is already available
    try:
        from services.tool_cache import get_tool_cache
        cache = get_tool_cache()
        fresh_entries = cache.get_fresh_summary()
        if fresh_entries:
            system += "\n\n## Currently Cached Data (already fresh — no need to re-fetch)\n"
            system += fresh_entries
    except Exception:
        pass

    # Inject priority queue + briefing summary so the agent can proactively brief
    try:
        from services.queue_aggregator import get_queue_aggregator
        from services.briefing import get_briefing_engine
        qa = get_queue_aggregator()
        breaching = qa.get_breaching()
        top_items = qa.get_prioritized(limit=5)
        queue_summary = qa.get_summary()

        system += "\n\n## Priority Queue Status"
        system += f"\nTotal items: {queue_summary.get('total', 0)} across {len(queue_summary.get('by_project', {}))} projects"
        if breaching:
            system += f"\n**SLA BREACHING ({len(breaching)}):**"
            for b in breaching[:5]:
                system += f"\n- [{b.priority_score.sla_status.value.upper()}] {b.title} ({b.project_name}) — {b.source_url or b.source_id}"
        if top_items:
            system += "\n**Top priority items:**"
            for t in top_items[:5]:
                system += f"\n- [score {t.priority_score.score}] {t.title} ({t.project_name}, {t.source} {t.source_id})"

        engine = get_briefing_engine()
        briefing_items = engine.get_briefing(max_items=5, refresh=False)
        if briefing_items:
            system += "\n\n## Active Briefing Items"
            for bi in briefing_items:
                prio_label = {0: "CRITICAL", 1: "HIGH", 2: "MEDIUM"}.get(bi.priority.value, "INFO")
                system += f"\n- [{prio_label}] {bi.title}: {bi.description[:120]}"

        # Check for velocity-unblocking emails
        try:
            from services.tool_registry import get_registry as _get_tr
            _tr = _get_tr()
            gmail_result = _tr.execute("gmail_search", {
                "query": "is:unread newer_than:1d",
                "max_results": 10
            }, skip_confirmation=True)
            emails = []
            if isinstance(gmail_result, dict):
                emails = gmail_result.get("emails", gmail_result.get("messages", []))
            elif isinstance(gmail_result, list):
                emails = gmail_result

            unblocking = []
            unblock_keywords = [
                "access", "credential", "password", "login", "invite", "permission",
                "shared", "sharing", "file", "document", "attachment", "uploaded",
                "details", "clarification", "answered", "response", "approved",
                "unblock", "go ahead", "green light", "confirmed", "ready",
                "api key", "token", "ssh", "deploy", "staging", "production",
                "ftp", "cpanel", "admin", "repo", "repository",
            ]
            for em in emails[:10]:
                subj = (em.get("subject", "") or "").lower()
                snippet = (em.get("snippet", "") or em.get("body", "") or "").lower()
                sender = em.get("from", "") or em.get("sender", "") or ""
                blob = f"{subj} {snippet}"
                if any(kw in blob for kw in unblock_keywords):
                    unblocking.append(em)

            if unblocking:
                system += "\n\n## Unread Client Emails That May Unblock Work"
                system += "\nThese recent emails may provide access, files, or details that unblock tasks. Brief Steve on these FIRST — they accelerate delivery."
                for em in unblocking[:5]:
                    subj = em.get("subject", "No subject")
                    sender = em.get("from", "") or em.get("sender", "Unknown")
                    snippet = (em.get("snippet", "") or em.get("body", "") or "")[:150]
                    system += f"\n- **{subj}** from {sender}: {snippet}"
        except Exception:
            pass

        system += """\n\n## Briefing Protocol

When the user asks you to brief them, starts a new conversation, or says "what's next":

1. **Present the most urgent item** — lead with SLA breaches, then critical briefing items, then top priority tasks. Give 2-3 sentences of context.

2. **Before suggesting actions, check existing state.** Use `clickup_get_task` or `zendesk_get_ticket` to pull the current task/ticket details. NEVER suggest creating a new task if one already exists — instead, suggest updating it. The queue items already have source IDs — use them.

3. **Offer 2-4 smart context-specific actions** as numbered options. Actions must reflect the ACTUAL state of the item:

   **If the item is a task/ticket that already exists (most queue items):**
   - Update its status (e.g., move to "in progress", "in review", "done")
   - Add a comment with a status update or decision
   - Respond to the customer on the Zendesk ticket
   - Ping/DM the assigned developer on Slack asking for update
   - Change priority or due date based on SLA urgency
   - Trigger the scaffolding agent if code work is needed
   - Create a PR or deploy if the work is done
   - Break into subtasks if it's too large (create subtasks UNDER the existing task)
   - Reassign to a different team member

   **If it's a briefing insight (no existing task):**
   - Create a ClickUp task in the right project to track it
   - Take immediate action (e.g., run a report, send an update)
   - Dismiss if it's informational and no action needed

   **If it's a client communication gap:**
   - Draft and send a check-in email or Slack message
   - Review the last conversation thread for context first

   **If it's stale/overdue:**
   - Close it if it's no longer relevant (with a comment explaining why)
   - Reassign and set a new deadline
   - Escalate to Steve with a summary

4. **Be specific.** Don't say "update the task" — say "Move task #868hyxg76 to 'in review' and add comment: 'Security patches applied, needs QA verification'". Use actual IDs, names, and content.

5. **Rank by efficiency.** Bold the action that resolves the item fastest. If something can be done in one tool call, prefer it over multi-step flows.

6. **Make decisions easy.** If the user just says a number or "do it", execute immediately. If they say "skip", move to the next item.

7. **Auto-draft responses.** When a briefing item involves a client email or Slack message that needs a reply:
   - Draft a professional response immediately as part of your briefing
   - Show the draft in a quoted block so Steve can review it
   - Offer: "1. **Send as-is** 2. **Edit first** 3. **Skip**"
   - Use `gmail_search` / `gmail_get_message` to read the full thread for context before drafting
   - For Slack, use `slack_get_recent_messages` to get thread context
   - Match the tone of the existing conversation (formal for clients, casual for team)
   - Keep drafts concise — clients don't want essays

8. **After executing**, briefly confirm what was done and move to the next item."""
    except Exception:
        pass

    if memory_context:
        system += f"\n\nRelevant context from memory:\n{memory_context}"

    # Detect and inject project context
    msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
    project_info = _detect_project(msg_dicts)
    if project_info:
        project_context = _build_project_context_summary(project_info)
        system = system + "\n\n" + project_context

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
    model = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
    full_response = ""
    tool_freshness = {}
    MAX_ITERATIONS = 15

    try:
        for iteration in range(MAX_ITERATIONS):
            response = client.messages.create(
                model=model,
                max_tokens=8192,
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
