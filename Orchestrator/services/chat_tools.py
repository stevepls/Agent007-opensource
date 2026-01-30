"""
Chat Tools for Claude

These are the actual tools that Claude can call during conversation.
Each tool has a definition (for Claude) and an implementation function.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

# Ensure .env is loaded
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# ============================================================================
# Gmail Tools
# ============================================================================

def gmail_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Search Gmail for emails matching the query."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        token_path = os.path.expanduser("~/.config/agent007/google/token.json")
        if not os.path.exists(token_path):
            return {"error": "Gmail not connected. Token file not found."}
        
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


# ============================================================================
# Google Calendar Tools
# ============================================================================

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
            return {"error": "Google Calendar not connected. Token file not found."}
        
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
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            duration_mins = None
            if 'dateTime' in event['start'] and 'dateTime' in event['end']:
                start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
                duration_mins = int((end_dt - start_dt).total_seconds() // 60)
            
            result_events.append({
                "date": start[:10],
                "time": start[11:16] if len(start) > 10 else "all-day",
                "summary": event.get('summary', 'No title'),
                "duration_minutes": duration_mins,
                "location": event.get('location', ''),
            })
        
        return {"count": len(result_events), "events": result_events}
    
    except Exception as e:
        error_msg = str(e)
        if "accessNotConfigured" in error_msg:
            return {"error": "Google Calendar API not enabled. Enable at console.developers.google.com"}
        return {"error": error_msg}


# ============================================================================
# Harvest Tools
# ============================================================================

def harvest_get_time_entries(date: Optional[str] = None) -> Dict[str, Any]:
    """Get time entries for a specific date (default: today)."""
    try:
        access_token = os.getenv("HARVEST_ACCESS_TOKEN")
        account_id = os.getenv("HARVEST_ACCOUNT_ID")
        
        if not access_token or not account_id:
            return {"error": "Harvest not configured. Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID."}
        
        import requests
        
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Harvest-Account-Id": account_id,
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
        
        return {
            "date": date,
            "total_hours": total_hours,
            "entry_count": len(entries),
            "entries": entries
        }
    
    except Exception as e:
        return {"error": str(e)}


def harvest_log_time(
    project_name: str,
    hours: float,
    notes: str = "",
    task_name: Optional[str] = None,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """Log time to Harvest."""
    try:
        access_token = os.getenv("HARVEST_ACCESS_TOKEN")
        account_id = os.getenv("HARVEST_ACCOUNT_ID")
        
        if not access_token or not account_id:
            return {"error": "Harvest not configured"}
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Harvest-Account-Id": account_id,
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
        
        # Find matching task or use first one
        task = task_assignments[0]["task"]
        if task_name:
            for t in task_assignments:
                if task_name.lower() in t["task"]["name"].lower():
                    task = t["task"]
                    break
        
        # Create time entry
        spent_date = date or datetime.now().strftime("%Y-%m-%d")
        entry_data = {
            "project_id": project["id"],
            "task_id": task["id"],
            "spent_date": spent_date,
            "hours": hours,
            "notes": notes or f"Logged via Agent007"
        }
        
        response = requests.post(
            "https://api.harvestapp.com/v2/time_entries",
            headers=headers,
            json=entry_data
        )
        response.raise_for_status()
        result = response.json()
        
        return {
            "success": True,
            "entry_id": result["id"],
            "project": project["name"],
            "task": task["name"],
            "hours": hours,
            "notes": notes,
            "date": spent_date
        }
    
    except Exception as e:
        return {"error": str(e)}


def harvest_list_projects() -> Dict[str, Any]:
    """List available Harvest projects (user's assigned projects)."""
    try:
        access_token = os.getenv("HARVEST_ACCESS_TOKEN")
        account_id = os.getenv("HARVEST_ACCOUNT_ID")
        
        if not access_token or not account_id:
            return {"error": "Harvest not configured"}
        
        import requests
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Harvest-Account-Id": account_id,
            "User-Agent": "Agent007 Orchestrator"
        }
        
        # Use project_assignments endpoint which doesn't require admin
        response = requests.get(
            "https://api.harvestapp.com/v2/users/me/project_assignments",
            headers=headers
        )
        response.raise_for_status()
        assignments = response.json().get("project_assignments", [])
        
        return {
            "count": len(assignments),
            "projects": [
                {
                    "id": a["project"]["id"], 
                    "name": a["project"]["name"], 
                    "client": a.get("client", {}).get("name", "") if a.get("client") else ""
                }
                for a in assignments if a.get("is_active", True)
            ]
        }
    
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Slack Tools
# ============================================================================

def slack_search_messages(query: str, channel: Optional[str] = None) -> Dict[str, Any]:
    """Search Slack messages."""
    try:
        from slack_sdk import WebClient
        
        token = os.getenv("SLACK_BOT_TOKEN")
        if not token:
            return {"error": "Slack not configured. Set SLACK_BOT_TOKEN."}
        
        client = WebClient(token=token)
        
        search_query = query
        if channel:
            search_query = f"in:{channel} {query}"
        
        response = client.search_messages(query=search_query, count=10)
        
        messages = []
        for match in response.get("messages", {}).get("matches", []):
            messages.append({
                "text": match.get("text", "")[:200],
                "user": match.get("username", ""),
                "channel": match.get("channel", {}).get("name", ""),
                "timestamp": match.get("ts", ""),
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
        
        # Get channel ID if name provided
        if channel.startswith("#"):
            channel = channel[1:]
        
        # List channels to find ID
        channels_response = client.conversations_list(types="public_channel,private_channel")
        channel_id = None
        for ch in channels_response.get("channels", []):
            if ch["name"] == channel:
                channel_id = ch["id"]
                break
        
        if not channel_id:
            return {"error": f"Channel '{channel}' not found"}
        
        # Get messages
        response = client.conversations_history(channel=channel_id, limit=limit)
        
        messages = []
        for msg in response.get("messages", []):
            messages.append({
                "text": msg.get("text", "")[:200],
                "user": msg.get("user", ""),
                "timestamp": msg.get("ts", ""),
            })
        
        return {"channel": channel, "count": len(messages), "messages": messages}
    
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Tool Definitions (for Claude)
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "gmail_search",
        "description": "Search Gmail for emails. Use this to find emails by sender, subject, or content. Example queries: 'from:notion.so', 'subject:invoice', 'after:2026/01/20'",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query (same syntax as Gmail search box)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "gmail_get_unread_count",
        "description": "Get the count of unread emails in the inbox.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "calendar_get_events",
        "description": "Get events from Google Calendar. Can search for specific events or get a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "Number of days in the past to include (default: 7)"
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days in the future to include (default: 7)"
                },
                "query": {
                    "type": "string",
                    "description": "Optional search query to filter events (e.g., 'forge', 'meeting')"
                }
            }
        }
    },
    {
        "name": "harvest_get_time_entries",
        "description": "Get time entries from Harvest for a specific date. Returns hours logged, projects, and tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Defaults to today if not provided."
                }
            }
        }
    },
    {
        "name": "harvest_log_time",
        "description": "Log time to a Harvest project. Requires project name and hours. Can log to past dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project (partial match works)"
                },
                "hours": {
                    "type": "number",
                    "description": "Hours to log (e.g., 1.5 for 1 hour 30 minutes)"
                },
                "notes": {
                    "type": "string",
                    "description": "Description of work done"
                },
                "task_name": {
                    "type": "string",
                    "description": "Optional task name within the project"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format. Defaults to today if not provided."
                }
            },
            "required": ["project_name", "hours"]
        }
    },
    {
        "name": "harvest_list_projects",
        "description": "List all active Harvest projects. Use this to find project names before logging time.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "slack_search_messages",
        "description": "Search Slack messages across channels.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "channel": {
                    "type": "string",
                    "description": "Optional channel name to search in"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "slack_get_recent_messages",
        "description": "Get recent messages from a specific Slack channel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel name (with or without #)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to fetch (default: 10)"
                }
            },
            "required": ["channel"]
        }
    }
]


# ============================================================================
# Tool Executor
# ============================================================================

def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with the given arguments."""
    tools = {
        "gmail_search": gmail_search,
        "gmail_get_unread_count": gmail_get_unread_count,
        "calendar_get_events": calendar_get_events,
        "harvest_get_time_entries": harvest_get_time_entries,
        "harvest_log_time": harvest_log_time,
        "harvest_list_projects": harvest_list_projects,
        "slack_search_messages": slack_search_messages,
        "slack_get_recent_messages": slack_get_recent_messages,
    }
    
    if name not in tools:
        return {"error": f"Unknown tool: {name}"}
    
    try:
        return tools[name](**arguments)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}
