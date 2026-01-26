"""
Harvest Time Tracking Tool

Provides time tracking capabilities for the Orchestrator.
Agents can start/stop timers and log time entries for tickets.
"""

import os
import requests
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from crewai.tools import BaseTool

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from governance.audit import get_audit_logger, AuditEvent, ActionType
from governance.allowlist import get_allowlist


@dataclass
class HarvestConfig:
    """Harvest API configuration."""
    access_token: str
    account_id: str
    default_project_id: Optional[int] = None
    default_task_id: Optional[int] = None
    
    @classmethod
    def from_env(cls) -> Optional["HarvestConfig"]:
        """Load config from environment variables."""
        token = os.getenv("HARVEST_ACCESS_TOKEN")
        account = os.getenv("HARVEST_ACCOUNT_ID")
        
        if not token or not account:
            return None
        
        return cls(
            access_token=token,
            account_id=account,
            default_project_id=int(os.getenv("HARVEST_DEFAULT_PROJECT_ID", 0)) or None,
            default_task_id=int(os.getenv("HARVEST_DEFAULT_TASK_ID", 0)) or None,
        )


class HarvestClient:
    """Client for Harvest API."""
    
    def __init__(self, config: HarvestConfig):
        self.config = config
        self.base_url = "https://api.harvestapp.com/v2"
        self.headers = {
            "Authorization": f"Bearer {config.access_token}",
            "Harvest-Account-Id": str(config.account_id),
            "User-Agent": "Orchestrator-Harvest-Integration",
            "Content-Type": "application/json",
        }
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all available projects."""
        try:
            response = requests.get(
                f"{self.base_url}/projects",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("projects", [])
        except Exception as e:
            return []
    
    def get_tasks(self) -> List[Dict[str, Any]]:
        """Get all available tasks."""
        try:
            response = requests.get(
                f"{self.base_url}/tasks",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("tasks", [])
        except Exception as e:
            return []
    
    def get_running_timer(self, ticket_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get currently running timer."""
        try:
            response = requests.get(
                f"{self.base_url}/time_entries",
                headers=self.headers,
                params={"is_running": "true"},
                timeout=30
            )
            response.raise_for_status()
            timers = response.json().get("time_entries", [])
            
            if not timers:
                return None
            
            if ticket_id:
                for timer in timers:
                    ref = timer.get("external_reference", {})
                    if ref.get("id") == str(ticket_id):
                        return timer
                return None
            
            return timers[0]
        except Exception:
            return None
    
    def start_timer(
        self,
        ticket_id: str,
        notes: str,
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Start a timer for a ticket."""
        project_id = project_id or self.config.default_project_id
        task_id = task_id or self.config.default_task_id
        
        if not project_id or not task_id:
            return {"error": "Project ID and Task ID are required. Set HARVEST_DEFAULT_PROJECT_ID and HARVEST_DEFAULT_TASK_ID."}
        
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "notes": f"Ticket #{ticket_id}: {notes}",
            "external_reference": {
                "id": str(ticket_id),
                "group_id": "orchestrator-tickets",
                "permalink": f"https://airtable.com/ticket/{ticket_id}"
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/time_entries",
                headers=self.headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            entry = response.json()
            return {
                "success": True,
                "timer_id": entry.get("id"),
                "message": f"Started timer for ticket #{ticket_id}",
            }
        except Exception as e:
            return {"error": str(e)}
    
    def stop_timer(self, ticket_id: Optional[str] = None) -> Dict[str, Any]:
        """Stop the running timer."""
        timer = self.get_running_timer(ticket_id)
        
        if not timer:
            return {"error": f"No running timer found" + (f" for ticket #{ticket_id}" if ticket_id else "")}
        
        timer_id = timer.get("id")
        
        try:
            response = requests.patch(
                f"{self.base_url}/time_entries/{timer_id}/stop",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            entry = response.json()
            return {
                "success": True,
                "timer_id": timer_id,
                "hours": entry.get("hours", 0),
                "message": f"Stopped timer. Logged {entry.get('hours', 0)} hours.",
            }
        except Exception as e:
            return {"error": str(e)}
    
    def log_time(
        self,
        ticket_id: str,
        hours: float,
        notes: str,
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
        entry_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a completed time entry."""
        project_id = project_id or self.config.default_project_id
        task_id = task_id or self.config.default_task_id
        
        if not project_id or not task_id:
            return {"error": "Project ID and Task ID are required."}
        
        if not entry_date:
            entry_date = date.today().strftime("%Y-%m-%d")
        
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "spent_date": entry_date,
            "hours": hours,
            "notes": f"Ticket #{ticket_id}: {notes}",
            "external_reference": {
                "id": str(ticket_id),
                "group_id": "orchestrator-tickets",
                "permalink": f"https://airtable.com/ticket/{ticket_id}"
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/time_entries",
                headers=self.headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            entry = response.json()
            return {
                "success": True,
                "entry_id": entry.get("id"),
                "hours": hours,
                "date": entry_date,
                "message": f"Logged {hours} hours for ticket #{ticket_id}",
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_today_entries(self) -> List[Dict[str, Any]]:
        """Get today's time entries."""
        try:
            today = date.today().strftime("%Y-%m-%d")
            response = requests.get(
                f"{self.base_url}/time_entries",
                headers=self.headers,
                params={"from": today, "to": today},
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("time_entries", [])
        except Exception:
            return []


# Singleton client
_client: Optional[HarvestClient] = None


def get_harvest_client() -> Optional[HarvestClient]:
    """Get or create Harvest client."""
    global _client
    
    if _client is None:
        config = HarvestConfig.from_env()
        if config:
            _client = HarvestClient(config)
    
    return _client


# =============================================================================
# CrewAI Tools
# =============================================================================

class HarvestStartTimerTool(BaseTool):
    """Start a Harvest timer for a ticket."""
    
    name: str = "harvest_start_timer"
    description: str = """Start a time tracking timer for a ticket.
    
    Input format: ticket_id ||| notes
    Example: 4962 ||| Working on payment plan update
    
    This starts a running timer in Harvest that will track time until stopped."""
    
    def _run(self, input_str: str) -> str:
        logger = get_audit_logger()
        client = get_harvest_client()
        
        if not client:
            return "ERROR: Harvest not configured. Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID."
        
        if "|||" not in input_str:
            return "ERROR: Input must be 'ticket_id ||| notes'"
        
        parts = input_str.split("|||", 1)
        ticket_id = parts[0].strip()
        notes = parts[1].strip()
        
        logger.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent="harvest_start_timer",
            description=f"Starting timer for ticket #{ticket_id}",
            input_data={"ticket_id": ticket_id, "notes": notes},
        ))
        
        result = client.start_timer(ticket_id, notes)
        
        if result.get("error"):
            return f"ERROR: {result['error']}"
        
        return f"⏱️ {result['message']}\nTimer ID: {result.get('timer_id')}"


class HarvestStopTimerTool(BaseTool):
    """Stop a running Harvest timer."""
    
    name: str = "harvest_stop_timer"
    description: str = """Stop the currently running Harvest timer.
    
    Input: Optional ticket_id to stop timer for specific ticket, or empty to stop any running timer.
    Example: 4962
    Example: (empty)
    
    Returns the logged hours."""
    
    def _run(self, ticket_id: str = "") -> str:
        logger = get_audit_logger()
        client = get_harvest_client()
        
        if not client:
            return "ERROR: Harvest not configured."
        
        ticket_id = ticket_id.strip() if ticket_id else None
        
        logger.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent="harvest_stop_timer",
            description=f"Stopping timer" + (f" for ticket #{ticket_id}" if ticket_id else ""),
        ))
        
        result = client.stop_timer(ticket_id)
        
        if result.get("error"):
            return f"ERROR: {result['error']}"
        
        return f"⏹️ {result['message']}"


class HarvestLogTimeTool(BaseTool):
    """Log a completed time entry to Harvest."""
    
    name: str = "harvest_log_time"
    description: str = """Log completed time for a ticket (without using a timer).
    
    Input format: ticket_id ||| hours ||| notes
    Example: 4962 ||| 2.5 ||| Updated payment plan database
    
    Hours should be a decimal (e.g., 1.5 for 1 hour 30 minutes)."""
    
    def _run(self, input_str: str) -> str:
        logger = get_audit_logger()
        client = get_harvest_client()
        
        if not client:
            return "ERROR: Harvest not configured."
        
        parts = input_str.split("|||")
        if len(parts) < 3:
            return "ERROR: Input must be 'ticket_id ||| hours ||| notes'"
        
        ticket_id = parts[0].strip()
        try:
            hours = float(parts[1].strip())
        except ValueError:
            return "ERROR: Hours must be a number (e.g., 2.5)"
        notes = parts[2].strip()
        
        logger.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent="harvest_log_time",
            description=f"Logging {hours}h for ticket #{ticket_id}",
            input_data={"ticket_id": ticket_id, "hours": hours, "notes": notes},
        ))
        
        result = client.log_time(ticket_id, hours, notes)
        
        if result.get("error"):
            return f"ERROR: {result['error']}"
        
        return f"📊 {result['message']}\nEntry ID: {result.get('entry_id')}"


class HarvestStatusTool(BaseTool):
    """Check Harvest timer status and today's time."""
    
    name: str = "harvest_status"
    description: str = """Check the current Harvest timer status and today's logged time.
    
    Input: (none required)
    
    Returns running timer info and today's total hours."""
    
    def _run(self, _: str = "") -> str:
        client = get_harvest_client()
        
        if not client:
            return "ERROR: Harvest not configured."
        
        # Get running timer
        running = client.get_running_timer()
        
        # Get today's entries
        entries = client.get_today_entries()
        total_hours = sum(e.get("hours", 0) for e in entries)
        
        lines = ["📊 Harvest Status\n"]
        
        if running:
            notes = running.get("notes", "No notes")
            started = running.get("started_time", "Unknown")
            lines.append(f"⏱️ TIMER RUNNING")
            lines.append(f"   Notes: {notes}")
            lines.append(f"   Started: {started}")
        else:
            lines.append("⏹️ No timer running")
        
        lines.append(f"\n📅 Today's Time: {total_hours:.2f} hours ({len(entries)} entries)")
        
        if entries:
            lines.append("\nRecent entries:")
            for entry in entries[:5]:
                hours = entry.get("hours", 0)
                notes = entry.get("notes", "")[:50]
                lines.append(f"  • {hours}h: {notes}...")
        
        return "\n".join(lines)


def get_harvest_tools() -> List[BaseTool]:
    """Get all Harvest tools for CrewAI agents."""
    return [
        HarvestStartTimerTool(),
        HarvestStopTimerTool(),
        HarvestLogTimeTool(),
        HarvestStatusTool(),
    ]


# =============================================================================
# Direct Functions (for Streamlit UI)
# =============================================================================

def start_timer(ticket_id: str, notes: str) -> Dict[str, Any]:
    """Start a timer (for direct use)."""
    client = get_harvest_client()
    if not client:
        return {"error": "Harvest not configured"}
    return client.start_timer(ticket_id, notes)


def stop_timer(ticket_id: Optional[str] = None) -> Dict[str, Any]:
    """Stop the timer (for direct use)."""
    client = get_harvest_client()
    if not client:
        return {"error": "Harvest not configured"}
    return client.stop_timer(ticket_id)


def log_time(ticket_id: str, hours: float, notes: str) -> Dict[str, Any]:
    """Log time (for direct use)."""
    client = get_harvest_client()
    if not client:
        return {"error": "Harvest not configured"}
    return client.log_time(ticket_id, hours, notes)


def get_status() -> Dict[str, Any]:
    """Get Harvest status (for direct use)."""
    client = get_harvest_client()
    if not client:
        return {"configured": False}
    
    running = client.get_running_timer()
    entries = client.get_today_entries()
    total_hours = sum(e.get("hours", 0) for e in entries)
    
    return {
        "configured": True,
        "running_timer": running,
        "today_hours": total_hours,
        "today_entries": len(entries),
        "entries": entries[:10],
    }


def get_projects() -> List[Dict[str, Any]]:
    """Get available projects (for UI)."""
    client = get_harvest_client()
    if not client:
        return []
    return client.get_projects()


def get_tasks() -> List[Dict[str, Any]]:
    """Get available tasks (for UI)."""
    client = get_harvest_client()
    if not client:
        return []
    return client.get_tasks()
