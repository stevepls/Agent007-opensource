"""
Audit Database Models

SQLAlchemy models for persistent audit storage.
Supports SQLite for local development and PostgreSQL for production.

Tables:
- audit_sessions: Track agent sessions
- audit_records: Individual actions within sessions
- policy_violations: Policy violations for analysis
- approval_requests: Pending human approvals

Usage:
    from audit.models import init_db, log_to_db, get_session_records
    
    # Initialize database (run once at startup)
    init_db()
    
    # Log an event
    log_to_db(session_id, action_type, agent, description, ...)
    
    # Query records
    records = get_session_records(session_id)
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Float,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
    Session,
)


# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# Use SQLite for local, PostgreSQL for production
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./logs/audit/audit.db"
)

# Handle Heroku/Railway postgres:// -> postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    # SQLite-specific settings
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# =============================================================================
# MODELS
# =============================================================================

class AuditSession(Base):
    """
    Represents an agent session.
    
    A session starts when a user submits a task and ends when the task completes.
    """
    __tablename__ = "audit_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), unique=True, nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    
    # Task info
    task_description = Column(Text, nullable=True)
    task_status = Column(String(20), default="in_progress")  # in_progress, completed, failed, blocked
    
    # Statistics
    total_tokens = Column(Integer, default=0)
    total_api_calls = Column(Integer, default=0)
    total_tool_calls = Column(Integer, default=0)
    estimated_cost_usd = Column(Float, default=0.0)
    
    # Results
    final_verdict = Column(String(20), nullable=True)  # PASS, FAIL, ESCALATE
    human_approved = Column(Boolean, nullable=True)
    approved_by = Column(String(100), nullable=True)
    
    # Relationships
    records = relationship("AuditRecord", back_populates="session", cascade="all, delete-orphan")
    violations = relationship("PolicyViolation", back_populates="session", cascade="all, delete-orphan")
    approvals = relationship("ApprovalRequest", back_populates="session", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<AuditSession {self.session_id} ({self.task_status})>"


class AuditRecord(Base):
    """
    Individual audit record for an action within a session.
    """
    __tablename__ = "audit_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("audit_sessions.session_id"), nullable=False, index=True)
    event_id = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Action info
    action_type = Column(String(50), nullable=False, index=True)
    agent = Column(String(50), nullable=True, index=True)
    description = Column(Text, nullable=True)
    
    # Data (stored as JSON)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    validation_result = Column(JSON, nullable=True)
    metadata = Column(JSON, nullable=True)
    
    # Metrics
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    
    # Policy tracking
    policy_violations = Column(JSON, nullable=True)  # List of violation codes
    requires_approval = Column(Boolean, default=False)
    
    # Relationship
    session = relationship("AuditSession", back_populates="records")
    
    # Indexes for common queries
    __table_args__ = (
        Index("ix_records_session_timestamp", "session_id", "timestamp"),
        Index("ix_records_action_agent", "action_type", "agent"),
    )
    
    def __repr__(self):
        return f"<AuditRecord {self.event_id} ({self.action_type})>"


class PolicyViolation(Base):
    """
    Tracked policy violation for analysis and reporting.
    """
    __tablename__ = "policy_violations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("audit_sessions.session_id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Violation details
    violation_code = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)  # critical, high, medium, low
    policy_category = Column(String(50), nullable=True)  # security, quality, production, etc.
    
    agent = Column(String(50), nullable=True)
    description = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    
    # Resolution
    blocked = Column(Boolean, default=True)
    resolved = Column(Boolean, default=False)
    resolved_by = Column(String(100), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    
    # Relationship
    session = relationship("AuditSession", back_populates="violations")
    
    def __repr__(self):
        return f"<PolicyViolation {self.violation_code} ({self.severity})>"


class ApprovalRequest(Base):
    """
    Request for human approval.
    """
    __tablename__ = "approval_requests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("audit_sessions.session_id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Request details
    request_type = Column(String(50), nullable=False)  # file_write, command_execute, etc.
    description = Column(Text, nullable=False)
    context = Column(JSON, nullable=True)
    
    # Decision
    status = Column(String(20), default="pending", index=True)  # pending, approved, denied
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), nullable=True)
    decision_notes = Column(Text, nullable=True)
    
    # Relationship
    session = relationship("AuditSession", back_populates="approvals")
    
    def __repr__(self):
        return f"<ApprovalRequest {self.request_type} ({self.status})>"


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def init_db():
    """Initialize the database, creating all tables."""
    # Ensure log directory exists for SQLite
    if "sqlite" in DATABASE_URL:
        import os
        log_dir = os.path.dirname(DATABASE_URL.replace("sqlite:///", ""))
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
    
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_db_session() -> Session:
    """Get a database session (context manager)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_session(
    session_id: str,
    task_description: str = None,
) -> AuditSession:
    """Create a new audit session in the database."""
    with get_db_session() as db:
        audit_session = AuditSession(
            session_id=session_id,
            task_description=task_description,
        )
        db.add(audit_session)
        db.commit()
        db.refresh(audit_session)
        return audit_session


def log_to_db(
    session_id: str,
    event_id: str,
    action_type: str,
    agent: str = None,
    description: str = None,
    input_data: Dict[str, Any] = None,
    output_data: Dict[str, Any] = None,
    tokens_used: int = 0,
    duration_ms: int = 0,
    policy_violations: List[str] = None,
    requires_approval: bool = False,
    validation_result: Dict[str, Any] = None,
    metadata: Dict[str, Any] = None,
) -> AuditRecord:
    """Log an audit record to the database."""
    with get_db_session() as db:
        record = AuditRecord(
            session_id=session_id,
            event_id=event_id,
            action_type=action_type,
            agent=agent,
            description=description,
            input_data=input_data,
            output_data=output_data,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            policy_violations=policy_violations,
            requires_approval=requires_approval,
            validation_result=validation_result,
            metadata=metadata,
        )
        db.add(record)
        
        # Update session statistics
        session = db.query(AuditSession).filter_by(session_id=session_id).first()
        if session:
            session.total_tokens += tokens_used
            if action_type == "agent_call":
                session.total_api_calls += 1
            elif action_type == "tool_use":
                session.total_tool_calls += 1
        
        db.commit()
        db.refresh(record)
        return record


def log_violation(
    session_id: str,
    violation_code: str,
    severity: str,
    description: str,
    agent: str = None,
    policy_category: str = None,
    context: str = None,
    blocked: bool = True,
) -> PolicyViolation:
    """Log a policy violation to the database."""
    with get_db_session() as db:
        violation = PolicyViolation(
            session_id=session_id,
            violation_code=violation_code,
            severity=severity,
            description=description,
            agent=agent,
            policy_category=policy_category,
            context=context,
            blocked=blocked,
        )
        db.add(violation)
        db.commit()
        db.refresh(violation)
        return violation


def create_approval_request(
    session_id: str,
    request_type: str,
    description: str,
    context: Dict[str, Any] = None,
) -> ApprovalRequest:
    """Create an approval request."""
    with get_db_session() as db:
        request = ApprovalRequest(
            session_id=session_id,
            request_type=request_type,
            description=description,
            context=context,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return request


def update_approval(
    approval_id: int,
    status: str,
    decided_by: str = "human",
    decision_notes: str = None,
) -> Optional[ApprovalRequest]:
    """Update an approval request with a decision."""
    with get_db_session() as db:
        request = db.query(ApprovalRequest).filter_by(id=approval_id).first()
        if request:
            request.status = status
            request.decided_at = datetime.utcnow()
            request.decided_by = decided_by
            request.decision_notes = decision_notes
            db.commit()
            db.refresh(request)
        return request


def get_session_records(session_id: str) -> List[AuditRecord]:
    """Get all records for a session."""
    with get_db_session() as db:
        return db.query(AuditRecord).filter_by(session_id=session_id).order_by(AuditRecord.timestamp).all()


def get_violations(
    session_id: str = None,
    severity: str = None,
    resolved: bool = None,
) -> List[PolicyViolation]:
    """Get policy violations with optional filters."""
    with get_db_session() as db:
        query = db.query(PolicyViolation)
        
        if session_id:
            query = query.filter_by(session_id=session_id)
        if severity:
            query = query.filter_by(severity=severity)
        if resolved is not None:
            query = query.filter_by(resolved=resolved)
        
        return query.order_by(PolicyViolation.timestamp.desc()).all()


def get_pending_approvals(session_id: str = None) -> List[ApprovalRequest]:
    """Get pending approval requests."""
    with get_db_session() as db:
        query = db.query(ApprovalRequest).filter_by(status="pending")
        
        if session_id:
            query = query.filter_by(session_id=session_id)
        
        return query.order_by(ApprovalRequest.created_at).all()


def close_session(
    session_id: str,
    task_status: str,
    final_verdict: str = None,
    human_approved: bool = None,
    estimated_cost_usd: float = None,
) -> Optional[AuditSession]:
    """Close an audit session with final status."""
    with get_db_session() as db:
        session = db.query(AuditSession).filter_by(session_id=session_id).first()
        if session:
            session.ended_at = datetime.utcnow()
            session.task_status = task_status
            session.final_verdict = final_verdict
            session.human_approved = human_approved
            if estimated_cost_usd:
                session.estimated_cost_usd = estimated_cost_usd
            db.commit()
            db.refresh(session)
        return session


def get_session_summary(session_id: str) -> Optional[Dict[str, Any]]:
    """Get a summary of a session from the database."""
    with get_db_session() as db:
        session = db.query(AuditSession).filter_by(session_id=session_id).first()
        if not session:
            return None
        
        records = db.query(AuditRecord).filter_by(session_id=session_id).count()
        violations = db.query(PolicyViolation).filter_by(session_id=session_id).count()
        pending = db.query(ApprovalRequest).filter_by(session_id=session_id, status="pending").count()
        
        return {
            "session_id": session.session_id,
            "task_description": session.task_description,
            "task_status": session.task_status,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "duration_seconds": (session.ended_at - session.started_at).total_seconds() if session.ended_at else None,
            "total_tokens": session.total_tokens,
            "total_api_calls": session.total_api_calls,
            "total_tool_calls": session.total_tool_calls,
            "estimated_cost_usd": session.estimated_cost_usd,
            "final_verdict": session.final_verdict,
            "human_approved": session.human_approved,
            "record_count": records,
            "violation_count": violations,
            "pending_approvals": pending,
        }
