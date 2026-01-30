"""
Ticket Management Tools for CrewAI

Provides Zendesk and ClickUp integration for the Orchestrator.
Enables agents to manage support tickets and project tasks.
"""

import os
from typing import Optional, List, Type
from pydantic import BaseModel, Field

try:
    from crewai.tools import BaseTool
except ImportError:
    from crewai_tools import BaseTool

# Handle both direct and package imports
try:
    from ..services.tickets import (
        ZendeskClient,
        ClickUpClient,
        get_zendesk_client,
        get_clickup_client,
    )
except ImportError:
    from services.tickets import (
        ZendeskClient,
        ClickUpClient,
        get_zendesk_client,
        get_clickup_client,
    )


# =============================================================================
# Input Schemas
# =============================================================================

class ZendeskGetTicketInput(BaseModel):
    ticket_id: int = Field(..., description="The Zendesk ticket ID")


class ZendeskListTicketsInput(BaseModel):
    status: Optional[str] = Field(None, description="Filter by status: new, open, pending, hold, solved, closed")
    tags: Optional[str] = Field(None, description="Comma-separated tags to filter by")
    limit: int = Field(20, description="Maximum number of tickets to return")


class ZendeskCreateTicketInput(BaseModel):
    subject: str = Field(..., description="Ticket subject line")
    description: str = Field(..., description="Ticket description/body")
    priority: str = Field("normal", description="Priority: low, normal, high, urgent")
    tags: Optional[str] = Field(None, description="Comma-separated tags")


class ZendeskAddCommentInput(BaseModel):
    ticket_id: int = Field(..., description="The Zendesk ticket ID")
    comment: str = Field(..., description="Comment text")
    public: bool = Field(True, description="Whether the comment is public (visible to requester)")


class ClickUpGetTaskInput(BaseModel):
    task_id: str = Field(..., description="The ClickUp task ID")


class ClickUpListTasksInput(BaseModel):
    list_id: str = Field(..., description="The ClickUp list ID")
    include_closed: bool = Field(False, description="Include closed tasks")


class ClickUpCreateTaskInput(BaseModel):
    list_id: str = Field(..., description="The ClickUp list ID")
    name: str = Field(..., description="Task name")
    description: str = Field("", description="Task description (markdown)")
    priority: int = Field(3, description="Priority: 1=Urgent, 2=High, 3=Normal, 4=Low")


class ClickUpAddCommentInput(BaseModel):
    task_id: str = Field(..., description="The ClickUp task ID")
    comment: str = Field(..., description="Comment text")


# =============================================================================
# Zendesk Tools
# =============================================================================

class ZendeskGetTicketTool(BaseTool):
    name: str = "zendesk_get_ticket"
    description: str = "Get details of a specific Zendesk support ticket by ID"
    args_schema: Type[BaseModel] = ZendeskGetTicketInput

    def _run(self, ticket_id: int) -> str:
        try:
            client = get_zendesk_client()
            ticket = client.get_ticket(ticket_id)

            if not ticket:
                return f"Ticket #{ticket_id} not found"

            return f"""
**Zendesk Ticket #{ticket.id}**
- **Subject:** {ticket.subject}
- **Status:** {ticket.status}
- **Priority:** {ticket.priority}
- **Requester:** {ticket.requester_email}
- **Assignee:** {ticket.assignee_email or 'Unassigned'}
- **Tags:** {', '.join(ticket.tags) if ticket.tags else 'None'}
- **Updated:** {ticket.updated_at.strftime('%Y-%m-%d %H:%M')}
- **URL:** {ticket.url}

**Description:**
{ticket.description[:500]}{'...' if len(ticket.description) > 500 else ''}
"""
        except Exception as e:
            return f"Error getting ticket: {str(e)}"


class ZendeskListTicketsTool(BaseTool):
    name: str = "zendesk_list_tickets"
    description: str = "List Zendesk tickets with optional filters (status, tags)"
    args_schema: Type[BaseModel] = ZendeskListTicketsInput

    def _run(self, status: str = None, tags: str = None, limit: int = 20) -> str:
        try:
            client = get_zendesk_client()
            tag_list = [t.strip() for t in tags.split(",")] if tags else None
            tickets = client.list_tickets(status=status, tags=tag_list, limit=limit)

            if not tickets:
                return "No tickets found matching criteria"

            lines = ["**Zendesk Tickets**\n"]
            for t in tickets[:limit]:
                lines.append(
                    f"- **#{t.id}** [{t.status}] {t.subject[:50]} "
                    f"({t.priority}, {t.requester_email})"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing tickets: {str(e)}"


class ZendeskCreateTicketTool(BaseTool):
    name: str = "zendesk_create_ticket"
    description: str = "Create a new Zendesk support ticket"
    args_schema: Type[BaseModel] = ZendeskCreateTicketInput

    def _run(
        self,
        subject: str,
        description: str,
        priority: str = "normal",
        tags: str = None,
    ) -> str:
        try:
            client = get_zendesk_client()
            tag_list = [t.strip() for t in tags.split(",")] if tags else None

            ticket = client.create_ticket(
                subject=subject,
                description=description,
                priority=priority,
                tags=tag_list,
            )

            if ticket:
                return f"✓ Created Zendesk ticket #{ticket.id}: {ticket.subject}"
            return "Failed to create ticket"
        except Exception as e:
            return f"Error creating ticket: {str(e)}"


class ZendeskAddCommentTool(BaseTool):
    name: str = "zendesk_add_comment"
    description: str = "Add a comment to an existing Zendesk ticket"
    args_schema: Type[BaseModel] = ZendeskAddCommentInput

    def _run(self, ticket_id: int, comment: str, public: bool = True) -> str:
        try:
            client = get_zendesk_client()
            success = client.add_comment(ticket_id, comment, public=public)

            if success:
                visibility = "public" if public else "internal"
                return f"✓ Added {visibility} comment to ticket #{ticket_id}"
            return f"Failed to add comment to ticket #{ticket_id}"
        except Exception as e:
            return f"Error adding comment: {str(e)}"


class ZendeskSearchTool(BaseTool):
    name: str = "zendesk_search"
    description: str = "Search Zendesk tickets with a query string"

    def _run(self, query: str) -> str:
        try:
            client = get_zendesk_client()
            tickets = client.search(query)

            if not tickets:
                return f"No tickets found for query: {query}"

            lines = [f"**Search Results for:** {query}\n"]
            for t in tickets[:20]:
                lines.append(
                    f"- **#{t.id}** [{t.status}] {t.subject[:50]}"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"Error searching: {str(e)}"


# =============================================================================
# ClickUp Tools
# =============================================================================

class ClickUpGetTaskTool(BaseTool):
    name: str = "clickup_get_task"
    description: str = "Get details of a specific ClickUp task by ID"
    args_schema: Type[BaseModel] = ClickUpGetTaskInput

    def _run(self, task_id: str) -> str:
        try:
            client = get_clickup_client()
            task = client.get_task(task_id)

            if not task:
                return f"Task {task_id} not found"

            return f"""
**ClickUp Task: {task.name}**
- **ID:** {task.id}
- **Status:** {task.status}
- **Priority:** {task.priority_name}
- **Assignees:** {', '.join(task.assignees) if task.assignees else 'Unassigned'}
- **Tags:** {', '.join(task.tags) if task.tags else 'None'}
- **Due:** {task.date_due.strftime('%Y-%m-%d') if task.date_due else 'None'}
- **Updated:** {task.date_updated.strftime('%Y-%m-%d %H:%M')}
- **URL:** {task.url}

**Description:**
{task.description[:500]}{'...' if len(task.description) > 500 else ''}
"""
        except Exception as e:
            return f"Error getting task: {str(e)}"


class ClickUpListTasksTool(BaseTool):
    name: str = "clickup_list_tasks"
    description: str = "List ClickUp tasks in a specific list"
    args_schema: Type[BaseModel] = ClickUpListTasksInput

    def _run(self, list_id: str, include_closed: bool = False) -> str:
        try:
            client = get_clickup_client()
            tasks = client.list_tasks(list_id, include_closed=include_closed)

            if not tasks:
                return f"No tasks found in list {list_id}"

            lines = ["**ClickUp Tasks**\n"]
            for t in tasks[:30]:
                due = f" (due {t.date_due.strftime('%m/%d')})" if t.date_due else ""
                lines.append(
                    f"- **{t.id}** [{t.status}] {t.name[:40]} "
                    f"({t.priority_name}){due}"
                )

            return "\n".join(lines)
        except Exception as e:
            return f"Error listing tasks: {str(e)}"


class ClickUpCreateTaskTool(BaseTool):
    name: str = "clickup_create_task"
    description: str = "Create a new ClickUp task in a list"
    args_schema: Type[BaseModel] = ClickUpCreateTaskInput

    def _run(
        self,
        list_id: str,
        name: str,
        description: str = "",
        priority: int = 3,
    ) -> str:
        try:
            client = get_clickup_client()

            task = client.create_task(
                list_id=list_id,
                name=name,
                description=description,
                priority=priority,
            )

            if task:
                return f"✓ Created ClickUp task: {task.name} (ID: {task.id})"
            return "Failed to create task"
        except Exception as e:
            return f"Error creating task: {str(e)}"


class ClickUpAddCommentTool(BaseTool):
    name: str = "clickup_add_comment"
    description: str = "Add a comment to an existing ClickUp task"
    args_schema: Type[BaseModel] = ClickUpAddCommentInput

    def _run(self, task_id: str, comment: str) -> str:
        try:
            client = get_clickup_client()
            success = client.add_comment(task_id, comment)

            if success:
                return f"✓ Added comment to task {task_id}"
            return f"Failed to add comment to task {task_id}"
        except Exception as e:
            return f"Error adding comment: {str(e)}"


class ClickUpUpdateTaskTool(BaseTool):
    name: str = "clickup_update_task"
    description: str = "Update a ClickUp task (status, name, priority)"

    def _run(
        self,
        task_id: str,
        name: str = None,
        status: str = None,
        priority: int = None,
    ) -> str:
        try:
            client = get_clickup_client()

            task = client.update_task(
                task_id=task_id,
                name=name,
                status=status,
                priority=priority,
            )

            if task:
                return f"✓ Updated task: {task.name}"
            return f"Failed to update task {task_id}"
        except Exception as e:
            return f"Error updating task: {str(e)}"


# =============================================================================
# Combined Tools
# =============================================================================

class TicketSyncStatusTool(BaseTool):
    name: str = "ticket_sync_status"
    description: str = "Check the sync status between Zendesk tickets and ClickUp tasks"

    def _run(self, ticket_or_task_id: str = None) -> str:
        try:
            zendesk_ok = False
            clickup_ok = False

            try:
                zd = get_zendesk_client()
                zendesk_ok = zd.test_connection()
            except Exception:
                pass

            try:
                cu = get_clickup_client()
                clickup_ok = cu.test_connection()
            except Exception:
                pass

            status = []
            status.append(f"**Zendesk:** {'✓ Connected' if zendesk_ok else '✗ Not connected'}")
            status.append(f"**ClickUp:** {'✓ Connected' if clickup_ok else '✗ Not connected'}")

            if zendesk_ok and clickup_ok:
                status.append("\n_Both systems connected. Sync available._")
            else:
                status.append("\n_Configure credentials in .env to enable sync._")

            return "\n".join(status)
        except Exception as e:
            return f"Error checking sync status: {str(e)}"


# =============================================================================
# Tool Registration
# =============================================================================

def get_zendesk_tools() -> List[BaseTool]:
    """Get all Zendesk tools."""
    return [
        ZendeskGetTicketTool(),
        ZendeskListTicketsTool(),
        ZendeskCreateTicketTool(),
        ZendeskAddCommentTool(),
        ZendeskSearchTool(),
    ]


def get_clickup_tools() -> List[BaseTool]:
    """Get all ClickUp tools."""
    return [
        ClickUpGetTaskTool(),
        ClickUpListTasksTool(),
        ClickUpCreateTaskTool(),
        ClickUpAddCommentTool(),
        ClickUpUpdateTaskTool(),
    ]


def get_ticket_tools() -> List[BaseTool]:
    """Get all ticket management tools."""
    tools = [TicketSyncStatusTool()]

    # Only add tools if credentials are configured
    if os.getenv("ZENDESK_API_TOKEN"):
        tools.extend(get_zendesk_tools())

    if os.getenv("CLICKUP_API_TOKEN"):
        tools.extend(get_clickup_tools())

    return tools
