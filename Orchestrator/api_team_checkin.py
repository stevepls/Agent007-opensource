"""
Team Check-in Agent API Endpoints

Provides REST API for message approval and manual triggers.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.team_checkin.agent import TeamCheckinAgent
from services.message_queue import get_message_queue, MessageType, MessageStatus

# Register Slack DM sender globally when module loads
def _register_slack_sender():
    """Register Slack DM sender with the message queue."""
    try:
        queue = get_message_queue()
        if MessageType.SLACK_DM not in queue._senders:
            # Initialize agent to register sender
            agent = TeamCheckinAgent()
            # Sender should now be registered
            if MessageType.SLACK_DM in queue._senders:
                print("✅ Slack DM sender registered globally")
    except Exception as e:
        print(f"⚠️ Could not register Slack sender (will retry on first use): {e}")

# Register on import (non-fatal)
try:
    _register_slack_sender()
except Exception as e:
    print(f"⚠️ Slack sender deferred: {e}")

router = APIRouter(prefix="/team-checkin", tags=["Team Check-in"])

# ============================================================================
# Cached Agent Instance (avoid re-initializing on every request)
# ============================================================================
_cached_agent: Optional[TeamCheckinAgent] = None
_agent_init_time: Optional[datetime] = None
AGENT_CACHE_TTL_SECONDS = 300  # Refresh every 5 minutes


def _get_agent() -> TeamCheckinAgent:
    """Get or create a cached TeamCheckinAgent instance."""
    global _cached_agent, _agent_init_time
    now = datetime.utcnow()
    if (
        _cached_agent is None
        or _agent_init_time is None
        or (now - _agent_init_time).total_seconds() > AGENT_CACHE_TTL_SECONDS
    ):
        _cached_agent = TeamCheckinAgent()
        _agent_init_time = now
    return _cached_agent

# Path to approval UI HTML file
APPROVAL_UI_PATH = Path(__file__).parent.parent / "agents" / "team_checkin" / "approval_ui.html"


# ============================================================================
# Request/Response Models
# ============================================================================

class MessageResponse(BaseModel):
    id: str
    member_name: str
    member_slack_id: Optional[str]
    message_text: str
    message_type: str
    created_at: str
    status: str
    approved_at: Optional[str] = None
    sent_at: Optional[str] = None
    error: Optional[str] = None
    context: Dict[str, Any] = {}


class ApproveRequest(BaseModel):
    message_id: str


class RejectRequest(BaseModel):
    message_id: str


class TriggerFollowupRequest(BaseModel):
    member_name: Optional[str] = None  # If None, triggers for all eligible members


class TriggerResponse(BaseModel):
    success: bool
    messages_queued: int
    message_ids: List[str]
    error: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/ui", response_class=HTMLResponse)
async def get_approval_ui():
    """Serve the approval UI HTML page."""
    # Calculate path relative to Orchestrator root
    orchestrator_root = Path(__file__).parent
    ui_path = orchestrator_root / "agents" / "team_checkin" / "approval_ui.html"
    
    if not ui_path.exists():
        raise HTTPException(status_code=404, detail=f"Approval UI not found at {ui_path}")
    
    with open(ui_path, 'r', encoding='utf-8') as f:
        return HTMLResponse(content=f.read())


@router.get("/messages/pending", response_model=List[MessageResponse])
async def get_pending_messages():
    """Get all pending messages awaiting approval."""
    queue = get_message_queue()
    
    # Force reload from disk to ensure we have latest data
    try:
        queue._load()
    except Exception:
        pass  # If reload fails, continue with in-memory data
    
    # Get messages requiring approval (pending_approval status)
    pending_messages = queue.list_requiring_approval()
    team_messages = [
        msg for msg in pending_messages 
        if msg.type == MessageType.SLACK_DM and msg.metadata.get("team_checkin")
    ]
    
    # Convert to response format
    results = []
    for msg in team_messages:
        results.append(MessageResponse(
            id=msg.id,
            member_name=msg.metadata.get("member_name", "Unknown"),
            member_slack_id=msg.channel,
            message_text=msg.content,
            message_type=msg.metadata.get("message_type", "unknown"),
            created_at=msg.created_at,
            status=msg.status.value,
            context=msg.metadata
        ))
    
    return results


@router.get("/messages/{message_id}", response_model=MessageResponse)
async def get_message(message_id: str):
    """Get a specific message by ID."""
    queue = get_message_queue()
    message = queue.get(message_id)
    if not message or not (message.type == MessageType.SLACK_DM and message.metadata.get("team_checkin")):
        raise HTTPException(status_code=404, detail="Message not found")
    
    return MessageResponse(
        id=message.id,
        member_name=message.metadata.get("member_name", "Unknown"),
        member_slack_id=message.channel,
        message_text=message.content,
        message_type=message.metadata.get("message_type", "unknown"),
        created_at=message.created_at,
        status=message.status.value,
        context=message.metadata
    )


@router.post("/messages/{message_id}/approve")
async def approve_message(message_id: str):
    """Approve a message (marks it ready to send)."""
    queue = get_message_queue()
    message = queue.get(message_id)
    
    if not message or not (message.type == MessageType.SLACK_DM and message.metadata.get("team_checkin")):
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message.status != MessageStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=400, detail=f"Message is not pending approval (status: {message.status.value})")
    
    # Approve through orchestrator queue
    approved_msg = queue.approve(message_id, approved_by="team_checkin_ui")
    
    if not approved_msg:
        raise HTTPException(status_code=400, detail="Failed to approve message")
    
    # Update agent state after approval
    try:
        agent = _get_agent()
        from agents.team_checkin.agent import TeamMember
        member = TeamMember(
            name=message.metadata.get("member_name", ""),
            slack_user_id=message.channel
        )
        
        # Update state if morning message
        if message.metadata.get("message_type") == "morning":
            state = agent._get_member_state(member)
            state.last_nudged = datetime.now().isoformat()
            state.morning_greeting_sent = True
            agent._save_state()
            # Start timer and update task
            agent._start_hubstaff_timer(member)
            agent._update_task_status(member, "in progress")
        elif message.metadata.get("message_type") == "followup":
            state = agent._get_member_state(member)
            state.last_nudged = datetime.now().isoformat()
            agent._save_state()
    except Exception as e:
        # Log but don't fail - message is already approved
        print(f"Warning: Failed to update agent state: {e}")
    
    return {"success": True, "status": "approved", "message_id": message_id}


@router.post("/messages/{message_id}/reject")
async def reject_message(message_id: str):
    """Reject a message."""
    queue = get_message_queue()
    message = queue.get(message_id)
    
    if not message or not (message.type == MessageType.SLACK_DM and message.metadata.get("team_checkin")):
        raise HTTPException(status_code=404, detail="Message not found")
    
    cancelled = queue.cancel(message_id, cancelled_by="team_checkin_ui", reason="Rejected by user")
    
    if not cancelled:
        raise HTTPException(status_code=400, detail="Message cannot be cancelled")
    
    return {"success": True, "status": "rejected"}


@router.post("/trigger/followup", response_model=TriggerResponse)
async def trigger_followup(request: TriggerFollowupRequest = Body(...)):
    """Manually trigger follow-up check-ins for team members."""
    try:
        agent = _get_agent()
        queue = get_message_queue()
        messages_queued = 0
        message_ids = []
        
        # Filter members if specific member requested
        members_to_check = agent.team_members
        if request.member_name:
            members_to_check = [m for m in members_to_check if m.name == request.member_name]
            if not members_to_check:
                return TriggerResponse(
                    success=False,
                    messages_queued=0,
                    message_ids=[],
                    error=f"Member '{request.member_name}' not found"
                )
        
        # Process each member
        for member in members_to_check:
            try:
                # Check if they need a follow-up
                state = agent._get_member_state(member)
                
                # Skip if they've responded or are done
                if state.responded_today or state.done_for_today:
                    continue
                
                # Check for activity
                if agent._has_recent_activity(member):
                    continue
                
                # Calculate quiet time
                quiet_hours = agent.CHECK_INTERVAL_HOURS
                if state.last_activity:
                    last_activity = datetime.fromisoformat(state.last_activity)
                    quiet_hours = (datetime.utcnow() - last_activity).total_seconds() / 3600
                
                # Generate follow-up message
                message_text = agent._generate_followup_message(member, quiet_hours)
                
                # Queue for approval via the correct queue.queue() method
                msg = queue.queue(
                    msg_type=MessageType.SLACK_DM,
                    channel=member.slack_user_id or "",
                    content=message_text,
                    metadata={
                        "team_checkin": True,
                        "member_name": member.name,
                        "message_type": "followup",
                        "quiet_hours": quiet_hours,
                        "priority_task": member.priority_tasks[0].get("name") if member.priority_tasks else None,
                    },
                    requires_approval=True,
                )
                message_ids.append(msg.id)
                messages_queued += 1
                
            except Exception as e:
                print(f"⚠️ Follow-up trigger failed for {member.name}: {e}")
                continue
        
        return TriggerResponse(
            success=True,
            messages_queued=messages_queued,
            message_ids=message_ids
        )
    
    except Exception as e:
        return TriggerResponse(
            success=False,
            messages_queued=0,
            message_ids=[],
            error=str(e)
        )


@router.get("/members", response_model=List[Dict[str, Any]])
async def get_team_members():
    """Get list of team members."""
    try:
        agent = _get_agent()
        members = []
        for member in agent.team_members:
            state = agent._get_member_state(member)
            members.append({
                "name": member.name,
                "slack_user_id": member.slack_user_id,
                "github_username": member.github_username,
                "has_priority_tasks": len(member.priority_tasks) > 0,
                "priority_tasks_count": len(member.priority_tasks),
                "last_nudged": state.last_nudged,
                "responded_today": state.responded_today,
                "done_for_today": state.done_for_today
            })
        return members
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger/morning")
async def trigger_morning_checkin():
    """Manually trigger morning check-ins for all team members."""
    try:
        agent = _get_agent()
        queue = get_message_queue()
        messages_queued = 0
        message_ids = []
        
        for member in agent.team_members:
            try:
                # Generate morning message
                message_text = agent._generate_morning_message(member)
                
                # Queue for approval via the correct queue.queue() method
                msg = queue.queue(
                    msg_type=MessageType.SLACK_DM,
                    channel=member.slack_user_id or "",
                    content=message_text,
                    metadata={
                        "team_checkin": True,
                        "member_name": member.name,
                        "message_type": "morning",
                        "priority_tasks": member.priority_tasks,
                    },
                    requires_approval=True,
                )
                message_ids.append(msg.id)
                messages_queued += 1
                
            except Exception as e:
                print(f"⚠️ Morning trigger failed for {member.name}: {e}")
                continue
        
        return {
            "success": True,
            "messages_queued": messages_queued,
            "message_ids": message_ids
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
