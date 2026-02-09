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
    
    url = f"https://api.clickup.com/api/v2/{endpoint}"
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


def clickup_search_tasks(query: str, space_id: str = None, list_id: str = None) -> Dict[str, Any]:
    """
    Search for tasks by name/keyword across the workspace.
    
    Args:
        query: Search term to find in task names (required)
        space_id: Optional - limit search to a specific space
        list_id: Optional - limit search to a specific list
    
    Returns matching tasks with their IDs, names, and URLs.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not query:
        return {"error": "query is required"}
    
    results = []
    query_lower = query.lower()
    
    # Get all teams
    teams = clickup_api_request("GET", "team")
    if "error" in teams:
        return teams
    
    for team in teams.get("teams", []):
        team_id = team["id"]
        
        # If list_id provided, just search that list
        if list_id:
            tasks = clickup_api_request("GET", f"list/{list_id}/task")
            if "tasks" in tasks:
                for task in tasks["tasks"]:
                    if query_lower in task.get("name", "").lower():
                        results.append({
                            "id": task["id"],
                            "name": task["name"],
                            "status": task.get("status", {}).get("status"),
                            "url": task.get("url"),
                            "list": task.get("list", {}).get("name"),
                            "assignees": [a.get("username") for a in task.get("assignees", [])]
                        })
            break
        
        # Get spaces
        spaces = clickup_api_request("GET", f"team/{team_id}/space")
        for space in spaces.get("spaces", []):
            if space_id and space["id"] != space_id:
                continue
            
            # Get folderless lists
            lists = clickup_api_request("GET", f"space/{space['id']}/list")
            for lst in lists.get("lists", []):
                tasks = clickup_api_request("GET", f"list/{lst['id']}/task")
                if "tasks" in tasks:
                    for task in tasks["tasks"]:
                        if query_lower in task.get("name", "").lower():
                            results.append({
                                "id": task["id"],
                                "name": task["name"],
                                "status": task.get("status", {}).get("status"),
                                "url": task.get("url"),
                                "space": space["name"],
                                "list": lst["name"],
                                "assignees": [a.get("username") for a in task.get("assignees", [])]
                            })
    
    return {
        "query": query,
        "count": len(results),
        "tasks": results
    }


def clickup_get_workspace_members() -> Dict[str, Any]:
    """
    Get all workspace members with their user IDs.
    Use this to find assignee IDs for task assignment.
    
    Returns list of members with id, username, email.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    teams = clickup_api_request("GET", "team")
    if "error" in teams:
        return teams
    
    all_members = []
    seen_ids = set()
    
    for team in teams.get("teams", []):
        for member in team.get("members", []):
            user = member.get("user", {})
            user_id = user.get("id")
            if user_id and user_id not in seen_ids:
                seen_ids.add(user_id)
                all_members.append({
                    "id": user_id,
                    "username": user.get("username"),
                    "email": user.get("email"),
                    "initials": user.get("initials"),
                })
    
    return {
        "count": len(all_members),
        "members": all_members
    }


def clickup_find_member_by_name(name: str) -> Dict[str, Any]:
    """
    Find a workspace member by name (partial match).
    Returns matching members with their IDs for task assignment.
    
    Args:
        name: Name or partial name to search for (required)
    """
    if not name:
        return {"error": "name is required"}
    
    members_result = clickup_get_workspace_members()
    if "error" in members_result:
        return members_result
    
    name_lower = name.lower()
    matches = []
    
    for member in members_result.get("members", []):
        username = member.get("username", "") or ""
        email = member.get("email", "") or ""
        
        if name_lower in username.lower() or name_lower in email.lower():
            matches.append(member)
    
    return {
        "query": name,
        "count": len(matches),
        "members": matches
    }


def clickup_create_subtasks_batch(
    parent_task_id: str,
    subtasks: List[str],
    assignee_id: int = None,
) -> Dict[str, Any]:
    """
    Create multiple subtasks under a parent task and optionally assign them all.
    
    Args:
        parent_task_id: The parent task ID (required)
        subtasks: List of subtask names to create (required)
        assignee_id: Optional user ID to assign all subtasks to
    
    Returns created subtasks with their IDs.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not parent_task_id or not subtasks:
        return {"error": "parent_task_id and subtasks are required"}
    
    # Get parent task to find list_id
    parent = clickup_api_request("GET", f"task/{parent_task_id}")
    if "error" in parent:
        return parent
    list_id = parent.get("list", {}).get("id")
    if not list_id:
        return {"error": "Could not determine list_id from parent task"}
    
    created = []
    failed = []
    
    for subtask_name in subtasks:
        data = {
            "name": subtask_name,
            "parent": parent_task_id
        }
        if assignee_id:
            data["assignees"] = [assignee_id]
        
        result = clickup_api_request("POST", f"list/{list_id}/task", data)
        
        if "id" in result:
            created.append({
                "id": result["id"],
                "name": result["name"],
                "url": result.get("url"),
                "assignees": [a.get("username") for a in result.get("assignees", [])]
            })
        else:
            failed.append({"name": subtask_name, "error": result.get("error", "Unknown error")})
    
    return {
        "parent_task_id": parent_task_id,
        "created_count": len(created),
        "failed_count": len(failed),
        "subtasks": created,
        "failed": failed if failed else None
    }


def clickup_add_checklist(
    task_id: str,
    checklist_name: str,
    items: List[str]
) -> Dict[str, Any]:
    """
    Add a checklist with items to a task.
    Note: Checklist items cannot be assigned to users. Use subtasks for assignable items.
    
    Args:
        task_id: The task to add checklist to (required)
        checklist_name: Name of the checklist (required)
        items: List of checklist item names (required)
    
    Returns checklist details with ID.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not task_id or not checklist_name or not items:
        return {"error": "task_id, checklist_name, and items are required"}
    
    # Create checklist
    checklist_result = clickup_api_request("POST", f"task/{task_id}/checklist", {"name": checklist_name})
    
    if "checklist" not in checklist_result:
        return {"error": f"Failed to create checklist: {checklist_result}"}
    
    checklist_id = checklist_result["checklist"]["id"]
    added_items = []
    
    # Add items
    for item_name in items:
        item_result = clickup_api_request("POST", f"checklist/{checklist_id}/checklist_item", {"name": item_name})
        if "checklist" in item_result:
            added_items.append(item_name)
    
    return {
        "success": True,
        "task_id": task_id,
        "checklist_id": checklist_id,
        "checklist_name": checklist_name,
        "items_added": len(added_items),
        "items": added_items,
        "note": "Checklist items cannot be assigned. Use clickup_create_subtasks_batch for assignable items."
    }


def clickup_delete_checklist(checklist_id: str) -> Dict[str, Any]:
    """
    Delete a checklist from a task.
    
    Args:
        checklist_id: The checklist ID to delete (required)
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not checklist_id:
        return {"error": "checklist_id is required"}
    
    # Need to add DELETE support to clickup_api_request
    headers = {"Authorization": token}
    try:
        resp = requests.delete(
            f"https://api.clickup.com/api/v2/checklist/{checklist_id}",
            headers=headers,
            timeout=30
        )
        if resp.status_code == 200:
            return {"success": True, "message": f"Checklist {checklist_id} deleted"}
        return {"error": f"Failed to delete: {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# Register new tools
CLICKUP_ENHANCED_TOOLS.extend([
    {
        "name": "clickup_search_tasks",
        "description": "Search for tasks by name/keyword across the workspace. Returns matching tasks with IDs, status, and URLs.",
        "function": clickup_search_tasks,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term to find in task names (required)"},
                "space_id": {"type": "string", "description": "Optional - limit search to a specific space"},
                "list_id": {"type": "string", "description": "Optional - limit search to a specific list"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "clickup_get_workspace_members",
        "description": "Get all workspace members with their user IDs. Use this to find assignee IDs for task assignment.",
        "function": clickup_get_workspace_members,
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "clickup_find_member_by_name",
        "description": "Find a workspace member by name (partial match). Returns matching members with IDs for task assignment.",
        "function": clickup_find_member_by_name,
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name or partial name to search for (required)"},
            },
            "required": ["name"]
        }
    },
    {
        "name": "clickup_create_subtasks_batch",
        "description": "Create multiple subtasks under a parent task and optionally assign them all to one user. Use instead of checklists when items need assignees.",
        "function": clickup_create_subtasks_batch,
        "parameters": {
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "string", "description": "The parent task ID (required)"},
                "subtasks": {"type": "array", "items": {"type": "string"}, "description": "List of subtask names (required)"},
                "assignee_id": {"type": "integer", "description": "Optional user ID to assign all subtasks to"},
            },
            "required": ["parent_task_id", "subtasks"]
        }
    },
    {
        "name": "clickup_add_checklist",
        "description": "Add a checklist with items to a task. NOTE: Checklist items CANNOT be assigned. Use clickup_create_subtasks_batch for assignable items.",
        "function": clickup_add_checklist,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task to add checklist to (required)"},
                "checklist_name": {"type": "string", "description": "Name of the checklist (required)"},
                "items": {"type": "array", "items": {"type": "string"}, "description": "List of checklist item names (required)"},
            },
            "required": ["task_id", "checklist_name", "items"]
        }
    },
    {
        "name": "clickup_delete_checklist",
        "description": "Delete a checklist from a task.",
        "function": clickup_delete_checklist,
        "parameters": {
            "type": "object",
            "properties": {
                "checklist_id": {"type": "string", "description": "The checklist ID to delete (required)"},
            },
            "required": ["checklist_id"]
        }
    },
])


# ============================================================================
# Task Assignment Tools
# ============================================================================

def clickup_assign_tasks(
    task_ids: List[str],
    assignee_ids: List[int],
    assignee_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Assign multiple tasks to users.
    
    Args:
        task_ids: List of task IDs to assign (required)
        assignee_ids: List of user IDs to assign tasks to (required)
        assignee_names: Optional list of names for display (for better error messages)
    
    Returns summary of assignments.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    if not task_ids or not assignee_ids:
        return {"error": "task_ids and assignee_ids are required"}
    
    assigned = []
    failed = []
    
    for task_id in task_ids:
        try:
            # Get task name for better error reporting
            task_info = clickup_api_request("GET", f"task/{task_id}")
            task_name = task_info.get("name", task_id) if "error" not in task_info else task_id
            
            # Assign users
            result = clickup_api_request("PUT", f"task/{task_id}", {"assignees": assignee_ids})
            
            if "error" not in result:
                assigned.append({
                    "task_id": task_id,
                    "task_name": task_name,
                    "url": result.get("url", f"https://app.clickup.com/t/{task_id}")
                })
            else:
                failed.append({
                    "task_id": task_id,
                    "task_name": task_name,
                    "error": result.get("error", "Unknown error")
                })
        except Exception as e:
            failed.append({
                "task_id": task_id,
                "error": str(e)
            })
    
    return {
        "success": len(assigned) > 0,
        "total_tasks": len(task_ids),
        "assigned_count": len(assigned),
        "failed_count": len(failed),
        "assignees": assignee_names or [f"User {uid}" for uid in assignee_ids],
        "assigned_tasks": assigned,
        "failed_tasks": failed if failed else None
    }


def clickup_find_assignees_by_name(names: List[str]) -> Dict[str, Any]:
    """
    Find ClickUp user IDs by name (for use with clickup_assign_tasks).
    
    Args:
        names: List of names to search for (e.g., ["Steve", "Muhammad"])
    
    Returns user IDs and details.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    teams = clickup_api_request("GET", "team")
    if "error" in teams:
        return teams
    
    found_users = []
    not_found = []
    
    for name in names:
        name_lower = name.lower()
        matched = False
        
        for team in teams.get("teams", []):
            for member in team.get("members", []):
                user = member.get("user", {})
                username = (user.get("username", "") or "").lower()
                email = (user.get("email", "") or "").lower()
                
                if name_lower in username or name_lower in email:
                    found_users.append({
                        "id": user.get("id"),
                        "username": user.get("username"),
                        "email": user.get("email"),
                        "search_name": name
                    })
                    matched = True
                    break
            
            if matched:
                break
        
        if not matched:
            not_found.append(name)
    
    return {
        "found_count": len(found_users),
        "not_found_count": len(not_found),
        "users": found_users,
        "not_found": not_found if not_found else None,
        "user_ids": [u["id"] for u in found_users]
    }


# ============================================================================
# Time Tracking Tools
# ============================================================================

def clickup_get_time_entries(
    task_id: Optional[str] = None,
    list_id: Optional[str] = None,
    space_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    project_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get time tracking entries from ClickUp.
    
    Args:
        task_id: Optional - get time for specific task
        list_id: Optional - get time for all tasks in list
        space_id: Optional - get time for all tasks in space
        start_date: Optional - filter by start date (ISO format: "2026-01-29")
        end_date: Optional - filter by end date (ISO format: "2026-02-04")
        project_name: Optional - search for space/list by name (e.g., "Phytto")
    
    Returns time entries with breakdown by task.
    """
    token = get_api_token()
    if not token:
        return {"error": "ClickUp not configured. Set CLICKUP_API_TOKEN."}
    
    from datetime import datetime
    from collections import defaultdict
    
    # Parse dates if provided
    start_ts = None
    end_ts = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
            start_ts = int(start_dt.timestamp() * 1000)
        except:
            return {"error": f"Invalid start_date format. Use ISO format: YYYY-MM-DD"}
    
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            end_ts = int(end_dt.timestamp() * 1000)
        except:
            return {"error": f"Invalid end_date format. Use ISO format: YYYY-MM-DD"}
    
    # Find tasks to check
    tasks_to_check = []
    
    if task_id:
        # Single task
        task_info = clickup_api_request("GET", f"task/{task_id}")
        if "error" not in task_info:
            tasks_to_check.append({
                "id": task_id,
                "name": task_info.get("name", "Unknown"),
                "list": task_info.get("list", {}).get("name", ""),
                "space": task_info.get("space", {}).get("name", "")
            })
    elif list_id:
        # All tasks in list
        tasks_resp = clickup_api_request("GET", f"list/{list_id}/task?include_closed=true")
        if "error" not in tasks_resp:
            for task in tasks_resp.get("tasks", []):
                tasks_to_check.append({
                    "id": task["id"],
                    "name": task.get("name", "Unknown"),
                    "list": task.get("list", {}).get("name", ""),
                    "space": task.get("space", {}).get("name", "")
                })
    elif space_id:
        # All tasks in space
        lists_resp = clickup_api_request("GET", f"space/{space_id}/list")
        if "error" not in lists_resp:
            for lst in lists_resp.get("lists", []):
                tasks_resp = clickup_api_request("GET", f"list/{lst['id']}/task?include_closed=true")
                if "error" not in tasks_resp:
                    for task in tasks_resp.get("tasks", []):
                        tasks_to_check.append({
                            "id": task["id"],
                            "name": task.get("name", "Unknown"),
                            "list": lst["name"],
                            "space": space_id
                        })
    elif project_name:
        # Search for project by name
        teams = clickup_api_request("GET", "team")
        if "error" in teams:
            return teams
        
        project_name_lower = project_name.lower()
        
        for team in teams.get("teams", []):
            spaces_resp = clickup_api_request("GET", f"team/{team['id']}/space")
            if "error" not in spaces_resp:
                for space in spaces_resp.get("spaces", []):
                    if project_name_lower in space["name"].lower():
                        # Found matching space
                        lists_resp = clickup_api_request("GET", f"space/{space['id']}/list")
                        if "error" not in lists_resp:
                            for lst in lists_resp.get("lists", []):
                                tasks_resp = clickup_api_request("GET", f"list/{lst['id']}/task?include_closed=true")
                                if "error" not in tasks_resp:
                                    for task in tasks_resp.get("tasks", []):
                                        tasks_to_check.append({
                                            "id": task["id"],
                                            "name": task.get("name", "Unknown"),
                                            "list": lst["name"],
                                            "space": space["name"]
                                        })
    
    if not tasks_to_check:
        return {"error": "No tasks found. Provide task_id, list_id, space_id, or project_name."}
    
    # Get time entries for each task
    time_by_task = defaultdict(lambda: {"total_ms": 0, "entries": []})
    total_time_ms = 0
    
    for task_info in tasks_to_check:
        task_id = task_info["id"]
        
        time_resp = clickup_api_request("GET", f"task/{task_id}/time")
        if "error" in time_resp:
            continue
        
        for user_data in time_resp.get("data", []):
            user = user_data.get("user", {})
            username = user.get("username", "Unknown")
            
            for interval in user_data.get("intervals", []):
                start_ts_interval = interval.get("start")
                if not start_ts_interval:
                    continue
                
                start_ts_interval_int = int(start_ts_interval)
                duration_ms = int(interval.get("time", 0))
                
                # Filter by date range if provided
                if start_ts and start_ts_interval_int < start_ts:
                    continue
                if end_ts and start_ts_interval_int > end_ts:
                    continue
                
                start_dt = datetime.fromtimestamp(start_ts_interval_int / 1000)
                duration_hours = duration_ms / 1000 / 3600
                
                time_by_task[task_info["name"]]["total_ms"] += duration_ms
                time_by_task[task_info["name"]]["list"] = task_info.get("list", "")
                time_by_task[task_info["name"]]["space"] = task_info.get("space", "")
                time_by_task[task_info["name"]]["entries"].append({
                    "date": start_dt.strftime("%Y-%m-%d"),
                    "time": start_dt.strftime("%H:%M"),
                    "duration_hours": round(duration_hours, 2),
                    "user": username,
                })
                
                total_time_ms += duration_ms
    
    total_hours = total_time_ms / 1000 / 3600
    
    return {
        "total_hours": round(total_hours, 2),
        "total_entries": sum(len(data["entries"]) for data in time_by_task.values()),
        "tasks_count": len(time_by_task),
        "date_range": {
            "start": start_date,
            "end": end_date
        },
        "breakdown_by_task": {
            task_name: {
                "total_hours": round(data["total_ms"] / 1000 / 3600, 2),
                "entries_count": len(data["entries"]),
                "list": data.get("list", ""),
                "space": data.get("space", ""),
                "entries": data["entries"]
            }
            for task_name, data in time_by_task.items()
        }
    }


# ============================================================================
# Google Doc Integration Tools
# ============================================================================

def google_doc_to_clickup_tasks(
    google_doc_id: str,
    list_id: str,
    assignee_ids: Optional[List[int]] = None,
    assignee_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Extract action items from a Google Doc and create ClickUp tasks.
    
    Args:
        google_doc_id: Google Doc ID from URL (e.g., "1z2E19fRqlmnDEI8LUDoAmljSj13Lndl9A6_hYiCFiRo")
        list_id: ClickUp list ID to create tasks in (required)
        assignee_ids: Optional - user IDs to assign tasks to
        assignee_names: Optional - names for display
    
    Returns summary of created tasks.
    """
    import sys
    from pathlib import Path
    
    # Try to import Google auth
    try:
        SERVICES_ROOT = Path(__file__).parent.parent
        sys.path.insert(0, str(SERVICES_ROOT))
        from google_auth import get_google_auth
        
        auth = get_google_auth()
        if not auth.is_authenticated:
            return {"error": "Not authenticated with Google. Run: python3 -m services.google_auth"}
        
        creds = auth.credentials
        
        # Use Drive API to export document as plain text
        from googleapiclient.discovery import build
        
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Get file metadata
        file_metadata = drive_service.files().get(fileId=google_doc_id, fields='name,mimeType').execute()
        doc_name = file_metadata.get('name', 'Untitled')
        
        # Export as plain text
        request = drive_service.files().export_media(fileId=google_doc_id, mimeType='text/plain')
        doc_text = request.execute().decode('utf-8')
        
        # Parse action items (simple format - each non-empty line is an action item)
        action_items = []
        lines = doc_text.split('\n')
        
        skip_phrases = ['next steps', 'action items', 'action iitems', 'todo list', 'tasks']
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped or len(line_stripped) < 15:
                continue
            
            if any(phrase in line_stripped.lower() for phrase in skip_phrases):
                continue
            
            action_items.append(line_stripped)
        
        # Remove duplicates
        seen = set()
        unique_items = []
        for item in action_items:
            normalized = item.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique_items.append(item)
        
        action_items = unique_items
        
        if not action_items:
            return {"error": "No action items found in document", "doc_name": doc_name, "preview": doc_text[:500]}
        
        # Create ClickUp tasks
        created_tasks = []
        failed_tasks = []
        
        for action_item in action_items:
            task_data = {
                "name": action_item,
                "markdown_description": f"**Source:** [Google Doc - {doc_name}](https://docs.google.com/document/d/{google_doc_id}/edit)\n\nAuto-created from action items list.",
                "priority": 3,
                "tags": ["google-doc", "action-item"]
            }
            
            if assignee_ids:
                task_data["assignees"] = assignee_ids
            
            result = clickup_api_request("POST", f"list/{list_id}/task", task_data)
            
            if "error" not in result and "id" in result:
                created_tasks.append({
                    "name": action_item,
                    "id": result.get("id"),
                    "url": result.get("url", f"https://app.clickup.com/t/{result.get('id')}")
                })
            else:
                failed_tasks.append({
                    "name": action_item,
                    "error": result.get("error", "Unknown error")
                })
        
        return {
            "success": len(created_tasks) > 0,
            "doc_name": doc_name,
            "doc_url": f"https://docs.google.com/document/d/{google_doc_id}/edit",
            "action_items_found": len(action_items),
            "created_count": len(created_tasks),
            "failed_count": len(failed_tasks),
            "assignees": assignee_names or ([f"User {uid}" for uid in assignee_ids] if assignee_ids else None),
            "created_tasks": created_tasks,
            "failed_tasks": failed_tasks if failed_tasks else None
        }
        
    except ImportError:
        return {"error": "Google API libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib"}
    except Exception as e:
        return {"error": f"Error processing Google Doc: {str(e)}"}


# Register new tools
CLICKUP_ENHANCED_TOOLS.extend([
    {
        "name": "clickup_assign_tasks",
        "description": "Assign multiple ClickUp tasks to users. Use clickup_find_assignees_by_name first to get user IDs.",
        "function": clickup_assign_tasks,
        "parameters": {
            "type": "object",
            "properties": {
                "task_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task IDs to assign (required)"
                },
                "assignee_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of user IDs to assign tasks to (required)"
                },
                "assignee_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of names for display"
                }
            },
            "required": ["task_ids", "assignee_ids"]
        }
    },
    {
        "name": "clickup_find_assignees_by_name",
        "description": "Find ClickUp user IDs by name. Use this before clickup_assign_tasks to get user IDs.",
        "function": clickup_find_assignees_by_name,
        "parameters": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of names to search for (e.g., ['Steve', 'Muhammad'])"
                }
            },
            "required": ["names"]
        }
    },
    {
        "name": "clickup_get_time_entries",
        "description": "Get time tracking entries from ClickUp. Can filter by task, list, space, project name, or date range.",
        "function": clickup_get_time_entries,
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Optional - get time for specific task"},
                "list_id": {"type": "string", "description": "Optional - get time for all tasks in list"},
                "space_id": {"type": "string", "description": "Optional - get time for all tasks in space"},
                "start_date": {"type": "string", "description": "Optional - filter by start date (ISO: YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Optional - filter by end date (ISO: YYYY-MM-DD)"},
                "project_name": {"type": "string", "description": "Optional - search for space/list by name (e.g., 'Phytto')"}
            }
        }
    },
    {
        "name": "google_doc_to_clickup_tasks",
        "description": "Extract action items from a Google Doc and create ClickUp tasks. Requires Google authentication.",
        "function": google_doc_to_clickup_tasks,
        "parameters": {
            "type": "object",
            "properties": {
                "google_doc_id": {
                    "type": "string",
                    "description": "Google Doc ID from URL (e.g., '1z2E19fRqlmnDEI8LUDoAmljSj13Lndl9A6_hYiCFiRo')"
                },
                "list_id": {
                    "type": "string",
                    "description": "ClickUp list ID to create tasks in (required)"
                },
                "assignee_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional - user IDs to assign tasks to"
                },
                "assignee_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional - names for display"
                }
            },
            "required": ["google_doc_id", "list_id"]
        },
        "requires_confirmation": True
    },
])
