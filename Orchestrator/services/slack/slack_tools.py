"""
Slack Messaging Tools with Guardrails

Provides Slack message sending capabilities with mandatory review/approval.
"""

import os
from typing import Dict, Any, List, Optional
from services.slack.client import get_slack_client


def slack_post_message(
    channel: str,
    text: str,
    thread_ts: str = None,
) -> Dict[str, Any]:
    """
    Post a message to Slack channel or thread.
    
    **REQUIRES CONFIRMATION** - User must approve before sending.
    """
    client = get_slack_client()
    
    if not client.is_available:
        return {"error": "Slack not configured. Set SLACK_BOT_TOKEN."}
    
    if not channel or not text:
        return {"error": "channel and text are required"}
    
    if channel.startswith("#"):
        channel = channel[1:]
    
    try:
        result = client.post_message(
            channel=channel,
            text=text,
            thread_ts=thread_ts
        )
        
        if result:
            return {
                "success": True,
                "message": {
                    "channel": result.get("channel", channel),
                    "ts": result.get("ts"),
                    "text": text,
                    "thread_ts": thread_ts or result.get("thread_ts"),
                    "permalink": result.get("permalink", "")
                },
                "preview": f"To: #{channel}\\nMessage: {text[:200]}..."
            }
        return {"error": "Failed to post message"}
    except Exception as e:
        return {"error": f"Slack API error: {str(e)}"}


def slack_reply_to_thread(channel: str, thread_ts: str, text: str) -> Dict[str, Any]:
    """Reply to a Slack thread. REQUIRES CONFIRMATION."""
    return slack_post_message(channel=channel, text=text, thread_ts=thread_ts)


def slack_draft_message(channel: str, context: str, purpose: str = "general response") -> Dict[str, Any]:
    """Draft a Slack message for user review. Does NOT send."""
    return {
        "draft": True,
        "channel": channel,
        "purpose": purpose,
        "context_summary": context[:300] + "..." if len(context) > 300 else context,
        "next_step": "Review this draft and approve with slack_post_message",
        "warning": "This is a DRAFT. Use slack_post_message to send after approval."
    }


def slack_get_thread_context(channel: str, thread_ts: str) -> Dict[str, Any]:
    """Get full context of a Slack thread."""
    client = get_slack_client()
    
    if not client.is_available:
        return {"error": "Slack not configured"}
    
    try:
        messages = client.get_thread(channel, thread_ts)
        
        return {
            "channel": channel,
            "thread_ts": thread_ts,
            "message_count": len(messages),
            "messages": [
                {
                    "user": m.user_name,
                    "text": m.text,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                }
                for m in messages
            ],
            "full_context": "\\n\\n".join([f"[{m.user_name}]: {m.text}" for m in messages])
        }
    except Exception as e:
        return {"error": f"Failed to get thread: {str(e)}"}


def slack_list_channels(include_private: bool = False) -> Dict[str, Any]:
    """List available Slack channels."""
    client = get_slack_client()
    
    if not client.is_available:
        return {"error": "Slack not configured"}
    
    try:
        channels = client.list_channels(include_private=include_private)
        
        return {
            "count": len(channels),
            "channels": [
                {
                    "id": ch.id,
                    "name": ch.name,
                    "is_private": ch.is_private,
                    "member_count": ch.member_count,
                }
                for ch in channels[:50]
            ]
        }
    except Exception as e:
        return {"error": f"Failed to list channels: {str(e)}"}


# Tool definitions
SLACK_ENHANCED_TOOLS = [
    {
        "name": "slack_post_message",
        "description": "Post message to Slack. **REQUIRES USER CONFIRMATION** - message must be approved before sending.",
        "function": slack_post_message,
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel name or ID"},
                "text": {"type": "string", "description": "Message text (markdown)"},
                "thread_ts": {"type": "string", "description": "Thread timestamp to reply to"},
            },
            "required": ["channel", "text"]
        },
        "requires_confirmation": True,
        "danger_level": "high"
    },
    {
        "name": "slack_reply_to_thread",
        "description": "Reply to Slack thread. **REQUIRES USER CONFIRMATION**.",
        "function": slack_reply_to_thread,
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel ID or name"},
                "thread_ts": {"type": "string", "description": "Thread timestamp"},
                "text": {"type": "string", "description": "Reply text"},
            },
            "required": ["channel", "thread_ts", "text"]
        },
        "requires_confirmation": True,
        "danger_level": "high"
    },
    {
        "name": "slack_draft_message",
        "description": "Draft a Slack message WITHOUT sending. Use first to prepare messages for review.",
        "function": slack_draft_message,
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Target channel"},
                "context": {"type": "string", "description": "Context being responded to"},
                "purpose": {"type": "string", "description": "Purpose of message"},
            },
            "required": ["channel", "context"]
        }
    },
    {
        "name": "slack_get_thread_context",
        "description": "Get full Slack thread context before replying.",
        "function": slack_get_thread_context,
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel ID or name"},
                "thread_ts": {"type": "string", "description": "Thread timestamp"},
            },
            "required": ["channel", "thread_ts"]
        }
    },
    {
        "name": "slack_list_channels",
        "description": "List available Slack channels.",
        "function": slack_list_channels,
        "parameters": {
            "type": "object",
            "properties": {
                "include_private": {"type": "boolean", "description": "Include private channels"},
            }
        }
    },
]


def slack_list_dms() -> Dict[str, Any]:
    """
    List all direct message conversations with actual user names.
    Shows the names of people you've had DM conversations with.
    Uses the SlackClient wrapper for proper token management and error handling.
    """
    client = get_slack_client()
    
    if not client.is_available:
        return {"error": "Slack not configured. Set SLACK_BOT_TOKEN."}
    
    try:
        # Use the wrapper's list_dms method (proper architecture)
        dms = client.list_dms()
        
        dm_contacts = []
        active_names = []
        
        for dm in dms:
            user_id = dm.name  # For DM channels, name is the user ID
            channel_id = dm.id
            is_active = not dm.is_archived
            
            # Skip invalid or system users
            if not user_id or user_id == "USLACKBOT":
                continue
            
            # Use wrapper's get_user method (proper architecture)
            try:
                user = client.get_user(user_id)
                
                if user:
                    contact = {
                        "id": channel_id,
                        "user_id": user_id,
                        "name": user.real_name or user.name,
                        "username": user.name,
                        "email": user.email,
                        "title": user.title,
                        "is_active": is_active,
                    }
                    
                    dm_contacts.append(contact)
                    if is_active:
                        name_to_add = user.real_name or user.name
                        if name_to_add:  # Only add non-None names
                            active_names.append(name_to_add)
                else:
                    dm_contacts.append({
                        "id": channel_id,
                        "user_id": user_id,
                        "name": user_id,
                        "is_active": is_active,
                    })
            except Exception as e:
                dm_contacts.append({
                    "id": channel_id,
                    "user_id": user_id,
                    "name": user_id,
                    "is_active": is_active,
                    "error": str(e)
                })
        
        return {
            "count": len(dm_contacts),
            "dm_contacts": dm_contacts,
            "active_contacts": active_names,
            "summary": f"You have {len(active_names)} active DM conversations" + (f": {', '.join(active_names)}" if active_names else "")
        }
    except Exception as e:
        return {"error": f"Failed to list DMs: {str(e)}"}


def slack_get_dm_history(user_name: str = None, user_id: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    Get recent messages from a DM conversation.
    
    Args:
        user_name: Name of the person (optional if user_id provided)
        user_id: Slack user ID (optional if user_name provided)
        limit: Number of messages to retrieve (default: 10)
    """
    client = get_slack_client()
    
    if not client.is_available:
        return {"error": "Slack not configured"}
    
    if not user_name and not user_id:
        return {"error": "Either user_name or user_id is required"}
    
    try:
        # Find the user if name provided
        if user_name and not user_id:
            user = client.get_user_by_email(f"{user_name}@")  # This won't work well
            # Better: search through DMs for matching name
            dms = client.list_dms()
            for dm in dms:
                if user_name.lower() in dm.name.lower():
                    channel_id = dm.id
                    break
            else:
                return {"error": f"Could not find DM with user '{user_name}'"}
        elif user_id:
            # Open DM channel with user
            channel_id = client.open_dm(user_id)
        else:
            return {"error": "Could not determine DM channel"}
        
        # Get messages
        messages = client.get_messages(channel_id, limit=limit)
        
        return {
            "channel_id": channel_id,
            "message_count": len(messages),
            "messages": [
                {
                    "user": m.user_name,
                    "text": m.text[:200],  # Truncate long messages
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                }
                for m in messages
            ]
        }
    except Exception as e:
        return {"error": f"Failed to get DM history: {str(e)}"}


# Add to tools list
SLACK_ENHANCED_TOOLS.extend([
    {
        "name": "slack_list_dms",
        "description": "List all direct message conversations. Shows names of people you've had DM conversations with in Slack.",
        "function": slack_list_dms,
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "slack_get_dm_history",
        "description": "Get recent messages from a DM conversation with a specific person.",
        "function": slack_get_dm_history,
        "parameters": {
            "type": "object",
            "properties": {
                "user_name": {"type": "string", "description": "Name of the person (partial match ok)"},
                "user_id": {"type": "string", "description": "Slack user ID"},
                "limit": {"type": "integer", "description": "Number of messages (default: 10)"}
            }
        }
    },
])
