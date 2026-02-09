"""
Asana Tools

Provides tools for reading Asana tasks and syncing them to ClickUp.
Follows the ENHANCED_TOOLS pattern from clickup_tools.py.
"""

import os
from typing import Dict, Any, List, Optional

from .client import get_asana_client


def asana_list_my_tasks(project_name: str = "MLN") -> Dict[str, Any]:
    """
    List Asana tasks assigned to me (or where I'm a follower) in a project.
    Read-only — no confirmation needed.

    Args:
        project_name: Project name to search for (default: "MLN")
    """
    client = get_asana_client()
    if not client.is_configured:
        return {"error": "Asana not configured. Set ASANA_PERSONAL_ACCESS_TOKEN."}

    # Find project by name
    projects = client.search_projects(project_name)
    if not projects:
        return {"error": f"No Asana project found matching '{project_name}'."}

    project = projects[0]
    project_gid = project["gid"]
    project_display = project.get("name", project_name)

    # Get current user
    me = client.get_me()
    if "error" in me:
        return me
    my_gid = me.get("gid")

    # Get tasks assigned to me
    raw_tasks = client.get_project_tasks(project_gid, assignee_gid=my_gid)

    tasks = []
    for t in raw_tasks:
        parsed = client.parse_task(t)
        tasks.append({
            "gid": parsed.gid,
            "name": parsed.name,
            "section": parsed.section_name,
            "due_date": parsed.due_date,
            "status": parsed.status,
            "url": parsed.url,
        })

    return {
        "project": project_display,
        "project_gid": project_gid,
        "assignee": me.get("name"),
        "task_count": len(tasks),
        "tasks": tasks,
    }


def asana_pull_to_clickup(
    project_name: str = "MLN",
    clickup_list_id: str = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Pull Asana tasks into ClickUp with duplicate detection and verification.
    Defaults to dry_run=True (preview only). Set dry_run=False to create tasks.

    Args:
        project_name: Asana project name to search for (default: "MLN")
        clickup_list_id: ClickUp list ID to create tasks in (defaults to CLICKUP_MLN_LIST_ID env var)
        dry_run: If True, preview what would be created without making changes (default: True)
    """
    from services.tickets.sync import SyncResult
    from services.tickets.clickup_client import get_clickup_client
    from services.tickets.clickup_tools import clickup_api_request

    # Resolve ClickUp target list
    target_list_id = clickup_list_id or os.getenv("CLICKUP_MLN_LIST_ID")
    if not target_list_id:
        return {
            "error": "No ClickUp list ID provided. Set CLICKUP_MLN_LIST_ID env var or pass clickup_list_id parameter."
        }

    # Step 1: Find Asana project
    client = get_asana_client()
    if not client.is_configured:
        return {"error": "Asana not configured. Set ASANA_PERSONAL_ACCESS_TOKEN."}

    projects = client.search_projects(project_name)
    if not projects:
        return {"error": f"No Asana project found matching '{project_name}'."}

    project = projects[0]
    project_gid = project["gid"]
    project_display = project.get("name", project_name)

    # Step 2: Get my tasks
    me = client.get_me()
    if "error" in me:
        return me
    my_gid = me.get("gid")

    raw_tasks = client.get_project_tasks(project_gid, assignee_gid=my_gid)
    if not raw_tasks:
        return {
            "project": project_display,
            "message": "No tasks assigned to you in this project.",
            "sync_results": [],
        }

    asana_tasks = [client.parse_task(t) for t in raw_tasks]

    # Step 3: Check for existing tasks in ClickUp (duplicate detection)
    existing_tasks = clickup_api_request("GET", f"list/{target_list_id}/task?include_closed=false")
    existing_names = []
    if "error" not in existing_tasks:
        existing_names = [t.get("name", "") for t in existing_tasks.get("tasks", [])]

    # Build sync results
    sync_results: List[Dict[str, Any]] = []
    to_create: List[Dict[str, Any]] = []

    for task in asana_tasks:
        prefix = f"[ASANA-{task.gid}]"
        already_exists = any(prefix in name for name in existing_names)

        if already_exists:
            sync_results.append({
                "source_id": task.gid,
                "source_name": task.name,
                "action": "skipped",
                "message": f"Already exists in ClickUp (matched {prefix})",
            })
        else:
            description = _build_clickup_description(task)
            clickup_name = f"{prefix} {task.name}"

            sync_results.append({
                "source_id": task.gid,
                "source_name": task.name,
                "action": "preview" if dry_run else "pending",
                "clickup_name": clickup_name,
                "message": "Would create in ClickUp" if dry_run else "Creating...",
            })

            to_create.append({
                "asana_task": task,
                "clickup_name": clickup_name,
                "description": description,
            })

    # Step 4: If dry_run, return preview
    if dry_run:
        return {
            "project": project_display,
            "target_list_id": target_list_id,
            "dry_run": True,
            "total_tasks": len(asana_tasks),
            "would_create": len(to_create),
            "would_skip": len(asana_tasks) - len(to_create),
            "sync_results": sync_results,
            "message": "Dry run complete. Set dry_run=False to create tasks.",
        }

    # Step 5: Create tasks in ClickUp
    clickup_client = get_clickup_client()
    created_results = []

    for item in to_create:
        task = item["asana_task"]
        due_date = None
        if task.due_date:
            from datetime import datetime
            try:
                due_date = datetime.strptime(task.due_date, "%Y-%m-%d")
            except ValueError:
                pass

        created = clickup_client.create_task(
            list_id=target_list_id,
            name=item["clickup_name"],
            description=item["description"],
            priority=3,  # Normal — Asana doesn't have priority
            tags=["from-asana"],
            due_date=due_date,
        )

        if created:
            # Step 6: Verify the created task
            verified = clickup_client.get_task(created.id)

            # Update the sync result for this task
            for sr in sync_results:
                if sr["source_id"] == task.gid and sr["action"] == "pending":
                    sr["action"] = "created"
                    sr["target_id"] = created.id
                    sr["target_url"] = created.url
                    sr["verified"] = verified is not None
                    sr["message"] = f"Created ClickUp task {created.id}"
                    break

            created_results.append({
                "asana_gid": task.gid,
                "clickup_id": created.id,
                "name": item["clickup_name"],
                "url": created.url,
                "verified": verified is not None,
            })
        else:
            for sr in sync_results:
                if sr["source_id"] == task.gid and sr["action"] == "pending":
                    sr["action"] = "error"
                    sr["message"] = "Failed to create ClickUp task"
                    break

    return {
        "project": project_display,
        "target_list_id": target_list_id,
        "dry_run": False,
        "total_tasks": len(asana_tasks),
        "created": len(created_results),
        "skipped": len(asana_tasks) - len(to_create),
        "failed": len(to_create) - len(created_results),
        "sync_results": sync_results,
        "created_tasks": created_results,
    }


def _build_clickup_description(task) -> str:
    """Build a ClickUp task description from an Asana task."""
    parts = [f"**Synced from Asana Task {task.gid}**\n"]

    if task.section_name:
        parts.append(f"**Section:** {task.section_name}")
    if task.assignee_name:
        parts.append(f"**Assignee:** {task.assignee_name}")
    if task.due_date:
        parts.append(f"**Due:** {task.due_date}")
    parts.append(f"**Status:** {task.status}")

    parts.append("\n---\n")

    if task.notes:
        parts.append(task.notes)
    else:
        parts.append("*(No description in Asana)*")

    parts.append("\n---")
    if task.url:
        parts.append(f"[View in Asana]({task.url})")

    return "\n".join(parts)


# Tool definitions for registration
ASANA_ENHANCED_TOOLS = [
    {
        "name": "asana_list_my_tasks",
        "description": "List Asana tasks assigned to me in a project. Read-only. Use to see what tasks exist before syncing.",
        "function": asana_list_my_tasks,
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Project name to search for (default: 'MLN')",
                },
            },
        },
    },
    {
        "name": "asana_pull_to_clickup",
        "description": "Pull Asana tasks into ClickUp. REQUIRES CONFIRMATION. Defaults to dry_run=True (preview only). Detects duplicates via [ASANA-{gid}] prefix. Verifies created tasks.",
        "function": asana_pull_to_clickup,
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Asana project name to search for (default: 'MLN')",
                },
                "clickup_list_id": {
                    "type": "string",
                    "description": "ClickUp list ID to create tasks in (defaults to CLICKUP_MLN_LIST_ID env var)",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, preview what would be created without making changes (default: true)",
                },
            },
        },
        "requires_confirmation": True,
        "danger_level": "medium",
    },
]
