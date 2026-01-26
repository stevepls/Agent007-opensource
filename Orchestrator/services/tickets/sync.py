"""
Ticket Sync Service

Provides bi-directional sync between Zendesk and ClickUp.
Leverages DevOps/config/tickets/org-mapping.yml for routing.

SECURITY:
- Read operations are safe
- All writes require explicit confirmation
- Sync operations are atomic where possible
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from .zendesk_client import ZendeskClient, ZendeskTicket, get_zendesk_client
from .clickup_client import ClickUpClient, ClickUpTask, get_clickup_client


# Find org mapping file
DEVOPS_ROOT = Path(os.getenv("DEVOPS_ROOT", Path.home() / "DevOps"))
ORG_MAPPING_PATH = DEVOPS_ROOT / "config" / "tickets" / "org-mapping.yml"


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool
    source_id: str
    target_id: Optional[str]
    action: str  # "created", "updated", "skipped", "error"
    message: str


class TicketSync:
    """Bi-directional sync between Zendesk and ClickUp."""
    
    def __init__(
        self,
        zendesk: ZendeskClient = None,
        clickup: ClickUpClient = None,
    ):
        self._zendesk = zendesk or get_zendesk_client()
        self._clickup = clickup or get_clickup_client()
        self._org_mapping = self._load_org_mapping()
    
    def _load_org_mapping(self) -> Dict[str, Any]:
        """Load organization to space mapping."""
        if ORG_MAPPING_PATH.exists():
            with open(ORG_MAPPING_PATH) as f:
                return yaml.safe_load(f) or {}
        return {}
    
    @property
    def is_available(self) -> bool:
        """Check if both services are available."""
        return self._zendesk.is_available and self._clickup.is_available
    
    def get_space_for_org(self, org_name: str) -> Optional[str]:
        """Map Zendesk org/tag to ClickUp space ID."""
        mappings = self._org_mapping.get("mappings", {})
        
        # Try exact match first
        org_lower = org_name.lower()
        for key, space_id in mappings.items():
            if key.lower() == org_lower:
                return str(space_id)
        
        # Try partial match
        for key, space_id in mappings.items():
            if org_lower in key.lower() or key.lower() in org_lower:
                return str(space_id)
        
        # Fallback
        return self._org_mapping.get("settings", {}).get("fallback_space_id")
    
    def get_list_for_space(self, space_id: str) -> Optional[str]:
        """Get the target list ID for a space."""
        space_lists = self._org_mapping.get("space_lists", {})
        return str(space_lists.get(space_id, "")) or None
    
    def get_org_for_space(self, space_id: str) -> Optional[str]:
        """Reverse mapping: ClickUp space to Zendesk org/tag."""
        reverse = self._org_mapping.get("reverse_mappings", {})
        return reverse.get(str(space_id))
    
    # =========================================================================
    # SYNC OPERATIONS
    # =========================================================================
    
    def preview_zendesk_to_clickup(
        self,
        ticket: ZendeskTicket,
    ) -> Dict[str, Any]:
        """Preview what a Zendesk→ClickUp sync would create."""
        # Determine target space/list
        org_tag = ticket.tags[0] if ticket.tags else ""
        space_id = self.get_space_for_org(org_tag)
        list_id = self.get_list_for_space(space_id) if space_id else None
        
        # Map priority (Zendesk: low/normal/high/urgent → ClickUp: 4/3/2/1)
        priority_map = {"low": 4, "normal": 3, "high": 2, "urgent": 1}
        priority = priority_map.get(ticket.priority, 3)
        
        return {
            "source": {
                "type": "zendesk",
                "id": ticket.id,
                "subject": ticket.subject,
            },
            "target": {
                "type": "clickup",
                "list_id": list_id,
                "space_id": space_id,
                "name": f"[ZD-{ticket.id}] {ticket.subject}",
                "description": self._build_clickup_description(ticket),
                "priority": priority,
            },
            "can_sync": list_id is not None,
        }
    
    def sync_zendesk_to_clickup(
        self,
        ticket: ZendeskTicket,
        dry_run: bool = True,
    ) -> SyncResult:
        """
        Sync a Zendesk ticket to ClickUp.
        
        REQUIRES CONFIRMATION - set dry_run=False to actually sync.
        """
        preview = self.preview_zendesk_to_clickup(ticket)
        
        if not preview["can_sync"]:
            return SyncResult(
                success=False,
                source_id=str(ticket.id),
                target_id=None,
                action="skipped",
                message="No target list configured for this organization",
            )
        
        if dry_run:
            return SyncResult(
                success=True,
                source_id=str(ticket.id),
                target_id=None,
                action="preview",
                message=f"Would create task in list {preview['target']['list_id']}",
            )
        
        # Actually create the task
        try:
            task = self._clickup.create_task(
                list_id=preview["target"]["list_id"],
                name=preview["target"]["name"],
                description=preview["target"]["description"],
                priority=preview["target"]["priority"],
            )
            
            if task:
                # Add zendesk tag
                self._clickup.add_tag(task.id, "from-zendesk")
                
                return SyncResult(
                    success=True,
                    source_id=str(ticket.id),
                    target_id=task.id,
                    action="created",
                    message=f"Created ClickUp task {task.id}",
                )
            else:
                return SyncResult(
                    success=False,
                    source_id=str(ticket.id),
                    target_id=None,
                    action="error",
                    message="Failed to create ClickUp task",
                )
                
        except Exception as e:
            return SyncResult(
                success=False,
                source_id=str(ticket.id),
                target_id=None,
                action="error",
                message=str(e),
            )
    
    def preview_clickup_to_zendesk(
        self,
        task: ClickUpTask,
    ) -> Dict[str, Any]:
        """Preview what a ClickUp→Zendesk sync would create."""
        # Determine target org/tag
        org = self.get_org_for_space(task.space_id)
        
        # Map priority (ClickUp: 1/2/3/4 → Zendesk: urgent/high/normal/low)
        priority_map = {1: "urgent", 2: "high", 3: "normal", 4: "low"}
        priority = priority_map.get(task.priority, "normal")
        
        return {
            "source": {
                "type": "clickup",
                "id": task.id,
                "name": task.name,
            },
            "target": {
                "type": "zendesk",
                "subject": task.name,
                "description": self._build_zendesk_description(task),
                "priority": priority,
                "tags": [org] if org else [],
            },
            "can_sync": True,  # Zendesk doesn't require org
        }
    
    def sync_clickup_to_zendesk(
        self,
        task: ClickUpTask,
        dry_run: bool = True,
    ) -> SyncResult:
        """
        Sync a ClickUp task to Zendesk.
        
        REQUIRES CONFIRMATION - set dry_run=False to actually sync.
        """
        preview = self.preview_clickup_to_zendesk(task)
        
        if dry_run:
            return SyncResult(
                success=True,
                source_id=task.id,
                target_id=None,
                action="preview",
                message="Would create Zendesk ticket",
            )
        
        try:
            ticket = self._zendesk.create_ticket(
                subject=preview["target"]["subject"],
                description=preview["target"]["description"],
                priority=preview["target"]["priority"],
                tags=preview["target"]["tags"],
            )
            
            if ticket:
                return SyncResult(
                    success=True,
                    source_id=task.id,
                    target_id=str(ticket.id),
                    action="created",
                    message=f"Created Zendesk ticket {ticket.id}",
                )
            else:
                return SyncResult(
                    success=False,
                    source_id=task.id,
                    target_id=None,
                    action="error",
                    message="Failed to create Zendesk ticket",
                )
                
        except Exception as e:
            return SyncResult(
                success=False,
                source_id=task.id,
                target_id=None,
                action="error",
                message=str(e),
            )
    
    # =========================================================================
    # READ OPERATIONS (aggregated view)
    # =========================================================================
    
    def get_recent_activity(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent activity from both systems."""
        activity = []
        
        # Get recent Zendesk tickets
        if self._zendesk.is_available:
            try:
                tickets = self._zendesk.get_recent_tickets(limit=limit // 2)
                for t in tickets:
                    activity.append({
                        "source": "zendesk",
                        "type": "ticket",
                        "id": t.id,
                        "title": t.subject,
                        "status": t.status,
                        "priority": t.priority,
                        "updated_at": t.updated_at,
                        "url": t.url,
                    })
            except Exception:
                pass
        
        # Get recent ClickUp tasks (from all spaces would be expensive)
        # Skip for now - would need to iterate spaces
        
        # Sort by updated_at
        activity.sort(key=lambda x: x.get("updated_at", datetime.min), reverse=True)
        
        return activity[:limit]
    
    def get_ticket_with_linked_task(
        self,
        ticket_id: int,
    ) -> Tuple[Optional[ZendeskTicket], Optional[ClickUpTask]]:
        """Get a Zendesk ticket and its linked ClickUp task if any."""
        ticket = self._zendesk.get_ticket(ticket_id)
        if not ticket:
            return None, None
        
        # Try to find linked ClickUp task
        # Look for pattern: [ZD-123] or ClickUp URL in description
        # This is a simplified version - full implementation would check custom fields
        
        return ticket, None  # Task linking not implemented yet
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _build_clickup_description(self, ticket: ZendeskTicket) -> str:
        """Build ClickUp task description from Zendesk ticket."""
        return f"""**Synced from Zendesk Ticket #{ticket.id}**

**Status:** {ticket.status}
**Priority:** {ticket.priority}
**Tags:** {', '.join(ticket.tags) if ticket.tags else 'None'}

---

{ticket.description}

---
[View in Zendesk]({ticket.url})
"""
    
    def _build_zendesk_description(self, task: ClickUpTask) -> str:
        """Build Zendesk ticket description from ClickUp task."""
        return f"""Synced from ClickUp Task {task.id}

Status: {task.status}
Tags: {', '.join(task.tags) if task.tags else 'None'}

---

{task.description}

---
View in ClickUp: {task.url}
"""
