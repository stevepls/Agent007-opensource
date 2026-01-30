"""Orchestrator Tools

Provides two sets of tools for agents:
1. Direct file tools (file_tools.py) - Python-based file operations
2. Claude CLI tools (claude_cli.py) - Delegates to Claude Code CLI

The hybrid approach uses:
- CrewAI agents for planning and review (using Claude API)
- Claude CLI for actual file operations (native tool use)
"""

from .file_tools import (
    ReadFileTool,
    WriteFileTool,
    ListDirectoryTool,
    SearchCodeTool,
    get_file_tools
)

from .claude_cli import (
    ClaudeCLITool,
    ClaudeCLIReadTool,
    ClaudeCLIEditTool,
    ClaudeCLIBashTool,
    ClaudeCLIConfig,
    PermissionMode,
    get_claude_cli_tools,
)

from .devops import (
    DevOpsToolRunner,
    DevOpsListTool,
    get_devops_tools,
    list_available_tools as list_devops_tools,
    DEVOPS_TOOLS,
    # Focus workspace tools
    FocusListTool,
    FocusOpenTool,
    get_focus_tools,
    list_workspaces,
)

from .harvest import (
    HarvestStartTimerTool,
    HarvestStopTimerTool,
    HarvestLogTimeTool,
    HarvestStatusTool,
    get_harvest_tools,
    # Direct functions for UI
    start_timer as harvest_start_timer,
    stop_timer as harvest_stop_timer,
    log_time as harvest_log_time,
    get_status as harvest_get_status,
    get_projects as harvest_get_projects,
    get_tasks as harvest_get_tasks,
)

from .tickets import (
    # Zendesk tools
    ZendeskGetTicketTool,
    ZendeskListTicketsTool,
    ZendeskCreateTicketTool,
    ZendeskAddCommentTool,
    ZendeskSearchTool,
    get_zendesk_tools,
    # ClickUp tools
    ClickUpGetTaskTool,
    ClickUpListTasksTool,
    ClickUpCreateTaskTool,
    ClickUpAddCommentTool,
    ClickUpUpdateTaskTool,
    get_clickup_tools,
    # Combined
    TicketSyncStatusTool,
    get_ticket_tools,
)

__all__ = [
    # Direct file tools
    "ReadFileTool",
    "WriteFileTool",
    "ListDirectoryTool",
    "SearchCodeTool",
    "get_file_tools",
    # Claude CLI tools
    "ClaudeCLITool",
    "ClaudeCLIReadTool",
    "ClaudeCLIEditTool",
    "ClaudeCLIBashTool",
    "ClaudeCLIConfig",
    "PermissionMode",
    "get_claude_cli_tools",
    # DevOps tools
    "DevOpsToolRunner",
    "DevOpsListTool",
    "get_devops_tools",
    "list_devops_tools",
    "DEVOPS_TOOLS",
    # Focus workspace tools
    "FocusListTool",
    "FocusOpenTool",
    "get_focus_tools",
    "list_workspaces",
    # Harvest time tracking tools
    "HarvestStartTimerTool",
    "HarvestStopTimerTool",
    "HarvestLogTimeTool",
    "HarvestStatusTool",
    "get_harvest_tools",
    "harvest_start_timer",
    "harvest_stop_timer",
    "harvest_log_time",
    "harvest_get_status",
    "harvest_get_projects",
    "harvest_get_tasks",
    # Ticket management tools
    "ZendeskGetTicketTool",
    "ZendeskListTicketsTool",
    "ZendeskCreateTicketTool",
    "ZendeskAddCommentTool",
    "ZendeskSearchTool",
    "get_zendesk_tools",
    "ClickUpGetTaskTool",
    "ClickUpListTasksTool",
    "ClickUpCreateTaskTool",
    "ClickUpAddCommentTool",
    "ClickUpUpdateTaskTool",
    "get_clickup_tools",
    "TicketSyncStatusTool",
    "get_ticket_tools",
]
