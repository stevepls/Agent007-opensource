"""
Hubstaff Time Tracking API Client

Provides integration with Hubstaff V2 API for:
- Viewing active time entries
- Starting/stopping time tracking
- Listing time entries for users

Setup:
1. Get your API token from Hubstaff dashboard
2. Set environment variables:
   - HUBSTAFF_API_TOKEN
   - HUBSTAFF_ORG_ID (optional, for org-scoped operations)
"""

import os
import httpx
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class TimeEntry:
    """A single Hubstaff time entry."""
    id: int
    user_id: int
    project_id: Optional[int]
    task_id: Optional[int]
    tracked: float  # seconds tracked
    date: str  # YYYY-MM-DD
    note: Optional[str] = None
    is_stopped: bool = True
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @property
    def is_active(self) -> bool:
        """Check if this entry is currently running."""
        return not self.is_stopped and self.stopped_at is None


@dataclass
class Project:
    """A Hubstaff project."""
    id: int
    name: str
    status: str
    description: Optional[str] = None


class HubstaffClient:
    """Client for Hubstaff V2 API."""
    
    BASE_URL = "https://api.hubstaff.com/v2"
    
    def __init__(self, api_token: Optional[str] = None, org_id: Optional[int] = None):
        """
        Initialize Hubstaff client.
        
        Args:
            api_token: Hubstaff API token (or from HUBSTAFF_API_TOKEN env var)
            org_id: Organization ID (or from HUBSTAFF_ORG_ID env var)
        """
        self.api_token = api_token or os.getenv('HUBSTAFF_API_TOKEN')
        if not self.api_token:
            raise ValueError("HUBSTAFF_API_TOKEN must be set")
        
        self.org_id = org_id or os.getenv('HUBSTAFF_ORG_ID')
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API request with error handling."""
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.request(method, url, headers=self.headers, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Hubstaff API error: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"Hubstaff request error: {str(e)}")
    
    def get_active_time_entries(self, user_id: Optional[int] = None) -> List[TimeEntry]:
        """
        Get active (running) time entries.
        
        Args:
            user_id: Filter by user ID (optional)
        
        Returns:
            List of active TimeEntry objects
        """
        params = {"active": "true"}
        if user_id:
            params["user_ids[]"] = user_id
        if self.org_id:
            params["organization_id"] = self.org_id
        
        data = self._request("GET", "/time_entries", params=params)
        
        entries = []
        for entry_data in data.get("time_entries", []):
            entries.append(self._parse_time_entry(entry_data))
        
        return entries
    
    def get_user_time_entries(
        self, 
        user_id: int, 
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TimeEntry]:
        """
        Get time entries for a specific user.
        
        Args:
            user_id: User ID
            start_date: Start date (defaults to today)
            end_date: End date (defaults to today)
        
        Returns:
            List of TimeEntry objects
        """
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = date.today()
        
        params = {
            "user_ids[]": user_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
        if self.org_id:
            params["organization_id"] = self.org_id
        
        data = self._request("GET", "/time_entries", params=params)
        
        entries = []
        for entry_data in data.get("time_entries", []):
            entries.append(self._parse_time_entry(entry_data))
        
        return entries
    
    def stop_time_entry(self, time_entry_id: int) -> bool:
        """
        Stop an active time entry.
        
        Args:
            time_entry_id: ID of the time entry to stop
        
        Returns:
            True if successful
        """
        try:
            self._request("PATCH", f"/time_entries/{time_entry_id}", json={"stopped_at": datetime.utcnow().isoformat()})
            return True
        except Exception as e:
            print(f"Error stopping time entry {time_entry_id}: {e}")
            return False
    
    def stop_user_active_entries(self, user_id: int) -> int:
        """
        Stop all active time entries for a user.
        
        Args:
            user_id: User ID
        
        Returns:
            Number of entries stopped
        """
        active_entries = self.get_active_time_entries(user_id=user_id)
        stopped_count = 0
        
        for entry in active_entries:
            if entry.user_id == user_id and entry.is_active:
                if self.stop_time_entry(entry.id):
                    stopped_count += 1
        
        return stopped_count
    
    def start_time_entry(
        self,
        user_id: int,
        project_id: Optional[int] = None,
        task_id: Optional[int] = None,
        note: Optional[str] = None
    ) -> Optional[TimeEntry]:
        """
        Start a new time entry.
        
        Args:
            user_id: User ID
            project_id: Project ID (optional)
            task_id: Task ID (optional)
            note: Note for the entry (optional)
        
        Returns:
            TimeEntry object if successful, None otherwise
        """
        payload = {
            "user_id": user_id,
            "started_at": datetime.utcnow().isoformat()
        }
        if project_id:
            payload["project_id"] = project_id
        if task_id:
            payload["task_id"] = task_id
        if note:
            payload["note"] = note
        if self.org_id:
            payload["organization_id"] = self.org_id
        
        try:
            data = self._request("POST", "/time_entries", json=payload)
            entry_data = data.get("time_entry", {})
            return self._parse_time_entry(entry_data)
        except Exception as e:
            print(f"Error starting time entry: {e}")
            return None
    
    def _parse_time_entry(self, data: Dict[str, Any]) -> TimeEntry:
        """Parse time entry from API response."""
        return TimeEntry(
            id=data.get("id", 0),
            user_id=data.get("user_id", 0),
            project_id=data.get("project_id"),
            task_id=data.get("task_id"),
            tracked=data.get("tracked", 0),
            date=data.get("date", ""),
            note=data.get("note"),
            is_stopped=data.get("stopped_at") is not None,
            started_at=data.get("started_at"),
            stopped_at=data.get("stopped_at")
        )
    
    def get_user_id_by_email(self, email: str) -> Optional[int]:
        """
        Get user ID by email address.
        Note: This requires appropriate API permissions.
        
        Args:
            email: User email address
        
        Returns:
            User ID if found, None otherwise
        """
        try:
            data = self._request("GET", "/users", params={"email": email})
            users = data.get("users", [])
            if users:
                return users[0].get("id")
        except Exception as e:
            print(f"Error finding user by email: {e}")
        return None
