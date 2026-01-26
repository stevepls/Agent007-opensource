"""
Shared Todo List System

A persistent todo list that both humans and agents can modify.
Stored in JSON file for simplicity and portability.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


# =============================================================================
# Configuration
# =============================================================================

DATA_DIR = Path(os.getenv("DATA_DIR", "/home/steve/Agent007/Orchestrator/data"))
TODO_FILE = DATA_DIR / "todos.json"


class TodoStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TodoPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Todo:
    """A single todo item."""
    id: str
    title: str
    description: str = ""
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = "human"  # "human" or agent name
    assigned_to: Optional[str] = None
    project: Optional[str] = None
    ticket_id: Optional[str] = None
    due_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    notes: List[Dict[str, str]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Todo":
        data["status"] = TodoStatus(data.get("status", "pending"))
        data["priority"] = TodoPriority(data.get("priority", "medium"))
        return cls(**data)
    
    def add_note(self, note: str, author: str = "human"):
        """Add a note to the todo."""
        self.notes.append({
            "timestamp": datetime.utcnow().isoformat(),
            "author": author,
            "note": note,
        })
        self.updated_at = datetime.utcnow().isoformat()


# =============================================================================
# Todo Manager
# =============================================================================

class TodoManager:
    """Manages the shared todo list."""
    
    def __init__(self):
        self.todos: Dict[str, Todo] = {}
        self._load()
    
    def _load(self):
        """Load todos from file."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        if TODO_FILE.exists():
            try:
                with open(TODO_FILE, "r") as f:
                    data = json.load(f)
                self.todos = {
                    id: Todo.from_dict(item)
                    for id, item in data.get("todos", {}).items()
                }
            except Exception as e:
                print(f"Error loading todos: {e}")
                self.todos = {}
        else:
            self.todos = {}
    
    def _save(self):
        """Save todos to file."""
        data = {
            "updated_at": datetime.utcnow().isoformat(),
            "todos": {id: todo.to_dict() for id, todo in self.todos.items()}
        }
        with open(TODO_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def add(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        created_by: str = "human",
        project: Optional[str] = None,
        ticket_id: Optional[str] = None,
        tags: List[str] = None,
    ) -> Todo:
        """Add a new todo."""
        todo = Todo(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            priority=TodoPriority(priority),
            created_by=created_by,
            project=project,
            ticket_id=ticket_id,
            tags=tags or [],
        )
        self.todos[todo.id] = todo
        self._save()
        return todo
    
    def update(
        self,
        todo_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assigned_to: Optional[str] = None,
        due_date: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[Todo]:
        """Update an existing todo."""
        if todo_id not in self.todos:
            return None
        
        todo = self.todos[todo_id]
        
        if title is not None:
            todo.title = title
        if description is not None:
            todo.description = description
        if status is not None:
            todo.status = TodoStatus(status)
        if priority is not None:
            todo.priority = TodoPriority(priority)
        if assigned_to is not None:
            todo.assigned_to = assigned_to
        if due_date is not None:
            todo.due_date = due_date
        if tags is not None:
            todo.tags = tags
        
        todo.updated_at = datetime.utcnow().isoformat()
        self._save()
        return todo
    
    def complete(self, todo_id: str, completed_by: str = "human") -> Optional[Todo]:
        """Mark a todo as complete."""
        todo = self.update(todo_id, status="completed")
        if todo:
            todo.add_note(f"Completed", completed_by)
            self._save()
        return todo
    
    def delete(self, todo_id: str) -> bool:
        """Delete a todo."""
        if todo_id in self.todos:
            del self.todos[todo_id]
            self._save()
            return True
        return False
    
    def get(self, todo_id: str) -> Optional[Todo]:
        """Get a todo by ID."""
        return self.todos.get(todo_id)
    
    def list(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        project: Optional[str] = None,
        assigned_to: Optional[str] = None,
        include_completed: bool = False,
    ) -> List[Todo]:
        """List todos with optional filtering."""
        todos = list(self.todos.values())
        
        if not include_completed:
            todos = [t for t in todos if t.status != TodoStatus.COMPLETED]
        
        if status:
            todos = [t for t in todos if t.status.value == status]
        
        if priority:
            todos = [t for t in todos if t.priority.value == priority]
        
        if project:
            todos = [t for t in todos if t.project and project.lower() in t.project.lower()]
        
        if assigned_to:
            todos = [t for t in todos if t.assigned_to and assigned_to.lower() in t.assigned_to.lower()]
        
        # Sort by priority then created date
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
        todos.sort(key=lambda t: (priority_order.get(t.priority.value, 2), t.created_at))
        
        return todos
    
    def get_summary(self) -> Dict[str, Any]:
        """Get todo summary stats."""
        all_todos = list(self.todos.values())
        
        return {
            "total": len(all_todos),
            "pending": len([t for t in all_todos if t.status == TodoStatus.PENDING]),
            "in_progress": len([t for t in all_todos if t.status == TodoStatus.IN_PROGRESS]),
            "completed": len([t for t in all_todos if t.status == TodoStatus.COMPLETED]),
            "blocked": len([t for t in all_todos if t.status == TodoStatus.BLOCKED]),
            "urgent": len([t for t in all_todos if t.priority == TodoPriority.URGENT and t.status != TodoStatus.COMPLETED]),
            "high": len([t for t in all_todos if t.priority == TodoPriority.HIGH and t.status != TodoStatus.COMPLETED]),
        }


# =============================================================================
# Global Access
# =============================================================================

_manager: Optional[TodoManager] = None


def get_todo_manager() -> TodoManager:
    """Get the global todo manager."""
    global _manager
    if _manager is None:
        _manager = TodoManager()
    return _manager


# Convenience functions
def add_todo(title: str, **kwargs) -> Todo:
    return get_todo_manager().add(title, **kwargs)


def complete_todo(todo_id: str, completed_by: str = "human") -> Optional[Todo]:
    return get_todo_manager().complete(todo_id, completed_by)


def list_todos(**kwargs) -> List[Todo]:
    return get_todo_manager().list(**kwargs)


def get_todo_summary() -> Dict[str, Any]:
    return get_todo_manager().get_summary()
