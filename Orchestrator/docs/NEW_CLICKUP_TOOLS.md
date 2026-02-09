# New ClickUp Tools - Reusable Actions

Added 4 new reusable tools to the Orchestrator toolkit (replacing throwaway scripts).

## 📋 New Tools

### 1. `clickup_assign_tasks`
**Purpose:** Assign multiple ClickUp tasks to users

**Parameters:**
- `task_ids` (array, required): List of task IDs to assign
- `assignee_ids` (array, required): List of user IDs to assign tasks to
- `assignee_names` (array, optional): Names for display

**Example:**
```python
clickup_assign_tasks(
    task_ids=["868hcxyeb", "868hcxyf9"],
    assignee_ids=[42404240, 54200842],
    assignee_names=["Steve", "Muhammad"]
)
```

---

### 2. `clickup_find_assignees_by_name`
**Purpose:** Find ClickUp user IDs by name (helper for assignment)

**Parameters:**
- `names` (array, required): List of names to search for

**Example:**
```python
clickup_find_assignees_by_name(["Steve", "Muhammad"])
# Returns: {"user_ids": [42404240, 54200842], "users": [...]}
```

---

### 3. `clickup_get_time_entries`
**Purpose:** Get time tracking entries from ClickUp with flexible filtering

**Parameters:**
- `task_id` (string, optional): Get time for specific task
- `list_id` (string, optional): Get time for all tasks in list
- `space_id` (string, optional): Get time for all tasks in space
- `start_date` (string, optional): Filter by start date (ISO: "2026-01-29")
- `end_date` (string, optional): Filter by end date (ISO: "2026-02-04")
- `project_name` (string, optional): Search for space/list by name (e.g., "Phytto")

**Example:**
```python
clickup_get_time_entries(
    project_name="Phytto",
    start_date="2026-01-29",
    end_date="2026-02-04"
)
# Returns: {"total_hours": 2.75, "breakdown_by_task": {...}}
```

---

### 4. `google_doc_to_clickup_tasks`
**Purpose:** Extract action items from Google Doc and create ClickUp tasks

**Parameters:**
- `google_doc_id` (string, required): Google Doc ID from URL
- `list_id` (string, required): ClickUp list ID to create tasks in
- `assignee_ids` (array, optional): User IDs to assign tasks to
- `assignee_names` (array, optional): Names for display

**Example:**
```python
google_doc_to_clickup_tasks(
    google_doc_id="1z2E19fRqlmnDEI8LUDoAmljSj13Lndl9A6_hYiCFiRo",
    list_id="901106405993",
    assignee_ids=[42404240, 54200842]
)
```

**Note:** Requires Google authentication. Returns confirmation request.

---

## 📍 Location

**File:** `/home/steve/Agent007/Orchestrator/services/tickets/clickup_tools.py`

**Registration:** Tools are automatically registered in `CLICKUP_ENHANCED_TOOLS` list and loaded by `ToolRegistry`.

---

## ✅ Testing

**Test File:** `/home/steve/Agent007/Orchestrator/tests/test_clickup_tools.py`

**Run Tests:**
```bash
cd /home/steve/Agent007/Orchestrator
python3 tests/test_clickup_tools.py
```

---

## 🎯 Usage in Orchestrator

These tools are now available to:
- **CrewAI Agents** - via tool registry
- **Chat API** - via `/api/chat` endpoint
- **Dashboard** - via agent interactions

**Example Chat Request:**
```
"Get time entries for Phytto project from last week"
→ Uses: clickup_get_time_entries(project_name="Phytto", start_date="2026-01-29", end_date="2026-02-04")
```

---

## 📝 Migration from Scripts

**Before (throwaway scripts):**
- `/tmp/clickup_phytto_final.py` → Now: `clickup_get_time_entries`
- `/tmp/assign_clickup_tasks.py` → Now: `clickup_assign_tasks` + `clickup_find_assignees_by_name`
- `/tmp/google_doc_to_clickup_v2.py` → Now: `google_doc_to_clickup_tasks`

**Benefits:**
- ✅ Reusable across all agents
- ✅ Proper error handling
- ✅ Integrated with tool registry
- ✅ Test coverage
- ✅ Type hints and documentation
