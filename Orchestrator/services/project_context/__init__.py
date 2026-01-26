"""
Project Context Aggregation Module

Provides a unified view of all project-related data:
- ClickUp tasks/tickets
- Zendesk tickets
- Time logged (Harvest)
- Slack messages
- Gmail emails
- Google Drive documents

Each project has a dedicated POC (Point of Contact) agent
that acts as the SME/Product Owner.
"""

from .aggregator import ProjectContextAggregator, ProjectContext
from .poc_agent import POCAgent, create_poc_agent

__all__ = [
    'ProjectContextAggregator',
    'ProjectContext',
    'POCAgent',
    'create_poc_agent',
]
