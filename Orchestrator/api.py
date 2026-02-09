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
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop background services."""
    from services.prefetch_scheduler import get_prefetch_scheduler
    from services.task_queue import get_task_queue
    scheduler = get_prefetch_scheduler()
    scheduler.start()

    # Clean up old messages from queue on startup
    try:
        from services.message_queue import get_message_queue
        queue = get_message_queue()
        removed = queue.cleanup_old_messages(max_age_hours=72)
        if removed:
            print(f"🧹 Cleaned up {removed} old messages from queue")
    except Exception as e:
        print(f"⚠️ Queue cleanup skipped: {e}")

    yield
    scheduler.stop()
    get_task_queue().shutdown()


app = FastAPI(
    title="Orchestrator API",
    description="REST API for Agent007 Orchestrator services",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ============================================================================
# CORS — locked to known origins only
# ============================================================================
ALLOWED_ORIGINS = [
    origin.strip() for origin in
    os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()
] or [
    "https://orchestrator-staging-dda3.up.railway.app",
    "https://dashboard-staging-ba60.up.railway.app",
    "http://localhost:8502",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ============================================================================
# Security Headers Middleware
# ============================================================================
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Prevent clickjacking — only allow our own frames
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy — don't leak full URLs
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions policy — disable unnecessary browser features
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Content Security Policy — only load resources from self + Google (for OAuth/profile pics)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' https://*.googleusercontent.com data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "frame-ancestors 'self';"
        )
        # Strict Transport Security — force HTTPS for 1 year
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ============================================================================
# Authentication
# ============================================================================

# Import auth module
try:
    from api_auth import router as auth_router, get_current_user, is_public_path, AUTH_ENABLED, COOKIE_NAME
    app.include_router(auth_router)
    print(f"✅ Auth router registered (AUTH_ENABLED={AUTH_ENABLED})")

    # Service-to-service API key (dashboard → orchestrator calls)
    _SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", os.getenv("SESSION_SECRET_KEY", ""))

    class AuthMiddleware(BaseHTTPMiddleware):
        """Middleware to enforce authentication on all non-public routes.

        Accepts either:
        - A valid session cookie (browser users)
        - An X-Service-Key header matching SERVICE_API_KEY (dashboard backend)
        """
        async def dispatch(self, request: Request, call_next):
            path = request.url.path

            # Skip auth check for public paths
            if is_public_path(path):
                return await call_next(request)

            # Skip auth if disabled
            if not AUTH_ENABLED:
                return await call_next(request)

            # Accept service-to-service API key (for dashboard → orchestrator calls)
            service_key = request.headers.get("x-service-key", "")
            if service_key and _SERVICE_API_KEY and service_key == _SERVICE_API_KEY:
                request.state.user = {"email": "dashboard@internal", "name": "Dashboard Service"}
                return await call_next(request)

            # Check session cookie
            user = get_current_user(request)
            if not user:
                # For API calls (JSON), return 401
                accept = request.headers.get("accept", "")
                if "application/json" in accept or path.startswith("/api/") or path.startswith("/openapi"):
                    from fastapi.responses import JSONResponse
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Not authenticated. Please login via the dashboard."}
                    )
                # For browser requests, redirect to Dashboard (the one UI)
                dashboard_url = os.getenv("DASHBOARD_PUBLIC_URL", "https://dashboard-staging-ba60.up.railway.app")
                return RedirectResponse(url=dashboard_url)

            # Attach user to request state
            request.state.user = user
            return await call_next(request)

    app.add_middleware(AuthMiddleware)

except Exception as auth_err:
    print(f"⚠️ Auth module not loaded (auth disabled): {auth_err}")
    AUTH_ENABLED = False

# Include chat router for dashboard integration
if CHAT_AVAILABLE and chat_router:
    app.include_router(chat_router)

# Include team check-in router
try:
    from api_team_checkin import router as team_checkin_router
    app.include_router(team_checkin_router)
    print("✅ Team check-in router registered")
    # Ensure Slack sender is registered on startup
    try:
        from services.message_queue import get_message_queue, MessageType
        queue = get_message_queue()
        if MessageType.SLACK_DM not in queue._senders:
            from agents.team_checkin.agent import TeamCheckinAgent
            TeamCheckinAgent()  # Initialize to register sender
    except Exception as sender_err:
        print(f"⚠️ Slack sender registration deferred: {sender_err}")
except Exception as e:
    print(f"⚠️ Team check-in router not loaded: {e}")
    import traceback
    traceback.print_exc()

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

@app.get("/")
async def root(request: Request):
    """Root endpoint - redirect to Dashboard (the one UI) or API docs."""
    dashboard_url = os.getenv("DASHBOARD_PUBLIC_URL", "https://dashboard-staging-ba60.up.railway.app")
    user = None
    try:
        user = get_current_user(request)
    except Exception:
        pass
    # If authenticated, show API docs; otherwise redirect to Dashboard
    if user:
        return RedirectResponse(url="/docs")
    return RedirectResponse(url=dashboard_url)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    # Check harvest configuration
    harvest_configured = False
    if HARVEST_AVAILABLE:
        from services.harvest_client import is_harvest_configured
        harvest_configured = is_harvest_configured()

    # Cache & prefetch status
    from services.tool_cache import get_tool_cache
    from services.prefetch_scheduler import get_prefetch_scheduler
    from services.task_queue import get_task_queue
    cache = get_tool_cache()
    scheduler = get_prefetch_scheduler()
    task_queue = get_task_queue()

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "schema_detector": True,
            "briefing": BRIEFING_AVAILABLE,
            "message_queue": QUEUE_AVAILABLE,
            "harvest": harvest_configured,
        },
        "cache": cache.get_stats(),
        "prefetch": scheduler.get_status(),
        "task_queue": task_queue.get_status(),
    }


# ============================================================================
# Cache Management Endpoints
# ============================================================================

@app.get("/api/cache/stats", tags=["Cache"])
async def cache_stats():
    """Get cache hit/miss stats and prefetch job status."""
    from services.tool_cache import get_tool_cache
    from services.prefetch_scheduler import get_prefetch_scheduler
    return {
        "cache": get_tool_cache().get_stats(),
        "prefetch": get_prefetch_scheduler().get_status(),
    }


@app.post("/api/cache/invalidate", tags=["Cache"])
async def cache_invalidate(tool_name: Optional[str] = Query(None, description="Tool to invalidate (all if omitted)")):
    """Manually invalidate cache entries."""
    from services.tool_cache import get_tool_cache
    cache = get_tool_cache()
    cache.invalidate(tool_name)
    return {"success": True, "message": f"Invalidated {'all' if not tool_name else tool_name} cache entries"}


# ============================================================================
# Background Task Queue Endpoints
# ============================================================================

@app.get("/api/tasks", tags=["Tasks"])
async def list_tasks(status: Optional[str] = Query(None, description="Filter by status: queued, running, completed, failed")):
    """List all background tasks."""
    from services.task_queue import get_task_queue
    tasks = get_task_queue().list_tasks(status=status)
    return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}


@app.get("/api/tasks/updates", tags=["Tasks"])
async def get_task_updates():
    """Get unreported completed tasks (FIFO order) for polling."""
    from services.task_queue import get_task_queue
    queue = get_task_queue()
    updates = queue.get_unreported_updates()
    return {
        "updates": [t.to_dict() for t in updates],
        "count": len(updates),
    }


@app.get("/api/tasks/{task_id}", tags=["Tasks"])
async def get_task(task_id: str):
    """Get a specific background task's details and result."""
    from services.task_queue import get_task_queue
    task = get_task_queue().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@app.post("/api/tasks/{task_id}/cancel", tags=["Tasks"])
async def cancel_background_task(task_id: str):
    """Cancel a running or queued background task."""
    from services.task_queue import get_task_queue
    success = get_task_queue().cancel_task(task_id)
    if success:
        return {"success": True, "message": f"Cancellation requested for task {task_id}"}
    raise HTTPException(status_code=404, detail="Task not found or not cancellable")


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
