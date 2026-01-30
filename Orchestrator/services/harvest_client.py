"""
Harvest Time Tracking API Client

Provides integration with Harvest for:
- Viewing time entries
- Logging time
- Fetching projects and tasks
- Time summaries

Setup:
1. Get your Personal Access Token from: https://id.getharvest.com/developers
2. Set environment variables:
   - HARVEST_ACCESS_TOKEN
   - HARVEST_ACCOUNT_ID
"""

import os
import httpx
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class TimeEntry:
    """A single time entry."""
    id: int
    hours: float
    notes: Optional[str]
    project_name: str
    task_name: str
    spent_date: str
    is_running: bool = False
    started_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Project:
    """A Harvest project."""
    id: int
    name: str
    code: Optional[str]
    client_name: Optional[str]
    is_active: bool = True


@dataclass 
class TimeSummary:
    """Summary of time logged."""
    hours_today: float
    hours_this_week: float
    hours_this_month: float
    entries_today: List[TimeEntry]
    active_timer: Optional[TimeEntry] = None


class HarvestClient:
    """Client for Harvest Time Tracking API."""
    
    BASE_URL = "https://api.harvestapp.com/v2"
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        account_id: Optional[str] = None,
    ):
        self.access_token = access_token or os.getenv("HARVEST_ACCESS_TOKEN")
        self.account_id = account_id or os.getenv("HARVEST_ACCOUNT_ID")
        
        if not self.access_token or not self.account_id:
            raise ValueError(
                "Harvest credentials not configured. Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID"
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Harvest-Account-Id": self.account_id,
            "User-Agent": "Agent007 Orchestrator",
            "Content-Type": "application/json",
        }
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an API request to Harvest."""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                json=json_data,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()
    
    # =========================================================================
    # Time Entries
    # =========================================================================
    
    async def get_time_entries(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        project_id: Optional[int] = None,
    ) -> List[TimeEntry]:
        """Get time entries for a date range."""
        params = {}
        
        if from_date:
            params["from"] = from_date.isoformat()
        if to_date:
            params["to"] = to_date.isoformat()
        if project_id:
            params["project_id"] = project_id
        
        data = await self._request("GET", "/time_entries", params=params)
        
        entries = []
        for entry in data.get("time_entries", []):
            entries.append(TimeEntry(
                id=entry["id"],
                hours=entry["hours"],
                notes=entry.get("notes"),
                project_name=entry["project"]["name"],
                task_name=entry["task"]["name"],
                spent_date=entry["spent_date"],
                is_running=entry.get("is_running", False),
                started_time=entry.get("started_time"),
            ))
        
        return entries
    
    async def get_today_entries(self) -> List[TimeEntry]:
        """Get all time entries for today."""
        today = date.today()
        return await self.get_time_entries(from_date=today, to_date=today)
    
    async def get_running_timer(self) -> Optional[TimeEntry]:
        """Get the currently running timer, if any."""
        entries = await self.get_today_entries()
        for entry in entries:
            if entry.is_running:
                return entry
        return None
    
    async def create_time_entry(
        self,
        project_id: int,
        task_id: int,
        hours: Optional[float] = None,
        notes: Optional[str] = None,
        spent_date: Optional[date] = None,
    ) -> TimeEntry:
        """Create a new time entry."""
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "spent_date": (spent_date or date.today()).isoformat(),
        }
        
        if hours is not None:
            data["hours"] = hours
        if notes:
            data["notes"] = notes
        
        result = await self._request("POST", "/time_entries", json_data=data)
        
        return TimeEntry(
            id=result["id"],
            hours=result["hours"],
            notes=result.get("notes"),
            project_name=result["project"]["name"],
            task_name=result["task"]["name"],
            spent_date=result["spent_date"],
            is_running=result.get("is_running", False),
        )
    
    async def start_timer(
        self,
        project_id: int,
        task_id: int,
        notes: Optional[str] = None,
    ) -> TimeEntry:
        """Start a new timer."""
        # First stop any running timer
        running = await self.get_running_timer()
        if running:
            await self.stop_timer(running.id)
        
        # Create entry with started_time to start timer
        data = {
            "project_id": project_id,
            "task_id": task_id,
            "spent_date": date.today().isoformat(),
            "started_time": datetime.now().strftime("%H:%M"),
        }
        
        if notes:
            data["notes"] = notes
        
        result = await self._request("POST", "/time_entries", json_data=data)
        
        return TimeEntry(
            id=result["id"],
            hours=result["hours"],
            notes=result.get("notes"),
            project_name=result["project"]["name"],
            task_name=result["task"]["name"],
            spent_date=result["spent_date"],
            is_running=True,
            started_time=result.get("started_time"),
        )
    
    async def stop_timer(self, entry_id: int) -> TimeEntry:
        """Stop a running timer."""
        result = await self._request("PATCH", f"/time_entries/{entry_id}/stop")
        
        return TimeEntry(
            id=result["id"],
            hours=result["hours"],
            notes=result.get("notes"),
            project_name=result["project"]["name"],
            task_name=result["task"]["name"],
            spent_date=result["spent_date"],
            is_running=False,
        )
    
    async def update_entry(
        self,
        entry_id: int,
        hours: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> TimeEntry:
        """Update an existing time entry."""
        data = {}
        if hours is not None:
            data["hours"] = hours
        if notes is not None:
            data["notes"] = notes
        
        result = await self._request("PATCH", f"/time_entries/{entry_id}", json_data=data)
        
        return TimeEntry(
            id=result["id"],
            hours=result["hours"],
            notes=result.get("notes"),
            project_name=result["project"]["name"],
            task_name=result["task"]["name"],
            spent_date=result["spent_date"],
            is_running=result.get("is_running", False),
        )
    
    async def delete_entry(self, entry_id: int) -> bool:
        """Delete a time entry."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.BASE_URL}/time_entries/{entry_id}",
                headers=self.headers,
                timeout=30.0,
            )
            return response.status_code == 200
    
    # =========================================================================
    # Projects & Tasks
    # =========================================================================
    
    async def get_projects(self, active_only: bool = True) -> List[Project]:
        """Get available projects."""
        params = {"is_active": "true"} if active_only else {}
        
        data = await self._request("GET", "/projects", params=params)
        
        projects = []
        for proj in data.get("projects", []):
            projects.append(Project(
                id=proj["id"],
                name=proj["name"],
                code=proj.get("code"),
                client_name=proj.get("client", {}).get("name"),
                is_active=proj.get("is_active", True),
            ))
        
        return projects
    
    async def get_project_tasks(self, project_id: int) -> List[Dict[str, Any]]:
        """Get tasks for a specific project."""
        data = await self._request("GET", f"/projects/{project_id}/task_assignments")
        
        tasks = []
        for assignment in data.get("task_assignments", []):
            task = assignment.get("task", {})
            tasks.append({
                "id": task.get("id"),
                "name": task.get("name"),
                "is_active": assignment.get("is_active", True),
            })
        
        return tasks
    
    async def find_project_by_name(self, name: str) -> Optional[Project]:
        """Find a project by name (case-insensitive partial match)."""
        projects = await self.get_projects()
        name_lower = name.lower()
        
        for project in projects:
            if name_lower in project.name.lower():
                return project
        
        return None
    
    # =========================================================================
    # Summaries
    # =========================================================================
    
    async def get_time_summary(self) -> TimeSummary:
        """Get a summary of time logged."""
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday
        month_start = today.replace(day=1)
        
        # Get entries for different periods
        today_entries = await self.get_time_entries(from_date=today, to_date=today)
        week_entries = await self.get_time_entries(from_date=week_start, to_date=today)
        month_entries = await self.get_time_entries(from_date=month_start, to_date=today)
        
        # Calculate totals
        hours_today = sum(e.hours for e in today_entries)
        hours_this_week = sum(e.hours for e in week_entries)
        hours_this_month = sum(e.hours for e in month_entries)
        
        # Find active timer
        active_timer = None
        for entry in today_entries:
            if entry.is_running:
                active_timer = entry
                break
        
        return TimeSummary(
            hours_today=round(hours_today, 2),
            hours_this_week=round(hours_this_week, 2),
            hours_this_month=round(hours_this_month, 2),
            entries_today=today_entries,
            active_timer=active_timer,
        )


# Singleton instance
_harvest_client: Optional[HarvestClient] = None


def get_harvest_client() -> Optional[HarvestClient]:
    """Get the Harvest client instance, or None if not configured."""
    global _harvest_client
    
    if _harvest_client is None:
        try:
            _harvest_client = HarvestClient()
        except ValueError:
            return None
    
    return _harvest_client


def is_harvest_configured() -> bool:
    """Check if Harvest credentials are configured."""
    return bool(
        os.getenv("HARVEST_ACCESS_TOKEN") and 
        os.getenv("HARVEST_ACCOUNT_ID")
    )
