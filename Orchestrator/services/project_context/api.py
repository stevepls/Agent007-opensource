"""
Project Context API

FastAPI endpoints for project context aggregation.
Can run standalone or be mounted into the main Orchestrator app.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from .aggregator import ProjectContextAggregator, DataSource
from .poc_agent import get_poc_agent, list_poc_agents, create_poc_agent


# Pydantic models for API responses
class TaskResponse(BaseModel):
    id: str
    source: str
    title: str
    status: str
    priority: Optional[str]
    assignee: Optional[str]
    updated_at: str
    url: str
    tags: List[str]


class MessageResponse(BaseModel):
    id: str
    source: str
    subject: str
    sender: str
    timestamp: str
    is_read: bool


class TimeEntryResponse(BaseModel):
    id: str
    date: str
    hours: float
    notes: str
    task: Optional[str]
    user: str


class ProjectContextResponse(BaseModel):
    project_id: str
    project_name: str
    total_open_tasks: int
    total_hours_logged: float
    unread_messages: int
    stale_days: int
    blocked_tasks: int
    last_activity: Optional[str]
    open_tasks: List[TaskResponse]
    recent_messages: List[MessageResponse]
    time_entries: List[TimeEntryResponse]


class ProjectListResponse(BaseModel):
    projects: List[str]


class BriefingResponse(BaseModel):
    project_id: str
    briefing: str
    generated_at: str


class QuestionRequest(BaseModel):
    question: str


class AnswerResponse(BaseModel):
    project_id: str
    question: str
    answer: str


# Create FastAPI app
app = FastAPI(
    title="Project Context API",
    description="Aggregated project data from ClickUp, Zendesk, Slack, Gmail, Harvest",
    version="1.0.0",
)

# Singleton aggregator
_aggregator: Optional[ProjectContextAggregator] = None


def get_aggregator() -> ProjectContextAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = ProjectContextAggregator()
    return _aggregator


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/", tags=["Health"])
async def root():
    """API health check."""
    return {
        "status": "ok",
        "service": "Project Context API",
        "version": "1.0.0",
    }


@app.get("/projects", response_model=ProjectListResponse, tags=["Projects"])
async def list_projects():
    """List all configured projects."""
    aggregator = get_aggregator()
    return {"projects": aggregator.list_projects()}


@app.get("/projects/{project_id}", response_model=ProjectContextResponse, tags=["Projects"])
async def get_project_context(
    project_id: str,
    include_tasks: bool = Query(True, description="Include tasks from ClickUp/Zendesk"),
    include_messages: bool = Query(True, description="Include Slack/Gmail messages"),
    include_time: bool = Query(True, description="Include Harvest time entries"),
    days_back: int = Query(7, description="Days of history to fetch"),
):
    """Get complete context for a project."""
    aggregator = get_aggregator()
    
    if project_id not in aggregator.list_projects():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    
    ctx = aggregator.get_project_context(
        project_id,
        include_tasks=include_tasks,
        include_messages=include_messages,
        include_time=include_time,
        days_back=days_back,
    )
    
    return ProjectContextResponse(
        project_id=ctx.project_id,
        project_name=ctx.project_name,
        total_open_tasks=ctx.total_open_tasks,
        total_hours_logged=ctx.total_hours_logged,
        unread_messages=ctx.unread_messages,
        stale_days=ctx.stale_days,
        blocked_tasks=ctx.blocked_tasks,
        last_activity=ctx.last_activity.isoformat() if ctx.last_activity else None,
        open_tasks=[
            TaskResponse(
                id=t.id,
                source=t.source.value,
                title=t.title,
                status=t.status,
                priority=t.priority,
                assignee=t.assignee,
                updated_at=t.updated_at.isoformat(),
                url=t.url,
                tags=t.tags,
            )
            for t in ctx.open_tasks
        ],
        recent_messages=[
            MessageResponse(
                id=m.id,
                source=m.source.value,
                subject=m.subject,
                sender=m.sender,
                timestamp=m.timestamp.isoformat(),
                is_read=m.is_read,
            )
            for m in ctx.recent_messages
        ],
        time_entries=[
            TimeEntryResponse(
                id=e.id,
                date=e.date.isoformat(),
                hours=e.hours,
                notes=e.notes,
                task=e.task,
                user=e.user,
            )
            for e in ctx.time_entries
        ],
    )


@app.get("/projects/{project_id}/summary", tags=["Projects"])
async def get_project_summary(project_id: str):
    """Get a text summary of project status."""
    aggregator = get_aggregator()
    
    if project_id not in aggregator.list_projects():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    
    summary = aggregator.get_project_summary(project_id)
    return {"project_id": project_id, "summary": summary}


# =============================================================================
# POC AGENT ENDPOINTS
# =============================================================================

@app.get("/agents", tags=["POC Agents"])
async def list_agents():
    """List all active POC agents."""
    return {"agents": list_poc_agents()}


@app.post("/agents/{project_id}/activate", tags=["POC Agents"])
async def activate_poc_agent(project_id: str):
    """Activate a POC agent for a project."""
    aggregator = get_aggregator()
    
    if project_id not in aggregator.list_projects():
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    
    agent = get_poc_agent(project_id)
    agent.refresh_context()
    
    return {
        "status": "activated",
        "project_id": project_id,
        "project_name": agent.context.project_name,
    }


@app.get("/agents/{project_id}/briefing", response_model=BriefingResponse, tags=["POC Agents"])
async def get_briefing(project_id: str):
    """Get a status briefing from the POC agent."""
    agent = get_poc_agent(project_id)
    briefing = agent.get_status_briefing()
    
    return BriefingResponse(
        project_id=project_id,
        briefing=briefing,
        generated_at=datetime.utcnow().isoformat(),
    )


@app.post("/agents/{project_id}/ask", response_model=AnswerResponse, tags=["POC Agents"])
async def ask_poc_agent(project_id: str, request: QuestionRequest):
    """Ask the POC agent a question about the project."""
    agent = get_poc_agent(project_id)
    answer = agent.answer_question(request.question)
    
    return AnswerResponse(
        project_id=project_id,
        question=request.question,
        answer=answer,
    )


@app.post("/agents/{project_id}/refresh", tags=["POC Agents"])
async def refresh_agent_context(project_id: str):
    """Force refresh the POC agent's context."""
    agent = get_poc_agent(project_id)
    agent.refresh_context()
    
    return {
        "status": "refreshed",
        "project_id": project_id,
        "last_refresh": agent._last_refresh.isoformat() if agent._last_refresh else None,
    }


# =============================================================================
# STANDALONE RUNNER
# =============================================================================

def run_api(host: str = "0.0.0.0", port: int = 8100):
    """Run the API standalone."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_api()
