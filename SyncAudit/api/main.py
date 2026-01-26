"""
SyncAudit - FastAPI Backend

Universal REST API for logging and querying sync events across all projects.
Designed for easy agent consumption.

Usage:
    uvicorn api.main:app --reload --port 8000
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from models.database import get_db, init_db
from models.sync_event import (
    SyncEventDB, FieldMappingDB,
    SyncEventCreate, SyncEventResponse, 
    CompareResult, StatsResponse, MismatchDetail,
    FieldMappingCreate
)

# Initialize FastAPI app
app = FastAPI(
    title="SyncAudit API",
    description="Universal sync audit service for tracking data flow between systems",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration - restrict to configured origins
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8501").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# API Key authentication - REQUIRED (no default key)
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    import warnings
    warnings.warn("API_KEY not set - API authentication will reject all requests", RuntimeWarning)


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """API key verification - always required."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: API_KEY not set")
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    # Use constant-time comparison to prevent timing attacks
    import hmac
    if not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# =============================================================================
# Startup
# =============================================================================

@app.on_event("startup")
def startup_event():
    """Initialize database on startup."""
    init_db()


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# =============================================================================
# Events CRUD
# =============================================================================

@app.post("/api/events", response_model=SyncEventResponse, tags=["Events"])
def create_event(
    event: SyncEventCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Log a new sync event.
    
    Called by projects (WP plugin, Python scripts, etc.) to record sync attempts,
    successes, failures, and detected mismatches.
    """
    # Convert mismatches to dict for JSON storage
    mismatches_data = None
    mismatch_count = 0
    if event.mismatches:
        mismatches_data = [m.model_dump() for m in event.mismatches]
        mismatch_count = len(event.mismatches)
    
    db_event = SyncEventDB(
        project=event.project,
        source_system=event.source_system,
        target_system=event.target_system,
        source_id=event.source_id,
        target_id=event.target_id,
        event_type=event.event_type,
        status=event.status,
        source_data=event.source_data,
        target_data=event.target_data,
        mismatches=mismatches_data,
        mismatch_count=mismatch_count,
        error_message=event.error_message,
        triggered_by=event.triggered_by,
        notes=event.notes,
        synced_at=datetime.utcnow() if event.status == "synced" else None
    )
    
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    
    return db_event


@app.get("/api/events", response_model=list[SyncEventResponse], tags=["Events"])
def list_events(
    project: Optional[str] = Query(None, description="Filter by project"),
    status: Optional[str] = Query(None, description="Filter by status"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    days: int = Query(7, description="Limit to last N days"),
    limit: int = Query(100, description="Max results"),
    offset: int = Query(0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Query sync events with filters.
    
    Use this endpoint for agents to find recent sync attempts, failures, or mismatches.
    """
    query = db.query(SyncEventDB)
    
    if project:
        query = query.filter(SyncEventDB.project == project)
    if status:
        query = query.filter(SyncEventDB.status == status)
    if event_type:
        query = query.filter(SyncEventDB.event_type == event_type)
    if source_id:
        query = query.filter(SyncEventDB.source_id == source_id)
    
    # Date filter
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.filter(SyncEventDB.created_at >= cutoff)
    
    # Order by most recent first
    query = query.order_by(desc(SyncEventDB.created_at))
    
    # Pagination
    query = query.offset(offset).limit(limit)
    
    return query.all()


@app.get("/api/events/{event_id}", response_model=SyncEventResponse, tags=["Events"])
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get a single event by ID with full data."""
    event = db.query(SyncEventDB).filter(SyncEventDB.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.put("/api/events/{event_id}", response_model=SyncEventResponse, tags=["Events"])
def update_event(
    event_id: int,
    update: SyncEventCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Update an existing event (e.g., after verification)."""
    event = db.query(SyncEventDB).filter(SyncEventDB.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Update fields
    for field, value in update.model_dump(exclude_unset=True).items():
        if field == "mismatches" and value:
            value = [m.model_dump() if hasattr(m, 'model_dump') else m for m in value]
            event.mismatch_count = len(value)
        setattr(event, field, value)
    
    event.updated_at = datetime.utcnow()
    if update.status == "synced":
        event.synced_at = datetime.utcnow()
    
    db.commit()
    db.refresh(event)
    return event


# =============================================================================
# Comparison & Verification
# =============================================================================

@app.get("/api/compare/{source_id}", response_model=CompareResult, tags=["Comparison"])
def compare_record(
    source_id: str,
    project: str = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Compare source vs target data for a specific record.
    
    Returns detailed mismatch information for agents to analyze.
    """
    # Get the most recent event for this source_id
    event = db.query(SyncEventDB).filter(
        SyncEventDB.project == project,
        SyncEventDB.source_id == source_id
    ).order_by(desc(SyncEventDB.created_at)).first()
    
    if not event:
        raise HTTPException(status_code=404, detail=f"No events found for source_id: {source_id}")
    
    # Parse mismatches
    mismatches = []
    if event.mismatches:
        for m in event.mismatches:
            mismatches.append(MismatchDetail(**m))
    
    return CompareResult(
        source_id=event.source_id,
        target_id=event.target_id,
        match=event.mismatch_count == 0 and event.status == "synced",
        mismatch_count=event.mismatch_count,
        mismatches=mismatches,
        source_data=event.source_data or {},
        target_data=event.target_data,
        compared_at=event.updated_at or event.created_at
    )


@app.get("/api/mismatches", response_model=list[SyncEventResponse], tags=["Comparison"])
def list_mismatches(
    project: Optional[str] = Query(None, description="Filter by project"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    days: int = Query(30, description="Limit to last N days"),
    limit: int = Query(50, description="Max results"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Get all detected mismatches.
    
    Use this for agents to find records that need attention.
    """
    query = db.query(SyncEventDB).filter(
        SyncEventDB.mismatch_count > 0
    )
    
    if project:
        query = query.filter(SyncEventDB.project == project)
    
    # Date filter
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = query.filter(SyncEventDB.created_at >= cutoff)
    
    # Order by mismatch count (most severe first)
    query = query.order_by(desc(SyncEventDB.mismatch_count), desc(SyncEventDB.created_at))
    
    return query.limit(limit).all()


# =============================================================================
# Statistics
# =============================================================================

@app.get("/api/stats", response_model=StatsResponse, tags=["Statistics"])
def get_stats(
    project: str = Query(..., description="Project identifier"),
    days: int = Query(7, description="Stats for last N days"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Get summary statistics for a project.
    
    Useful for dashboards and quick health checks.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Base query
    base = db.query(SyncEventDB).filter(
        SyncEventDB.project == project,
        SyncEventDB.created_at >= cutoff
    )
    
    total = base.count()
    synced = base.filter(SyncEventDB.status == "synced").count()
    failed = base.filter(SyncEventDB.status == "failed").count()
    mismatches = base.filter(SyncEventDB.mismatch_count > 0).count()
    pending = base.filter(SyncEventDB.status == "pending").count()
    
    success_rate = (synced / total * 100) if total > 0 else 0.0
    
    # Common errors
    error_query = db.query(
        SyncEventDB.error_message,
        func.count(SyncEventDB.id).label('count')
    ).filter(
        SyncEventDB.project == project,
        SyncEventDB.status == "failed",
        SyncEventDB.error_message.isnot(None),
        SyncEventDB.created_at >= cutoff
    ).group_by(SyncEventDB.error_message).order_by(desc('count')).limit(5)
    
    common_errors = [
        {"error": row[0], "count": row[1]} 
        for row in error_query.all()
    ]
    
    # Recent mismatches
    recent_mismatch_query = base.filter(
        SyncEventDB.mismatch_count > 0
    ).order_by(desc(SyncEventDB.created_at)).limit(5)
    
    recent_mismatches = [
        {
            "source_id": e.source_id,
            "mismatch_count": e.mismatch_count,
            "created_at": e.created_at.isoformat()
        }
        for e in recent_mismatch_query.all()
    ]
    
    return StatsResponse(
        project=project,
        total_events=total,
        synced=synced,
        failed=failed,
        mismatches=mismatches,
        pending=pending,
        success_rate=round(success_rate, 2),
        common_errors=common_errors,
        recent_mismatches=recent_mismatches
    )


# =============================================================================
# Field Mappings
# =============================================================================

@app.post("/api/mappings", tags=["Configuration"])
def create_field_mapping(
    mapping: FieldMappingCreate,
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Create a field mapping configuration for a project."""
    db_mapping = FieldMappingDB(
        project=mapping.project,
        source_system=mapping.source_system,
        target_system=mapping.target_system,
        source_field=mapping.source_field,
        target_field=mapping.target_field,
        transform_type=mapping.transform_type,
        transform_config=mapping.transform_config,
        is_required=1 if mapping.is_required else 0,
        is_key_field=1 if mapping.is_key_field else 0,
        tolerance=mapping.tolerance
    )
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)
    return {"id": db_mapping.id, "status": "created"}


@app.get("/api/mappings", tags=["Configuration"])
def list_field_mappings(
    project: str = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """Get all field mappings for a project."""
    mappings = db.query(FieldMappingDB).filter(
        FieldMappingDB.project == project
    ).all()
    
    return [
        {
            "id": m.id,
            "source_field": m.source_field,
            "target_field": m.target_field,
            "transform_type": m.transform_type,
            "is_required": bool(m.is_required),
            "is_key_field": bool(m.is_key_field)
        }
        for m in mappings
    ]


# =============================================================================
# Agent-Friendly Endpoints
# =============================================================================

@app.get("/api/agent/summary", tags=["Agent"])
def agent_summary(
    project: Optional[str] = Query(None, description="Filter by project"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Agent-optimized summary endpoint.
    
    Returns a concise overview formatted for LLM consumption.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)
    
    query = db.query(SyncEventDB).filter(SyncEventDB.created_at >= cutoff)
    if project:
        query = query.filter(SyncEventDB.project == project)
    
    events = query.all()
    
    # Calculate stats
    total = len(events)
    by_status = {}
    by_project = {}
    critical_issues = []
    
    for e in events:
        # Count by status
        by_status[e.status] = by_status.get(e.status, 0) + 1
        by_project[e.project] = by_project.get(e.project, 0) + 1
        
        # Collect critical issues (failed syncs or high mismatch count)
        if e.status == "failed" or e.mismatch_count >= 3:
            critical_issues.append({
                "id": e.id,
                "project": e.project,
                "source_id": e.source_id,
                "status": e.status,
                "mismatch_count": e.mismatch_count,
                "error": e.error_message[:100] if e.error_message else None
            })
    
    return {
        "period": "last_7_days",
        "total_events": total,
        "by_status": by_status,
        "by_project": by_project,
        "critical_issues_count": len(critical_issues),
        "critical_issues": critical_issues[:10],  # Top 10
        "needs_attention": len(critical_issues) > 0,
        "generated_at": datetime.utcnow().isoformat()
    }


@app.get("/api/agent/diagnose/{source_id}", tags=["Agent"])
def agent_diagnose(
    source_id: str,
    project: str = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Agent-optimized diagnosis for a specific record.
    
    Returns all relevant information for an agent to analyze a sync issue.
    """
    # Get all events for this source_id
    events = db.query(SyncEventDB).filter(
        SyncEventDB.project == project,
        SyncEventDB.source_id == source_id
    ).order_by(SyncEventDB.created_at).all()
    
    if not events:
        raise HTTPException(status_code=404, detail=f"No events found for {source_id}")
    
    latest = events[-1]
    
    # Build diagnosis
    diagnosis = {
        "source_id": source_id,
        "project": project,
        "event_count": len(events),
        "timeline": [
            {
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "status": e.status,
                "error": e.error_message
            }
            for e in events
        ],
        "current_status": latest.status,
        "target_id": latest.target_id,
        "last_sync_attempt": latest.created_at.isoformat(),
        "source_data": latest.source_data,
        "target_data": latest.target_data,
        "mismatches": latest.mismatches or [],
        "mismatch_count": latest.mismatch_count,
        "has_error": latest.error_message is not None,
        "error_message": latest.error_message,
        "retry_count": latest.retry_count,
        "diagnosis": {
            "synced": latest.status == "synced" and latest.mismatch_count == 0,
            "has_mismatches": latest.mismatch_count > 0,
            "failed": latest.status == "failed",
            "needs_manual_review": latest.mismatch_count >= 3 or latest.retry_count >= 3
        }
    }
    
    return diagnosis


# =============================================================================
# Run with: uvicorn api.main:app --reload --port 8000
# =============================================================================
