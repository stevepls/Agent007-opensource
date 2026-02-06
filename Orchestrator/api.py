"""
Orchestrator REST API

Provides REST endpoints for programmatic access to Orchestrator services.

Usage:
    uvicorn api:app --host 0.0.0.0 --port $PORT --reload

    # Or with the Orchestrator
    python -m api
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import services
from services.schema_detector import (
    get_schema_detector,
    add_client_project,
    SchemaChange,
)

# Optional imports
try:
    from services.briefing import get_briefing_engine
    BRIEFING_AVAILABLE = True
except ImportError:
    BRIEFING_AVAILABLE = False

try:
    from services.message_queue import get_message_queue
    QUEUE_AVAILABLE = True
except ImportError:
    QUEUE_AVAILABLE = False

# Import chat router
try:
    from api_chat import router as chat_router
    CHAT_AVAILABLE = True
except ImportError:
    CHAT_AVAILABLE = False
    chat_router = None

# Import harvest router
try:
    from api_harvest import router as harvest_router
    HARVEST_AVAILABLE = True
except ImportError:
    HARVEST_AVAILABLE = False
    harvest_router = None


# ============================================================================
# App Configuration
# ============================================================================

app = FastAPI(
    title="Orchestrator API",
    description="REST API for Agent007 Orchestrator services",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include chat router for dashboard integration
if CHAT_AVAILABLE and chat_router:
    app.include_router(chat_router)

# Include harvest router for time tracking
if HARVEST_AVAILABLE and harvest_router:
    app.include_router(harvest_router)


# ============================================================================
# Models
# ============================================================================

class ProjectCreate(BaseModel):
    """Request to add a new project to monitor."""
    name: str = Field(..., description="Project identifier (e.g., 'ap-driving')")
    path: str = Field(..., description="Absolute path to project directory")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "ap-driving",
                "path": "/home/steve/projects/ap-driving"
            }
        }


class ProjectResponse(BaseModel):
    """Project information."""
    name: str
    path: str
    exists: bool


class ProjectListResponse(BaseModel):
    """List of monitored projects."""
    projects: List[ProjectResponse]
    count: int


class SchemaChangeResponse(BaseModel):
    """Schema change information."""
    id: str
    type: str
    file_path: str
    commit_hash: str
    commit_message: str
    commit_date: str
    author: str
    project: str
    lines_added: int
    lines_removed: int
    preview: str
    reviewed: bool


class SchemaSummaryResponse(BaseModel):
    """Schema detection summary."""
    total: int
    unreviewed: int
    by_type: Dict[str, int]
    by_project: Dict[str, int]
    monitored_projects: List[str]
    last_check: Optional[str]


class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool
    message: str


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Check harvest configuration
    harvest_configured = False
    if HARVEST_AVAILABLE:
        from services.harvest_client import is_harvest_configured
        harvest_configured = is_harvest_configured()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "schema_detector": True,
            "briefing": BRIEFING_AVAILABLE,
            "message_queue": QUEUE_AVAILABLE,
            "harvest": harvest_configured,
        }
    }


# ============================================================================
# Project Management Endpoints
# ============================================================================

@app.get(
    "/projects",
    response_model=ProjectListResponse,
    tags=["Projects"],
    summary="List monitored projects",
)
async def list_projects():
    """Get all projects being monitored for schema changes."""
    detector = get_schema_detector()
    projects = []
    
    for name, path in detector.list_projects().items():
        projects.append(ProjectResponse(
            name=name,
            path=str(path),
            exists=Path(path).exists(),
        ))
    
    return ProjectListResponse(projects=projects, count=len(projects))


@app.post(
    "/projects",
    response_model=SuccessResponse,
    tags=["Projects"],
    summary="Add a project to monitor",
)
async def add_project(project: ProjectCreate):
    """
    Add a new project to the schema change detector.
    
    The project path must exist and be a valid git repository.
    """
    path = Path(project.path).expanduser()
    
    # Validate path exists
    if not path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Path does not exist: {project.path}"
        )
    
    # Validate it's a git repo
    if not (path / ".git").exists():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a git repository: {project.path}"
        )
    
    # Add project
    detector = get_schema_detector()
    success = detector.add_project(project.name, path)
    
    if success:
        return SuccessResponse(
            success=True,
            message=f"Project '{project.name}' added successfully"
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to add project '{project.name}'"
        )


@app.delete(
    "/projects/{name}",
    response_model=SuccessResponse,
    tags=["Projects"],
    summary="Remove a project from monitoring",
)
async def remove_project(name: str):
    """
    Remove a project from the schema change detector.
    
    Note: Cannot remove the main 'agent007' project.
    """
    if name == "agent007":
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the main agent007 project"
        )
    
    detector = get_schema_detector()
    success = detector.remove_project(name)
    
    if success:
        return SuccessResponse(
            success=True,
            message=f"Project '{name}' removed successfully"
        )
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{name}' not found"
        )


@app.post(
    "/projects/batch",
    response_model=SuccessResponse,
    tags=["Projects"],
    summary="Add multiple projects at once",
)
async def add_projects_batch(projects: List[ProjectCreate]):
    """Add multiple projects in a single request."""
    detector = get_schema_detector()
    added = []
    failed = []
    
    for project in projects:
        path = Path(project.path).expanduser()
        
        if not path.exists():
            failed.append(f"{project.name}: path does not exist")
            continue
        
        if detector.add_project(project.name, path):
            added.append(project.name)
        else:
            failed.append(f"{project.name}: failed to add")
    
    if failed:
        return SuccessResponse(
            success=len(added) > 0,
            message=f"Added: {added}. Failed: {failed}"
        )
    
    return SuccessResponse(
        success=True,
        message=f"Added {len(added)} projects: {added}"
    )


# ============================================================================
# Schema Detection Endpoints
# ============================================================================

@app.get(
    "/schema/changes",
    response_model=List[SchemaChangeResponse],
    tags=["Schema"],
    summary="Get detected schema changes",
)
async def get_schema_changes(
    since: str = Query("7 days ago", description="How far back to look"),
    limit: int = Query(20, description="Max commits per project"),
    project: Optional[str] = Query(None, description="Filter by project"),
    include_reviewed: bool = Query(False, description="Include reviewed changes"),
):
    """Get all detected schema changes across monitored projects."""
    detector = get_schema_detector()
    
    projects = [project] if project else None
    changes = detector.detect_changes(
        since=since,
        limit=limit,
        include_reviewed=include_reviewed,
        projects=projects,
    )
    
    return [
        SchemaChangeResponse(
            id=c.id,
            type=c.type.value,
            file_path=c.file_path,
            commit_hash=c.commit_hash,
            commit_message=c.commit_message,
            commit_date=c.commit_date,
            author=c.author,
            project=c.project,
            lines_added=c.lines_added,
            lines_removed=c.lines_removed,
            preview=c.preview,
            reviewed=c.reviewed,
        )
        for c in changes
    ]


@app.get(
    "/schema/summary",
    response_model=SchemaSummaryResponse,
    tags=["Schema"],
    summary="Get schema change summary",
)
async def get_schema_summary():
    """Get a summary of schema changes."""
    detector = get_schema_detector()
    summary = detector.get_summary()
    
    return SchemaSummaryResponse(
        total=summary["total"],
        unreviewed=summary["unreviewed"],
        by_type=summary.get("by_type", {}),
        by_project=summary.get("by_project", {}),
        monitored_projects=summary.get("monitored_projects", []),
        last_check=summary.get("last_check"),
    )


@app.post(
    "/schema/review/{change_id}",
    response_model=SuccessResponse,
    tags=["Schema"],
    summary="Mark a schema change as reviewed",
)
async def mark_reviewed(
    change_id: str,
    reviewer: str = Query("api", description="Reviewer identifier"),
):
    """Mark a schema change as reviewed."""
    detector = get_schema_detector()
    detector.mark_reviewed(change_id, reviewer)
    
    return SuccessResponse(
        success=True,
        message=f"Change '{change_id}' marked as reviewed by {reviewer}"
    )


@app.post(
    "/schema/refresh",
    response_model=SchemaSummaryResponse,
    tags=["Schema"],
    summary="Refresh schema change detection",
)
async def refresh_schema_detection(
    since: str = Query("7 days ago", description="How far back to look"),
):
    """Force a refresh of schema change detection."""
    detector = get_schema_detector()
    detector.detect_changes(since=since)
    summary = detector.get_summary()
    
    return SchemaSummaryResponse(
        total=summary["total"],
        unreviewed=summary["unreviewed"],
        by_type=summary.get("by_type", {}),
        by_project=summary.get("by_project", {}),
        monitored_projects=summary.get("monitored_projects", []),
        last_check=summary.get("last_check"),
    )


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8502"))
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    Orchestrator REST API                      ║
╠═══════════════════════════════════════════════════════════════╣
║  Endpoints:                                                   ║
║    GET  /projects           - List monitored projects         ║
║    POST /projects           - Add a project to monitor        ║
║    DELETE /projects/:name   - Remove a project                ║
║    GET  /schema/changes     - Get schema changes              ║
║    GET  /schema/summary     - Get summary stats               ║
║    POST /schema/review/:id  - Mark change as reviewed         ║
║                                                               ║
║  Docs: http://localhost:{port}/docs                            ║
╚═══════════════════════════════════════════════════════════════╝
""")
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )


# DEBUG: Test auth endpoint
@app.get("/debug/auth")
async def debug_auth():
    """Debug Google auth status."""
    from services.google_auth import get_google_auth, TOKEN_FILE
    
    auth = get_google_auth()
    
    return {
        "token_file_exists": TOKEN_FILE.exists(),
        "token_file_path": str(TOKEN_FILE),
        "is_authenticated": auth.is_authenticated,
        "credentials_valid": auth.credentials.valid if auth.credentials else None,
        "credentials_expired": auth.credentials.expired if auth.credentials else None,
    }


# DEBUG: Test docs_list_files directly
@app.get("/debug/drive")
async def debug_drive():
    """Debug Drive client."""
    try:
        from services.drive.client import get_drive_client
        
        client = get_drive_client()
        files = client.list_files(page_size=3)
        
        return {
            "success": True,
            "count": len(files),
            "files": [f.name for f in files],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# DEBUG: Test sheets auth
@app.get("/debug/sheets")
async def debug_sheets():
    """Debug sheets authentication."""
    results = {}
    
    # Test google_auth
    try:
        from services.google_auth import get_google_auth
        auth = get_google_auth()
        results["google_auth"] = {
            "is_authenticated": auth.is_authenticated,
            "has_credentials": auth.credentials is not None,
        }
    except Exception as e:
        results["google_auth"] = {"error": str(e)}
    
    # Test sheets client
    try:
        from services.sheets import get_sheets_client
        client = get_sheets_client()
        results["sheets_client"] = {
            "is_available": client.is_available,
        }
        
        # Try authenticate
        auth_result = client.authenticate(headless=True)
        results["sheets_auth"] = {"success": auth_result}
        
        # Try read
        values = client.get_values("1AKRK_nAKoDwSUnzl5r9L_KaOD8aNMl8EeROJYZuGYdc", "A1:B3")
        results["sheets_read"] = {"rows": len(values), "data": values}
    except Exception as e:
        results["sheets_error"] = str(e)
    
    return results


# ============================================================================
# Approval System
# ============================================================================

# Store pending approvals (in-memory for now)
pending_approvals: Dict[str, Dict[str, Any]] = {}

@app.post("/api/approve")
async def approve_action(request: Dict[str, Any]):
    """
    Approve or reject a pending action.
    
    Body:
        approval_id: str - The approval request ID
        approved: bool - True to approve, False to reject
        tool_name: Optional[str] - Tool name to execute
        arguments: Optional[Dict] - Tool arguments
    """
    approval_id = request.get("approval_id")
    approved = request.get("approved", False)
    tool_name = request.get("tool_name")
    arguments = request.get("arguments", {})
    
    if not approval_id:
        return {"error": "Missing approval_id"}
    
    if approved:
        # Execute the approved action
        from services.tool_registry import execute_tool
        
        if not tool_name:
            return {"error": "Missing tool_name"}
        
        try:
            # Execute with skip_confirmation=True
            result = execute_tool(tool_name, arguments, skip_confirmation=True)
            
            return {
                "approved": True,
                "executed": True,
                "tool": tool_name,
                "result": result
            }
        except Exception as e:
            return {
                "approved": True,
                "executed": False,
                "error": str(e)
            }
    else:
        # User rejected the action
        return {
            "approved": False,
            "executed": False,
            "message": "Action cancelled by user"
        }


@app.get("/api/approvals/pending")
async def get_pending_approvals():
    """List all pending approvals."""
    return {
        "count": len(pending_approvals),
        "approvals": list(pending_approvals.values())
    }
