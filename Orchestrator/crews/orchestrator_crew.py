"""
General-Purpose Orchestrator Crew

Handles ALL tasks (time tracking, task management, communication, etc.)
Routes requests through CrewAI agents instead of direct tool execution.

This crew provides a unified interface for all operations through AI agents.
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from crewai import Crew, Task, Process, Agent
from crewai.tools import BaseTool
from crewai.events import (
    crewai_event_bus,
    ToolUsageStartedEvent,
    ToolUsageFinishedEvent,
    TaskStartedEvent,
    TaskCompletedEvent,
    AgentReasoningStartedEvent,
)
from pydantic import BaseModel, Field

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base import get_llm, AGENT_CONFIG, create_policy_aware_backstory
from services.tool_registry import ToolRegistry, get_registry
from governance.audit import get_audit_logger, AuditEvent, ActionType
from governance.cost_tracker import get_cost_tracker
from services.progress_tracker import ProgressTracker

# Import existing CrewAI tools
from tools.harvest import get_harvest_tools
from tools.tickets import get_ticket_tools
from tools.communication import get_communication_tools
from tools.drive import get_drive_tools
from tools.sheets import get_sheets_tools
from tools.file_tools import get_file_tools
from tools.github import get_github_tools


# ============================================================================
# Tool Registry to CrewAI Bridge
# ============================================================================

def create_tool_wrapper(tool_name: str, tool_def: Dict[str, Any], registry: ToolRegistry) -> BaseTool:
    """Create a CrewAI BaseTool wrapper for a ToolRegistry tool."""
    
    class DynamicToolWrapper(BaseTool):
        """Dynamic wrapper for ToolRegistry tools."""
        name: str = tool_name
        description: str = tool_def.get("description", "")
        
        def _run(self, **kwargs) -> str:
            """Execute the tool via ToolRegistry."""
            # Remove None values
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            
            result = registry.execute(tool_name, kwargs, skip_confirmation=False)
            
            # Handle confirmation requests
            if result.get("requires_confirmation"):
                return json.dumps({
                    "status": "requires_confirmation",
                    "message": result.get("message", "This action needs approval"),
                    "preview": result.get("preview", ""),
                    "danger_level": result.get("danger_level", "medium")
                }, indent=2)
            
            # Convert result to string for CrewAI
            if isinstance(result, dict):
                return json.dumps(result, indent=2, default=str)
            return str(result)
    
    # Set the name dynamically
    DynamicToolWrapper.name = tool_name
    DynamicToolWrapper.description = tool_def.get("description", "")
    
    return DynamicToolWrapper()


def get_all_crewai_tools() -> List[BaseTool]:
    """
    Get all tools in CrewAI BaseTool format.
    
    Combines:
    1. Existing CrewAI tools (from tools/ directory)
    2. ToolRegistry tools (wrapped for CrewAI)
    """
    all_tools = []

    # Add existing CrewAI tools
    tool_loaders = [
        ("harvest", get_harvest_tools),
        ("tickets", get_ticket_tools),
        ("communication", get_communication_tools),
        ("drive", get_drive_tools),
        ("sheets", get_sheets_tools),
        ("file_tools", get_file_tools),
        ("github", get_github_tools),
    ]

    for name, loader in tool_loaders:
        try:
            all_tools.extend(loader())
        except Exception as e:
            print(f"[WARN] Failed to load {name} tools: {e}")
    
    # Add ToolRegistry tools (wrapped)
    registry = get_registry()
    existing_tool_names = {tool.name for tool in all_tools}
    
    for tool_name, tool_def in registry._tools.items():
        # Skip if already have a CrewAI version
        if tool_name in existing_tool_names:
            continue
        
        try:
            wrapper = create_tool_wrapper(tool_name, tool_def, registry)
            all_tools.append(wrapper)
        except Exception as e:
            print(f"[WARN] Could not wrap tool {tool_name}: {e}")
            continue
    
    return all_tools


# ============================================================================
# Orchestrator Agent
# ============================================================================

ORCHESTRATOR_AGENT_BACKSTORY = """You are Agent007, an AI assistant that helps Steve manage software development and business operations.

You have access to ALL tools and can handle ANY request:
- Time tracking (Harvest)
- Task management (ClickUp, Zendesk)
- Communication (Gmail, Slack)
- File management (Google Drive, Docs, Sheets)
- Development tasks (code changes, file operations)
- And more...

CRITICAL RULES:
1. ALWAYS use tools to get real data - never guess or fabricate
2. When user asks for something, use the appropriate tool
3. For complex multi-step tasks, break them down
4. Report only facts you can verify from tool responses
5. If a tool fails, explain the error clearly

TOOL CATEGORIES:
- **Time Tracking**: harvest_log_time, harvest_get_time_entries, harvest_list_projects, hubstaff_get_active_entries, hubstaff_get_time_entries, hubstaff_start_time, hubstaff_stop_time, generate_timesheet, generate_draft_invoice
- **Task Management**: clickup_create_task, clickup_list_tasks, clickup_update_task, clickup_get_task, clickup_get_comments, zendesk_list_tickets
- **Communication**: gmail_search, slack_get_recent_messages, slack_search_messages, slack_get_dm_history, slack_list_dms, slack_send_dm, slack_post_message
- **Files & Reports**: docs_read_file, sheets_read_range, sheets_create, drive_list_files
- **Asana**: asana_list_my_tasks, asana_pull_to_clickup
- **GitHub**: github_list_prs, github_get_pr, github_list_branches, github_get_branch_commits, github_search_code
- **Development**: run_dev_task (for code changes)
- **Utility**: get_current_datetime (ALWAYS use before time-sensitive work)

TIME AWARENESS:
- ALWAYS call get_current_datetime before time-sensitive operations (logging time, generating timesheets/invoices, scheduling, checking what day it is)
- The date/time at the top of the task may be stale if the conversation has been running — use the tool to verify
- When a user says "today", "this week", "yesterday", etc., confirm the actual date with the tool first

RESPONSE STYLE:
- Be conversational and helpful
- Summarize tool results clearly
- Don't dump raw data - interpret it
- Keep responses concise
- Only state facts from tool responses

DATA FRESHNESS:
Tool results include a "_cache_meta" field with data freshness info.
When _cache_meta.source is "cache", mention the age parenthetically,
e.g., "(cached 3m ago)". When source is "live", optionally note "(live data)".
This helps the user know how recent the data is.

When user asks:
- "Log time" → Use harvest_log_time
- "Show my tasks" → Use clickup_list_tasks
- "Check email" → Use gmail_search
- "Show my DMs with X" / "What did X say?" → Use slack_get_dm_history with user_name
- "Who have I DM'd?" → Use slack_list_dms
- "Create a task" → Use clickup_create_task
- "What did I work on?" → Use harvest_get_time_entries
- "Show my Asana tasks" → Use asana_list_my_tasks
- "Sync Asana tasks" → Use asana_pull_to_clickup
- "Generate a timesheet" / "Create a timesheet" → Use generate_timesheet with start_date and end_date
- "Create an invoice" / "Draft invoice" → Use generate_draft_invoice with start_date and end_date
- "Read task comments" / "What did X say on task" → Use clickup_get_comments with task_id
- "DM someone" / "Send a message to X" → Use slack_send_dm with user_name and text
- "Show PRs" / "List pull requests" → Use github_list_prs
- "Show branches" → Use github_list_branches
- "What's on branch X" → Use github_get_branch_commits with branch name
- "Build a feature" → Use run_dev_task (delegates to dev crew)
- "Check Notion" / "Notion tickets" / "What's assigned in Notion" → Use gmail_search with query "from:notify@mail.notion.so" (Notion sends assignment/update notifications via email — search Gmail to find them)
"""


def create_orchestrator_agent(tools: list = None) -> Agent:
    """Create the main orchestrator agent with access to all tools."""
    if tools is None:
        tools = get_all_crewai_tools()
    
    policy_backstory = create_policy_aware_backstory(
        ORCHESTRATOR_AGENT_BACKSTORY,
        categories=["security", "production", "quality", "escalation"]
    )
    
    return Agent(
        role="AI Assistant & Task Orchestrator",
        goal="Help Steve manage all aspects of software development and business operations using available tools",
        backstory=policy_backstory,
        llm=get_llm(),
        tools=tools,
        verbose=True,
        allow_delegation=False,  # Single agent handles everything
        max_iter=15,  # Allow more iterations for complex multi-tool tasks
        max_rpm=30,
    )


# ============================================================================
# Crew Creation
# ============================================================================

def create_orchestrator_crew(verbose: bool = True) -> Crew:
    """
    Create the general-purpose orchestrator crew.
    
    This crew handles ALL tasks (time tracking, task management, etc.)
    through a single agent with access to all tools.
    """
    # Get all tools (CrewAI + ToolRegistry wrapped)
    all_tools = get_all_crewai_tools()
    
    print(f"[INFO] Orchestrator crew loaded {len(all_tools)} tools")
    
    # Create orchestrator agent with all tools
    orchestrator = create_orchestrator_agent(tools=all_tools)
    
    # Create crew (sequential process - single agent)
    crew = Crew(
        agents=[orchestrator],
        tasks=[],  # Tasks added dynamically
        process=Process.sequential,
        verbose=verbose,
    )
    
    return crew


# ============================================================================
# Event Listener for Progress Tracking (thread-local, registered once)
# ============================================================================

_listeners_registered = False


def setup_progress_listeners():
    """Register CrewAI event-bus listeners once at module level.

    Handlers use thread-local storage to find the ProgressTracker for the
    current worker thread, enabling safe concurrent crew execution.
    """
    global _listeners_registered
    if _listeners_registered:
        return
    _listeners_registered = True

    from services.task_queue import get_current_tracker

    @crewai_event_bus.on(ToolUsageStartedEvent)
    def on_tool_start(source, event: ToolUsageStartedEvent):
        tracker = get_current_tracker()
        if tracker and not tracker.is_cancelled:
            tracker.emit(
                event_type="tool_start",
                agent=event.agent_role or "",
                tool=event.tool_name or "",
                message=f"Using {event.tool_name}...",
            )
        if tracker and tracker.is_cancelled:
            raise InterruptedError("Task cancelled by user")

    @crewai_event_bus.on(ToolUsageFinishedEvent)
    def on_tool_done(source, event: ToolUsageFinishedEvent):
        tracker = get_current_tracker()
        if tracker and not tracker.is_cancelled:
            output_preview = str(event.output)[:200] if event.output else ""
            # Extract cache source from tool output
            cache_source = ""
            try:
                if event.output:
                    output_data = json.loads(str(event.output)) if isinstance(event.output, str) else event.output
                    if isinstance(output_data, dict) and "_cache_meta" in output_data:
                        cache_source = output_data["_cache_meta"].get("source", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
            tracker.emit(
                event_type="tool_done",
                agent=event.agent_role or "",
                tool=event.tool_name or "",
                output=output_preview,
                message=f"{event.tool_name} complete",
                cache_source=cache_source,
            )

    @crewai_event_bus.on(AgentReasoningStartedEvent)
    def on_reasoning(source, event: AgentReasoningStartedEvent):
        tracker = get_current_tracker()
        if tracker and not tracker.is_cancelled:
            tracker.emit(
                event_type="thinking",
                agent=event.agent_role or "",
                message=f"Thinking (attempt {event.attempt})...",
            )
        if tracker and tracker.is_cancelled:
            raise InterruptedError("Task cancelled by user")

    @crewai_event_bus.on(TaskStartedEvent)
    def on_task_start(source, event: TaskStartedEvent):
        tracker = get_current_tracker()
        if tracker and not tracker.is_cancelled:
            tracker.emit(
                event_type="task_start",
                message=f"Starting task: {event.task_name or 'processing'}",
            )

    @crewai_event_bus.on(TaskCompletedEvent)
    def on_task_done(source, event: TaskCompletedEvent):
        tracker = get_current_tracker()
        if tracker and not tracker.is_cancelled:
            tracker.emit(
                event_type="task_done",
                message=f"Task complete: {event.task_name or 'done'}",
            )


# ============================================================================
# Task Execution
# ============================================================================

def run_orchestrator_task(
    user_request: str,
    context: Optional[str] = None,
    session_id: Optional[str] = None,
    progress_tracker: Optional[ProgressTracker] = None,
) -> Dict[str, Any]:
    """
    Run any task through the orchestrator crew.

    This replaces direct tool execution in the Chat API.
    All requests now go through CrewAI agents.

    Args:
        user_request: What the user wants (e.g., "Log 2 hours to project X")
        context: Additional context (conversation history, etc.)
        session_id: Session ID for audit logging
        progress_tracker: Optional tracker for real-time progress events

    Returns:
        dict with 'result', 'status', 'audit_summary', 'cost_summary'
    """
    # Initialize governance
    logger = get_audit_logger()
    cost_tracker = get_cost_tracker()

    # Ensure event-bus listeners are registered (once), and set thread-local tracker
    setup_progress_listeners()
    from services.task_queue import set_current_tracker
    set_current_tracker(progress_tracker)

    # Log task start
    logger.log(AuditEvent(
        action_type=ActionType.TASK_START,
        description=f"Orchestrator task: {user_request[:100]}...",
        input_data={"request": user_request, "context": context[:200] if context else None},
    ))

    try:
        # Create crew
        crew = create_orchestrator_crew(verbose=True)

        # Build task description with current date/time so the LLM knows the real date
        now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
        task_description = f"CURRENT DATE/TIME: {now} (use get_current_datetime tool to verify before time-sensitive operations)\n\n{user_request}"
        if context:
            task_description = f"CURRENT DATE/TIME: {now} (use get_current_datetime tool to verify before time-sensitive operations)\n\n{user_request}\n\nContext:\n{context}"

        # Create task
        task = Task(
            description=task_description,
            agent=crew.agents[0],  # Use orchestrator agent
            expected_output="A helpful response that addresses the user's request, using tools as needed to get real data."
        )

        # Add task to crew
        crew.tasks = [task]

        # Execute
        result = crew.kickoff()

        # Log success
        logger.log(AuditEvent(
            action_type=ActionType.TASK_COMPLETE,
            description="Orchestrator task completed",
            output_data={"result_length": len(str(result))},
        ))

        return {
            "result": str(result),
            "status": "success",
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }

    except InterruptedError:
        print(f"[INFO] Orchestrator task cancelled by user")
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description="Orchestrator task cancelled by user",
            error="cancelled",
        ))
        return {
            "result": None,
            "status": "cancelled",
            "error": "Task cancelled by user",
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] Orchestrator crew execution failed: {error_trace}")

        # Log error
        logger.log(AuditEvent(
            action_type=ActionType.TASK_FAILED,
            description=f"Orchestrator task failed: {str(e)}",
            error=str(e),
        ))

        return {
            "result": None,
            "status": "error",
            "error": str(e),
            "audit_summary": logger.get_session_summary(),
            "cost_summary": cost_tracker.get_summary(),
            "needs_approval": False,
        }
    finally:
        set_current_tracker(None)
        if progress_tracker:
            progress_tracker.finish()
