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


def clickup_verify_tasks(list_id: str, expected_tasks: List[str] = None) -> Dict[str, Any]:
    """
    Verify tasks exist in a ClickUp list.
    
    Args:
        list_id: The list to check
        expected_tasks: Optional list of task names to verify
    
    Returns verification report with found/missing tasks.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    # Get list info
    list_resp = clickup_api_request("GET", f"/list/{list_id}")
    list_name = list_resp.get("name", "Unknown") if "error" not in list_resp else "Unknown"
    
    # Get all tasks in the list
    tasks_resp = clickup_api_request("GET", f"/list/{list_id}/task?include_closed=false")
    if "error" in tasks_resp:
        return tasks_resp
    
    tasks = tasks_resp.get("tasks", [])
    task_names = [t.get("name", "") for t in tasks]
    
    result = {
        "list_id": list_id,
        "list_name": list_name,
        "total_tasks": len(tasks),
        "tasks": [
            {"id": t["id"], "name": t.get("name", ""), "status": t.get("status", {}).get("status", "")}
            for t in tasks[:30]  # Limit to 30 for readability
        ]
    }
    
    # If expected tasks provided, check which are missing
    if expected_tasks:
        found = []
        missing = []
        for expected in expected_tasks:
            # Fuzzy match - check if expected task name is contained in any actual task
            matched = any(expected.lower() in name.lower() for name in task_names)
            if matched:
                found.append(expected)
            else:
                missing.append(expected)
        
        result["verification"] = {
            "expected": len(expected_tasks),
            "found": len(found),
            "missing": len(missing),
            "found_tasks": found,
            "missing_tasks": missing,
            "match_rate": f"{len(found)}/{len(expected_tasks)} ({100*len(found)//len(expected_tasks) if expected_tasks else 0}%)"
        }
    
    return result


# Add to the tools list
CLICKUP_ENHANCED_TOOLS.append({
    "name": "clickup_verify_tasks",
    "description": "Verify tasks exist in a ClickUp list. Can check if specific expected tasks are present.",
    "function": clickup_verify_tasks,
    "parameters": {
        "type": "object",
        "properties": {
            "list_id": {"type": "string", "description": "List ID to verify tasks in (required)"},
            "expected_tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of task names to check for"
            },
        },
        "required": ["list_id"]
    }
})


def clickup_create_subtask(
    parent_task_id: str,
    name: str,
    description: str = "",
    priority: int = 3,
) -> Dict[str, Any]:
    """
    Create a subtask under a parent task.
    
    Args:
        parent_task_id: ID of the parent task (required)
        name: Name of the subtask (required)
        description: Optional description
        priority: 1=Urgent, 2=High, 3=Normal, 4=Low
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not parent_task_id or not name:
        return {"error": "parent_task_id and name are required"}
    
    # First get the parent task to find its list_id
    parent_resp = clickup_api_request("GET", f"/task/{parent_task_id}")
    if "error" in parent_resp:
        return {"error": f"Could not find parent task: {parent_resp.get('error')}"}
    
    list_id = parent_resp.get("list", {}).get("id")
    if not list_id:
        return {"error": "Could not determine list_id from parent task"}
    
    # Create the subtask
    data = {
        "name": name,
        "markdown_description": description,
        "priority": priority,
        "parent": parent_task_id,  # This makes it a subtask
    }
    
    result = clickup_api_request("POST", f"/list/{list_id}/task", data)
    
    if "error" not in result and "id" in result:
        return {
            "success": True,
            "subtask": {
                "id": result["id"],
                "name": result["name"],
                "url": result.get("url", f"https://app.clickup.com/t/{result['id']}"),
                "parent_id": parent_task_id,
            },
            "message": f"Created subtask '{name}' under parent task"
        }
    
    return {"error": result.get("err", "Failed to create subtask")}


def clickup_list_subtasks(task_id: str) -> Dict[str, Any]:
    """
    List all subtasks of a parent task.
    
    Args:
        task_id: ID of the parent task
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    # Get the task with subtasks
    result = clickup_api_request("GET", f"/task/{task_id}?include_subtasks=true")
    
    if "error" in result:
        return result
    
    subtasks = result.get("subtasks", [])
    
    return {
        "parent_task": {
            "id": result.get("id"),
            "name": result.get("name"),
        },
        "subtask_count": len(subtasks),
        "subtasks": [
            {
                "id": st.get("id"),
                "name": st.get("name"),
                "status": st.get("status", {}).get("status", ""),
                "url": st.get("url", f"https://app.clickup.com/t/{st.get('id')}")
            }
            for st in subtasks
        ]
    }


def clickup_get_task_with_subtasks(task_id: str) -> Dict[str, Any]:
    """
    Get full task details including all subtasks.
    Use this to see the complete task hierarchy.
    
    Args:
        task_id: ID of the task to get
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    result = clickup_api_request("GET", f"/task/{task_id}?include_subtasks=true")
    
    if "error" in result:
        return result
    
    subtasks = result.get("subtasks", [])
    
    return {
        "task": {
            "id": result.get("id"),
            "name": result.get("name"),
            "description": result.get("description", "")[:500],
            "status": result.get("status", {}).get("status", ""),
            "priority": result.get("priority", {}).get("priority", "none") if result.get("priority") else "none",
            "url": result.get("url"),
            "list": result.get("list", {}).get("name", ""),
            "list_id": result.get("list", {}).get("id", ""),
        },
        "has_subtasks": len(subtasks) > 0,
        "subtask_count": len(subtasks),
        "subtasks": [
            {
                "id": st.get("id"),
                "name": st.get("name"),
                "status": st.get("status", {}).get("status", ""),
            }
            for st in subtasks
        ]
    }


# Add subtask tools to the list
CLICKUP_ENHANCED_TOOLS.extend([
    {
        "name": "clickup_create_subtask",
        "description": "Create a subtask under a parent task. Use for breaking down large tasks into smaller pieces.",
        "function": clickup_create_subtask,
        "parameters": {
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "string", "description": "ID of the parent task (required)"},
                "name": {"type": "string", "description": "Name of the subtask (required)"},
                "description": {"type": "string", "description": "Optional description"},
                "priority": {"type": "integer", "description": "1=Urgent, 2=High, 3=Normal, 4=Low (default: 3)"},
            },
            "required": ["parent_task_id", "name"]
        }
    },
    {
        "name": "clickup_list_subtasks",
        "description": "List all subtasks of a parent task. Shows subtask names, statuses, and IDs.",
        "function": clickup_list_subtasks,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the parent task"},
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "clickup_get_task_with_subtasks",
        "description": "Get full task details including all subtasks. Use to see complete task hierarchy.",
        "function": clickup_get_task_with_subtasks,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to get"},
            },
            "required": ["task_id"]
        }
    },
])


def clickup_create_tasks_batch(
    list_id: str,
    tasks: List[Dict[str, Any]],
    verify: bool = True,
) -> Dict[str, Any]:
    """
    Create multiple ClickUp tasks at once with automatic verification.
    
    Args:
        list_id: List ID to create tasks in (required)
        tasks: List of task objects with 'name' (required), 'description', 'priority', 'tags'
        verify: Auto-verify after creation (default: True)
    
    Returns summary with all created task IDs (never truncated).
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not list_id or not tasks:
        return {"error": "list_id and tasks are required"}
    
    created = []
    failed = []
    
    for i, task_data in enumerate(tasks):
        name = task_data.get("name")
        if not name:
            failed.append({"index": i, "reason": "Missing task name"})
            continue
        
        # Create the task
        data = {
            "name": name,
            "markdown_description": task_data.get("description", ""),
            "priority": task_data.get("priority", 3),
        }
        
        if task_data.get("tags"):
            data["tags"] = task_data["tags"]
        
        result = clickup_api_request("POST", f"/list/{list_id}/task", data)
        
        if "error" not in result and "id" in result:
            created.append({
                "name": name,
                "id": result["id"],
                "url": result.get("url", f"https://app.clickup.com/t/{result['id']}")
            })
        else:
            failed.append({
                "name": name,
                "reason": result.get("err", result.get("error", "Unknown error"))
            })
    
    result = {
        "success": len(created) > 0,
        "total_attempted": len(tasks),
        "created_count": len(created),
        "failed_count": len(failed),
        "list_id": list_id,
        "created_tasks": created,  # ALWAYS include all IDs, never truncated
    }
    
    if failed:
        result["failed_tasks"] = failed
    
    # Auto-verify if requested
    if verify and created:
        task_names = [t["name"] for t in created]
        verification = clickup_verify_tasks(list_id, task_names)
        result["verification"] = verification.get("verification", {})
    
    return result


# Add to tools list
CLICKUP_ENHANCED_TOOLS.append({
    "name": "clickup_create_tasks_batch",
    "description": "Create multiple ClickUp tasks at once with automatic verification. Returns ALL task IDs (never truncated). Use for bulk task creation.",
    "function": clickup_create_tasks_batch,
    "parameters": {
        "type": "object",
        "properties": {
            "list_id": {"type": "string", "description": "List ID to create tasks in (required)"},
            "tasks": {
                "type": "array",
                "description": "Array of task objects",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Task name (required)"},
                        "description": {"type": "string", "description": "Task description"},
                        "priority": {"type": "integer", "description": "1=Urgent, 2=High, 3=Normal, 4=Low"},
                        "tags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["name"]
                }
            },
            "verify": {"type": "boolean", "description": "Auto-verify after creation (default: true)"}
        },
        "required": ["list_id", "tasks"]
    }
})
