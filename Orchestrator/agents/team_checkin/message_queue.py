"""
Message Queue for Team Check-in Agent

Stores pending messages that require approval before sending.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class MessageStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"


@dataclass
class PendingMessage:
    """A message pending approval."""
    id: str
    member_name: str
    member_slack_id: Optional[str]
    message_text: str
    message_type: str  # "morning" or "followup"
    created_at: str
    status: str = MessageStatus.PENDING.value
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    error: Optional[str] = None
    context: Dict = None  # Additional context (tasks, quiet hours, etc.)
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}
    
    def to_dict(self) -> Dict:
        return asdict(self)


class MessageQueue:
    """Manages pending messages for approval."""
    
    def __init__(self, queue_path: Optional[Path] = None):
        self.queue_path = queue_path or Path(__file__).parent / "config" / "message_queue.json"
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self._messages: Dict[str, PendingMessage] = {}
        self._load_queue()
    
    def _load_queue(self):
        """Load messages from disk."""
        if not self.queue_path.exists():
            return
        
        try:
            with open(self.queue_path, 'r') as f:
                data = json.load(f)
                for msg_data in data.get("messages", []):
                    msg = PendingMessage(**msg_data)
                    # Only keep pending messages
                    if msg.status == MessageStatus.PENDING.value:
                        self._messages[msg.id] = msg
        except Exception as e:
            print(f"Error loading message queue: {e}")
    
    def _save_queue(self):
        """Save messages to disk."""
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "messages": [msg.to_dict() for msg in self._messages.values()]
            }
            with open(self.queue_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving message queue: {e}")
    
    def add_message(
        self,
        member_name: str,
        message_text: str,
        message_type: str,
        member_slack_id: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> str:
        """Add a message to the queue. Returns message ID."""
        msg_id = str(uuid.uuid4())
        message = PendingMessage(
            id=msg_id,
            member_name=member_name,
            member_slack_id=member_slack_id,
            message_text=message_text,
            message_type=message_type,
            created_at=datetime.now().isoformat(),
            context=context or {}
        )
        self._messages[msg_id] = message
        self._save_queue()
        return msg_id
    
    def get_pending_messages(self) -> List[PendingMessage]:
        """Get all pending messages."""
        return [msg for msg in self._messages.values() if msg.status == MessageStatus.PENDING.value]
    
    def get_message(self, message_id: str) -> Optional[PendingMessage]:
        """Get a specific message by ID."""
        return self._messages.get(message_id)
    
    def approve_message(self, message_id: str) -> bool:
        """Approve a message (marks it as approved, ready to send)."""
        message = self._messages.get(message_id)
        if not message:
            return False
        
        if message.status != MessageStatus.PENDING.value:
            return False
        
        message.status = MessageStatus.APPROVED.value
        message.approved_at = datetime.now().isoformat()
        self._save_queue()
        return True
    
    def reject_message(self, message_id: str) -> bool:
        """Reject a message."""
        message = self._messages.get(message_id)
        if not message:
            return False
        
        if message.status != MessageStatus.PENDING.value:
            return False
        
        message.status = MessageStatus.REJECTED.value
        message.approved_at = datetime.now().isoformat()
        self._save_queue()
        return True
    
    def mark_sent(self, message_id: str) -> bool:
        """Mark a message as sent."""
        message = self._messages.get(message_id)
        if not message:
            return False
        
        message.status = MessageStatus.SENT.value
        message.sent_at = datetime.now().isoformat()
        self._save_queue()
        return True
    
    def mark_failed(self, message_id: str, error: str) -> bool:
        """Mark a message as failed."""
        message = self._messages.get(message_id)
        if not message:
            return False
        
        message.status = MessageStatus.FAILED.value
        message.error = error
        self._save_queue()
        return True
    
    def get_approved_messages(self) -> List[PendingMessage]:
        """Get all approved messages (ready to send)."""
        return [msg for msg in self._messages.values() if msg.status == MessageStatus.APPROVED.value]
    
    def cleanup_old_messages(self, days: int = 7):
        """Remove old messages (older than N days)."""
        cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
        to_remove = []
        
        for msg_id, msg in self._messages.items():
            try:
                msg_time = datetime.fromisoformat(msg.created_at).timestamp()
                if msg_time < cutoff:
                    to_remove.append(msg_id)
            except:
                to_remove.append(msg_id)
        
        for msg_id in to_remove:
            del self._messages[msg_id]
        
        if to_remove:
            self._save_queue()


# Global instance
_queue: Optional[MessageQueue] = None


def get_message_queue() -> MessageQueue:
    """Get the global message queue instance."""
    global _queue
    if _queue is None:
        _queue = MessageQueue()
    return _queue
