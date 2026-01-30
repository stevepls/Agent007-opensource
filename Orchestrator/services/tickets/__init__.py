"""
Ticket Management Services

Provides unified access to Zendesk and ClickUp APIs.
Wraps the existing DevOps shell libraries with Python interfaces.
"""

from .zendesk_client import ZendeskClient, get_zendesk_client
from .clickup_client import ClickUpClient, get_clickup_client

__all__ = [
    "ZendeskClient",
    "ClickUpClient",
    "get_zendesk_client",
    "get_clickup_client",
]
