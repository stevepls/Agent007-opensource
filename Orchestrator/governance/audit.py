"""
Audit Logger

Logs all agent actions for traceability and compliance.
Supports both file-based and database storage.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum
import hashlib
import uuid

from .policies import get_policy


class ActionType(Enum):
    """Types of auditable actions."""
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    AGENT_CALL = "agent_call"
    TOOL_USE = "tool_use"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    COMMAND_EXECUTE = "command_execute"
    VALIDATION_CHECK = "validation_check"
    ESCALATION = "escalation"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class AuditEvent:
    """A single auditable event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    session_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    action_type: ActionType = ActionType.AGENT_CALL
    agent: str = ""
    description: str = ""
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    tokens_used: int = 0
    duration_ms: int = 0
    validation_result: Optional[Dict[str, Any]] = None
    policy_violations: List[str] = field(default_factory=list)
    error: Optional[str] = None
    requires_approval: bool = False
    approved_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["action_type"] = self.action_type.value
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)
    
    @property
    def has_violations(self) -> bool:
        return len(self.policy_violations) > 0
    
    def mask_sensitive_data(self) -> "AuditEvent":
        """Return a copy with sensitive data masked."""
        sensitive_fields = get_policy("data_protection", "sensitive_fields") or []
        
        def mask_dict(d: Dict) -> Dict:
            if not d:
                return d
            masked = {}
            for key, value in d.items():
                if any(sf in key.lower() for sf in sensitive_fields):
                    masked[key] = "[REDACTED]"
                elif isinstance(value, dict):
                    masked[key] = mask_dict(value)
                elif isinstance(value, str) and len(value) > 50:
                    # Mask long strings that might contain secrets
                    masked[key] = value[:20] + "...[TRUNCATED]"
                else:
                    masked[key] = value
            return masked
        
        masked_event = AuditEvent(
            event_id=self.event_id,
            session_id=self.session_id,
            timestamp=self.timestamp,
            action_type=self.action_type,
            agent=self.agent,
            description=self.description,
            input_data=mask_dict(self.input_data) if self.input_data else None,
            output_data=mask_dict(self.output_data) if self.output_data else None,
            tokens_used=self.tokens_used,
            duration_ms=self.duration_ms,
            validation_result=self.validation_result,
            policy_violations=self.policy_violations,
            error=self.error,
            requires_approval=self.requires_approval,
            approved_by=self.approved_by,
            metadata=self.metadata,
        )
        return masked_event


class AuditLogger:
    """
    Central audit logging system.
    
    Logs all agent actions to file and optionally to database.
    Provides session tracking and query capabilities.
    """
    
    def __init__(
        self,
        log_dir: str = None,
        session_id: str = None,
        db_url: str = None,
    ):
        """
        Initialize audit logger.
        
        Args:
            log_dir: Directory for log files (default: ./logs/audit)
            session_id: Unique session identifier (auto-generated if not provided)
            db_url: Optional database URL for persistent storage
        """
        self.log_dir = Path(log_dir or "./logs/audit")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_id = session_id or self._generate_session_id()
        self.db_url = db_url
        
        self.events: List[AuditEvent] = []
        self._log_file = self.log_dir / f"session_{self.session_id}.jsonl"
        
        # Log session start
        self.log(AuditEvent(
            action_type=ActionType.TASK_START,
            description=f"Audit session started: {self.session_id}",
            metadata={"log_file": str(self._log_file)},
        ))
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:6]
        return f"{timestamp}_{random_suffix}"
    
    def log(self, event: AuditEvent) -> AuditEvent:
        """
        Log an audit event.
        
        Args:
            event: The event to log
        
        Returns:
            The logged event (with session_id populated)
        """
        event.session_id = self.session_id
        
        # Mask sensitive data before logging
        masked_event = event.mask_sensitive_data()
        
        # Store in memory
        self.events.append(masked_event)
        
        # Write to file (append mode)
        with open(self._log_file, "a") as f:
            f.write(masked_event.to_json().replace("\n", " ") + "\n")
        
        # Optional: Write to database
        if self.db_url:
            self._write_to_db(masked_event)
        
        return event
    
    def log_agent_call(
        self,
        agent: str,
        task: str,
        response: str,
        tokens_used: int = 0,
        duration_ms: int = 0,
    ) -> AuditEvent:
        """Log an agent call."""
        return self.log(AuditEvent(
            action_type=ActionType.AGENT_CALL,
            agent=agent,
            description=f"Agent {agent} executed task",
            input_data={"task": task[:500]},  # Truncate long tasks
            output_data={"response": response[:1000]},  # Truncate long responses
            tokens_used=tokens_used,
            duration_ms=duration_ms,
        ))
    
    def log_tool_use(
        self,
        agent: str,
        tool: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        duration_ms: int = 0,
    ) -> AuditEvent:
        """Log a tool usage."""
        return self.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent=agent,
            description=f"Agent {agent} used tool {tool}",
            input_data={"tool": tool, **input_data},
            output_data=output_data,
            duration_ms=duration_ms,
        ))
    
    def log_file_operation(
        self,
        agent: str,
        operation: str,
        file_path: str,
        success: bool,
        details: str = None,
    ) -> AuditEvent:
        """Log a file operation."""
        action_map = {
            "read": ActionType.FILE_READ,
            "write": ActionType.FILE_WRITE,
            "delete": ActionType.FILE_DELETE,
        }
        return self.log(AuditEvent(
            action_type=action_map.get(operation, ActionType.FILE_READ),
            agent=agent,
            description=f"File {operation}: {file_path}",
            input_data={"file_path": file_path, "operation": operation},
            output_data={"success": success, "details": details},
        ))
    
    def log_validation(
        self,
        validator: str,
        result: Dict[str, Any],
        context: str = None,
    ) -> AuditEvent:
        """Log a validation check."""
        violations = [
            issue.get("code", "UNKNOWN")
            for issue in result.get("issues", [])
            if issue.get("severity") in ["block", "escalate"]
        ]
        return self.log(AuditEvent(
            action_type=ActionType.VALIDATION_CHECK,
            description=f"Validation by {validator}: {result.get('status', 'unknown')}",
            validation_result=result,
            policy_violations=violations,
            metadata={"context": context} if context else {},
        ))
    
    def log_escalation(
        self,
        agent: str,
        reason: str,
        context: Dict[str, Any] = None,
    ) -> AuditEvent:
        """Log an escalation to human."""
        return self.log(AuditEvent(
            action_type=ActionType.ESCALATION,
            agent=agent,
            description=f"Escalation: {reason}",
            metadata={"reason": reason, "context": context or {}},
        ))
    
    def log_approval(
        self,
        action: str,
        approved: bool,
        approved_by: str = "human",
        details: str = None,
    ) -> AuditEvent:
        """Log an approval decision."""
        action_type = ActionType.APPROVAL_GRANTED if approved else ActionType.APPROVAL_DENIED
        return self.log(AuditEvent(
            action_type=action_type,
            description=f"Approval {'granted' if approved else 'denied'} for: {action}",
            approved_by=approved_by if approved else None,
            metadata={"action": action, "details": details},
        ))
    
    def log_policy_violation(
        self,
        agent: str,
        violation_code: str,
        details: str,
        blocked: bool = True,
    ) -> AuditEvent:
        """Log a policy violation."""
        return self.log(AuditEvent(
            action_type=ActionType.POLICY_VIOLATION,
            agent=agent,
            description=f"Policy violation: {violation_code}",
            policy_violations=[violation_code],
            metadata={"details": details, "blocked": blocked},
        ))
    
    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session."""
        total_tokens = sum(e.tokens_used for e in self.events)
        total_duration = sum(e.duration_ms for e in self.events)
        violations = [v for e in self.events for v in e.policy_violations]
        
        return {
            "session_id": self.session_id,
            "event_count": len(self.events),
            "total_tokens_used": total_tokens,
            "total_duration_ms": total_duration,
            "policy_violations": list(set(violations)),
            "violation_count": len(violations),
            "log_file": str(self._log_file),
        }
    
    def export_session(self, format: str = "json") -> str:
        """Export session logs."""
        if format == "json":
            return json.dumps([e.to_dict() for e in self.events], indent=2, default=str)
        elif format == "jsonl":
            return "\n".join(e.to_json().replace("\n", " ") for e in self.events)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _write_to_db(self, event: AuditEvent):
        """Write event to database (placeholder for DB implementation)."""
        # TODO: Implement database storage
        pass
    
    def close(self):
        """Close the audit session."""
        self.log(AuditEvent(
            action_type=ActionType.TASK_COMPLETE,
            description=f"Audit session closed: {self.session_id}",
            metadata=self.get_session_summary(),
        ))


# Global logger instance (initialized per session)
_current_logger: Optional[AuditLogger] = None


def get_audit_logger(session_id: str = None) -> AuditLogger:
    """Get or create the audit logger for the current session."""
    global _current_logger
    
    if _current_logger is None or (session_id and session_id != _current_logger.session_id):
        _current_logger = AuditLogger(session_id=session_id)
    
    return _current_logger


def log_event(event: AuditEvent) -> AuditEvent:
    """Convenience function to log an event to the current session."""
    return get_audit_logger().log(event)
