"""
Briefing Engine

Aggregates information from all services to create a prioritized
briefing for the user. Like a smart assistant constantly monitoring
and surfacing what needs attention.

Features:
- Detect schema changes in recent commits
- Aggregate pending approvals
- Surface high-priority items
- Track conversation context
- Proactive suggestions

The UI should feel like a meeting with your assistant briefing you.
"""

import os
import re
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


# Configuration
SERVICES_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent


class Priority(Enum):
    """Priority levels for briefing items."""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    INFO = 4


class ItemType(Enum):
    """Types of briefing items."""
    SCHEMA_CHANGE = "schema_change"
    PENDING_APPROVAL = "pending_approval"
    CODE_REVIEW = "code_review"
    MESSAGE_QUEUE = "message_queue"
    ERROR = "error"
    TODO = "todo"
    MEETING = "meeting"
    DEADLINE = "deadline"
    INSIGHT = "insight"
    SUGGESTION = "suggestion"


@dataclass
class BriefingItem:
    """A single item to brief the user about."""
    id: str
    type: ItemType
    priority: Priority
    title: str
    description: str
    action_label: Optional[str] = None
    action_callback: Optional[str] = None  # Name of action to take
    action_data: Optional[Dict[str, Any]] = None
    source: str = "system"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    expires_at: Optional[str] = None
    dismissed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "action_label": self.action_label,
            "action_callback": self.action_callback,
            "action_data": self.action_data,
            "source": self.source,
            "created_at": self.created_at,
            "dismissed": self.dismissed,
            "metadata": self.metadata,
        }


@dataclass
class ConversationContext:
    """Tracks the current conversation context."""
    current_project: Optional[str] = None
    current_task: Optional[str] = None
    recent_topics: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_action_time: Optional[str] = None
    focus_mode: bool = False  # When true, minimize distractions
    

class BriefingEngine:
    """Generates prioritized briefings for the user."""
    
    _instance: Optional["BriefingEngine"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.context = ConversationContext()
        self._dismissed_items: set = set()
        self._last_refresh: Optional[datetime] = None
        self._cached_items: List[BriefingItem] = []
    
    def set_context(self, **kwargs):
        """Update conversation context."""
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
    
    def dismiss_item(self, item_id: str):
        """Dismiss a briefing item."""
        self._dismissed_items.add(item_id)
    
    def _detect_schema_changes(self) -> List[BriefingItem]:
        """Detect database schema changes in recent commits."""
        items = []
        
        try:
            # Use the dedicated schema detector
            from services.schema_detector import get_schema_detector
            
            detector = get_schema_detector()
            changes = detector.detect_changes(since="7 days ago", include_reviewed=False)
            
            if changes:
                # Group by type for summary
                by_type = {}
                for change in changes:
                    by_type[change.type.value] = by_type.get(change.type.value, 0) + 1
                
                type_summary = ", ".join([f"{v} {k.replace('_', ' ')}" for k, v in by_type.items()])
                
                items.append(BriefingItem(
                    id="schema-changes-recent",
                    type=ItemType.SCHEMA_CHANGE,
                    priority=Priority.HIGH,
                    title="📊 Schema Changes Need Review",
                    description=f"{len(changes)} unreviewed change(s): {type_summary}",
                    action_label="Review Schema",
                    action_callback="review_schema_changes",
                    action_data={"count": len(changes)},
                    metadata={
                        "files": [c.file_path for c in changes[:5]],
                        "by_type": by_type,
                    },
                ))
        except ImportError:
            # Fallback to basic git check
            try:
                result = subprocess.run(
                    ["git", "log", "--oneline", "--name-only", "-10"],
                    cwd=AGENT007_ROOT,
                    capture_output=True,
                    text=True,
                )
                
                if result.returncode == 0:
                    migration_patterns = [r'migrations?/', r'schema', r'\.sql$', r'alembic/']
                    changes = []
                    for line in result.stdout.split('\n'):
                        for pattern in migration_patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                changes.append(line.strip())
                                break
                    
                    if changes:
                        items.append(BriefingItem(
                            id="schema-changes-recent",
                            type=ItemType.SCHEMA_CHANGE,
                            priority=Priority.HIGH,
                            title="📊 Schema Changes Detected",
                            description=f"Found {len(changes)} schema-related changes in recent commits.",
                            action_label="Review Changes",
                            action_callback="review_schema_changes",
                            action_data={"files": changes[:5]},
                            metadata={"files": changes},
                        ))
            except Exception:
                pass
        
        return items
    
    def _get_pending_approvals(self) -> List[BriefingItem]:
        """Get pending approvals from all services."""
        items = []
        
        # Message queue approvals
        try:
            from services.message_queue import get_message_queue, MessageStatus
            queue = get_message_queue()
            pending = [m for m in queue.list_pending() if m.status == MessageStatus.PENDING_APPROVAL]
            
            if pending:
                for msg in pending[:3]:  # Top 3
                    items.append(BriefingItem(
                        id=f"msg-{msg.id}",
                        type=ItemType.MESSAGE_QUEUE,
                        priority=Priority.HIGH,
                        title=f"📬 Message: {msg.type.value}",
                        description=f"To: {msg.channel}\n{msg.content[:100]}...",
                        action_label="Review & Approve",
                        action_callback="approve_message",
                        action_data={"message_id": msg.id},
                        metadata={"seconds_until_send": msg.seconds_until_send},
                    ))
        except ImportError:
            pass
        
        # Database query approvals
        try:
            from services.database.client import get_database_manager
            db = get_database_manager()
            pending = db.get_pending_approvals()
            
            for req in pending[:3]:
                items.append(BriefingItem(
                    id=f"db-{req.id}",
                    type=ItemType.PENDING_APPROVAL,
                    priority=Priority.CRITICAL if req.risk_level.value == "critical" else Priority.HIGH,
                    title=f"🗄️ Query: {req.query_type.value.upper()}",
                    description=f"On {req.connection_name}\n{req.query[:80]}...",
                    action_label="Review Query",
                    action_callback="review_query",
                    action_data={"request_id": req.id},
                    metadata={"risk_level": req.risk_level.value},
                ))
        except ImportError:
            pass
        
        # GitHub code reviews
        try:
            from services.github.client import get_github_client
            gh = get_github_client()
            reviews = gh.get_pending_reviews()
            
            for review in reviews[:3]:
                items.append(BriefingItem(
                    id=f"review-{review.id}",
                    type=ItemType.CODE_REVIEW,
                    priority=Priority.MEDIUM,
                    title=f"💻 Code Review: {review.title}",
                    description=f"{review.files_changed} files, +{review.additions}/-{review.deletions}",
                    action_label="Review Code",
                    action_callback="review_code",
                    action_data={"review_id": review.id},
                ))
        except ImportError:
            pass
        
        # Confirmation requests
        try:
            from governance.confirmations import get_confirmation_manager
            confirm = get_confirmation_manager()
            pending = confirm.list_pending()
            
            for req in pending[:3]:
                items.append(BriefingItem(
                    id=f"confirm-{req.id}",
                    type=ItemType.PENDING_APPROVAL,
                    priority=Priority.CRITICAL if req.level.value == "critical" else Priority.HIGH,
                    title=f"⚠️ {req.title}",
                    description=req.description,
                    action_label="Review & Confirm",
                    action_callback="confirm_action",
                    action_data={"request_id": req.id},
                    metadata={"level": req.level.value},
                ))
        except ImportError:
            pass
        
        return items
    
    def _get_todos(self) -> List[BriefingItem]:
        """Get high-priority todos."""
        items = []
        
        try:
            from utils.todos import get_todo_manager
            tm = get_todo_manager()
            todos = tm.list(include_completed=False)
            
            # Filter to urgent/high priority
            urgent = [t for t in todos if t.priority.value in ("urgent", "high")]
            
            for todo in urgent[:5]:
                items.append(BriefingItem(
                    id=f"todo-{todo.id}",
                    type=ItemType.TODO,
                    priority=Priority.HIGH if todo.priority.value == "urgent" else Priority.MEDIUM,
                    title=f"📝 {todo.title}",
                    description=todo.description or "No description",
                    action_label="Mark Complete",
                    action_callback="complete_todo",
                    action_data={"todo_id": todo.id},
                    metadata={"project": todo.project, "status": todo.status.value},
                ))
        except ImportError:
            pass
        
        return items
    
    def _get_errors(self) -> List[BriefingItem]:
        """Get recent errors from logs."""
        items = []
        
        try:
            from utils.logger import get_logger
            logger = get_logger()
            errors = logger.get_errors(n=5)
            
            for err in errors[:3]:
                if err.level == "ERROR" or err.level == "CRITICAL":
                    items.append(BriefingItem(
                        id=f"error-{err.timestamp}",
                        type=ItemType.ERROR,
                        priority=Priority.HIGH,
                        title=f"🔴 Error: {err.source}",
                        description=err.message[:100],
                        action_label="View Details",
                        action_callback="view_error",
                        action_data={"timestamp": err.timestamp},
                        metadata={"level": err.level},
                    ))
        except ImportError:
            pass
        
        return items
    
    def _generate_suggestions(self) -> List[BriefingItem]:
        """Generate contextual suggestions."""
        items = []
        
        # If there are uncommitted changes, suggest committing
        try:
            from services.github.client import get_github_client
            gh = get_github_client()
            
            if gh.has_uncommitted_changes:
                items.append(BriefingItem(
                    id="suggestion-commit",
                    type=ItemType.SUGGESTION,
                    priority=Priority.LOW,
                    title="💡 Uncommitted Changes",
                    description="You have uncommitted changes. Consider committing or stashing.",
                    action_label="View Diff",
                    action_callback="view_diff",
                ))
        except ImportError:
            pass
        
        return items
    
    def _get_business_advisories(self) -> List[BriefingItem]:
        """Get proactive business advisories from the Business Advisor."""
        items = []
        
        try:
            from services.business_advisor import get_advisor, Severity
            
            advisor = get_advisor()
            advisories = advisor.get_advisories(refresh=False)
            
            severity_map = {
                Severity.CRITICAL: Priority.CRITICAL,
                Severity.WARNING: Priority.HIGH,
                Severity.INFO: Priority.MEDIUM,
                Severity.POSITIVE: Priority.LOW,
            }
            
            for adv in advisories[:10]:
                items.append(BriefingItem(
                    id=f"advisor-{adv.id}",
                    type=ItemType.INSIGHT,
                    priority=severity_map.get(adv.severity, Priority.MEDIUM),
                    title=adv.title,
                    description=f"{adv.detail}\n\n**Recommendation:** {adv.recommendation}",
                    source=f"advisor/{adv.source}",
                    metadata=adv.data,
                ))
        except ImportError:
            pass
        except Exception as e:
            print(f"[WARN] Business advisor briefing failed: {e}")

        return items

    def _get_proactive_agent_results(self) -> List[BriefingItem]:
        """Get results from proactive background agents (scaffolding, ticket manager)."""
        items = []

        try:
            from services.proactive_scheduler import get_proactive_scheduler
            scheduler = get_proactive_scheduler()
            results = scheduler.get_latest_results()

            for agent_name, result in results.items():
                if not result or result.get("error"):
                    if result and result.get("error"):
                        items.append(BriefingItem(
                            id=f"proactive-error-{agent_name}",
                            type=ItemType.ALERT,
                            priority=Priority.HIGH,
                            title=f"{agent_name.replace('_', ' ').title()} Agent Error",
                            description=result["error"],
                            source=f"proactive/{agent_name}",
                        ))
                    continue

                found = result.get("items_found", 0)
                if found == 0:
                    continue

                # Scaffolding completions
                if agent_name == "scaffolding":
                    for detail in result.get("details", []):
                        if detail.get("status") == "success":
                            items.append(BriefingItem(
                                id=f"scaffolding-done-{detail.get('task_id', 'x')}",
                                type=ItemType.UPDATE,
                                priority=Priority.MEDIUM,
                                title=f"Scaffolded: {detail.get('task_name', 'Unknown')}",
                                description=f"Branch `{detail.get('branch', '?')}` ready for {detail.get('project', '?')}",
                                source="proactive/scaffolding",
                                metadata=detail,
                            ))

                # Ticket duplicates
                if agent_name == "ticket_scan":
                    items.append(BriefingItem(
                        id=f"ticket-dupes-{result.get('timestamp', 'x')[:10]}",
                        type=ItemType.ALERT,
                        priority=Priority.HIGH if found >= 3 else Priority.MEDIUM,
                        title=f"{found} Potential Duplicate Ticket(s)",
                        description="\n".join(
                            f"• {d['ticket_a']['subject']} ↔ {d['ticket_b']['subject']}"
                            for d in result.get("details", [])[:5]
                        ),
                        source="proactive/ticket_manager",
                    ))

        except ImportError:
            pass
        except Exception as e:
            print(f"[WARN] Proactive agent briefing failed: {e}")

        return items

    def get_briefing(self, max_items: int = 10, refresh: bool = False) -> List[BriefingItem]:
        """
        Get a prioritized briefing of items needing attention.
        
        Args:
            max_items: Maximum items to return
            refresh: Force refresh even if recently cached
        
        Returns:
            List of BriefingItems sorted by priority
        """
        # Use cache if recent
        if not refresh and self._last_refresh:
            age = datetime.utcnow() - self._last_refresh
            if age.total_seconds() < 30:
                return self._cached_items[:max_items]
        
        items = []
        
        # Gather from all sources
        items.extend(self._detect_schema_changes())
        items.extend(self._get_pending_approvals())
        items.extend(self._get_todos())
        items.extend(self._get_errors())
        items.extend(self._generate_suggestions())
        items.extend(self._get_business_advisories())
        items.extend(self._get_proactive_agent_results())
        
        # Filter dismissed
        items = [i for i in items if i.id not in self._dismissed_items]
        
        # Sort by priority
        items.sort(key=lambda x: x.priority.value)
        
        # Cache
        self._cached_items = items
        self._last_refresh = datetime.utcnow()
        
        return items[:max_items]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the current state."""
        items = self.get_briefing(max_items=50)
        
        by_type = {}
        by_priority = {}
        
        for item in items:
            by_type[item.type.value] = by_type.get(item.type.value, 0) + 1
            by_priority[item.priority.name] = by_priority.get(item.priority.name, 0) + 1
        
        return {
            "total_items": len(items),
            "by_type": by_type,
            "by_priority": by_priority,
            "critical_count": by_priority.get("CRITICAL", 0),
            "high_count": by_priority.get("HIGH", 0),
            "needs_attention": by_priority.get("CRITICAL", 0) + by_priority.get("HIGH", 0) > 0,
        }
    
    def get_greeting(self) -> str:
        """Get a contextual greeting."""
        hour = datetime.now().hour
        
        if hour < 12:
            greeting = "Good morning"
        elif hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        
        summary = self.get_summary()
        
        if summary["critical_count"] > 0:
            return f"{greeting}! 🚨 You have {summary['critical_count']} critical item(s) needing immediate attention."
        elif summary["high_count"] > 0:
            return f"{greeting}! You have {summary['high_count']} high-priority item(s) to review."
        elif summary["total_items"] > 0:
            return f"{greeting}! {summary['total_items']} item(s) for your review when you're ready."
        else:
            return f"{greeting}! All clear - no items needing attention. 🎉"


# Global access
_engine: Optional[BriefingEngine] = None


def get_briefing_engine() -> BriefingEngine:
    """Get the global briefing engine."""
    global _engine
    if _engine is None:
        _engine = BriefingEngine()
    return _engine
