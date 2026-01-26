"""
Manual Confirmation System

Provides a robust confirmation workflow for sensitive operations.
All destructive or external-facing actions require explicit human approval.

Confirmation Levels:
1. STANDARD - Single approval (e.g., sending a message)
2. ELEVATED - Requires reason (e.g., deleting a file)
3. CRITICAL - Double confirmation + reason (e.g., sharing with external)

Protected Operations:
- Sending emails/messages
- Deleting files/emails
- Sharing data externally
- Modifying production data
- Running database migrations
- Executing shell commands
"""

import os
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum


# Configuration
GOVERNANCE_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = GOVERNANCE_ROOT.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(ORCHESTRATOR_ROOT / "data")))
CONFIRMATIONS_FILE = DATA_DIR / "confirmations.json"


class ConfirmationLevel(Enum):
    """Confirmation security levels."""
    STANDARD = "standard"      # Single click approval
    ELEVATED = "elevated"      # Requires reason
    CRITICAL = "critical"      # Double confirmation + reason


class ConfirmationStatus(Enum):
    """Status of a confirmation request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"


class OperationType(Enum):
    """Types of operations requiring confirmation."""
    SEND_EMAIL = "send_email"
    SEND_SLACK = "send_slack"
    DELETE_EMAIL = "delete_email"
    DELETE_FILE = "delete_file"
    SHARE_FILE = "share_file"
    UPLOAD_FILE = "upload_file"
    EXECUTE_COMMAND = "execute_command"
    MODIFY_PRODUCTION = "modify_production"
    CREATE_USER = "create_user"
    DELETE_USER = "delete_user"
    CHANGE_PERMISSIONS = "change_permissions"
    OTHER = "other"


# Map operations to required confirmation levels
OPERATION_LEVELS = {
    OperationType.SEND_EMAIL: ConfirmationLevel.STANDARD,
    OperationType.SEND_SLACK: ConfirmationLevel.STANDARD,
    OperationType.DELETE_EMAIL: ConfirmationLevel.ELEVATED,
    OperationType.DELETE_FILE: ConfirmationLevel.ELEVATED,
    OperationType.SHARE_FILE: ConfirmationLevel.ELEVATED,
    OperationType.UPLOAD_FILE: ConfirmationLevel.STANDARD,
    OperationType.EXECUTE_COMMAND: ConfirmationLevel.CRITICAL,
    OperationType.MODIFY_PRODUCTION: ConfirmationLevel.CRITICAL,
    OperationType.CREATE_USER: ConfirmationLevel.ELEVATED,
    OperationType.DELETE_USER: ConfirmationLevel.CRITICAL,
    OperationType.CHANGE_PERMISSIONS: ConfirmationLevel.ELEVATED,
    OperationType.OTHER: ConfirmationLevel.ELEVATED,
}


@dataclass
class ConfirmationRequest:
    """A request for human confirmation."""
    id: str
    operation: OperationType
    level: ConfirmationLevel
    status: ConfirmationStatus
    
    # Request details
    title: str
    description: str
    details: Dict[str, Any]
    impact: str  # Human-readable impact description
    
    # Timing
    created_at: str
    expires_at: str
    
    # Requestor
    requested_by: str  # Agent name
    
    # Resolution
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    reason: Optional[str] = None  # Required for elevated/critical rejections
    
    # For critical: track double confirmation
    first_confirmation: Optional[str] = None
    first_confirmed_by: Optional[str] = None
    
    # Callback for execution
    callback_data: Optional[Dict[str, Any]] = None
    execution_result: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["operation"] = self.operation.value
        d["level"] = self.level.value
        d["status"] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfirmationRequest":
        data = data.copy()
        data["operation"] = OperationType(data["operation"])
        data["level"] = ConfirmationLevel(data["level"])
        data["status"] = ConfirmationStatus(data["status"])
        return cls(**data)
    
    @property
    def is_pending(self) -> bool:
        return self.status == ConfirmationStatus.PENDING
    
    @property
    def is_expired(self) -> bool:
        if self.status == ConfirmationStatus.EXPIRED:
            return True
        return datetime.utcnow() > datetime.fromisoformat(self.expires_at)
    
    @property
    def requires_reason(self) -> bool:
        return self.level in (ConfirmationLevel.ELEVATED, ConfirmationLevel.CRITICAL)
    
    @property
    def requires_double_confirmation(self) -> bool:
        return self.level == ConfirmationLevel.CRITICAL


class ConfirmationManager:
    """Manages confirmation requests."""
    
    _instance: Optional["ConfirmationManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.requests: Dict[str, ConfirmationRequest] = {}
        self._callbacks: Dict[str, Callable] = {}
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _load(self):
        """Load confirmations from disk."""
        if CONFIRMATIONS_FILE.exists():
            try:
                with open(CONFIRMATIONS_FILE) as f:
                    data = json.load(f)
                for req_data in data.get("requests", []):
                    req = ConfirmationRequest.from_dict(req_data)
                    self.requests[req.id] = req
            except Exception as e:
                print(f"Error loading confirmations: {e}")
    
    def _save(self):
        """Save confirmations to disk."""
        data = {
            "updated_at": datetime.utcnow().isoformat(),
            "requests": [r.to_dict() for r in self.requests.values()],
        }
        with open(CONFIRMATIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def request(
        self,
        operation: OperationType,
        title: str,
        description: str,
        details: Dict[str, Any],
        impact: str,
        requested_by: str = "agent",
        callback: Callable = None,
        callback_data: Dict[str, Any] = None,
        expires_in_minutes: int = 60,
        level: ConfirmationLevel = None,
    ) -> ConfirmationRequest:
        """
        Request confirmation for an operation.
        
        Args:
            operation: Type of operation
            title: Short title
            description: Detailed description
            details: Technical details (shown in UI)
            impact: Human-readable impact description
            requested_by: Agent requesting
            callback: Function to call on approval
            callback_data: Data to pass to callback
            expires_in_minutes: How long until request expires
            level: Override default confirmation level
        
        Returns:
            ConfirmationRequest
        """
        now = datetime.utcnow()
        
        req = ConfirmationRequest(
            id=str(uuid.uuid4())[:8],
            operation=operation,
            level=level or OPERATION_LEVELS.get(operation, ConfirmationLevel.ELEVATED),
            status=ConfirmationStatus.PENDING,
            title=title,
            description=description,
            details=details,
            impact=impact,
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=expires_in_minutes)).isoformat(),
            requested_by=requested_by,
            callback_data=callback_data,
        )
        
        self.requests[req.id] = req
        if callback:
            self._callbacks[req.id] = callback
        
        self._save()
        return req
    
    def approve(
        self,
        request_id: str,
        approved_by: str = "human",
        reason: str = None,
        is_second_confirmation: bool = False,
    ) -> Optional[ConfirmationRequest]:
        """
        Approve a confirmation request.
        
        For CRITICAL level, this may need to be called twice.
        """
        req = self.requests.get(request_id)
        if not req or not req.is_pending:
            return None
        
        # Check expiration
        if req.is_expired:
            req.status = ConfirmationStatus.EXPIRED
            self._save()
            return None
        
        # Handle double confirmation for critical
        if req.requires_double_confirmation and not is_second_confirmation:
            if not req.first_confirmation:
                req.first_confirmation = datetime.utcnow().isoformat()
                req.first_confirmed_by = approved_by
                self._save()
                return req  # Return with first confirmation done
            # Already has first confirmation, this is the second
            is_second_confirmation = True
        
        # Full approval
        req.status = ConfirmationStatus.APPROVED
        req.resolved_at = datetime.utcnow().isoformat()
        req.resolved_by = approved_by
        req.reason = reason
        self._save()
        
        # Execute callback if registered
        callback = self._callbacks.get(request_id)
        if callback:
            try:
                result = callback(req.callback_data or {})
                req.status = ConfirmationStatus.EXECUTED
                req.execution_result = str(result)
            except Exception as e:
                req.status = ConfirmationStatus.FAILED
                req.execution_result = f"Error: {e}"
            self._save()
        
        return req
    
    def reject(
        self,
        request_id: str,
        rejected_by: str = "human",
        reason: str = None,
    ) -> Optional[ConfirmationRequest]:
        """Reject a confirmation request."""
        req = self.requests.get(request_id)
        if not req or not req.is_pending:
            return None
        
        # Require reason for elevated/critical
        if req.requires_reason and not reason:
            return None  # Can't reject without reason
        
        req.status = ConfirmationStatus.REJECTED
        req.resolved_at = datetime.utcnow().isoformat()
        req.resolved_by = rejected_by
        req.reason = reason
        self._save()
        
        return req
    
    def get(self, request_id: str) -> Optional[ConfirmationRequest]:
        """Get a request by ID."""
        return self.requests.get(request_id)
    
    def list_pending(self) -> List[ConfirmationRequest]:
        """List all pending requests."""
        return [r for r in self.requests.values() if r.is_pending and not r.is_expired]
    
    def list_by_level(self, level: ConfirmationLevel) -> List[ConfirmationRequest]:
        """List pending requests by level."""
        return [r for r in self.list_pending() if r.level == level]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary stats."""
        pending = self.list_pending()
        
        return {
            "total_pending": len(pending),
            "standard": len([r for r in pending if r.level == ConfirmationLevel.STANDARD]),
            "elevated": len([r for r in pending if r.level == ConfirmationLevel.ELEVATED]),
            "critical": len([r for r in pending if r.level == ConfirmationLevel.CRITICAL]),
            "requests": [
                {
                    "id": r.id,
                    "title": r.title,
                    "operation": r.operation.value,
                    "level": r.level.value,
                    "requested_by": r.requested_by,
                    "created_at": r.created_at,
                }
                for r in pending[:10]
            ],
        }
    
    def cleanup_expired(self):
        """Mark expired requests as expired."""
        for req in self.requests.values():
            if req.is_pending and req.is_expired:
                req.status = ConfirmationStatus.EXPIRED
        self._save()


# Global access
_manager: Optional[ConfirmationManager] = None


def get_confirmation_manager() -> ConfirmationManager:
    """Get the global confirmation manager."""
    global _manager
    if _manager is None:
        _manager = ConfirmationManager()
    return _manager


def require_confirmation(
    operation: OperationType,
    title: str,
    description: str,
    details: Dict[str, Any],
    impact: str,
    callback: Callable = None,
    callback_data: Dict[str, Any] = None,
) -> ConfirmationRequest:
    """Convenience function to request confirmation."""
    return get_confirmation_manager().request(
        operation=operation,
        title=title,
        description=description,
        details=details,
        impact=impact,
        callback=callback,
        callback_data=callback_data,
    )
