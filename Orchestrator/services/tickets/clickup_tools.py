"""
Enhanced ClickUp Tools

Provides dynamic workspace/space/list selection and creation capabilities.
"""

import os
import requests
from typing import Dict, Any, List, Optional


def get_api_token() -> Optional[str]:
    """Get ClickUp API token from environment."""
    return os.getenv("CLICKUP_API_TOKEN")


def clickup_api_request(method: str, endpoint: str, data: dict = None) -> Dict[str, Any]:
    """Make a ClickUp API request."""
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    url = f"https://api.clickup.com/api/v2{endpoint}"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == "PUT":
            resp = requests.put(url, headers=headers, json=data, timeout=30)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def clickup_browse_workspace() -> Dict[str, Any]:
    """
    Browse the ClickUp workspace structure.
    Shows all spaces, folders, and lists with their IDs and task counts.
    Use this to find the right list_id before creating tasks.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    # Get workspaces (teams)
    teams_resp = clickup_api_request("GET", "/team")
    if "error" in teams_resp:
        return teams_resp
    
    result = {
        "help": "Use list_id when creating tasks. Use space_id when creating lists.",
        "workspaces": []
    }
    
    for team in teams_resp.get("teams", []):
        workspace = {
            "id": team["id"],
            "name": team["name"],
            "spaces": []
        }
        
        # Get spaces in this workspace
        spaces_resp = clickup_api_request("GET", f"/team/{team['id']}/space")
        if "error" not in spaces_resp:
            for space in spaces_resp.get("spaces", []):
                space_data = {
                    "id": space["id"],
                    "name": space["name"],
                    "lists": [],
                    "folders": []
                }
                
                # Get folderless lists
                lists_resp = clickup_api_request("GET", f"/space/{space['id']}/list")
                if "error" not in lists_resp:
                    for lst in lists_resp.get("lists", []):
                        space_data["lists"].append({
                            "id": lst["id"],
                            "name": lst["name"],
                            "task_count": lst.get("task_count", 0)
                        })
                
                # Get folders and their lists
                folders_resp = clickup_api_request("GET", f"/space/{space['id']}/folder")
                if "error" not in folders_resp:
                    for folder in folders_resp.get("folders", []):
                        folder_data = {
                            "id": folder["id"],
                            "name": folder["name"],
                            "lists": []
                        }
                        for lst in folder.get("lists", []):
                            folder_data["lists"].append({
                                "id": lst["id"],
                                "name": lst["name"],
                                "task_count": lst.get("task_count", 0)
                            })
                        space_data["folders"].append(folder_data)
                
                workspace["spaces"].append(space_data)
        
        result["workspaces"].append(workspace)
    
    return result


def clickup_create_list(
    space_id: str,
    name: str,
    description: str = "",
    folder_id: str = None,
) -> Dict[str, Any]:
    """
    Create a new list in a ClickUp space.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not space_id or not name:
        return {"error": "space_id and name are required"}
    
    data = {"name": name, "content": description}
    
    if folder_id:
        endpoint = f"/folder/{folder_id}/list"
    else:
        endpoint = f"/space/{space_id}/list"
    
    result = clickup_api_request("POST", endpoint, data)
    
    if "error" not in result and "id" in result:
        return {
            "success": True,
            "message": f"Created list '{name}'",
            "list": {
                "id": result["id"],
                "name": result["name"],
                "url": f"https://app.clickup.com/{result['id']}"
            }
        }
    
    return {"error": result.get("err", "Failed to create list")}


def clickup_create_space(
    workspace_id: str,
    name: str,
    color: str = "#7B68EE",
) -> Dict[str, Any]:
    """
    Create a new space in a ClickUp workspace.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not workspace_id or not name:
        return {"error": "workspace_id and name are required"}
    
    data = {
        "name": name,
        "multiple_assignees": True,
        "features": {
            "due_dates": {"enabled": True, "start_date": True, "remap_due_dates": True},
            "time_tracking": {"enabled": True},
            "tags": {"enabled": True},
            "time_estimates": {"enabled": True},
            "checklists": {"enabled": True},
            "custom_fields": {"enabled": True},
        }
    }
    if color:
        data["color"] = color
    
    result = clickup_api_request("POST", f"/team/{workspace_id}/space", data)
    
    if "error" not in result and "id" in result:
        return {
            "success": True,
            "message": f"Created space '{name}'",
            "space": {"id": result["id"], "name": result["name"]},
            "next_step": f"Now create a list using clickup_create_list with space_id={result['id']}"
        }
    
    return {"error": result.get("err", "Failed to create space")}


def clickup_create_folder(space_id: str, name: str) -> Dict[str, Any]:
    """Create a new folder in a ClickUp space."""
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not space_id or not name:
        return {"error": "space_id and name are required"}
    
    result = clickup_api_request("POST", f"/space/{space_id}/folder", {"name": name})
    
    if "error" not in result and "id" in result:
        return {
            "success": True,
            "message": f"Created folder '{name}'",
            "folder": {"id": result["id"], "name": result["name"]},
            "next_step": f"Now create a list using clickup_create_list with folder_id={result['id']}"
        }
    
    return {"error": result.get("err", "Failed to create folder")}


def clickup_get_statuses(list_id: str) -> Dict[str, Any]:
    """Get available statuses for a ClickUp list."""
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    result = clickup_api_request("GET", f"/list/{list_id}")
    
    if "error" not in result and "statuses" in result:
        return {
            "list_id": list_id,
            "list_name": result.get("name", ""),
            "statuses": [{"name": s["status"], "color": s.get("color", "")} for s in result["statuses"]]
        }
    
    return {"error": "Could not get list statuses"}


# Tool definitions for registration
CLICKUP_ENHANCED_TOOLS = [
    {
        "name": "clickup_browse_workspace",
        "description": "Browse ClickUp workspace structure. Shows all spaces, folders, and lists with IDs and task counts. Use this FIRST to find the right list_id before creating tasks.",
        "function": clickup_browse_workspace,
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "clickup_create_list",
        "description": "Create a new list in a ClickUp space. REQUIRES CONFIRMATION. Use clickup_browse_workspace first to find space_id.",
        "function": clickup_create_list,
        "parameters": {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "Space ID to create list in (required)"},
                "name": {"type": "string", "description": "Name of the new list (required)"},
                "description": {"type": "string", "description": "Optional list description"},
                "folder_id": {"type": "string", "description": "Optional folder ID to create list inside"},
            },
            "required": ["space_id", "name"]
        },
        "requires_confirmation": True
    },
    {
        "name": "clickup_create_space",
        "description": "Create a new space in a ClickUp workspace. REQUIRES CONFIRMATION. Use for new projects/clients.",
        "function": clickup_create_space,
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace (team) ID - use 14298923"},
                "name": {"type": "string", "description": "Name of the new space (required)"},
                "color": {"type": "string", "description": "Hex color code (default: #7B68EE)"},
            },
            "required": ["workspace_id", "name"]
        },
        "requires_confirmation": True
    },
    {
        "name": "clickup_create_folder",
        "description": "Create a new folder in a ClickUp space. Folders organize lists within a space.",
        "function": clickup_create_folder,
        "parameters": {
            "type": "object",
            "properties": {
                "space_id": {"type": "string", "description": "Space ID to create folder in (required)"},
                "name": {"type": "string", "description": "Name of the new folder (required)"},
            },
            "required": ["space_id", "name"]
        },
        "requires_confirmation": True
    },
    {
        "name": "clickup_get_statuses",
        "description": "Get available statuses for a ClickUp list. Shows what statuses can be used for tasks.",
        "function": clickup_get_statuses,
        "parameters": {
            "type": "object",
            "properties": {
                "list_id": {"type": "string", "description": "List ID to get statuses for"},
            },
            "required": ["list_id"]
        }
    },
]
