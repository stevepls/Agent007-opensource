"""
Harvest Time Tracking API Endpoints

Exposes Harvest functionality through REST endpoints.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.harvest_client import (
    get_harvest_client,
    is_harvest_configured,
)


router = APIRouter(prefix="/api/harvest", tags=["Harvest Time Tracking"])


# ============================================================================
# Models
# ============================================================================

class TimeEntryCreate(BaseModel):
    """Request to create a time entry."""
    project_id: int
    task_id: int
    hours: Optional[float] = None
    notes: Optional[str] = None
    date: Optional[str] = Field(None, description="ISO date string (YYYY-MM-DD)")


class TimerStart(BaseModel):
    """Request to start a timer."""
    project_id: int
    task_id: int
    notes: Optional[str] = None


class TimeEntryUpdate(BaseModel):
    """Request to update a time entry."""
    hours: Optional[float] = None
    notes: Optional[str] = None


class QuickLogRequest(BaseModel):
    """Quick log time by project name."""
    project_name: str
    hours: float
    notes: Optional[str] = None
    task_name: Optional[str] = Field("Development", description="Task name to use")


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/status")
async def get_harvest_status():
    """Check if Harvest is configured and available."""
    configured = is_harvest_configured()
    
    if not configured:
        return {
            "configured": False,
            "message": "Harvest not configured. Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID",
            "setup_url": "https://id.getharvest.com/developers",
        }
    
    # Test connection
    try:
        client = get_harvest_client()
        if client:
            await client.get_projects()
            return {"configured": True, "connected": True}
    except Exception as e:
        return {
            "configured": True,
            "connected": False,
            "error": str(e),
        }


@router.get("/summary")
async def get_time_summary():
    """Get time summary for today, this week, and this month."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(
            status_code=503,
            detail="Harvest not configured. Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID",
        )
    
    try:
        summary = await client.get_time_summary()
        
        return {
            "hours_today": summary.hours_today,
            "hours_this_week": summary.hours_this_week,
            "hours_this_month": summary.hours_this_month,
            "entries_today": [e.to_dict() for e in summary.entries_today],
            "active_timer": summary.active_timer.to_dict() if summary.active_timer else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entries")
async def get_entries(
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    project_id: Optional[int] = Query(None, description="Filter by project ID"),
):
    """Get time entries for a date range."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        from_dt = date.fromisoformat(from_date) if from_date else None
        to_dt = date.fromisoformat(to_date) if to_date else None
        
        entries = await client.get_time_entries(
            from_date=from_dt,
            to_date=to_dt,
            project_id=project_id,
        )
        
        return {"entries": [e.to_dict() for e in entries]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entries/today")
async def get_today_entries():
    """Get all time entries for today."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        entries = await client.get_today_entries()
        total_hours = sum(e.hours for e in entries)
        
        return {
            "entries": [e.to_dict() for e in entries],
            "total_hours": round(total_hours, 2),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entries")
async def create_entry(request: TimeEntryCreate):
    """Create a new time entry."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        spent_date = date.fromisoformat(request.date) if request.date else None
        
        entry = await client.create_time_entry(
            project_id=request.project_id,
            task_id=request.task_id,
            hours=request.hours,
            notes=request.notes,
            spent_date=spent_date,
        )
        
        return {"success": True, "entry": entry.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/timer/start")
async def start_timer(request: TimerStart):
    """Start a new timer (stops any running timer first)."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        entry = await client.start_timer(
            project_id=request.project_id,
            task_id=request.task_id,
            notes=request.notes,
        )
        
        return {
            "success": True,
            "message": f"Timer started for {entry.project_name}",
            "entry": entry.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/timer/stop")
async def stop_timer():
    """Stop the currently running timer."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        running = await client.get_running_timer()
        
        if not running:
            return {"success": False, "message": "No timer is currently running"}
        
        entry = await client.stop_timer(running.id)
        
        return {
            "success": True,
            "message": f"Timer stopped. Logged {entry.hours}h to {entry.project_name}",
            "entry": entry.to_dict(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timer/current")
async def get_current_timer():
    """Get the currently running timer, if any."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        running = await client.get_running_timer()
        
        if running:
            return {"running": True, "entry": running.to_dict()}
        else:
            return {"running": False, "entry": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/entries/{entry_id}")
async def update_entry(entry_id: int, request: TimeEntryUpdate):
    """Update an existing time entry."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        entry = await client.update_entry(
            entry_id=entry_id,
            hours=request.hours,
            notes=request.notes,
        )
        
        return {"success": True, "entry": entry.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: int):
    """Delete a time entry."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        success = await client.delete_entry(entry_id)
        return {"success": success}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects")
async def get_projects(active_only: bool = True):
    """Get available projects."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        projects = await client.get_projects(active_only=active_only)
        
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "code": p.code,
                    "client_name": p.client_name,
                }
                for p in projects
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/tasks")
async def get_project_tasks(project_id: int):
    """Get tasks for a specific project."""
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        tasks = await client.get_project_tasks(project_id)
        return {"tasks": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quick-log")
async def quick_log_time(request: QuickLogRequest):
    """
    Quick log time by project name.
    Finds the project by name and logs time to the first matching task.
    """
    client = get_harvest_client()
    if not client:
        raise HTTPException(status_code=503, detail="Harvest not configured")
    
    try:
        # Find project
        project = await client.find_project_by_name(request.project_name)
        if not project:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{request.project_name}' not found",
            )
        
        # Get tasks for project
        tasks = await client.get_project_tasks(project.id)
        if not tasks:
            raise HTTPException(
                status_code=404,
                detail=f"No tasks found for project '{project.name}'",
            )
        
        # Find matching task or use first
        task = None
        if request.task_name:
            task_name_lower = request.task_name.lower()
            for t in tasks:
                if task_name_lower in t["name"].lower():
                    task = t
                    break
        
        if not task:
            task = tasks[0]  # Default to first task
        
        # Create entry
        entry = await client.create_time_entry(
            project_id=project.id,
            task_id=task["id"],
            hours=request.hours,
            notes=request.notes,
        )
        
        return {
            "success": True,
            "message": f"Logged {request.hours}h to {project.name} / {task['name']}",
            "entry": entry.to_dict(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
