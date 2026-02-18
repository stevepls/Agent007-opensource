"""
Session Time Tracker

Tracks elapsed time per chat session and infers topics/projects
from conversation content. Stores pending time entries locally
so they can be logged to Harvest later.
"""

import re
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


# Harvest project keywords → project name mapping
PROJECT_KEYWORDS: Dict[str, str] = {
    # Product & Technology
    "agent007": "Product & Technology",
    "orchestrator": "Product & Technology",
    "dashboard": "Product & Technology",
    "syncaudit": "Product & Technology",
    "infrastructure": "Product & Technology",
    "devops": "Product & Technology",
    "deploy": "Product & Technology",
    "railway": "Product & Technology",
    # CYS-001
    "cys": "CYS-001",
    "pcos": "CYS-001",
    # Ongoing support
    "support": "Ongoing support",
    "zendesk": "Ongoing support",
    "ticket": "Ongoing support",
    "bug": "Ongoing support",
    "fix": "Ongoing support",
    # Client development
    "client": "Client development",
    "shipstation": "Client development",
    "woocommerce": "Client development",
    "wordpress": "Client development",
    # Customer Dashboard
    "customer dashboard": "Customer Dashboard and Document Handling",
    "document": "Customer Dashboard and Document Handling",
    # Operations
    "operations": "Operations",
    "accounting": "Operations",
    "invoice": "Operations",
    "upwork": "Operations",
    "quickbooks": "Operations",
    # Error tracking
    "error tracking": "Proactive error tracking and visibility",
    "monitoring": "Proactive error tracking and visibility",
    "observability": "Proactive error tracking and visibility",
}

# Task type keywords → task name mapping
TASK_KEYWORDS: Dict[str, str] = {
    "programming": "Programming",
    "code": "Programming",
    "implement": "Programming",
    "refactor": "Programming",
    "api": "Programming",
    "bug": "Bug Fixes",
    "fix": "Bug Fixes",
    "debug": "Bug Fixes",
    "architect": "System architecture",
    "design": "System architecture",
    "schema": "System architecture",
    "meeting": "Client meetings",
    "call": "Client meetings",
    "engineer": "Engineering",
    "platform": "Platform & Data Engineer",
    "data": "Platform & Data Engineer",
    "product": "Product Management",
    "requirements": "Product Requirements",
    "project manage": "Project Management",
    "ops": "Operations",
}


@dataclass
class SessionState:
    """Tracks time state for a single session."""
    session_id: str
    first_message_at: datetime
    last_message_at: datetime
    turn_count: int = 0
    topic_keywords: set = field(default_factory=set)
    messages_summary: List[str] = field(default_factory=list)

    @property
    def elapsed_minutes(self) -> float:
        delta = self.last_message_at - self.first_message_at
        return round(delta.total_seconds() / 60, 1)

    @property
    def elapsed_hours(self) -> float:
        return round(self.elapsed_minutes / 60, 2)

    @property
    def inferred_project(self) -> Optional[str]:
        keywords_lower = " ".join(self.topic_keywords).lower()
        # Check multi-word patterns first
        for kw, project in sorted(PROJECT_KEYWORDS.items(), key=lambda x: -len(x[0])):
            if kw in keywords_lower:
                return project
        return None

    @property
    def inferred_task(self) -> Optional[str]:
        keywords_lower = " ".join(self.topic_keywords).lower()
        for kw, task in sorted(TASK_KEYWORDS.items(), key=lambda x: -len(x[0])):
            if kw in keywords_lower:
                return task
        return None


class SessionTimer:
    """Tracks elapsed time per chat session."""

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def start_turn(self, session_id: str, user_message: str) -> None:
        """Record the start of a conversation turn."""
        now = datetime.now(timezone.utc)

        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(
                session_id=session_id,
                first_message_at=now,
                last_message_at=now,
            )

        state = self._sessions[session_id]
        state.last_message_at = now
        state.turn_count += 1

        # Extract keywords from the message
        keywords = _extract_keywords(user_message)
        state.topic_keywords.update(keywords)

        # Keep a short summary of messages (last 5)
        summary = user_message[:100].strip()
        if summary:
            state.messages_summary = state.messages_summary[-4:] + [summary]

    def end_turn(self, session_id: str) -> None:
        """Update the timestamp at end of a turn."""
        if session_id in self._sessions:
            self._sessions[session_id].last_message_at = datetime.now(timezone.utc)

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get time tracking summary for a session."""
        state = self._sessions.get(session_id)
        if not state:
            return {"error": "No active session found", "session_id": session_id}

        return {
            "session_id": session_id,
            "elapsed_minutes": state.elapsed_minutes,
            "elapsed_hours": state.elapsed_hours,
            "turn_count": state.turn_count,
            "topics": sorted(state.topic_keywords),
            "inferred_project": state.inferred_project,
            "inferred_task": state.inferred_task,
            "started_at": state.first_message_at.isoformat(),
            "last_activity": state.last_message_at.isoformat(),
        }

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get summaries for all active sessions."""
        return [self.get_session_summary(sid) for sid in self._sessions]

    def flush_to_memory(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Persist session time to the memory context_entries table."""
        state = self._sessions.get(session_id)
        if not state or state.elapsed_minutes < 1:
            return None

        try:
            from services.memory import get_memory_service
            memory = get_memory_service()

            summary = self.get_session_summary(session_id)
            topics_str = ", ".join(sorted(state.topic_keywords)[:10]) or "general"
            date_str = state.first_message_at.strftime("%Y-%m-%d")

            memory.add_context(
                category="pending_time",
                key=f"{date_str}_{session_id[:12]}",
                value=f"{state.elapsed_hours}h — {topics_str}",
                source="session_timer",
                metadata={
                    "session_id": session_id,
                    "date": date_str,
                    "hours": state.elapsed_hours,
                    "minutes": state.elapsed_minutes,
                    "turn_count": state.turn_count,
                    "topics": sorted(state.topic_keywords),
                    "inferred_project": state.inferred_project,
                    "inferred_task": state.inferred_task,
                    "messages_summary": state.messages_summary,
                },
            )
            return summary
        except Exception as e:
            return {"error": f"Failed to flush: {e}"}

    def clear_session(self, session_id: str) -> None:
        """Remove a session from tracking (after logging)."""
        self._sessions.pop(session_id, None)


def _extract_keywords(text: str) -> set:
    """Extract meaningful keywords from a message."""
    # Lowercase and split
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', text.lower())

    # Filter stopwords
    stopwords = {
        "the", "and", "for", "are", "but", "not", "you", "all", "can",
        "her", "was", "one", "our", "out", "day", "had", "has", "his",
        "how", "its", "may", "new", "now", "old", "see", "way", "who",
        "did", "get", "let", "say", "she", "too", "use", "this", "that",
        "with", "have", "from", "they", "been", "said", "each", "which",
        "their", "will", "other", "about", "many", "then", "them", "these",
        "some", "would", "make", "like", "just", "over", "such", "take",
        "than", "very", "what", "when", "where", "here", "there", "please",
        "could", "should", "want", "need", "help", "show", "tell", "give",
        "look", "also", "back", "after", "year", "much", "still", "into",
        "think", "know", "long", "time", "been", "work", "right", "going",
        "really", "yeah", "okay", "sure", "thanks", "thank",
    }

    return {w for w in words if w not in stopwords and len(w) > 2}


# ── Singleton ──

_timer: Optional[SessionTimer] = None


def get_session_timer() -> SessionTimer:
    """Get the global session timer."""
    global _timer
    if _timer is None:
        _timer = SessionTimer()
    return _timer
