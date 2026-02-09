"""
Asana API Client

Lightweight wrapper around the Asana REST API.
Provides typed interfaces for reading tasks from Asana projects.

Required env vars:
- ASANA_PERSONAL_ACCESS_TOKEN
"""

import os
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


@dataclass
class AsanaTask:
    """Represents an Asana task."""
    gid: str
    name: str
    notes: str
    assignee_name: Optional[str]
    due_date: Optional[str]
    status: str  # "incomplete" or "completed"
    url: str
    section_name: Optional[str]
    project_gid: Optional[str]


class AsanaClient:
    """Asana API client."""

    API_BASE = "https://app.asana.com/api/1.0"

    def __init__(self, token: str = None):
        self.token = token or os.getenv("ASANA_PERSONAL_ACCESS_TOKEN")

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    def _api_request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
    ) -> Dict[str, Any]:
        """Make an Asana API request."""
        if not self.is_configured:
            return {"error": "Asana not configured. Set ASANA_PERSONAL_ACCESS_TOKEN."}

        url = f"{self.API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            else:
                return {"error": f"Unsupported method: {method}"}

            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_me(self) -> Dict[str, Any]:
        """Get the current authenticated user."""
        result = self._api_request("GET", "users/me")
        if "error" in result:
            return result
        data = result.get("data", {})
        return {"gid": data.get("gid"), "name": data.get("name"), "email": data.get("email")}

    def get_workspaces(self) -> List[Dict[str, Any]]:
        """Get all workspaces for the authenticated user."""
        result = self._api_request("GET", "workspaces")
        if "error" in result:
            return []
        return result.get("data", [])

    def search_projects(self, name_query: str) -> List[Dict[str, Any]]:
        """Search for projects matching a name across all workspaces."""
        workspaces = self.get_workspaces()
        matches = []

        for ws in workspaces:
            ws_gid = ws.get("gid")
            result = self._api_request(
                "GET",
                f"workspaces/{ws_gid}/projects",
                params={"opt_fields": "name,gid,permalink_url"},
            )
            if "error" not in result:
                for project in result.get("data", []):
                    if name_query.lower() in project.get("name", "").lower():
                        project["workspace_gid"] = ws_gid
                        matches.append(project)

        return matches

    def get_project_tasks(
        self,
        project_gid: str,
        assignee_gid: str = None,
        completed_since: str = None,
        opt_fields: str = "name,assignee,assignee.name,due_on,completed,permalink_url,memberships.section.name,notes",
    ) -> List[Dict[str, Any]]:
        """Get tasks from a project, optionally filtered by assignee."""
        params = {"opt_fields": opt_fields}
        if completed_since:
            params["completed_since"] = completed_since

        result = self._api_request(
            "GET",
            f"projects/{project_gid}/tasks",
            params=params,
        )

        if "error" in result:
            return []

        tasks = result.get("data", [])

        # Filter by assignee if specified
        if assignee_gid:
            tasks = [
                t for t in tasks
                if t.get("assignee") and t["assignee"].get("gid") == assignee_gid
            ]

        return tasks

    def get_project_sections(self, project_gid: str) -> List[Dict[str, Any]]:
        """Get sections in a project."""
        result = self._api_request(
            "GET",
            f"projects/{project_gid}/sections",
            params={"opt_fields": "name,gid"},
        )
        if "error" in result:
            return []
        return result.get("data", [])

    def get_task(self, task_gid: str) -> Optional[AsanaTask]:
        """Get full task details."""
        result = self._api_request(
            "GET",
            f"tasks/{task_gid}",
            params={
                "opt_fields": "name,notes,assignee,assignee.name,due_on,completed,permalink_url,memberships.section.name,memberships.project.gid"
            },
        )
        if "error" in result:
            return None

        data = result.get("data", {})
        if not data:
            return None

        # Extract section name from memberships
        section_name = None
        project_gid = None
        for membership in data.get("memberships", []):
            section = membership.get("section")
            if section:
                section_name = section.get("name")
            project = membership.get("project")
            if project:
                project_gid = project.get("gid")

        return AsanaTask(
            gid=data.get("gid", ""),
            name=data.get("name", ""),
            notes=data.get("notes", ""),
            assignee_name=data.get("assignee", {}).get("name") if data.get("assignee") else None,
            due_date=data.get("due_on"),
            status="completed" if data.get("completed") else "incomplete",
            url=data.get("permalink_url", ""),
            section_name=section_name,
            project_gid=project_gid,
        )

    def parse_task(self, task_data: Dict[str, Any]) -> AsanaTask:
        """Parse raw task dict into AsanaTask dataclass."""
        section_name = None
        project_gid = None
        for membership in task_data.get("memberships", []):
            section = membership.get("section")
            if section:
                section_name = section.get("name")
            project = membership.get("project")
            if project:
                project_gid = project.get("gid")

        return AsanaTask(
            gid=task_data.get("gid", ""),
            name=task_data.get("name", ""),
            notes=task_data.get("notes", ""),
            assignee_name=task_data.get("assignee", {}).get("name") if task_data.get("assignee") else None,
            due_date=task_data.get("due_on"),
            status="completed" if task_data.get("completed") else "incomplete",
            url=task_data.get("permalink_url", ""),
            section_name=section_name,
            project_gid=project_gid,
        )


# Global instance
_client: Optional[AsanaClient] = None


def get_asana_client() -> AsanaClient:
    """Get the global Asana client."""
    global _client
    if _client is None:
        _client = AsanaClient()
    return _client
