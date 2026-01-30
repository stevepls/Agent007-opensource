#!/usr/bin/env python3
"""
Fetch LCP project tasks from ClickUp to analyze actual work done
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set ClickUp credentials
os.environ["CLICKUP_API_TOKEN"] = "pk_42404240_M4H93V4M2H55U037FEYIFSZSBA6RJIAA"
os.environ["CLICKUP_WORKSPACE_ID"] = "14298923"

import requests

# LCP Space and List IDs
LCP_SPACE_ID = "48528603"
LCP_LIST_ID = "901106405993"
CLICKUP_API_BASE = "https://api.clickup.com/api/v2"

def get_headers():
    return {
        "Authorization": os.environ["CLICKUP_API_TOKEN"],
        "Content-Type": "application/json",
    }

def get_all_lists_in_space(space_id):
    """Get all lists in a space (including from folders)."""
    lists = []
    
    # Get folders first
    folders_resp = requests.get(
        f"{CLICKUP_API_BASE}/space/{space_id}/folder",
        headers=get_headers()
    )
    if folders_resp.ok:
        for folder in folders_resp.json().get("folders", []):
            folder_id = folder["id"]
            folder_name = folder["name"]
            
            # Get lists in this folder
            lists_resp = requests.get(
                f"{CLICKUP_API_BASE}/folder/{folder_id}/list",
                headers=get_headers()
            )
            if lists_resp.ok:
                for lst in lists_resp.json().get("lists", []):
                    lists.append({
                        "id": lst["id"],
                        "name": lst["name"],
                        "folder": folder_name,
                        "task_count": lst.get("task_count", 0)
                    })
    
    # Get folderless lists
    folderless_resp = requests.get(
        f"{CLICKUP_API_BASE}/space/{space_id}/list",
        headers=get_headers()
    )
    if folderless_resp.ok:
        for lst in folderless_resp.json().get("lists", []):
            lists.append({
                "id": lst["id"],
                "name": lst["name"],
                "folder": None,
                "task_count": lst.get("task_count", 0)
            })
    
    return lists

def get_tasks_from_list(list_id, include_closed=True):
    """Get all tasks from a list."""
    tasks = []
    page = 0
    
    while True:
        resp = requests.get(
            f"{CLICKUP_API_BASE}/list/{list_id}/task",
            headers=get_headers(),
            params={
                "include_closed": str(include_closed).lower(),
                "page": page,
                "subtasks": "true",
            }
        )
        
        if not resp.ok:
            print(f"Error fetching tasks: {resp.status_code} {resp.text}")
            break
        
        data = resp.json()
        batch = data.get("tasks", [])
        
        if not batch:
            break
        
        tasks.extend(batch)
        page += 1
        
        # Safety limit
        if page > 20:
            break
    
    return tasks

def format_time(ms):
    """Convert milliseconds to readable time."""
    if not ms:
        return "N/A"
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d")
    except:
        return "N/A"

def get_time_spent(task):
    """Extract time tracked from task."""
    time_spent = task.get("time_spent", 0)
    if time_spent:
        hours = time_spent / (1000 * 60 * 60)
        return f"{hours:.1f}h"
    return "0h"

def main():
    print("=" * 80)
    print("LCP ClickUp Project Analysis")
    print("=" * 80)
    
    # Get all lists in the LCP space
    print(f"\nFetching lists from LCP space ({LCP_SPACE_ID})...")
    lists = get_all_lists_in_space(LCP_SPACE_ID)
    
    print(f"\nFound {len(lists)} lists:")
    for lst in lists:
        folder_info = f" (in {lst['folder']})" if lst['folder'] else " (no folder)"
        print(f"  - {lst['name']}: {lst['task_count']} tasks{folder_info}")
    
    # Collect all tasks
    all_tasks = []
    
    for lst in lists:
        print(f"\nFetching tasks from '{lst['name']}'...")
        tasks = get_tasks_from_list(lst["id"])
        print(f"  Found {len(tasks)} tasks")
        
        for task in tasks:
            task["_list_name"] = lst["name"]
            task["_folder_name"] = lst["folder"]
        
        all_tasks.extend(tasks)
    
    print(f"\n{'=' * 80}")
    print(f"TOTAL TASKS: {len(all_tasks)}")
    print("=" * 80)
    
    # Categorize tasks by status
    status_counts = {}
    for task in all_tasks:
        status = task.get("status", {}).get("status", "Unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\nTask Status Distribution:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {status}: {count}")
    
    # Find completed/closed tasks (actual work done)
    completed_tasks = [t for t in all_tasks if t.get("status", {}).get("status", "").lower() in 
                       ["complete", "closed", "done", "completed", "resolved"]]
    
    print(f"\n{'=' * 80}")
    print(f"COMPLETED TASKS ({len(completed_tasks)} total)")
    print("=" * 80)
    
    # Group by list/category
    tasks_by_list = {}
    for task in completed_tasks:
        list_name = task.get("_list_name", "Unknown")
        if list_name not in tasks_by_list:
            tasks_by_list[list_name] = []
        tasks_by_list[list_name].append(task)
    
    for list_name, tasks in sorted(tasks_by_list.items()):
        print(f"\n### {list_name} ({len(tasks)} tasks)")
        print("-" * 60)
        
        for task in sorted(tasks, key=lambda x: x.get("date_closed", x.get("date_updated", "0")), reverse=True):
            name = task.get("name", "Untitled")
            priority = task.get("priority", {})
            priority_str = f"P{priority.get('id', '?')}" if priority else ""
            time_spent = get_time_spent(task)
            date_closed = format_time(task.get("date_closed") or task.get("date_updated"))
            tags = [t.get("name", "") for t in task.get("tags", [])]
            tags_str = f" [{', '.join(tags)}]" if tags else ""
            
            print(f"  ✓ {name[:60]:<60} {time_spent:>6} {date_closed} {tags_str}")
    
    # Print ALL tasks for full visibility
    print(f"\n{'=' * 80}")
    print(f"ALL TASKS (for comparison with estimate)")
    print("=" * 80)
    
    for list_name, tasks in sorted(tasks_by_list.items()):
        pass  # Already printed above
    
    # All tasks grouped by list
    all_by_list = {}
    for task in all_tasks:
        list_name = task.get("_list_name", "Unknown")
        if list_name not in all_by_list:
            all_by_list[list_name] = []
        all_by_list[list_name].append(task)
    
    print("\n### ALL TASKS BY LIST ###\n")
    for list_name, tasks in sorted(all_by_list.items()):
        print(f"\n=== {list_name} ({len(tasks)} tasks) ===")
        
        for task in tasks:
            name = task.get("name", "Untitled")
            status = task.get("status", {}).get("status", "?")
            time_spent = get_time_spent(task)
            
            status_icon = "✓" if status.lower() in ["complete", "closed", "done", "completed", "resolved"] else "○"
            print(f"  {status_icon} [{status:12}] {name[:55]:<55} {time_spent:>6}")


if __name__ == "__main__":
    main()
