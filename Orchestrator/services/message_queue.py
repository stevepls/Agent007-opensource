"""
Delayed Message Queue

All outgoing messages (email, Slack, etc.) go through this queue.
Messages are held for a configurable delay before sending, allowing:
- Human review and cancellation
- Last-minute edits
- Audit trail

Default delay: 2 minutes for Slack, 5 minutes for email
"""

import os
import json
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum


# Configuration
SERVICES_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
QUEUE_DIR = Path(os.getenv("MESSAGE_QUEUE_DIR", str(ORCHESTRATOR_ROOT / "data" / "message_queue")))

# Default delays (seconds)
DEFAULT_DELAYS = {
    "slack": 120,      # 2 minutes
    "email": 300,      # 5 minutes
    "drive": 60,       # 1 minute (for destructive ops)
    "default": 120,
}


class MessageStatus(Enum):
    QUEUED = "queued"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MessageType(Enum):
    SLACK_MESSAGE = "slack_message"
    SLACK_DM = "slack_dm"
    EMAIL_SEND = "email_send"
    EMAIL_REPLY = "email_reply"
    DRIVE_UPLOAD = "drive_upload"
    DRIVE_DELETE = "drive_delete"
    DRIVE_SHARE = "drive_share"


@dataclass
class QueuedMessage:
    """A message waiting to be sent."""
    id: str
    type: MessageType
    channel: str  # email address, slack channel, etc.
    subject: Optional[str]
    content: str
    metadata: Dict[str, Any]
    status: MessageStatus
    created_at: str
    send_at: str  # When the message should actually be sent
    created_by: str  # Agent or human
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    error_message: Optional[str] = None
    requires_approval: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueuedMessage":
        data = data.copy()
        data["type"] = MessageType(data["type"])
        data["status"] = MessageStatus(data["status"])
        return cls(**data)
    
    @property
    def is_cancellable(self) -> bool:
        return self.status in (MessageStatus.QUEUED, MessageStatus.PENDING_APPROVAL, MessageStatus.APPROVED)
    
    @property
    def time_until_send(self) -> timedelta:
        send_time = datetime.fromisoformat(self.send_at)
        return send_time - datetime.utcnow()
    
    @property
    def seconds_until_send(self) -> int:
        return max(0, int(self.time_until_send.total_seconds()))


class MessageQueue:
    """Manages delayed message sending with approval workflow."""
    
    _instance: Optional["MessageQueue"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.messages: Dict[str, QueuedMessage] = {}
        self._senders: Dict[MessageType, Callable] = {}
        self._lock = threading.Lock()
        self._timer_threads: Dict[str, threading.Timer] = {}
        
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _load(self):
        """Load queued messages from disk."""
        queue_file = QUEUE_DIR / "queue.json"
        if queue_file.exists():
            try:
                with open(queue_file) as f:
                    data = json.load(f)
                for msg_data in data.get("messages", []):
                    msg = QueuedMessage.from_dict(msg_data)
                    # Only load non-terminal states
                    if msg.status in (MessageStatus.QUEUED, MessageStatus.PENDING_APPROVAL, MessageStatus.APPROVED):
                        self.messages[msg.id] = msg
            except Exception as e:
                print(f"Error loading message queue: {e}")
    
    def _save(self):
        """Save queue to disk."""
        queue_file = QUEUE_DIR / "queue.json"
        data = {
            "updated_at": datetime.utcnow().isoformat(),
            "messages": [m.to_dict() for m in self.messages.values()]
        }
        with open(queue_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def register_sender(self, msg_type: MessageType, sender: Callable):
        """Register a sender function for a message type."""
        self._senders[msg_type] = sender
    
    def queue(
        self,
        msg_type: MessageType,
        channel: str,
        content: str,
        subject: Optional[str] = None,
        metadata: Dict[str, Any] = None,
        created_by: str = "agent",
        delay_seconds: int = None,
        requires_approval: bool = True,
    ) -> QueuedMessage:
        """Queue a message for delayed sending."""
        
        if delay_seconds is None:
            # Get default delay for this type
            type_key = msg_type.value.split("_")[0]  # e.g., "slack" from "slack_message"
            delay_seconds = DEFAULT_DELAYS.get(type_key, DEFAULT_DELAYS["default"])
        
        now = datetime.utcnow()
        send_at = now + timedelta(seconds=delay_seconds)
        
        msg = QueuedMessage(
            id=str(uuid.uuid4())[:8],
            type=msg_type,
            channel=channel,
            subject=subject,
            content=content,
            metadata=metadata or {},
            status=MessageStatus.PENDING_APPROVAL if requires_approval else MessageStatus.QUEUED,
            created_at=now.isoformat(),
            send_at=send_at.isoformat(),
            created_by=created_by,
            requires_approval=requires_approval,
        )
        
        with self._lock:
            self.messages[msg.id] = msg
            self._save()
        
        # If no approval required, schedule the send
        if not requires_approval:
            self._schedule_send(msg)
        
        return msg
    
    def _schedule_send(self, msg: QueuedMessage):
        """Schedule a message to be sent after delay."""
        delay = msg.seconds_until_send
        if delay > 0:
            timer = threading.Timer(delay, self._execute_send, args=[msg.id])
            timer.daemon = True
            timer.start()
            self._timer_threads[msg.id] = timer
        else:
            # Send immediately if delay has passed
            self._execute_send(msg.id)
    
    def _execute_send(self, msg_id: str):
        """Actually send the message."""
        with self._lock:
            msg = self.messages.get(msg_id)
            if not msg or msg.status not in (MessageStatus.QUEUED, MessageStatus.APPROVED):
                return
            
            msg.status = MessageStatus.SENDING
            self._save()
        
        # Get the sender for this message type
        sender = self._senders.get(msg.type)
        if not sender:
            msg.status = MessageStatus.FAILED
            msg.error_message = f"No sender registered for {msg.type.value}"
            self._save()
            return
        
        try:
            sender(msg)
            msg.status = MessageStatus.SENT
            msg.sent_at = datetime.utcnow().isoformat()
        except Exception as e:
            msg.status = MessageStatus.FAILED
            msg.error_message = str(e)
        
        with self._lock:
            self._save()
            # Clean up timer
            if msg_id in self._timer_threads:
                del self._timer_threads[msg_id]
    
    def approve(self, msg_id: str, approved_by: str = "human") -> Optional[QueuedMessage]:
        """Approve a pending message for sending."""
        with self._lock:
            msg = self.messages.get(msg_id)
            if not msg or msg.status != MessageStatus.PENDING_APPROVAL:
                return None
            
            msg.status = MessageStatus.APPROVED
            msg.approved_by = approved_by
            msg.approved_at = datetime.utcnow().isoformat()
            self._save()
        
        # Schedule the send
        self._schedule_send(msg)
        return msg
    
    def cancel(self, msg_id: str, cancelled_by: str = "human", reason: str = None) -> Optional[QueuedMessage]:
        """Cancel a queued message."""
        with self._lock:
            msg = self.messages.get(msg_id)
            if not msg or not msg.is_cancellable:
                return None
            
            msg.status = MessageStatus.CANCELLED
            msg.cancelled_at = datetime.utcnow().isoformat()
            msg.cancelled_by = cancelled_by
            msg.cancel_reason = reason
            self._save()
            
            # Cancel the timer if exists
            if msg_id in self._timer_threads:
                self._timer_threads[msg_id].cancel()
                del self._timer_threads[msg_id]
        
        return msg
    
    def edit(self, msg_id: str, content: str = None, subject: str = None) -> Optional[QueuedMessage]:
        """Edit a queued message before it's sent."""
        with self._lock:
            msg = self.messages.get(msg_id)
            if not msg or not msg.is_cancellable:
                return None
            
            if content is not None:
                msg.content = content
            if subject is not None:
                msg.subject = subject
            
            self._save()
        
        return msg
    
    def get(self, msg_id: str) -> Optional[QueuedMessage]:
        """Get a message by ID."""
        return self.messages.get(msg_id)
    
    def list_pending(self) -> List[QueuedMessage]:
        """List all pending/queued messages."""
        return [
            m for m in self.messages.values()
            if m.status in (MessageStatus.QUEUED, MessageStatus.PENDING_APPROVAL, MessageStatus.APPROVED)
        ]
    
    def list_requiring_approval(self) -> List[QueuedMessage]:
        """List messages waiting for approval."""
        return [m for m in self.messages.values() if m.status == MessageStatus.PENDING_APPROVAL]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get queue summary."""
        all_msgs = list(self.messages.values())
        pending = [m for m in all_msgs if m.status == MessageStatus.PENDING_APPROVAL]
        queued = [m for m in all_msgs if m.status == MessageStatus.QUEUED]
        approved = [m for m in all_msgs if m.status == MessageStatus.APPROVED]
        
        return {
            "pending_approval": len(pending),
            "queued": len(queued),
            "approved": len(approved),
            "total_waiting": len(pending) + len(queued) + len(approved),
            "messages": [
                {
                    "id": m.id,
                    "type": m.type.value,
                    "channel": m.channel,
                    "status": m.status.value,
                    "seconds_until_send": m.seconds_until_send,
                    "preview": m.content[:50] + "..." if len(m.content) > 50 else m.content,
                }
                for m in pending + queued + approved
            ]
        }


# Global access
_queue: Optional[MessageQueue] = None


def get_message_queue() -> MessageQueue:
    """Get the global message queue."""
    global _queue
    if _queue is None:
        _queue = MessageQueue()
    return _queue
