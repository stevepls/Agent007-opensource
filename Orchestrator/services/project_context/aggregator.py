"""
Project Context Aggregator

Aggregates data from multiple sources into a unified project context.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# Import all data sources
from ..tickets import get_clickup_client, get_zendesk_client
from ..gmail.client import GmailClient
from ..slack.client import SlackClient

# Harvest time tracking
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
try:
    from utils.time_logger import HarvestTimeTracker
    HARVEST_AVAILABLE = True
except ImportError:
    HARVEST_AVAILABLE = False
    HarvestTimeTracker = None


class DataSource(Enum):
    """Available data sources."""
    CLICKUP = "clickup"
    ZENDESK = "zendesk"
    HARVEST = "harvest"
    SLACK = "slack"
    GMAIL = "gmail"
    DRIVE = "drive"


@dataclass
class ProjectTask:
    """Unified task representation."""
    id: str
    source: DataSource
    title: str
    description: str
    status: str
    priority: Optional[str]
    assignee: Optional[str]
    created_at: datetime
    updated_at: datetime
    url: str
    tags: List[str] = field(default_factory=list)
    comments_count: int = 0


@dataclass
class ProjectMessage:
    """Unified message representation (email/slack)."""
    id: str
    source: DataSource
    subject: str
    body: str
    sender: str
    recipients: List[str]
    timestamp: datetime
    thread_id: Optional[str]
    is_read: bool = True


@dataclass
class TimeEntry:
    """Time logged for the project."""
    id: str
    date: datetime
    hours: float
    notes: str
    task: Optional[str]
    user: str
    billable: bool = True


@dataclass
class ProjectContext:
    """Complete context for a project."""
    project_id: str
    project_name: str
    
    # Identifiers for data sources
    clickup_space_id: Optional[str] = None
    clickup_list_id: Optional[str] = None
    zendesk_org_id: Optional[str] = None
    zendesk_tags: List[str] = field(default_factory=list)
    harvest_project_id: Optional[str] = None
    slack_channel_id: Optional[str] = None
    gmail_label: Optional[str] = None
    
    # Aggregated data
    open_tasks: List[ProjectTask] = field(default_factory=list)
    recent_tasks: List[ProjectTask] = field(default_factory=list)
    recent_messages: List[ProjectMessage] = field(default_factory=list)
    time_entries: List[TimeEntry] = field(default_factory=list)
    
    # Summary stats
    total_open_tasks: int = 0
    total_hours_logged: float = 0.0
    unread_messages: int = 0
    last_activity: Optional[datetime] = None
    
    # Health indicators
    overdue_tasks: int = 0
    blocked_tasks: int = 0
    stale_days: int = 0  # Days since last activity


class ProjectContextAggregator:
    """
    Aggregates data from multiple sources for a project.
    
    Usage:
        aggregator = ProjectContextAggregator()
        context = aggregator.get_project_context("ap-driving")
    """
    
    def __init__(self):
        self._clickup = None
        self._zendesk = None
        self._gmail = None
        self._slack = None
        self._harvest = None
        
        # Load project mappings
        self._project_config = self._load_project_config()
    
    def _load_project_config(self) -> Dict[str, Dict]:
        """Load project configurations from DevOps config."""
        # Default to DevOps sibling directory relative to Agent007 root
        agent007_root = Path(__file__).parent.parent.parent.parent
        config_path = Path(os.getenv(
            'DEVOPS_ROOT',
            str(agent007_root / 'DevOps')
        )) / 'config' / 'tickets' / 'org-mapping.yml'
        
        projects = {}
        
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                data = yaml.safe_load(f)
            
            # Build project configs from mappings
            mappings = data.get('mappings', {})
            space_lists = data.get('space_lists', {})
            reverse = data.get('reverse_mappings', {})
            
            for space_id, org_name in reverse.items():
                projects[org_name] = {
                    'name': org_name.replace('-', ' ').title(),
                    'clickup_space_id': space_id,
                    'clickup_list_id': space_lists.get(space_id),
                    'zendesk_tags': [org_name],
                }
        
        return projects
    
    @property
    def clickup(self):
        if self._clickup is None:
            self._clickup = get_clickup_client()
        return self._clickup
    
    @property
    def zendesk(self):
        if self._zendesk is None:
            self._zendesk = get_zendesk_client()
        return self._zendesk
    
    @property
    def gmail(self):
        if self._gmail is None:
            self._gmail = GmailClient()
        return self._gmail
    
    @property
    def slack(self):
        if self._slack is None:
            self._slack = SlackClient()
        return self._slack
    
    @property
    def harvest(self):
        if self._harvest is None and HARVEST_AVAILABLE:
            self._harvest = HarvestTimeTracker()
        return self._harvest
    
    def list_projects(self) -> List[str]:
        """List all configured projects."""
        return list(self._project_config.keys())
    
    def get_project_context(
        self,
        project_id: str,
        include_tasks: bool = True,
        include_messages: bool = True,
        include_time: bool = True,
        days_back: int = 7,
    ) -> ProjectContext:
        """
        Get complete context for a project.
        
        Args:
            project_id: Project identifier (e.g., 'ap-driving')
            include_tasks: Include ClickUp/Zendesk tasks
            include_messages: Include Slack/Gmail messages
            include_time: Include Harvest time entries
            days_back: How many days of history to fetch
        """
        config = self._project_config.get(project_id, {})
        
        context = ProjectContext(
            project_id=project_id,
            project_name=config.get('name', project_id.replace('-', ' ').title()),
            clickup_space_id=config.get('clickup_space_id'),
            clickup_list_id=config.get('clickup_list_id'),
            zendesk_tags=config.get('zendesk_tags', []),
            harvest_project_id=config.get('harvest_project_id'),
            slack_channel_id=config.get('slack_channel_id'),
            gmail_label=config.get('gmail_label'),
        )
        
        since = datetime.utcnow() - timedelta(days=days_back)
        
        # Aggregate from each source
        if include_tasks:
            self._fetch_clickup_tasks(context, since)
            self._fetch_zendesk_tickets(context, since)
        
        if include_messages:
            self._fetch_slack_messages(context, since)
            self._fetch_gmail_messages(context, since)
        
        if include_time:
            self._fetch_harvest_time(context, since)
        
        # Calculate summary stats
        self._calculate_stats(context)
        
        return context
    
    def _fetch_clickup_tasks(self, context: ProjectContext, since: datetime):
        """Fetch tasks from ClickUp."""
        if not context.clickup_list_id:
            return
        
        try:
            tasks = self.clickup.get_tasks(
                context.clickup_list_id,
                include_closed=False,
            )
            
            for t in tasks:
                task = ProjectTask(
                    id=t.id,
                    source=DataSource.CLICKUP,
                    title=t.name,
                    description=t.description[:500] if t.description else '',
                    status=t.status,
                    priority=str(t.priority) if t.priority else None,
                    assignee=t.assignees[0].get('username') if t.assignees else None,
                    created_at=t.date_created,
                    updated_at=t.date_updated,
                    url=t.url,
                    tags=t.tags,
                )
                context.open_tasks.append(task)
                
                if t.date_updated >= since:
                    context.recent_tasks.append(task)
        except Exception as e:
            print(f"Error fetching ClickUp tasks: {e}")
    
    def _fetch_zendesk_tickets(self, context: ProjectContext, since: datetime):
        """Fetch tickets from Zendesk."""
        if not context.zendesk_tags:
            return
        
        try:
            for tag in context.zendesk_tags:
                tickets = self.zendesk.search_tickets(
                    tags=[tag],
                    status='open,pending,new',
                    limit=50,
                )
                
                for t in tickets:
                    task = ProjectTask(
                        id=str(t.id),
                        source=DataSource.ZENDESK,
                        title=t.subject,
                        description=t.description[:500] if t.description else '',
                        status=t.status,
                        priority=t.priority,
                        assignee=t.assignee_email,
                        created_at=t.created_at,
                        updated_at=t.updated_at,
                        url=f"https://{self.zendesk.subdomain}.zendesk.com/agent/tickets/{t.id}",
                        tags=t.tags,
                    )
                    context.open_tasks.append(task)
                    
                    if t.updated_at >= since:
                        context.recent_tasks.append(task)
        except Exception as e:
            print(f"Error fetching Zendesk tickets: {e}")
    
    def _fetch_slack_messages(self, context: ProjectContext, since: datetime):
        """Fetch messages from Slack channel."""
        if not context.slack_channel_id:
            return
        
        try:
            if not self.slack.is_connected:
                self.slack.connect()
            
            messages = self.slack.get_messages(
                context.slack_channel_id,
                limit=50,
            )
            
            for m in messages:
                if m.timestamp >= since:
                    msg = ProjectMessage(
                        id=m.ts,
                        source=DataSource.SLACK,
                        subject=f"Slack: {m.text[:50]}...",
                        body=m.text,
                        sender=m.user,
                        recipients=[],
                        timestamp=m.timestamp,
                        thread_id=m.thread_ts,
                    )
                    context.recent_messages.append(msg)
        except Exception as e:
            print(f"Error fetching Slack messages: {e}")
    
    def _fetch_gmail_messages(self, context: ProjectContext, since: datetime):
        """Fetch emails from Gmail with project label."""
        if not context.gmail_label:
            return
        
        try:
            if not self.gmail.is_authenticated:
                return  # Skip if not authenticated
            
            emails = self.gmail.search_emails(
                query=f"label:{context.gmail_label} after:{since.strftime('%Y/%m/%d')}",
                max_results=50,
            )
            
            for e in emails:
                msg = ProjectMessage(
                    id=e.id,
                    source=DataSource.GMAIL,
                    subject=e.subject,
                    body=e.body[:500] if e.body else '',
                    sender=e.sender,
                    recipients=e.to,
                    timestamp=e.date,
                    thread_id=e.thread_id,
                    is_read=e.is_read,
                )
                context.recent_messages.append(msg)
                if not e.is_read:
                    context.unread_messages += 1
        except Exception as e:
            print(f"Error fetching Gmail messages: {e}")
    
    def _fetch_harvest_time(self, context: ProjectContext, since: datetime):
        """Fetch time entries from Harvest."""
        if not context.harvest_project_id or not self.harvest:
            return
        
        try:
            entries = self.harvest.get_time_entries(
                project_id=context.harvest_project_id,
                from_date=since.strftime('%Y-%m-%d'),
            )
            
            for e in entries:
                entry = TimeEntry(
                    id=str(e.get('id')),
                    date=datetime.fromisoformat(e.get('spent_date')),
                    hours=e.get('hours', 0),
                    notes=e.get('notes', ''),
                    task=e.get('task', {}).get('name'),
                    user=e.get('user', {}).get('name', 'Unknown'),
                    billable=e.get('billable', True),
                )
                context.time_entries.append(entry)
                context.total_hours_logged += entry.hours
        except Exception as e:
            print(f"Error fetching Harvest time: {e}")
    
    def _calculate_stats(self, context: ProjectContext):
        """Calculate summary statistics."""
        context.total_open_tasks = len(context.open_tasks)
        
        # Find last activity
        all_dates = []
        for t in context.recent_tasks:
            all_dates.append(t.updated_at)
        for m in context.recent_messages:
            all_dates.append(m.timestamp)
        
        if all_dates:
            context.last_activity = max(all_dates)
            context.stale_days = (datetime.utcnow() - context.last_activity).days
        
        # Count overdue/blocked
        for t in context.open_tasks:
            status_lower = t.status.lower()
            if 'block' in status_lower or 'stuck' in status_lower:
                context.blocked_tasks += 1
            # Could add due date checking here
    
    def get_project_summary(self, project_id: str) -> str:
        """Get a text summary of project status."""
        context = self.get_project_context(project_id)
        
        lines = [
            f"# {context.project_name} Status",
            f"",
            f"## Overview",
            f"- Open tasks: {context.total_open_tasks}",
            f"- Hours logged (7d): {context.total_hours_logged:.1f}",
            f"- Unread messages: {context.unread_messages}",
            f"- Last activity: {context.last_activity or 'Unknown'}",
            f"- Stale days: {context.stale_days}",
            f"",
        ]
        
        if context.blocked_tasks > 0:
            lines.append(f"⚠️ BLOCKED TASKS: {context.blocked_tasks}")
            lines.append("")
        
        lines.append("## Recent Tasks")
        for t in context.recent_tasks[:5]:
            lines.append(f"- [{t.source.value}] {t.title} ({t.status})")
        
        lines.append("")
        lines.append("## Recent Messages")
        for m in context.recent_messages[:5]:
            lines.append(f"- [{m.source.value}] {m.subject}")
        
        return "\n".join(lines)
