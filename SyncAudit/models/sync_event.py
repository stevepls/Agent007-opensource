"""
SyncAudit - Universal Sync Event Models

Project-agnostic schema for tracking data flow between any source and target system.
Designed for easy agent consumption via REST API.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Enum, Index
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, Field
import enum

Base = declarative_base()


# =============================================================================
# Enums
# =============================================================================

class EventType(str, enum.Enum):
    """Types of sync events"""
    SYNC_ATTEMPT = "sync_attempt"       # Sync was attempted
    SYNC_SUCCESS = "sync_success"       # Sync completed successfully
    SYNC_FAILED = "sync_failed"         # Sync failed with error
    MISMATCH_DETECTED = "mismatch"      # Data mismatch found during verification
    VERIFICATION = "verification"        # Manual/scheduled verification run
    CANCELLATION = "cancellation"        # Record was cancelled in one or both systems
    UPDATE = "update"                    # Record was updated


class SyncStatus(str, enum.Enum):
    """Status of the sync"""
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    MISMATCH = "mismatch"
    SKIPPED = "skipped"


# =============================================================================
# SQLAlchemy Models (Database)
# =============================================================================

class SyncEventDB(Base):
    """
    Database model for sync events.
    Universal schema that works across all projects.
    """
    __tablename__ = "sync_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Project identification
    project = Column(String(100), nullable=False, index=True)  # "apdriving", "lcp", "phyto"
    source_system = Column(String(100), nullable=False)         # "woocommerce", "shopify", "magento"
    target_system = Column(String(100), nullable=False)         # "acuity", "nav", "odoo"
    
    # Record references
    source_id = Column(String(255), nullable=False, index=True)  # Order ID, transaction ID
    target_id = Column(String(255), nullable=True, index=True)   # External system ID
    
    # Event metadata
    event_type = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="pending", index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at = Column(DateTime, nullable=True)
    
    # Data snapshots (JSON)
    source_data = Column(JSON, nullable=True)   # Full data from source system
    target_data = Column(JSON, nullable=True)   # Full data from target system
    
    # Comparison results
    mismatches = Column(JSON, nullable=True)    # List of field mismatches
    mismatch_count = Column(Integer, default=0)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Additional context
    triggered_by = Column(String(100), nullable=True)  # "webhook", "cron", "manual", "agent"
    notes = Column(Text, nullable=True)
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_project_status', 'project', 'status'),
        Index('ix_project_created', 'project', 'created_at'),
        Index('ix_source_lookup', 'project', 'source_system', 'source_id'),
    )


class FieldMappingDB(Base):
    """
    Field mapping configuration per project.
    Defines how fields map between source and target systems.
    """
    __tablename__ = "field_mappings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project = Column(String(100), nullable=False, index=True)
    source_system = Column(String(100), nullable=False)
    target_system = Column(String(100), nullable=False)
    
    # Field mapping
    source_field = Column(String(255), nullable=False)
    target_field = Column(String(255), nullable=False)
    
    # Transformation
    transform_type = Column(String(50), nullable=True)  # "datetime", "lookup", "format"
    transform_config = Column(JSON, nullable=True)
    
    # Comparison settings
    is_required = Column(Integer, default=1)  # 1 = required for sync
    is_key_field = Column(Integer, default=0)  # 1 = used for record matching
    tolerance = Column(String(50), nullable=True)  # For numeric/date comparisons
    
    created_at = Column(DateTime, default=datetime.utcnow)


# =============================================================================
# Pydantic Models (API Request/Response)
# =============================================================================

class MismatchDetail(BaseModel):
    """Detail of a single field mismatch"""
    field: str
    source_value: Optional[str] = None
    target_value: Optional[str] = None
    severity: str = "medium"  # critical, high, medium, low
    message: Optional[str] = None


class SyncEventCreate(BaseModel):
    """Request model for creating a sync event"""
    project: str = Field(..., description="Project identifier", example="apdriving")
    source_system: str = Field(..., description="Source system name", example="woocommerce")
    target_system: str = Field(..., description="Target system name", example="acuity")
    source_id: str = Field(..., description="Record ID in source system", example="12345")
    target_id: Optional[str] = Field(None, description="Record ID in target system")
    event_type: str = Field(..., description="Type of event", example="sync_attempt")
    status: str = Field("pending", description="Sync status")
    source_data: Optional[dict] = Field(None, description="Data snapshot from source")
    target_data: Optional[dict] = Field(None, description="Data snapshot from target")
    mismatches: Optional[list[MismatchDetail]] = Field(None, description="Detected mismatches")
    error_message: Optional[str] = None
    triggered_by: Optional[str] = Field(None, description="What triggered this event")
    notes: Optional[str] = None


class SyncEventResponse(BaseModel):
    """Response model for sync event"""
    id: int
    project: str
    source_system: str
    target_system: str
    source_id: str
    target_id: Optional[str]
    event_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    synced_at: Optional[datetime]
    source_data: Optional[dict]
    target_data: Optional[dict]
    mismatches: Optional[list]
    mismatch_count: int
    error_message: Optional[str]
    triggered_by: Optional[str]
    
    class Config:
        from_attributes = True


class CompareResult(BaseModel):
    """Result of comparing source vs target data"""
    source_id: str
    target_id: Optional[str]
    match: bool
    mismatch_count: int
    mismatches: list[MismatchDetail]
    source_data: dict
    target_data: Optional[dict]
    compared_at: datetime


class StatsResponse(BaseModel):
    """Summary statistics for a project"""
    project: str
    total_events: int
    synced: int
    failed: int
    mismatches: int
    pending: int
    success_rate: float
    common_errors: list[dict]
    recent_mismatches: list[dict]


class FieldMappingCreate(BaseModel):
    """Request model for creating field mapping"""
    project: str
    source_system: str
    target_system: str
    source_field: str
    target_field: str
    transform_type: Optional[str] = None
    transform_config: Optional[dict] = None
    is_required: bool = True
    is_key_field: bool = False
    tolerance: Optional[str] = None
