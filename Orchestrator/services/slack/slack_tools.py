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
    
    if not client.is_available():
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
    
    if not client.is_available():
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
    
    if not client.is_available():
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
