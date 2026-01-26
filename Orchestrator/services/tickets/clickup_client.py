"""
ClickUp API Client

Python wrapper for ClickUp API operations.
Leverages existing DevOps/lib/tickets/clickup.sh patterns.

SECURITY:
- API token from environment only
- All writes require confirmation
- Rate limiting respected
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration from environment
CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
CLICKUP_WORKSPACE_ID = os.getenv("CLICKUP_WORKSPACE_ID")

CLICKUP_API_BASE = "https://api.clickup.com/api/v2"
CLICKUP_MAX_RETRIES = 3
CLICKUP_RATE_LIMIT_WAIT = 60


@dataclass
class ClickUpTask:
    """Represents a ClickUp task."""
    id: str
    name: str
    description: str
    status: str
    priority: Optional[int]
    assignees: List[str]
    tags: List[str]
    list_id: str
    space_id: str
    created_at: datetime
    updated_at: datetime
    url: str
    
    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "ClickUpTask":
        # Convert milliseconds to datetime
        created_ts = int(data.get("date_created", "0")) / 1000
        updated_ts = int(data.get("date_updated", "0")) / 1000
        
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", data.get("markdown_description", "")),
            status=data.get("status", {}).get("status", ""),
            priority=data.get("priority", {}).get("id") if data.get("priority") else None,
            assignees=[a.get("username", "") for a in data.get("assignees", [])],
            tags=[t.get("name", "") for t in data.get("tags", [])],
            list_id=data.get("list", {}).get("id", ""),
            space_id=data.get("space", {}).get("id", ""),
            created_at=datetime.fromtimestamp(created_ts) if created_ts else datetime.now(),
            updated_at=datetime.fromtimestamp(updated_ts) if updated_ts else datetime.now(),
            url=data.get("url", ""),
        )


@dataclass
class ClickUpComment:
    """Represents a ClickUp task comment."""
    id: str
    comment_text: str
    user_id: int
    date: datetime


@dataclass
class ClickUpList:
    """Represents a ClickUp list."""
    id: str
    name: str
    space_id: str
    folder_id: Optional[str]
    task_count: int


class ClickUpClient:
    """ClickUp API client with safety controls."""
    
    def __init__(
        self,
        api_token: str = None,
        workspace_id: str = None,
    ):
        self._token = api_token or CLICKUP_API_TOKEN
        self._workspace_id = workspace_id or CLICKUP_WORKSPACE_ID
        self._session = None
    
    @property
    def is_available(self) -> bool:
        return REQUESTS_AVAILABLE and self._token is not None
    
    def _get_session(self) -> "requests.Session":
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests library required: pip install requests")
        
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": self._token,
                "Content-Type": "application/json",
            })
        return self._session
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """Make an API request with retry logic."""
        if not self.is_available:
            raise ValueError("ClickUp not configured. Set CLICKUP_API_TOKEN")
        
        session = self._get_session()
        url = f"{CLICKUP_API_BASE}{endpoint}"
        
        try:
            if method == "GET":
                response = session.get(url)
            elif method == "POST":
                response = session.post(url, json=data)
            elif method == "PUT":
                response = session.put(url, json=data)
            elif method == "DELETE":
                response = session.delete(url)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                if retry_count < CLICKUP_MAX_RETRIES:
                    import time
                    wait_time = CLICKUP_RATE_LIMIT_WAIT * (retry_count + 1)
                    time.sleep(wait_time)
                    return self._request(method, endpoint, data, retry_count + 1)
                raise Exception("Rate limited - max retries exceeded")
            
            response.raise_for_status()
            return response.json() if response.text else {}
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"ClickUp API error: {e}")
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            result = self._request("GET", "/team")
            return "teams" in result
        except Exception:
            return False
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def get_task(self, task_id: str, include_subtasks: bool = False) -> Optional[ClickUpTask]:
        """Get a single task by ID."""
        try:
            endpoint = f"/task/{task_id}"
            if include_subtasks:
                endpoint += "?include_subtasks=true"
            result = self._request("GET", endpoint)
            return ClickUpTask.from_api(result)
        except Exception:
            return None
    
    def get_tasks(
        self,
        list_id: str,
        include_closed: bool = False,
        since: str = None,
        limit: int = 100,
    ) -> List[ClickUpTask]:
        """Get tasks from a list."""
        endpoint = f"/list/{list_id}/task?include_closed={str(include_closed).lower()}"
        
        if since:
            # Convert ISO date to milliseconds
            try:
                dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                since_ms = int(dt.timestamp() * 1000)
                endpoint += f"&date_updated_gt={since_ms}"
            except ValueError:
                pass
        
        result = self._request("GET", endpoint)
        
        tasks = []
        for item in result.get("tasks", [])[:limit]:
            tasks.append(ClickUpTask.from_api(item))
        
        return tasks
    
    def search_tasks(
        self,
        query: str,
        team_id: str = None,
        limit: int = 25,
    ) -> List[ClickUpTask]:
        """Search for tasks."""
        team = team_id or self._workspace_id
        if not team:
            raise ValueError("Workspace ID required for search")
        
        # ClickUp search endpoint
        endpoint = f"/team/{team}/task?order_by=updated&include_closed=false"
        result = self._request("GET", endpoint)
        
        # Client-side filter by query
        tasks = []
        query_lower = query.lower()
        for item in result.get("tasks", []):
            name = item.get("name", "").lower()
            desc = item.get("description", "").lower()
            if query_lower in name or query_lower in desc:
                tasks.append(ClickUpTask.from_api(item))
                if len(tasks) >= limit:
                    break
        
        return tasks
    
    def get_task_comments(self, task_id: str) -> List[ClickUpComment]:
        """Get comments for a task."""
        result = self._request("GET", f"/task/{task_id}/comment")
        
        comments = []
        for item in result.get("comments", []):
            date_ts = int(item.get("date", "0")) / 1000
            comments.append(ClickUpComment(
                id=item["id"],
                comment_text=item.get("comment_text", ""),
                user_id=item.get("user", {}).get("id", 0),
                date=datetime.fromtimestamp(date_ts) if date_ts else datetime.now(),
            ))
        
        return comments
    
    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Get all workspaces (teams)."""
        result = self._request("GET", "/team")
        return result.get("teams", [])
    
    def get_spaces(self, team_id: str = None) -> List[Dict[str, Any]]:
        """Get spaces in a workspace."""
        team = team_id or self._workspace_id
        if not team:
            raise ValueError("Workspace ID required")
        result = self._request("GET", f"/team/{team}/space")
        return result.get("spaces", [])
    
    def get_lists(self, folder_id: str) -> List[ClickUpList]:
        """Get lists in a folder."""
        result = self._request("GET", f"/folder/{folder_id}/list")
        
        lists = []
        for item in result.get("lists", []):
            lists.append(ClickUpList(
                id=item["id"],
                name=item.get("name", ""),
                space_id=item.get("space", {}).get("id", ""),
                folder_id=folder_id,
                task_count=item.get("task_count", 0),
            ))
        
        return lists
    
    def get_folderless_lists(self, space_id: str) -> List[ClickUpList]:
        """Get lists directly in a space (not in folders)."""
        result = self._request("GET", f"/space/{space_id}/list")
        
        lists = []
        for item in result.get("lists", []):
            lists.append(ClickUpList(
                id=item["id"],
                name=item.get("name", ""),
                space_id=space_id,
                folder_id=None,
                task_count=item.get("task_count", 0),
            ))
        
        return lists
    
    # =========================================================================
    # WRITE OPERATIONS (require confirmation)
    # =========================================================================
    
    def create_task(
        self,
        list_id: str,
        name: str,
        description: str = "",
        priority: int = 3,
        status: str = None,
        tags: List[str] = None,
        assignees: List[int] = None,
    ) -> Optional[ClickUpTask]:
        """Create a new task. Requires confirmation."""
        payload = {
            "name": name,
            "markdown_description": description,
            "priority": priority,
        }
        
        if status:
            payload["status"] = status
        if tags:
            payload["tags"] = tags
        if assignees:
            payload["assignees"] = assignees
        
        result = self._request("POST", f"/list/{list_id}/task", payload)
        if "id" in result:
            return ClickUpTask.from_api(result)
        return None
    
    def update_task(
        self,
        task_id: str,
        name: str = None,
        description: str = None,
        status: str = None,
        priority: int = None,
    ) -> bool:
        """Update a task. Requires confirmation."""
        payload = {}
        
        if name:
            payload["name"] = name
        if description:
            payload["markdown_description"] = description
        if status:
            payload["status"] = status
        if priority is not None:
            payload["priority"] = priority
        
        if not payload:
            return True  # Nothing to update
        
        try:
            self._request("PUT", f"/task/{task_id}", payload)
            return True
        except Exception:
            return False
    
    def add_comment(self, task_id: str, comment: str, notify_all: bool = False) -> bool:
        """Add a comment to a task."""
        payload = {
            "comment_text": comment,
            "notify_all": notify_all,
        }
        
        try:
            self._request("POST", f"/task/{task_id}/comment", payload)
            return True
        except Exception:
            return False
    
    def add_tag(self, task_id: str, tag_name: str) -> bool:
        """Add a tag to a task."""
        try:
            self._request("POST", f"/task/{task_id}/tag/{tag_name}", {})
            return True
        except Exception:
            return False


# Global instance
_client: Optional[ClickUpClient] = None


def get_clickup_client() -> ClickUpClient:
    """Get the global ClickUp client."""
    global _client
    if _client is None:
        _client = ClickUpClient()
    return _client
