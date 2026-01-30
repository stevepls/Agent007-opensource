"""
ClickUp API Client

Python wrapper around the DevOps ClickUp shell library.
Provides typed interfaces for task management.

Required env vars:
- CLICKUP_API_TOKEN
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

# DevOps library path
DEVOPS_ROOT = Path(__file__).parent.parent.parent.parent / "DevOps"
CLICKUP_LIB = DEVOPS_ROOT / "lib" / "tickets" / "clickup.sh"


@dataclass
class ClickUpTask:
    """Represents a ClickUp task."""
    id: str
    name: str
    description: str
    status: str
    priority: Optional[int]  # 1=Urgent, 2=High, 3=Normal, 4=Low
    assignees: List[str]
    tags: List[str]
    list_id: str
    space_id: Optional[str]
    folder_id: Optional[str]
    date_created: datetime
    date_updated: datetime
    date_due: Optional[datetime]
    url: str
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClickUpTask":
        # Parse timestamps (ClickUp uses milliseconds)
        def parse_ts(ts):
            if ts:
                return datetime.fromtimestamp(int(ts) / 1000)
            return datetime.now()

        return cls(
            id=data["id"],
            name=data.get("name", ""),
            description=data.get("description", data.get("markdown_description", "")),
            status=data.get("status", {}).get("status", ""),
            priority=data.get("priority", {}).get("id") if data.get("priority") else None,
            assignees=[a.get("email", a.get("username", "")) for a in data.get("assignees", [])],
            tags=[t.get("name", t) if isinstance(t, dict) else t for t in data.get("tags", [])],
            list_id=data.get("list", {}).get("id", ""),
            space_id=data.get("space", {}).get("id"),
            folder_id=data.get("folder", {}).get("id"),
            date_created=parse_ts(data.get("date_created")),
            date_updated=parse_ts(data.get("date_updated")),
            date_due=parse_ts(data.get("due_date")) if data.get("due_date") else None,
            url=data.get("url", ""),
            custom_fields={
                cf.get("name", ""): cf.get("value")
                for cf in data.get("custom_fields", [])
            },
        )

    @property
    def priority_name(self) -> str:
        """Get human-readable priority name."""
        return {1: "Urgent", 2: "High", 3: "Normal", 4: "Low"}.get(self.priority, "None")


@dataclass
class ClickUpComment:
    """Represents a ClickUp comment."""
    id: str
    text: str
    user: str
    date: datetime


@dataclass
class ClickUpList:
    """Represents a ClickUp list."""
    id: str
    name: str
    space_id: str
    folder_id: Optional[str]
    task_count: int
    statuses: List[str]


class ClickUpClient:
    """ClickUp API client."""

    API_BASE = "https://api.clickup.com/api/v2"

    def __init__(self, api_token: str = None):
        self.api_token = api_token or os.getenv("CLICKUP_API_TOKEN")

        if not self.api_token:
            raise ValueError(
                "Missing ClickUp API token. Set CLICKUP_API_TOKEN environment variable."
            )

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
    ) -> Optional[Dict]:
        """Make a direct API request."""
        url = f"{self.API_BASE}{endpoint}"

        cmd = [
            "curl", "-sS", "-X", method,
            "-H", f"Authorization: {self.api_token}",
            "-H", "Content-Type: application/json",
        ]

        if data:
            cmd.extend(["-d", json.dumps(data)])

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return None

    # =========================================================================
    # Task Operations
    # =========================================================================

    def get_task(self, task_id: str, include_subtasks: bool = False) -> Optional[ClickUpTask]:
        """Get a task by ID."""
        endpoint = f"/task/{task_id}"
        if include_subtasks:
            endpoint += "?include_subtasks=true"

        result = self._api_request("GET", endpoint)
        if result and "id" in result:
            return ClickUpTask.from_dict(result)
        return None

    def list_tasks(
        self,
        list_id: str,
        include_closed: bool = False,
        statuses: List[str] = None,
    ) -> List[ClickUpTask]:
        """List tasks in a list."""
        endpoint = f"/list/{list_id}/task?include_closed={str(include_closed).lower()}"

        if statuses:
            for status in statuses:
                endpoint += f"&statuses[]={status}"

        result = self._api_request("GET", endpoint)

        tasks = []
        if result and "tasks" in result:
            for item in result["tasks"]:
                try:
                    tasks.append(ClickUpTask.from_dict(item))
                except Exception:
                    pass
        return tasks

    def create_task(
        self,
        list_id: str,
        name: str,
        description: str = "",
        priority: int = 3,
        status: str = None,
        tags: List[str] = None,
        assignees: List[int] = None,
        due_date: datetime = None,
    ) -> Optional[ClickUpTask]:
        """Create a new task."""
        data = {
            "name": name,
            "markdown_description": description,
            "priority": priority,
        }

        if status:
            data["status"] = status
        if tags:
            data["tags"] = tags
        if assignees:
            data["assignees"] = assignees
        if due_date:
            data["due_date"] = int(due_date.timestamp() * 1000)

        result = self._api_request("POST", f"/list/{list_id}/task", data)
        if result and "id" in result:
            return ClickUpTask.from_dict(result)
        return None

    def update_task(
        self,
        task_id: str,
        name: str = None,
        description: str = None,
        status: str = None,
        priority: int = None,
    ) -> Optional[ClickUpTask]:
        """Update an existing task."""
        data = {}

        if name:
            data["name"] = name
        if description:
            data["markdown_description"] = description
        if status:
            data["status"] = status
        if priority:
            data["priority"] = priority

        result = self._api_request("PUT", f"/task/{task_id}", data)
        if result and "id" in result:
            return ClickUpTask.from_dict(result)
        return None

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        result = self._api_request("DELETE", f"/task/{task_id}")
        return result is not None

    # =========================================================================
    # Comments
    # =========================================================================

    def get_comments(self, task_id: str) -> List[ClickUpComment]:
        """Get all comments for a task."""
        result = self._api_request("GET", f"/task/{task_id}/comment")

        comments = []
        if result and "comments" in result:
            for c in result["comments"]:
                try:
                    comments.append(ClickUpComment(
                        id=c["id"],
                        text=c.get("comment_text", ""),
                        user=c.get("user", {}).get("email", ""),
                        date=datetime.fromtimestamp(int(c.get("date", 0)) / 1000),
                    ))
                except Exception:
                    pass
        return comments

    def add_comment(
        self,
        task_id: str,
        text: str,
        notify_all: bool = False,
    ) -> bool:
        """Add a comment to a task."""
        data = {
            "comment_text": text,
            "notify_all": notify_all,
        }

        result = self._api_request("POST", f"/task/{task_id}/comment", data)
        return result is not None and "id" in result

    # =========================================================================
    # Lists & Spaces
    # =========================================================================

    def get_list(self, list_id: str) -> Optional[ClickUpList]:
        """Get list details."""
        result = self._api_request("GET", f"/list/{list_id}")
        if result and "id" in result:
            return ClickUpList(
                id=result["id"],
                name=result.get("name", ""),
                space_id=result.get("space", {}).get("id", ""),
                folder_id=result.get("folder", {}).get("id"),
                task_count=result.get("task_count", 0),
                statuses=[s.get("status", "") for s in result.get("statuses", [])],
            )
        return None

    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Get all workspaces (teams)."""
        result = self._api_request("GET", "/team")
        if result and "teams" in result:
            return result["teams"]
        return []

    def get_spaces(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Get all spaces in a workspace."""
        result = self._api_request("GET", f"/team/{workspace_id}/space")
        if result and "spaces" in result:
            return result["spaces"]
        return []

    def get_folders(self, space_id: str) -> List[Dict[str, Any]]:
        """Get all folders in a space."""
        result = self._api_request("GET", f"/space/{space_id}/folder")
        if result and "folders" in result:
            return result["folders"]
        return []

    def get_lists_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """Get all lists in a folder."""
        result = self._api_request("GET", f"/folder/{folder_id}/list")
        if result and "lists" in result:
            return result["lists"]
        return []

    def get_folderless_lists(self, space_id: str) -> List[Dict[str, Any]]:
        """Get folderless lists in a space."""
        result = self._api_request("GET", f"/space/{space_id}/list")
        if result and "lists" in result:
            return result["lists"]
        return []

    # =========================================================================
    # Tags
    # =========================================================================

    def add_tag(self, task_id: str, tag_name: str) -> bool:
        """Add a tag to a task."""
        result = self._api_request("POST", f"/task/{task_id}/tag/{tag_name}", {})
        return result is not None

    def remove_tag(self, task_id: str, tag_name: str) -> bool:
        """Remove a tag from a task."""
        result = self._api_request("DELETE", f"/task/{task_id}/tag/{tag_name}")
        return result is not None

    # =========================================================================
    # Connection Test
    # =========================================================================

    def test_connection(self) -> bool:
        """Test the ClickUp connection."""
        result = self._api_request("GET", "/user")
        return result is not None and "user" in result

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get the current authenticated user."""
        result = self._api_request("GET", "/user")
        return result.get("user") if result else None


# Global instance
_client: Optional[ClickUpClient] = None


def get_clickup_client() -> ClickUpClient:
    """Get the global ClickUp client."""
    global _client
    if _client is None:
        _client = ClickUpClient()
    return _client
