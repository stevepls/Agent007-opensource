"""
Ticket Management Services

Integrates Zendesk and ClickUp for unified ticket/task management.
Wraps the existing DevOps shell scripts in Python for Orchestrator use.
"""

from .zendesk_client import ZendeskClient, get_zendesk_client
from .clickup_client import ClickUpClient, get_clickup_client
from .sync import TicketSync

__all__ = [
    "ZendeskClient",
    "ClickUpClient",
    "TicketSync",
    "get_zendesk_client",
    "get_clickup_client",
]
