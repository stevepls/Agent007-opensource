"""
Project POC (Point of Contact) Agent

A specialized agent that acts as the SME/Product Owner for a project.
Maintains project context and answers questions about the project.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

from crewai import Agent, Task
from .aggregator import ProjectContextAggregator, ProjectContext


@dataclass
class POCAgentConfig:
    """Configuration for a POC agent."""
    project_id: str
    project_name: str
    
    # Agent personality
    role: str = "Project Product Owner"
    goal: str = "Maintain complete project context and answer questions accurately"
    backstory: str = ""
    
    # Data source toggles
    include_tasks: bool = True
    include_messages: bool = True
    include_time: bool = True
    
    # Update frequency
    refresh_interval_minutes: int = 15


class POCAgent:
    """
    Point of Contact agent for a specific project.
    
    Acts as the SME/Product Owner by:
    - Maintaining up-to-date project context
    - Answering questions about project status
    - Alerting on issues (blocked tasks, stale projects)
    - Interfacing with the Orchestrator
    - Communicating with users through the UI
    """
    
    def __init__(self, config: POCAgentConfig):
        self.config = config
        self.aggregator = ProjectContextAggregator()
        self._context: Optional[ProjectContext] = None
        self._last_refresh: Optional[datetime] = None
        self._agent: Optional[Agent] = None
    
    @property
    def context(self) -> ProjectContext:
        """Get current project context, refreshing if stale."""
        now = datetime.utcnow()
        
        if self._context is None or self._should_refresh(now):
            self.refresh_context()
        
        return self._context
    
    def _should_refresh(self, now: datetime) -> bool:
        """Check if context needs refresh."""
        if self._last_refresh is None:
            return True
        
        elapsed = (now - self._last_refresh).total_seconds() / 60
        return elapsed >= self.config.refresh_interval_minutes
    
    def refresh_context(self):
        """Refresh project context from all sources."""
        self._context = self.aggregator.get_project_context(
            self.config.project_id,
            include_tasks=self.config.include_tasks,
            include_messages=self.config.include_messages,
            include_time=self.config.include_time,
        )
        self._last_refresh = datetime.utcnow()
    
    def get_crewai_agent(self) -> Agent:
        """Get a CrewAI agent for this POC."""
        if self._agent is None:
            backstory = self.config.backstory or self._generate_backstory()
            
            self._agent = Agent(
                role=f"{self.config.project_name} {self.config.role}",
                goal=self.config.goal,
                backstory=backstory,
                verbose=True,
                allow_delegation=False,
            )
        
        return self._agent
    
    def _generate_backstory(self) -> str:
        """Generate agent backstory from project context."""
        ctx = self.context
        
        return f"""You are the Product Owner and Subject Matter Expert for {ctx.project_name}.

Current Project Status:
- {ctx.total_open_tasks} open tasks across ClickUp and Zendesk
- {ctx.total_hours_logged:.1f} hours logged in the past week
- {ctx.unread_messages} unread messages
- Last activity: {ctx.last_activity or 'Unknown'}
- Blocked tasks: {ctx.blocked_tasks}

You have access to:
- All ClickUp tasks and comments
- All Zendesk tickets
- Slack channel messages
- Email threads
- Time tracking data

You answer questions about:
- Project status and progress
- Task priorities and blockers
- Timeline and estimates
- Team communication
- Historical context

You alert the user when:
- Tasks are blocked or stale
- Important messages need attention
- Deadlines are approaching
- Anomalies in time tracking
"""
    
    def get_status_briefing(self) -> str:
        """Get a status briefing for the user."""
        ctx = self.context
        
        # Build briefing
        lines = [
            f"## {ctx.project_name} Briefing",
            f"*Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*",
            "",
        ]
        
        # Alerts first
        alerts = self._get_alerts()
        if alerts:
            lines.append("### ⚠️ Alerts")
            for alert in alerts:
                lines.append(f"- {alert}")
            lines.append("")
        
        # Status overview
        lines.extend([
            "### Status",
            f"- Open tasks: **{ctx.total_open_tasks}**",
            f"- Hours this week: **{ctx.total_hours_logged:.1f}**",
            f"- Unread messages: **{ctx.unread_messages}**",
            "",
        ])
        
        # Recent activity
        if ctx.recent_tasks:
            lines.append("### Recent Task Updates")
            for t in ctx.recent_tasks[:3]:
                lines.append(f"- **{t.title}** - {t.status}")
            lines.append("")
        
        # Action items
        action_items = self._get_action_items()
        if action_items:
            lines.append("### Suggested Actions")
            for item in action_items:
                lines.append(f"- [ ] {item}")
        
        return "\n".join(lines)
    
    def _get_alerts(self) -> List[str]:
        """Get alerts that need attention."""
        alerts = []
        ctx = self.context
        
        if ctx.blocked_tasks > 0:
            alerts.append(f"🚫 {ctx.blocked_tasks} task(s) are blocked")
        
        if ctx.stale_days > 3:
            alerts.append(f"⏰ No activity for {ctx.stale_days} days")
        
        if ctx.unread_messages > 5:
            alerts.append(f"📬 {ctx.unread_messages} unread messages")
        
        return alerts
    
    def _get_action_items(self) -> List[str]:
        """Get suggested action items."""
        items = []
        ctx = self.context
        
        if ctx.blocked_tasks > 0:
            items.append("Review and unblock stalled tasks")
        
        if ctx.unread_messages > 0:
            items.append("Check unread messages for urgent items")
        
        if ctx.total_hours_logged < 1 and ctx.total_open_tasks > 0:
            items.append("Log time for recent work")
        
        return items
    
    def answer_question(self, question: str) -> str:
        """Answer a question about the project."""
        ctx = self.context
        
        # Build context for answering
        context_text = f"""
Project: {ctx.project_name}
Open Tasks: {ctx.total_open_tasks}
Hours Logged (7d): {ctx.total_hours_logged}
Last Activity: {ctx.last_activity}

Recent Tasks:
{chr(10).join(f'- {t.title} ({t.status})' for t in ctx.recent_tasks[:5])}

Recent Messages:
{chr(10).join(f'- {m.subject}' for m in ctx.recent_messages[:5])}
"""
        
        # For now, return context-based answer
        # In full implementation, this would use the LLM
        return f"""Based on {ctx.project_name} context:

{context_text}

To answer: "{question}"

(Full LLM-powered answers coming soon)
"""


def create_poc_agent(project_id: str, **kwargs) -> POCAgent:
    """
    Factory function to create a POC agent for a project.
    
    Args:
        project_id: Project identifier (e.g., 'ap-driving')
        **kwargs: Additional POCAgentConfig options
    
    Returns:
        Configured POCAgent instance
    """
    # Get project name from aggregator
    aggregator = ProjectContextAggregator()
    config_data = aggregator._project_config.get(project_id, {})
    
    config = POCAgentConfig(
        project_id=project_id,
        project_name=config_data.get('name', project_id.replace('-', ' ').title()),
        **kwargs,
    )
    
    return POCAgent(config)


# Registry of active POC agents
_poc_agents: Dict[str, POCAgent] = {}


def get_poc_agent(project_id: str) -> POCAgent:
    """Get or create a POC agent for a project."""
    if project_id not in _poc_agents:
        _poc_agents[project_id] = create_poc_agent(project_id)
    return _poc_agents[project_id]


def list_poc_agents() -> List[str]:
    """List all active POC agents."""
    return list(_poc_agents.keys())
