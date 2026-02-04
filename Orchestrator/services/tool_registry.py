"""
Unified Tool Registry

Single source of truth for all tools in Agent007.
Provides tools for both CrewAI agents and the Chat API.

Usage:
    from services.tool_registry import get_all_tools, execute_tool, TOOL_DEFINITIONS
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from functools import wraps

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ============================================================================
# Tool Registry
# ============================================================================

class ToolRegistry:
    """Central registry for all tools."""
    
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._load_tools()
    
    def _load_tools(self):
        """Load all tool implementations."""
        # Gmail
        self._register_gmail_tools()
        # Calendar
        self._register_calendar_tools()
        # Harvest
        self._register_harvest_tools()
        # Slack
        self._register_slack_tools()
        # ClickUp
        self._register_clickup_tools()
        # Zendesk
        self._register_zendesk_tools()
        # Memory
        self._register_memory_tools()
        # Google Sheets
        self._register_sheets_tools()
        # Google Docs/Drive
        self._register_docs_tools()
        # Notification Hub (Notion, Slack, Airtable)
        self._register_notification_tools()
        # Agents
        self._register_agent_tools()
        # Airtable
        self._register_airtable_tools()
        # Notion (via email)
        self._register_notion_tools()
    
    def register(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Dict[str, Any],
        category: str = "general",
    ):
        """Register a tool."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "func": func,
            "parameters": parameters,
            "category": category,
        }
    
    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name."""
        if name not in self._tools:
            return {"error": f"Unknown tool: {name}"}
        
        try:
            return self._tools[name]["func"](**arguments)
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}
    
    def get_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for Claude API."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in self._tools.values()
        ]
    
    def get_tools_by_category(self, category: str) -> List[str]:
        """Get tool names by category."""
        return [
            name for name, tool in self._tools.items()
            if tool["category"] == category
        ]
    
    # =========================================================================
    # Gmail Tools
    # =========================================================================
    
    def _register_gmail_tools(self):
        def gmail_search(query: str, max_results: int = 10) -> Dict[str, Any]:
            """Search Gmail for emails matching the query."""
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                
                token_path = os.path.expanduser("~/.config/agent007/google/token.json")
                if not os.path.exists(token_path):
                    return {"error": "Gmail not connected. Run Google OAuth setup."}
                
                with open(token_path) as f:
                    token_data = json.load(f)
                
                creds = Credentials(
                    token=token_data['token'],
                    refresh_token=token_data.get('refresh_token'),
                    token_uri=token_data.get('token_uri'),
                    client_id=token_data.get('client_id'),
                    client_secret=token_data.get('client_secret')
                )
                
                service = build('gmail', 'v1', credentials=creds)
                results = service.users().messages().list(
                    userId='me', q=query, maxResults=max_results
                ).execute()
                
                messages = results.get('messages', [])
                emails = []
                
                for msg in messages:
                    msg_data = service.users().messages().get(
                        userId='me', id=msg['id'], format='metadata',
                        metadataHeaders=['Subject', 'From', 'Date']
                    ).execute()
                    headers = {h['name']: h['value'] for h in msg_data['payload']['headers']}
                    emails.append({
                        "id": msg['id'],
                        "subject": headers.get('Subject', 'No subject'),
                        "from": headers.get('From', ''),
                        "date": headers.get('Date', ''),
                    })
                
                return {"count": len(emails), "emails": emails}
            
            except Exception as e:
                return {"error": str(e)}
        
        def gmail_get_unread_count() -> Dict[str, Any]:
            """Get count of unread emails."""
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                
                token_path = os.path.expanduser("~/.config/agent007/google/token.json")
                if not os.path.exists(token_path):
                    return {"error": "Gmail not connected"}
                
                with open(token_path) as f:
                    token_data = json.load(f)
                
                creds = Credentials(
                    token=token_data['token'],
                    refresh_token=token_data.get('refresh_token'),
                    token_uri=token_data.get('token_uri'),
                    client_id=token_data.get('client_id'),
                    client_secret=token_data.get('client_secret')
                )
                
                service = build('gmail', 'v1', credentials=creds)
                results = service.users().messages().list(
                    userId='me', q='is:unread', maxResults=1
                ).execute()
                
                return {"unread_count": results.get('resultSizeEstimate', 0)}
            
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "gmail_search",
            "Search Gmail for emails. Use Gmail search syntax: 'from:sender', 'subject:text', 'after:2024/01/01'",
            gmail_search,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query"},
                    "max_results": {"type": "integer", "description": "Max results (default: 10)", "default": 10}
                },
                "required": ["query"]
            },
            category="gmail"
        )
        
        self.register(
            "gmail_get_unread_count",
            "Get the count of unread emails in the inbox.",
            gmail_get_unread_count,
            {"type": "object", "properties": {}},
            category="gmail"
        )
    
    # =========================================================================
    # Calendar Tools
    # =========================================================================
    
    def _register_calendar_tools(self):
        def calendar_get_events(
            days_back: int = 7,
            days_ahead: int = 7,
            query: Optional[str] = None
        ) -> Dict[str, Any]:
            """Get calendar events from Google Calendar."""
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from datetime import timezone
                
                token_path = os.path.expanduser("~/.config/agent007/google/token.json")
                if not os.path.exists(token_path):
                    return {"error": "Google Calendar not connected."}
                
                with open(token_path) as f:
                    token_data = json.load(f)
                
                creds = Credentials(
                    token=token_data['token'],
                    refresh_token=token_data.get('refresh_token'),
                    token_uri=token_data.get('token_uri'),
                    client_id=token_data.get('client_id'),
                    client_secret=token_data.get('client_secret')
                )
                
                service = build('calendar', 'v3', credentials=creds)
                
                now = datetime.now(timezone.utc)
                time_min = (now - timedelta(days=days_back)).isoformat()
                time_max = (now + timedelta(days=days_ahead)).isoformat()
                
                params = {
                    "calendarId": "primary",
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": 50,
                    "singleEvents": True,
                    "orderBy": "startTime"
                }
                
                if query:
                    params["q"] = query
                
                events_result = service.events().list(**params).execute()
                events = events_result.get('items', [])
                
                result_events = []
                for event in events:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    result_events.append({
                        "date": start[:10],
                        "time": start[11:16] if len(start) > 10 else "all-day",
                        "summary": event.get('summary', 'No title'),
                        "location": event.get('location', ''),
                    })
                
                return {"count": len(result_events), "events": result_events}
            
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "calendar_get_events",
            "Get events from Google Calendar. Can search for specific events or get a date range.",
            calendar_get_events,
            {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "Days in the past to include (default: 7)"},
                    "days_ahead": {"type": "integer", "description": "Days in the future to include (default: 7)"},
                    "query": {"type": "string", "description": "Search query to filter events"}
                }
            },
            category="calendar"
        )
    
    # =========================================================================
    # Harvest Tools
    # =========================================================================
    
    def _register_harvest_tools(self):
        # Import from existing implementation
        try:
            from tools.harvest import (
                get_harvest_client,
                get_status as harvest_get_status_impl,
                get_projects as harvest_get_projects_impl,
            )
            
            def harvest_get_time_entries(date: Optional[str] = None) -> Dict[str, Any]:
                """Get time entries for a specific date."""
                client = get_harvest_client()
                if not client:
                    return {"error": "Harvest not configured. Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID."}
                
                import requests
                if date is None:
                    date = datetime.now().strftime("%Y-%m-%d")
                
                headers = {
                    "Authorization": f"Bearer {client.config.access_token}",
                    "Harvest-Account-Id": str(client.config.account_id),
                    "User-Agent": "Agent007 Orchestrator"
                }
                
                response = requests.get(
                    f"https://api.harvestapp.com/v2/time_entries?from={date}&to={date}",
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
                
                entries = []
                total_hours = 0
                for entry in data.get("time_entries", []):
                    entries.append({
                        "id": entry["id"],
                        "project": entry.get("project", {}).get("name", "Unknown"),
                        "task": entry.get("task", {}).get("name", "Unknown"),
                        "hours": entry["hours"],
                        "notes": entry.get("notes", ""),
                        "is_running": entry.get("is_running", False),
                    })
                    total_hours += entry["hours"]
                
                return {"date": date, "total_hours": total_hours, "entries": entries}
            
            def harvest_log_time(
                project_name: str,
                hours: float,
                notes: str = "",
                task_name: Optional[str] = None,
                date: Optional[str] = None,
            ) -> Dict[str, Any]:
                """Log time to Harvest."""
                client = get_harvest_client()
                if not client:
                    return {"error": "Harvest not configured"}
                
                import requests
                headers = {
                    "Authorization": f"Bearer {client.config.access_token}",
                    "Harvest-Account-Id": str(client.config.account_id),
                    "User-Agent": "Agent007 Orchestrator",
                    "Content-Type": "application/json"
                }
                
                # Get user's project assignments
                response = requests.get(
                    "https://api.harvestapp.com/v2/users/me/project_assignments",
                    headers=headers
                )
                response.raise_for_status()
                assignments = response.json().get("project_assignments", [])
                
                # Find matching project
                project_assignment = None
                for a in assignments:
                    if project_name.lower() in a["project"]["name"].lower():
                        project_assignment = a
                        break
                
                if not project_assignment:
                    available = [a["project"]["name"] for a in assignments[:10]]
                    return {"error": f"Project '{project_name}' not found. Available: {available}"}
                
                project = project_assignment["project"]
                task_assignments = project_assignment.get("task_assignments", [])
                
                if not task_assignments:
                    return {"error": f"No tasks found for project {project['name']}"}
                
                task = task_assignments[0]["task"]
                if task_name:
                    for t in task_assignments:
                        if task_name.lower() in t["task"]["name"].lower():
                            task = t["task"]
                            break
                
                spent_date = date or datetime.now().strftime("%Y-%m-%d")
                entry_data = {
                    "project_id": project["id"],
                    "task_id": task["id"],
                    "spent_date": spent_date,
                    "hours": hours,
                    "notes": notes or "Logged via Agent007"
                }
                
                response = requests.post(
                    "https://api.harvestapp.com/v2/time_entries",
                    headers=headers,
                    json=entry_data
                )
                response.raise_for_status()
                
                return {
                    "success": True,
                    "project": project["name"],
                    "task": task["name"],
                    "hours": hours,
                    "date": spent_date
                }
            
            def harvest_list_projects() -> Dict[str, Any]:
                """List available Harvest projects."""
                client = get_harvest_client()
                if not client:
                    return {"error": "Harvest not configured"}
                
                import requests
                headers = {
                    "Authorization": f"Bearer {client.config.access_token}",
                    "Harvest-Account-Id": str(client.config.account_id),
                    "User-Agent": "Agent007 Orchestrator"
                }
                
                response = requests.get(
                    "https://api.harvestapp.com/v2/users/me/project_assignments",
                    headers=headers
                )
                response.raise_for_status()
                assignments = response.json().get("project_assignments", [])
                
                return {
                    "count": len(assignments),
                    "projects": [
                        {"id": a["project"]["id"], "name": a["project"]["name"]}
                        for a in assignments if a.get("is_active", True)
                    ]
                }
            
            self.register(
                "harvest_get_time_entries",
                "Get time entries from Harvest for a specific date. Returns hours logged, projects, and tasks.",
                harvest_get_time_entries,
                {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format. Defaults to today."}
                    }
                },
                category="harvest"
            )
            
            self.register(
                "harvest_log_time",
                "Log time to a Harvest project. Requires project name and hours.",
                harvest_log_time,
                {
                    "type": "object",
                    "properties": {
                        "project_name": {"type": "string", "description": "Name of the project (partial match works)"},
                        "hours": {"type": "number", "description": "Hours to log (e.g., 1.5)"},
                        "notes": {"type": "string", "description": "Description of work done"},
                        "task_name": {"type": "string", "description": "Optional task name"},
                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format"}
                    },
                    "required": ["project_name", "hours"]
                },
                category="harvest"
            )
            
            self.register(
                "harvest_list_projects",
                "List all active Harvest projects you're assigned to.",
                harvest_list_projects,
                {"type": "object", "properties": {}},
                category="harvest"
            )
            
        except ImportError:
            pass  # Harvest tools not available
    
    # =========================================================================
    # Slack Tools
    # =========================================================================
    
    def _register_slack_tools(self):
        def slack_search_messages(query: str, channel: Optional[str] = None) -> Dict[str, Any]:
            """Search Slack messages."""
            try:
                from slack_sdk import WebClient
                
                token = os.getenv("SLACK_BOT_TOKEN")
                if not token:
                    return {"error": "Slack not configured. Set SLACK_BOT_TOKEN."}
                
                client = WebClient(token=token)
                search_query = f"in:{channel} {query}" if channel else query
                response = client.search_messages(query=search_query, count=10)
                
                messages = []
                for match in response.get("messages", {}).get("matches", []):
                    messages.append({
                        "text": match.get("text", "")[:200],
                        "user": match.get("username", ""),
                        "channel": match.get("channel", {}).get("name", ""),
                    })
                
                return {"count": len(messages), "messages": messages}
            
            except Exception as e:
                return {"error": str(e)}
        
        def slack_get_recent_messages(channel: str, limit: int = 10) -> Dict[str, Any]:
            """Get recent messages from a Slack channel."""
            try:
                from slack_sdk import WebClient
                
                token = os.getenv("SLACK_BOT_TOKEN")
                if not token:
                    return {"error": "Slack not configured"}
                
                client = WebClient(token=token)
                if channel.startswith("#"):
                    channel = channel[1:]
                
                channels_response = client.conversations_list(types="public_channel,private_channel")
                channel_id = None
                for ch in channels_response.get("channels", []):
                    if ch["name"] == channel:
                        channel_id = ch["id"]
                        break
                
                if not channel_id:
                    return {"error": f"Channel '{channel}' not found"}
                
                response = client.conversations_history(channel=channel_id, limit=limit)
                
                return {
                    "channel": channel,
                    "messages": [{"text": m.get("text", "")[:200]} for m in response.get("messages", [])]
                }
            
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "slack_search_messages",
            "Search Slack messages across channels.",
            slack_search_messages,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "channel": {"type": "string", "description": "Optional channel name to search in"}
                },
                "required": ["query"]
            },
            category="slack"
        )
        
        self.register(
            "slack_get_recent_messages",
            "Get recent messages from a specific Slack channel.",
            slack_get_recent_messages,
            {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name (with or without #)"},
                    "limit": {"type": "integer", "description": "Number of messages (default: 10)"}
                },
                "required": ["channel"]
            },
            category="slack"
        )
    
    # =========================================================================
    # ClickUp Tools
    # =========================================================================
    
    def _register_clickup_tools(self):
        try:
            from services.tickets.clickup_client import get_clickup_client, ClickUpClient
            
            def clickup_list_tasks(list_id: str = None, include_closed: bool = False) -> Dict[str, Any]:
                """List tasks from ClickUp."""
                api_token = os.getenv("CLICKUP_API_TOKEN")
                if not api_token:
                    return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
                
                client = get_clickup_client()
                
                if not list_id:
                    list_id = os.getenv("CLICKUP_DEFAULT_LIST_ID")
                    if not list_id:
                        workspaces = client.get_workspaces()
                        if workspaces:
                            spaces = client.get_spaces(workspaces[0]["id"])
                            if spaces:
                                lists = client.get_folderless_lists(spaces[0]["id"])
                                if lists:
                                    list_id = lists[0]["id"]
                
                if not list_id:
                    return {"error": "No list_id provided. Set CLICKUP_DEFAULT_LIST_ID or use clickup_list_spaces to find one."}
                
                tasks = client.list_tasks(list_id, include_closed=include_closed)
                
                return {
                    "list_id": list_id,
                    "count": len(tasks),
                    "tasks": [
                        {
                            "id": t.id,
                            "name": t.name,
                            "status": t.status,
                            "priority": t.priority_name,
                            "url": t.url,
                        }
                        for t in tasks[:20]
                    ]
                }
            
            def clickup_create_task(
                name: str,
                description: str = "",
                priority: int = 3,
                list_id: str = None,
                status: str = None,
                tags: List[str] = None,
            ) -> Dict[str, Any]:
                """Create a new task in ClickUp."""
                api_token = os.getenv("CLICKUP_API_TOKEN")
                if not api_token:
                    return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
                
                client = get_clickup_client()
                
                if not list_id:
                    list_id = os.getenv("CLICKUP_DEFAULT_LIST_ID")
                
                if not list_id:
                    return {"error": "No list_id provided. Set CLICKUP_DEFAULT_LIST_ID."}
                
                task = client.create_task(
                    list_id=list_id,
                    name=name,
                    description=description,
                    priority=priority,
                    status=status,
                    tags=tags or [],
                )
                
                if task:
                    return {
                        "success": True,
                        "task": {"id": task.id, "name": task.name, "url": task.url}
                    }
                return {"error": "Failed to create task"}
            
            def clickup_update_task(
                task_id: str,
                name: str = None,
                description: str = None,
                status: str = None,
                priority: int = None,
            ) -> Dict[str, Any]:
                """Update an existing ClickUp task."""
                api_token = os.getenv("CLICKUP_API_TOKEN")
                if not api_token:
                    return {"error": "ClickUp not configured"}
                
                client = get_clickup_client()
                task = client.update_task(task_id, name, description, status, priority)
                
                if task:
                    return {"success": True, "task": {"id": task.id, "name": task.name, "status": task.status}}
                return {"error": "Failed to update task"}
            
            def clickup_get_task(task_id: str) -> Dict[str, Any]:
                """Get details of a specific ClickUp task."""
                api_token = os.getenv("CLICKUP_API_TOKEN")
                if not api_token:
                    return {"error": "ClickUp not configured"}
                
                client = get_clickup_client()
                task = client.get_task(task_id)
                
                if task:
                    return {
                        "task": {
                            "id": task.id,
                            "name": task.name,
                            "description": task.description[:500] if task.description else "",
                            "status": task.status,
                            "priority": task.priority_name,
                            "url": task.url,
                        }
                    }
                return {"error": "Task not found"}
            
            def clickup_add_comment(task_id: str, comment: str) -> Dict[str, Any]:
                """Add a comment to a ClickUp task."""
                api_token = os.getenv("CLICKUP_API_TOKEN")
                if not api_token:
                    return {"error": "ClickUp not configured"}
                
                client = get_clickup_client()
                success = client.add_comment(task_id, comment)
                
                return {"success": success, "task_id": task_id}
            
            def clickup_list_spaces() -> Dict[str, Any]:
                """List ClickUp workspaces, spaces, and lists."""
                api_token = os.getenv("CLICKUP_API_TOKEN")
                if not api_token:
                    return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
                
                client = get_clickup_client()
                workspaces = client.get_workspaces()
                
                result = {"workspaces": []}
                for ws in workspaces[:3]:
                    ws_data = {"id": ws["id"], "name": ws["name"], "spaces": []}
                    
                    spaces = client.get_spaces(ws["id"])
                    for space in spaces[:5]:
                        space_data = {"id": space["id"], "name": space["name"], "lists": []}
                        
                        lists = client.get_folderless_lists(space["id"])
                        for lst in lists[:10]:
                            space_data["lists"].append({"id": lst["id"], "name": lst["name"]})
                        
                        ws_data["spaces"].append(space_data)
                    
                    result["workspaces"].append(ws_data)
                
                return result
            
            self.register(
                "clickup_list_tasks",
                "List tasks from a ClickUp list. Shows open tasks with status and priority.",
                clickup_list_tasks,
                {
                    "type": "object",
                    "properties": {
                        "list_id": {"type": "string", "description": "ClickUp list ID (uses default if not provided)"},
                        "include_closed": {"type": "boolean", "description": "Include closed tasks (default: false)"}
                    }
                },
                category="clickup"
            )
            
            self.register(
                "clickup_create_task",
                "Create a new task in ClickUp. Use for creating tickets, tasks, or to-dos.",
                clickup_create_task,
                {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Task title"},
                        "description": {"type": "string", "description": "Task description (markdown)"},
                        "priority": {"type": "integer", "description": "1=Urgent, 2=High, 3=Normal, 4=Low"},
                        "list_id": {"type": "string", "description": "ClickUp list ID"},
                        "status": {"type": "string", "description": "Task status"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags"}
                    },
                    "required": ["name"]
                },
                category="clickup"
            )
            
            self.register(
                "clickup_update_task",
                "Update an existing ClickUp task (status, priority, name, description).",
                clickup_update_task,
                {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "ClickUp task ID"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "status": {"type": "string"},
                        "priority": {"type": "integer"}
                    },
                    "required": ["task_id"]
                },
                category="clickup"
            )
            
            self.register(
                "clickup_get_task",
                "Get detailed information about a specific ClickUp task.",
                clickup_get_task,
                {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "ClickUp task ID"}
                    },
                    "required": ["task_id"]
                },
                category="clickup"
            )
            
            self.register(
                "clickup_add_comment",
                "Add a comment to a ClickUp task.",
                clickup_add_comment,
                {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "ClickUp task ID"},
                        "comment": {"type": "string", "description": "Comment text"}
                    },
                    "required": ["task_id", "comment"]
                },
                category="clickup"
            )
            
            self.register(
                "clickup_list_spaces",
                "List ClickUp workspaces, spaces, and lists. Use to find list IDs for creating tasks.",
                clickup_list_spaces,
                {"type": "object", "properties": {}},
                category="clickup"
            )
            
        except ImportError:
            pass
    
    # =========================================================================
    # Zendesk Tools
    # =========================================================================
    
    def _register_zendesk_tools(self):
        try:
            from services.tickets.zendesk_client import get_zendesk_client
            
            def zendesk_list_tickets(status: str = None, limit: int = 20) -> Dict[str, Any]:
                """List Zendesk tickets."""
                api_token = os.getenv("ZENDESK_API_TOKEN")
                if not api_token:
                    return {"error": "Zendesk not configured. Set ZENDESK_API_TOKEN."}
                
                client = get_zendesk_client()
                tickets = client.list_tickets(status=status, limit=limit)
                
                return {
                    "count": len(tickets),
                    "tickets": [
                        {
                            "id": t.id,
                            "subject": t.subject,
                            "status": t.status,
                            "priority": t.priority,
                            "requester": t.requester_email,
                        }
                        for t in tickets
                    ]
                }
            
            def zendesk_get_ticket(ticket_id: int) -> Dict[str, Any]:
                """Get details of a Zendesk ticket."""
                client = get_zendesk_client()
                ticket = client.get_ticket(ticket_id)
                
                if ticket:
                    return {
                        "ticket": {
                            "id": ticket.id,
                            "subject": ticket.subject,
                            "status": ticket.status,
                            "priority": ticket.priority,
                            "description": ticket.description[:500],
                            "url": ticket.url,
                        }
                    }
                return {"error": "Ticket not found"}
            
            def zendesk_create_ticket(
                subject: str,
                description: str,
                priority: str = "normal",
            ) -> Dict[str, Any]:
                """Create a new Zendesk ticket."""
                client = get_zendesk_client()
                ticket = client.create_ticket(subject, description, priority)
                
                if ticket:
                    return {"success": True, "ticket_id": ticket.id}
                return {"error": "Failed to create ticket"}
            
            self.register(
                "zendesk_list_tickets",
                "List Zendesk support tickets with optional status filter.",
                zendesk_list_tickets,
                {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Filter: new, open, pending, solved, closed"},
                        "limit": {"type": "integer", "description": "Max tickets to return (default: 20)"}
                    }
                },
                category="zendesk"
            )
            
            self.register(
                "zendesk_get_ticket",
                "Get details of a specific Zendesk ticket.",
                zendesk_get_ticket,
                {
                    "type": "object",
                    "properties": {
                        "ticket_id": {"type": "integer", "description": "Zendesk ticket ID"}
                    },
                    "required": ["ticket_id"]
                },
                category="zendesk"
            )
            
            self.register(
                "zendesk_create_ticket",
                "Create a new Zendesk support ticket.",
                zendesk_create_ticket,
                {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "Ticket subject"},
                        "description": {"type": "string", "description": "Ticket description"},
                        "priority": {"type": "string", "description": "low, normal, high, urgent"}
                    },
                    "required": ["subject", "description"]
                },
                category="zendesk"
            )
            
        except ImportError:
            pass
    
    # =========================================================================
    # Memory Tools
    # =========================================================================
    
    def _register_memory_tools(self):
        def memory_remember(category: str, key: str, value: str) -> Dict[str, Any]:
            """Store a fact or context in memory."""
            try:
                from services.memory import get_memory_service
                memory = get_memory_service()
                entry_id = memory.add_context(category, key, value, source="assistant")
                return {"success": True, "id": entry_id, "message": f"Remembered: {category}/{key}"}
            except Exception as e:
                return {"error": str(e)}
        
        def memory_recall(query: str) -> Dict[str, Any]:
            """Search memory for relevant context."""
            try:
                from services.memory import get_memory_service
                memory = get_memory_service()
                results = memory.search_context(query, limit=5)
                return {
                    "count": len(results),
                    "results": [
                        {"category": r.category, "key": r.key, "value": r.content}
                        for r in results
                    ]
                }
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "memory_remember",
            "Store a fact, preference, or context for future reference.",
            memory_remember,
            {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category: project, preference, fact, person, workflow"},
                    "key": {"type": "string", "description": "Unique identifier"},
                    "value": {"type": "string", "description": "Information to remember"}
                },
                "required": ["category", "key", "value"]
            },
            category="memory"
        )
        
        self.register(
            "memory_recall",
            "Search memory for relevant stored information.",
            memory_recall,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            },
            category="memory"
        )
    
    # =========================================================================
    # Google Sheets Tools
    # =========================================================================
    
    def _register_sheets_tools(self):
        def _check_google_auth():
            """Check if Google auth is available."""
            try:
                from services.google_auth import get_google_auth
                auth = get_google_auth()
                # Just check if authenticated, don't force auth
                if not auth.is_authenticated:
                    return "Google Drive not authenticated. Token may be expired."
                return None  # No error
            except Exception as e:
                return f"Google authentication error: {e}"
        
        def sheets_get_info(spreadsheet_id: str) -> Dict[str, Any]:
            """Get spreadsheet metadata and list of sheets."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.sheets import get_sheets_client
                client = get_sheets_client()
                
                if not client.is_available:
                    return {"error": "Google Sheets not configured. Install google-api-python-client."}
                
                client.authenticate(headless=True)
                info = client.get_spreadsheet(spreadsheet_id)
                
                return {
                    "title": info.title,
                    "id": info.id,
                    "url": info.url,
                    "sheets": [
                        {"title": s.title, "rows": s.row_count, "columns": s.column_count}
                        for s in info.sheets
                    ]
                }
            except Exception as e:
                return {"error": str(e)}
        
        def sheets_read_range(spreadsheet_id: str, range_notation: str) -> Dict[str, Any]:
            """Read values from a spreadsheet range."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.sheets import get_sheets_client
                client = get_sheets_client()
                
                if not client.is_available:
                    return {"error": "Google Sheets not configured"}
                
                client.authenticate(headless=True)
                values = client.get_values(spreadsheet_id, range_notation)
                
                return {
                    "range": range_notation,
                    "rows": len(values),
                    "data": values[:50],  # Limit to 50 rows
                    "truncated": len(values) > 50,
                }
            except Exception as e:
                return {"error": str(e)}
        
        def sheets_update_range(
            spreadsheet_id: str,
            range_notation: str,
            values: List[List[Any]],
        ) -> Dict[str, Any]:
            """Update values in a spreadsheet range."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.sheets import get_sheets_client
                client = get_sheets_client()
                
                if not client.is_available:
                    return {"error": "Google Sheets not configured"}
                
                client.authenticate(headless=True)
                result = client.update_values(spreadsheet_id, range_notation, values)
                
                return {
                    "success": True,
                    "updated_range": result["updated_range"],
                    "updated_cells": result["updated_cells"],
                }
            except Exception as e:
                return {"error": str(e)}
        
        def sheets_append_rows(
            spreadsheet_id: str,
            sheet_name: str,
            rows: List[List[Any]],
        ) -> Dict[str, Any]:
            """Append rows to a spreadsheet."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.sheets import get_sheets_client
                client = get_sheets_client()
                
                if not client.is_available:
                    return {"error": "Google Sheets not configured"}
                
                client.authenticate(headless=True)
                result = client.append_values(spreadsheet_id, f"'{sheet_name}'", rows)
                
                return {
                    "success": True,
                    "rows_added": result["updated_rows"],
                }
            except Exception as e:
                return {"error": str(e)}
        
        def sheets_find_value(
            spreadsheet_id: str,
            sheet_name: str,
            search_value: str,
        ) -> Dict[str, Any]:
            """Find a value in a spreadsheet."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.sheets import get_sheets_client
                client = get_sheets_client()
                
                if not client.is_available:
                    return {"error": "Google Sheets not configured"}
                
                client.authenticate(headless=True)
                result = client.find_value(spreadsheet_id, sheet_name, search_value)
                
                if result:
                    return {
                        "found": True,
                        "row": result["row"],
                        "column": result["column"],
                        "row_data": result["row_data"],
                    }
                return {"found": False, "message": f"Value '{search_value}' not found"}
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "sheets_get_info",
            "Get Google Sheets spreadsheet info including title and list of sheets.",
            sheets_get_info,
            {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID from the URL"}
                },
                "required": ["spreadsheet_id"]
            },
            category="sheets"
        )
        
        self.register(
            "sheets_read_range",
            "Read values from a Google Sheets range using A1 notation (e.g., 'Sheet1!A1:C10').",
            sheets_read_range,
            {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID"},
                    "range_notation": {"type": "string", "description": "A1 notation (e.g., 'Sheet1!A1:C10')"}
                },
                "required": ["spreadsheet_id", "range_notation"]
            },
            category="sheets"
        )
        
        self.register(
            "sheets_update_range",
            "Update values in a Google Sheets range. Use with caution.",
            sheets_update_range,
            {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID"},
                    "range_notation": {"type": "string", "description": "A1 notation"},
                    "values": {"type": "array", "description": "2D array of values", "items": {"type": "array"}}
                },
                "required": ["spreadsheet_id", "range_notation", "values"]
            },
            category="sheets"
        )
        
        self.register(
            "sheets_append_rows",
            "Append rows to a Google Sheets spreadsheet.",
            sheets_append_rows,
            {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID"},
                    "sheet_name": {"type": "string", "description": "Sheet name to append to"},
                    "rows": {"type": "array", "description": "Rows to append", "items": {"type": "array"}}
                },
                "required": ["spreadsheet_id", "sheet_name", "rows"]
            },
            category="sheets"
        )
        
        self.register(
            "sheets_find_value",
            "Search for a value in a Google Sheets spreadsheet.",
            sheets_find_value,
            {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {"type": "string", "description": "Spreadsheet ID"},
                    "sheet_name": {"type": "string", "description": "Sheet name to search"},
                    "search_value": {"type": "string", "description": "Value to find"}
                },
                "required": ["spreadsheet_id", "sheet_name", "search_value"]
            },
            category="sheets"
        )
    
    # =========================================================================
    # Google Docs/Drive Tools
    # =========================================================================
    
    def _register_docs_tools(self):
        def _check_google_auth():
            """Check if Google auth is available."""
            try:
                from services.google_auth import get_google_auth
                auth = get_google_auth()
                # Just check if authenticated, don't force auth
                if not auth.is_authenticated:
                    return "Google Drive not authenticated. Token may be expired."
                return None  # No error
            except Exception as e:
                return f"Google authentication error: {e}"
        
        def docs_list_files(query: str = "") -> Dict[str, Any]:
            """List files in Google Drive."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.drive.client import get_drive_client
                client = get_drive_client()
                
                # New Drive client uses unified auth - no manual auth needed
                files = client.list_files(query=query or None, page_size=20)
                
                return {
                    "count": len(files),
                    "files": [
                        {
                            "id": f.id,
                            "name": f.name,
                            "type": f.mime_type.split('.')[-1] if '.' in f.mime_type else f.mime_type,
                            "modified": f.modified_time,
                        }
                        for f in files
                    ]
                }
            except Exception as e:
                return {"error": str(e)}
        
        def docs_search(search_term: str) -> Dict[str, Any]:
            """Search for files by name in Google Drive."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.drive.client import get_drive_client
                client = get_drive_client()
                
                
                files = client.search_files(search_term, max_results=15)
                
                return {
                    "count": len(files),
                    "files": [
                        {"id": f.id, "name": f.name, "type": f.mime_type.split('.')[-1]}
                        for f in files
                    ]
                }
            except Exception as e:
                return {"error": str(e)}
        
        def docs_read_file(file_id: str) -> Dict[str, Any]:
            """Read text content from a Google Drive file (Docs, text files)."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.drive.client import get_drive_client
                client = get_drive_client()
                
                
                content = client.read_file_content(file_id)
                
                if content is None:
                    return {"error": "Could not read file. It may be binary or inaccessible."}
                
                # Truncate if too long
                truncated = len(content) > 10000
                if truncated:
                    content = content[:10000]
                
                return {
                    "content": content,
                    "length": len(content),
                    "truncated": truncated,
                }
            except Exception as e:
                return {"error": str(e)}
        
        def docs_get_file_info(file_id: str) -> Dict[str, Any]:
            """Get metadata about a Google Drive file."""
            auth_error = _check_google_auth()
            if auth_error:
                return {"error": auth_error}
            
            try:
                from services.drive.client import get_drive_client
                client = get_drive_client()
                
                
                f = client.get_file(file_id)
                
                if not f:
                    return {"error": "File not found"}
                
                return {
                    "name": f.name,
                    "id": f.id,
                    "type": f.mime_type,
                    "size_kb": f.size / 1024 if f.size else 0,
                    "created": f.created_time,
                    "modified": f.modified_time,
                    "shared": f.shared,
                    "link": f.web_view_link,
                }
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "docs_list_files",
            "List files in Google Drive. Optional query using Drive syntax (e.g., \"name contains 'report'\").",
            docs_list_files,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional Drive search query"}
                }
            },
            category="docs"
        )
        
        self.register(
            "docs_search",
            "Search for files by name in Google Drive.",
            docs_search,
            {
                "type": "object",
                "properties": {
                    "search_term": {"type": "string", "description": "Search term to find files"}
                },
                "required": ["search_term"]
            },
            category="docs"
        )
        
        self.register(
            "docs_read_file",
            "Read text content from a Google Doc or text file in Drive.",
            docs_read_file,
            {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "Google Drive file ID"}
                },
                "required": ["file_id"]
            },
            category="docs"
        )
        
        self.register(
            "docs_get_file_info",
            "Get metadata about a Google Drive file (name, size, modified date, etc.).",
            docs_get_file_info,
            {
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "Google Drive file ID"}
                },
                "required": ["file_id"]
            },
            category="docs"
        )
    
    # =========================================================================
    # Agent Tools - Dispatch to CrewAI Agents
    # =========================================================================
    
    def _register_notification_tools(self):
        """Register Notification Hub tools (Notion, Slack, Airtable)."""
        
        def notification_fetch_all(days: int = 7) -> Dict[str, Any]:
            """Fetch all notifications from Notion, Slack emails, and Airtable tickets."""
            try:
                from services.notification_hub import notification_fetch_all as fetch_all
                return fetch_all(days=days)
            except Exception as e:
                return {"error": str(e)}
        
        def notification_search(query: str, days: int = 7) -> Dict[str, Any]:
            """Search notifications across Notion, Slack, and Airtable."""
            try:
                from services.notification_hub import notification_search as search_notifs
                return search_notifs(query=query, days=days)
            except Exception as e:
                return {"error": str(e)}
        
        def notion_get_updates(days: int = 7) -> Dict[str, Any]:
            """Get Notion updates by parsing email notifications (workaround for no API access)."""
            try:
                from services.notification_hub import notion_get_updates as get_notion
                return get_notion(days=days)
            except Exception as e:
                return {"error": str(e)}
        
        def slack_get_updates(days: int = 7) -> Dict[str, Any]:
            """Get Slack updates by parsing email notifications."""
            try:
                from services.notification_hub import slack_get_updates as get_slack
                return get_slack(days=days)
            except Exception as e:
                return {"error": str(e)}
        
        def airtable_get_tickets(status: str = None) -> Dict[str, Any]:
            """Get tickets from Airtable with optional status filter."""
            try:
                from services.notification_hub import airtable_get_tickets as get_tickets
                return get_tickets(status=status)
            except Exception as e:
                return {"error": str(e)}
        
        def airtable_search_ticket(query: str) -> Dict[str, Any]:
            """Search for an Airtable ticket by name."""
            try:
                from services.notification_hub import get_notification_hub
                hub = get_notification_hub()
                ticket = hub.get_ticket_by_name(query)
                if ticket:
                    return {
                        "found": True,
                        "ticket": {
                            "id": ticket.get("id"),
                            "name": ticket.get("fields", {}).get("Ticket Name"),
                            "status": ticket.get("fields", {}).get("Ticket Status"),
                            "priority": ticket.get("fields", {}).get("Priority"),
                            "description": ticket.get("fields", {}).get("Issue Description", "")[:500],
                        }
                    }
                return {"found": False, "query": query}
            except Exception as e:
                return {"error": str(e)}
        
        # Register tools
        self.register(
            "notification_fetch_all",
            "Fetch all notifications from Notion emails, Slack emails, and Airtable tickets. Cross-references notifications with tickets for context.",
            notification_fetch_all,
            {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Days to look back (default: 7)"}
                },
            },
            category="notifications"
        )
        
        self.register(
            "notification_search",
            "Search across all notification sources (Notion, Slack, Airtable) for a specific topic, person, or keyword.",
            notification_search,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "days": {"type": "integer", "description": "Days to look back (default: 7)"}
                },
                "required": ["query"]
            },
            category="notifications"
        )
        
        self.register(
            "notion_get_updates",
            "Get Notion page updates, comments, and mentions by parsing email notifications. Use this since we don't have direct Notion API access.",
            notion_get_updates,
            {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Days to look back (default: 7)"}
                },
            },
            category="notifications"
        )
        
        self.register(
            "slack_get_updates",
            "Get Slack messages, mentions, and DMs by parsing email notifications. Groups by channel.",
            slack_get_updates,
            {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Days to look back (default: 7)"}
                },
            },
            category="notifications"
        )
        
        self.register(
            "airtable_get_tickets",
            "Get Airtable tickets (direct API access). Filter by status like 'In Progress', 'Assigned', etc.",
            airtable_get_tickets,
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (optional)"}
                },
            },
            category="notifications"
        )
        
        self.register(
            "airtable_search_ticket",
            "Search for a specific Airtable ticket by name or partial match.",
            airtable_search_ticket,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Ticket name to search for"}
                },
                "required": ["query"]
            },
            category="notifications"
        )

    def _register_agent_tools(self):
        def run_dev_task(
            task: str,
            context: str = "",
            require_review: bool = True,
        ) -> Dict[str, Any]:
            """Run a development task through the CrewAI dev crew."""
            try:
                from crews.dev_crew import run_dev_task as crew_run_dev_task
                result = crew_run_dev_task(
                    task_description=task,
                    context=context,
                    require_review=require_review,
                )
                return result
            except Exception as e:
                return {"error": str(e)}
        
        def get_agent_status() -> Dict[str, Any]:
            """Get status of available agents and crews."""
            try:
                from agents import (
                    create_manager_agent,
                    create_coder_agent,
                    create_reviewer_agent,
                )
                
                agents = []
                for name, creator in [
                    ("Manager", create_manager_agent),
                    ("Coder", create_coder_agent),
                    ("Reviewer", create_reviewer_agent),
                ]:
                    try:
                        agent = creator()
                        agents.append({
                            "name": name,
                            "role": agent.role,
                            "status": "available"
                        })
                    except Exception as e:
                        agents.append({"name": name, "status": "error", "error": str(e)})
                
                return {"agents": agents}
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "run_dev_task",
            "Run a development task through the AI crew (Manager plans, Coder implements, Reviewer checks). Use for code changes, file operations, or complex tasks.",
            run_dev_task,
            {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "What needs to be done"},
                    "context": {"type": "string", "description": "Additional context (existing code, requirements)"},
                    "require_review": {"type": "boolean", "description": "Run code review after implementation (default: true)"}
                },
                "required": ["task"]
            },
            category="agents"
        )
        
        self.register(
            "get_agent_status",
            "Check status of available AI agents and crews.",
            get_agent_status,
            {"type": "object", "properties": {}},
            category="agents"
        )


    # -------------------------------------------------------------------------
    # Airtable Tools
    # -------------------------------------------------------------------------
    def _register_airtable_tools(self):
        """Register Airtable ticket tools."""
        
        def airtable_list_tickets(status: str = None, limit: int = 20) -> Dict[str, Any]:
            """List Airtable tickets."""
            try:
                from services.airtable import get_airtable_service
                service = get_airtable_service()
                
                if not service.is_configured():
                    return {"error": "Airtable not configured. Set AIRTABLE_PERSONAL_ACCESS_TOKEN."}
                
                if status:
                    tickets = service.get_tickets_by_status(status)
                else:
                    tickets = service.get_active_tickets()
                
                return {
                    "tickets": [t.to_dict() for t in tickets[:limit]],
                    "total": len(tickets),
                }
            except Exception as e:
                return {"error": str(e)}
        
        def airtable_search_tickets(query: str, limit: int = 10) -> Dict[str, Any]:
            """Search Airtable tickets."""
            try:
                from services.airtable import get_airtable_service
                service = get_airtable_service()
                
                if not service.is_configured():
                    return {"error": "Airtable not configured."}
                
                tickets = service.search_tickets(query)
                return {
                    "query": query,
                    "tickets": [t.to_dict() for t in tickets[:limit]],
                    "total": len(tickets),
                }
            except Exception as e:
                return {"error": str(e)}
        
        def airtable_get_ticket(ticket_id: str) -> Dict[str, Any]:
            """Get a specific Airtable ticket."""
            try:
                from services.airtable import get_airtable_service
                service = get_airtable_service()
                
                if not service.is_configured():
                    return {"error": "Airtable not configured."}
                
                # Try as numeric ID first
                ticket = None
                if ticket_id.isdigit():
                    ticket = service.get_ticket_by_id(int(ticket_id))
                
                # Try as record ID
                if not ticket and ticket_id.startswith('rec'):
                    ticket = service.get_ticket_by_record_id(ticket_id)
                
                if ticket:
                    return {"ticket": ticket.to_dict()}
                return {"error": f"Ticket not found: {ticket_id}"}
            except Exception as e:
                return {"error": str(e)}
        
        def airtable_update_ticket(
            ticket_id: str,
            status: str = None,
            comment: str = None
        ) -> Dict[str, Any]:
            """Update an Airtable ticket status and/or add a comment."""
            try:
                from services.airtable import get_airtable_service
                service = get_airtable_service()
                
                if not service.is_configured():
                    return {"error": "Airtable not configured."}
                
                # Get record ID
                record_id = ticket_id
                if ticket_id.isdigit():
                    ticket = service.get_ticket_by_id(int(ticket_id))
                    if ticket:
                        record_id = ticket.record_id
                    else:
                        return {"error": f"Ticket not found: {ticket_id}"}
                
                results = {}
                
                if status:
                    if service.update_status(record_id, status):
                        results["status_updated"] = status
                    else:
                        results["status_error"] = f"Failed to update status to: {status}"
                
                if comment:
                    if service.add_comment(record_id, comment):
                        results["comment_added"] = True
                    else:
                        results["comment_error"] = "Failed to add comment"
                
                return results
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "airtable_list_tickets",
            "List tickets from Airtable. Can filter by status. Returns ticket ID, name, status, priority, and assignees.",
            airtable_list_tickets,
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter by status (e.g., 'In Progress - Small', 'Assigned - Large')"},
                    "limit": {"type": "integer", "description": "Max tickets to return (default: 20)"}
                }
            },
            category="airtable"
        )
        
        self.register(
            "airtable_search_tickets",
            "Search Airtable tickets by name or description.",
            airtable_search_tickets,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results (default: 10)"}
                },
                "required": ["query"]
            },
            category="airtable"
        )
        
        self.register(
            "airtable_get_ticket",
            "Get details of a specific Airtable ticket by ID or record ID.",
            airtable_get_ticket,
            {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Ticket ID (numeric) or record ID (recXXX)"}
                },
                "required": ["ticket_id"]
            },
            category="airtable"
        )
        
        self.register(
            "airtable_update_ticket",
            "Update an Airtable ticket's status and/or add a comment.",
            airtable_update_ticket,
            {
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Ticket ID or record ID"},
                    "status": {"type": "string", "description": "New status"},
                    "comment": {"type": "string", "description": "Comment to add"}
                },
                "required": ["ticket_id"]
            },
            category="airtable"
        )
    
    # -------------------------------------------------------------------------
    # Notion Tools (via Email)
    # -------------------------------------------------------------------------
    def _register_notion_tools(self):
        """Register Notion tools (via Gmail notification parsing)."""
        
        def notion_get_updates(
            days_back: int = 7,
            update_type: str = None,
            limit: int = 20
        ) -> Dict[str, Any]:
            """Get Notion updates from email notifications."""
            try:
                from services.notion_email import get_notion_email_parser
                parser = get_notion_email_parser()
                
                if not parser.is_configured():
                    return {"error": "Gmail not configured for Notion email parsing."}
                
                types = [update_type] if update_type else None
                updates = parser.fetch_notion_updates(
                    days_back=days_back,
                    limit=limit,
                    update_types=types
                )
                
                return {
                    "updates": [u.to_dict() for u in updates],
                    "total": len(updates),
                    "days_back": days_back,
                }
            except Exception as e:
                return {"error": str(e)}
        
        def notion_get_summary(days_back: int = 7) -> Dict[str, Any]:
            """Get a summary of Notion activity from email notifications."""
            try:
                from services.notion_email import get_notion_email_parser
                parser = get_notion_email_parser()
                
                if not parser.is_configured():
                    return {"error": "Gmail not configured for Notion email parsing."}
                
                return parser.get_updates_summary(days_back=days_back)
            except Exception as e:
                return {"error": str(e)}
        
        def notion_search(query: str, days_back: int = 30) -> Dict[str, Any]:
            """Search Notion updates from email notifications."""
            try:
                from services.notion_email import get_notion_email_parser
                parser = get_notion_email_parser()
                
                if not parser.is_configured():
                    return {"error": "Gmail not configured for Notion email parsing."}
                
                updates = parser.search_notion_updates(query, days_back=days_back)
                
                return {
                    "query": query,
                    "updates": [u.to_dict() for u in updates[:20]],
                    "total": len(updates),
                }
            except Exception as e:
                return {"error": str(e)}
        
        self.register(
            "notion_get_updates",
            "Get Notion updates by parsing email notifications. Shows page changes, comments, mentions, and invites. Cross-references with Airtable tickets.",
            notion_get_updates,
            {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "How many days to look back (default: 7)"},
                    "update_type": {"type": "string", "description": "Filter by type: mention, comment, edit, invite, reminder"},
                    "limit": {"type": "integer", "description": "Max updates to return (default: 20)"}
                }
            },
            category="notion"
        )
        
        self.register(
            "notion_get_summary",
            "Get a summary of Notion activity: who's been active, what pages changed, and related Airtable tickets.",
            notion_get_summary,
            {
                "type": "object",
                "properties": {
                    "days_back": {"type": "integer", "description": "How many days to summarize (default: 7)"}
                }
            },
            category="notion"
        )
        
        self.register(
            "notion_search",
            "Search through Notion email notifications for specific topics or pages.",
            notion_search,
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "days_back": {"type": "integer", "description": "How many days to search (default: 30)"}
                },
                "required": ["query"]
            },
            category="notion"
        )


# ============================================================================
# Singleton Instance
# ============================================================================

_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def get_all_tools() -> List[str]:
    """Get names of all registered tools."""
    return list(get_registry()._tools.keys())


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name."""
    return get_registry().execute(name, arguments)


def get_tool_definitions() -> List[Dict[str, Any]]:
    """Get tool definitions for Claude API."""
    return get_registry().get_definitions()


# Alias for backwards compatibility
TOOL_DEFINITIONS = property(lambda self: get_tool_definitions())
