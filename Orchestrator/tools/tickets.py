"""
Ticket Management Tools

CrewAI tools for interacting with Zendesk and ClickUp.
Provides unified interface for ticket/task operations.

SECURITY:
- Read operations are always allowed
- Write operations require confirmation through governance
"""

from typing import Any, Type, Optional, List
from pydantic import BaseModel, Field

try:
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    BaseTool = object

from ..services.tickets import (
    ZendeskClient,
    ClickUpClient,
    TicketSync,
    get_zendesk_client,
    get_clickup_client,
)
from ..governance.confirmations import require_confirmation, ConfirmationLevel


# =============================================================================
# Zendesk Tools
# =============================================================================

class ZendeskSearchInput(BaseModel):
    """Input for Zendesk search."""
    query: str = Field(default="", description="Search query text")
    status: str = Field(default="", description="Filter by status: new, open, pending, solved, closed")
    priority: str = Field(default="", description="Filter by priority: low, normal, high, urgent")
    limit: int = Field(default=10, description="Maximum results to return")


class ZendeskSearchTool(BaseTool if CREWAI_AVAILABLE else object):
    """Search Zendesk tickets."""
    
    name: str = "zendesk_search"
    description: str = "Search for Zendesk support tickets by query, status, or priority"
    args_schema: Type[BaseModel] = ZendeskSearchInput
    
    def _run(
        self,
        query: str = "",
        status: str = "",
        priority: str = "",
        limit: int = 10,
    ) -> str:
        client = get_zendesk_client()
        
        if not client.is_available:
            return "❌ Zendesk not configured. Set ZENDESK_EMAIL, ZENDESK_API_TOKEN, ZENDESK_SUBDOMAIN in .env"
        
        try:
            tickets = client.search_tickets(
                query=query if query else None,
                status=status if status else None,
                priority=priority if priority else None,
                limit=limit,
            )
            
            if not tickets:
                return "No tickets found matching criteria."
            
            results = [f"Found {len(tickets)} ticket(s):\n"]
            for t in tickets:
                results.append(
                    f"• #{t.id} [{t.status}] [{t.priority}] {t.subject}\n"
                    f"  Updated: {t.updated_at.strftime('%Y-%m-%d %H:%M')}"
                )
            
            return "\n".join(results)
            
        except Exception as e:
            return f"❌ Error searching Zendesk: {e}"


class ZendeskTicketInput(BaseModel):
    """Input for getting a single ticket."""
    ticket_id: int = Field(..., description="The Zendesk ticket ID")


class ZendeskGetTicketTool(BaseTool if CREWAI_AVAILABLE else object):
    """Get a specific Zendesk ticket."""
    
    name: str = "zendesk_get_ticket"
    description: str = "Get details of a specific Zendesk ticket by ID"
    args_schema: Type[BaseModel] = ZendeskTicketInput
    
    def _run(self, ticket_id: int) -> str:
        client = get_zendesk_client()
        
        if not client.is_available:
            return "❌ Zendesk not configured"
        
        try:
            ticket = client.get_ticket(ticket_id)
            
            if not ticket:
                return f"Ticket #{ticket_id} not found"
            
            # Get comments
            comments = client.get_ticket_comments(ticket_id)
            
            result = f"""
## Zendesk Ticket #{ticket.id}

**Subject:** {ticket.subject}
**Status:** {ticket.status}
**Priority:** {ticket.priority}
**Tags:** {', '.join(ticket.tags) if ticket.tags else 'None'}
**Created:** {ticket.created_at.strftime('%Y-%m-%d %H:%M')}
**Updated:** {ticket.updated_at.strftime('%Y-%m-%d %H:%M')}

### Description
{ticket.description}

### Comments ({len(comments)})
"""
            for c in comments[-5:]:  # Last 5 comments
                visibility = "Public" if c.public else "Internal"
                result += f"\n**[{visibility}]** {c.created_at.strftime('%Y-%m-%d %H:%M')}\n{c.body[:200]}...\n"
            
            return result
            
        except Exception as e:
            return f"❌ Error: {e}"


class ZendeskAddCommentInput(BaseModel):
    """Input for adding a comment."""
    ticket_id: int = Field(..., description="The Zendesk ticket ID")
    comment: str = Field(..., description="The comment text to add")
    public: bool = Field(default=True, description="Whether the comment is public (visible to customer)")


class ZendeskAddCommentTool(BaseTool if CREWAI_AVAILABLE else object):
    """Add a comment to a Zendesk ticket. Requires confirmation."""
    
    name: str = "zendesk_add_comment"
    description: str = "Add a comment or internal note to a Zendesk ticket. REQUIRES HUMAN CONFIRMATION."
    args_schema: Type[BaseModel] = ZendeskAddCommentInput
    
    def _run(
        self,
        ticket_id: int,
        comment: str,
        public: bool = True,
    ) -> str:
        client = get_zendesk_client()
        
        if not client.is_available:
            return "❌ Zendesk not configured"
        
        # Require confirmation for writes
        visibility = "PUBLIC" if public else "INTERNAL"
        confirmation = require_confirmation(
            action=f"Add {visibility} comment to Zendesk ticket #{ticket_id}",
            details=f"Comment preview:\n{comment[:200]}...",
            level=ConfirmationLevel.STANDARD,
        )
        
        if not confirmation.approved:
            return f"❌ Action requires approval. Confirmation ID: {confirmation.id}"
        
        try:
            if public:
                success = client.add_comment(ticket_id, comment)
            else:
                success = client.add_internal_note(ticket_id, comment)
            
            if success:
                return f"✅ Added {visibility.lower()} comment to ticket #{ticket_id}"
            else:
                return f"❌ Failed to add comment"
                
        except Exception as e:
            return f"❌ Error: {e}"


# =============================================================================
# ClickUp Tools
# =============================================================================

class ClickUpSearchInput(BaseModel):
    """Input for ClickUp search."""
    query: str = Field(..., description="Search query text")
    limit: int = Field(default=10, description="Maximum results")


class ClickUpSearchTool(BaseTool if CREWAI_AVAILABLE else object):
    """Search ClickUp tasks."""
    
    name: str = "clickup_search"
    description: str = "Search for ClickUp tasks by name or description"
    args_schema: Type[BaseModel] = ClickUpSearchInput
    
    def _run(self, query: str, limit: int = 10) -> str:
        client = get_clickup_client()
        
        if not client.is_available:
            return "❌ ClickUp not configured. Set CLICKUP_API_TOKEN in .env"
        
        try:
            tasks = client.search_tasks(query, limit=limit)
            
            if not tasks:
                return f"No tasks found matching '{query}'"
            
            results = [f"Found {len(tasks)} task(s):\n"]
            for t in tasks:
                priority_emoji = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢"}.get(t.priority, "⚪")
                results.append(
                    f"• {priority_emoji} [{t.status}] {t.name}\n"
                    f"  ID: {t.id} | Updated: {t.updated_at.strftime('%Y-%m-%d')}"
                )
            
            return "\n".join(results)
            
        except Exception as e:
            return f"❌ Error: {e}"


class ClickUpTaskInput(BaseModel):
    """Input for getting a single task."""
    task_id: str = Field(..., description="The ClickUp task ID")


class ClickUpGetTaskTool(BaseTool if CREWAI_AVAILABLE else object):
    """Get a specific ClickUp task."""
    
    name: str = "clickup_get_task"
    description: str = "Get details of a specific ClickUp task by ID"
    args_schema: Type[BaseModel] = ClickUpTaskInput
    
    def _run(self, task_id: str) -> str:
        client = get_clickup_client()
        
        if not client.is_available:
            return "❌ ClickUp not configured"
        
        try:
            task = client.get_task(task_id, include_subtasks=True)
            
            if not task:
                return f"Task {task_id} not found"
            
            priority_text = {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}.get(task.priority, "None")
            
            result = f"""
## ClickUp Task: {task.name}

**ID:** {task.id}
**Status:** {task.status}
**Priority:** {priority_text}
**Tags:** {', '.join(task.tags) if task.tags else 'None'}
**Assignees:** {', '.join(task.assignees) if task.assignees else 'Unassigned'}
**Created:** {task.created_at.strftime('%Y-%m-%d %H:%M')}
**Updated:** {task.updated_at.strftime('%Y-%m-%d %H:%M')}

### Description
{task.description or 'No description'}

**URL:** {task.url}
"""
            return result
            
        except Exception as e:
            return f"❌ Error: {e}"


class ClickUpAddCommentInput(BaseModel):
    """Input for adding a comment."""
    task_id: str = Field(..., description="The ClickUp task ID")
    comment: str = Field(..., description="The comment text")


class ClickUpAddCommentTool(BaseTool if CREWAI_AVAILABLE else object):
    """Add a comment to a ClickUp task. Requires confirmation."""
    
    name: str = "clickup_add_comment"
    description: str = "Add a comment to a ClickUp task. REQUIRES HUMAN CONFIRMATION."
    args_schema: Type[BaseModel] = ClickUpAddCommentInput
    
    def _run(self, task_id: str, comment: str) -> str:
        client = get_clickup_client()
        
        if not client.is_available:
            return "❌ ClickUp not configured"
        
        confirmation = require_confirmation(
            action=f"Add comment to ClickUp task {task_id}",
            details=f"Comment preview:\n{comment[:200]}...",
            level=ConfirmationLevel.STANDARD,
        )
        
        if not confirmation.approved:
            return f"❌ Action requires approval. Confirmation ID: {confirmation.id}"
        
        try:
            success = client.add_comment(task_id, comment)
            
            if success:
                return f"✅ Added comment to task {task_id}"
            else:
                return f"❌ Failed to add comment"
                
        except Exception as e:
            return f"❌ Error: {e}"


# =============================================================================
# Sync Tools
# =============================================================================

class SyncPreviewInput(BaseModel):
    """Input for sync preview."""
    source: str = Field(..., description="Source system: 'zendesk' or 'clickup'")
    source_id: str = Field(..., description="ID of the ticket/task to sync")


class TicketSyncPreviewTool(BaseTool if CREWAI_AVAILABLE else object):
    """Preview what syncing a ticket/task would create."""
    
    name: str = "ticket_sync_preview"
    description: str = "Preview what syncing a Zendesk ticket to ClickUp (or vice versa) would create, without making changes"
    args_schema: Type[BaseModel] = SyncPreviewInput
    
    def _run(self, source: str, source_id: str) -> str:
        sync = TicketSync()
        
        if not sync.is_available:
            return "❌ Sync not available - configure both Zendesk and ClickUp"
        
        try:
            if source.lower() == "zendesk":
                ticket = get_zendesk_client().get_ticket(int(source_id))
                if not ticket:
                    return f"Zendesk ticket #{source_id} not found"
                
                preview = sync.preview_zendesk_to_clickup(ticket)
                
                return f"""
## Sync Preview: Zendesk → ClickUp

**Source:** Zendesk Ticket #{preview['source']['id']}
**Subject:** {preview['source']['subject']}

**Would Create:**
- ClickUp Task in List: {preview['target']['list_id'] or 'N/A'}
- Name: {preview['target']['name']}
- Priority: {preview['target']['priority']}

**Can Sync:** {'✅ Yes' if preview['can_sync'] else '❌ No - no target list configured'}
"""
            
            elif source.lower() == "clickup":
                task = get_clickup_client().get_task(source_id)
                if not task:
                    return f"ClickUp task {source_id} not found"
                
                preview = sync.preview_clickup_to_zendesk(task)
                
                return f"""
## Sync Preview: ClickUp → Zendesk

**Source:** ClickUp Task {preview['source']['id']}
**Name:** {preview['source']['name']}

**Would Create:**
- Zendesk Ticket
- Subject: {preview['target']['subject']}
- Priority: {preview['target']['priority']}
- Tags: {', '.join(preview['target']['tags']) if preview['target']['tags'] else 'None'}

**Can Sync:** ✅ Yes
"""
            
            else:
                return f"❌ Unknown source: {source}. Use 'zendesk' or 'clickup'"
                
        except Exception as e:
            return f"❌ Error: {e}"


class RecentActivityInput(BaseModel):
    """Input for recent activity."""
    limit: int = Field(default=10, description="Maximum items to return")


class TicketRecentActivityTool(BaseTool if CREWAI_AVAILABLE else object):
    """Get recent ticket/task activity across systems."""
    
    name: str = "ticket_recent_activity"
    description: str = "Get recent activity from Zendesk and ClickUp in one unified view"
    args_schema: Type[BaseModel] = RecentActivityInput
    
    def _run(self, limit: int = 10) -> str:
        sync = TicketSync()
        
        try:
            activity = sync.get_recent_activity(limit=limit)
            
            if not activity:
                return "No recent activity found"
            
            results = ["## Recent Ticket Activity\n"]
            
            for item in activity:
                emoji = "🎫" if item["source"] == "zendesk" else "📋"
                priority_color = {"urgent": "🔴", "high": "🟠", "normal": "🟡", "low": "🟢"}.get(
                    item.get("priority", ""), "⚪"
                )
                
                results.append(
                    f"{emoji} {priority_color} [{item['status']}] {item['title']}\n"
                    f"   {item['source'].title()} #{item['id']} • "
                    f"Updated: {item['updated_at'].strftime('%Y-%m-%d %H:%M')}"
                )
            
            return "\n".join(results)
            
        except Exception as e:
            return f"❌ Error: {e}"


# =============================================================================
# Tool Collection
# =============================================================================

def get_ticket_tools() -> List:
    """Get all ticket management tools."""
    if not CREWAI_AVAILABLE:
        return []
    
    return [
        ZendeskSearchTool(),
        ZendeskGetTicketTool(),
        ZendeskAddCommentTool(),
        ClickUpSearchTool(),
        ClickUpGetTaskTool(),
        ClickUpAddCommentTool(),
        TicketSyncPreviewTool(),
        TicketRecentActivityTool(),
    ]
