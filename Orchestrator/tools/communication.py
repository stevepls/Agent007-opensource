"""
Communication Tools for CrewAI Agents

Provides safe, controlled access to Gmail and Slack.
ALL outgoing messages:
1. Must use canned responses (no freeform text)
2. Go through the message queue with delay
3. Require human approval before sending
4. Are checked for grammar/spelling

AGENTS CANNOT SEND ARBITRARY MESSAGES.
"""

import sys
from pathlib import Path
from typing import List, Optional
from crewai.tools import BaseTool

# Add parent paths
TOOLS_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = TOOLS_ROOT.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.message_queue import (
    get_message_queue, MessageType, MessageStatus
)
from services.canned_responses import (
    get_response_registry, ResponseCategory, ResponseChannel
)
from services.grammarly.client import get_text_checker
from governance.audit import get_audit_logger


# =============================================================================
# Gmail Tools
# =============================================================================

class GmailReadTool(BaseTool):
    """Read emails from Gmail."""
    
    name: str = "gmail_read"
    description: str = """Read emails from Gmail inbox.
    Input: query string (optional). Examples:
      - "is:unread" - unread messages
      - "from:client@example.com" - from specific sender
      - "subject:invoice" - subject contains invoice
      - "" (empty) - recent messages"""
    
    def _run(self, query: str = "") -> str:
        from services.gmail.client import get_gmail_client
        
        try:
            client = get_gmail_client()
            if not client.is_authenticated:
                return "Gmail not authenticated. Run setup to authenticate."
            
            messages = client.list_messages(query=query or None, max_results=10)
            
            if not messages:
                return f"No messages found{f' matching: {query}' if query else ''}."
            
            lines = [f"Found {len(messages)} message(s):\n"]
            for msg in messages:
                unread = "📬" if msg.is_unread else "📭"
                lines.append(
                    f"{unread} [{msg.date[:16]}] From: {msg.from_email[:30]}\n"
                    f"   Subject: {msg.subject[:50]}\n"
                    f"   Preview: {msg.snippet[:60]}..."
                )
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error reading Gmail: {e}"


class GmailSearchTool(BaseTool):
    """Search emails in Gmail."""
    
    name: str = "gmail_search"
    description: str = """Search Gmail for specific emails.
    Input: search query using Gmail syntax
    Examples: "from:john subject:meeting after:2024/01/01" """
    
    def _run(self, query: str) -> str:
        from services.gmail.client import get_gmail_client
        
        if not query:
            return "Please provide a search query."
        
        try:
            client = get_gmail_client()
            if not client.is_authenticated:
                return "Gmail not authenticated."
            
            messages = client.search(query, max_results=10)
            
            if not messages:
                return f"No messages found for: {query}"
            
            lines = [f"Search results for '{query}':\n"]
            for msg in messages:
                lines.append(f"• {msg.subject[:50]} - from {msg.from_email[:30]}")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Search error: {e}"


class GmailDraftTool(BaseTool):
    """Queue an email using a canned response."""
    
    name: str = "gmail_queue_send"
    description: str = """Queue an email for sending using a pre-approved canned response.
    
    IMPORTANT: You can ONLY use pre-approved response templates.
    
    Input format: JSON with fields:
    - response_id: ID of the canned response to use (REQUIRED)
    - to: recipient email address (REQUIRED)
    - variables: dict of template variables (REQUIRED based on template)
    
    Example: {"response_id": "status-working", "to": "client@example.com", "variables": {"recipient_name": "John", "project_name": "Website", "task_description": "homepage redesign", "eta": "Friday", "sender_name": "Steve"}}
    
    To see available responses, use the list_canned_responses tool."""
    
    def _run(self, input_json: str) -> str:
        import json
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input. See tool description for format."
        
        response_id = data.get("response_id")
        to_email = data.get("to")
        variables = data.get("variables", {})
        
        if not response_id:
            return "Missing required field: response_id"
        if not to_email:
            return "Missing required field: to"
        
        try:
            # Get and render the canned response
            registry = get_response_registry()
            subject, body = registry.use(response_id, variables)
            
            # Check text quality
            checker = get_text_checker()
            check_result = checker.check(body)
            if not check_result.is_clean:
                return (
                    f"Text quality issues found:\n{check_result.format_issues()}\n\n"
                    "Please fix the template variables and try again."
                )
            
            # Queue for sending (with approval required)
            queue = get_message_queue()
            msg = queue.queue(
                msg_type=MessageType.EMAIL_SEND,
                channel=to_email,
                content=body,
                subject=subject,
                metadata={
                    "response_id": response_id,
                    "variables": variables,
                },
                created_by="agent",
                requires_approval=True,
            )
            
            get_audit_logger().log_tool_use(
                agent="communication",
                tool="gmail_queue_send",
                input_data={"to": to_email, "response_id": response_id},
                output_data={"queue_id": msg.id},
            )
            
            return (
                f"✓ Email queued for approval\n"
                f"Queue ID: {msg.id}\n"
                f"To: {to_email}\n"
                f"Subject: {subject}\n"
                f"Status: PENDING APPROVAL\n"
                f"Send after approval: {msg.seconds_until_send}s delay\n\n"
                "A human must approve this email before it sends."
            )
            
        except ValueError as e:
            return f"Error: {e}"


# =============================================================================
# Slack Tools
# =============================================================================

class SlackReadTool(BaseTool):
    """Read messages from Slack channels."""
    
    name: str = "slack_read"
    description: str = """Read recent messages from a Slack channel.
    Input: channel name or ID (e.g., "general" or "C01234567")"""
    
    def _run(self, channel: str) -> str:
        from services.slack.client import get_slack_client
        
        if not channel:
            return "Please provide a channel name or ID."
        
        try:
            client = get_slack_client()
            if not client.is_available:
                return "Slack not configured. Set SLACK_BOT_TOKEN in .env"
            
            messages = client.get_messages(channel, limit=10)
            
            if not messages:
                return f"No messages found in {channel}."
            
            lines = [f"Recent messages in {channel}:\n"]
            for msg in messages:
                time_str = msg.timestamp.strftime("%H:%M")
                user = msg.user[:15] if msg.user else "unknown"
                lines.append(f"[{time_str}] {user}: {msg.text[:100]}")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error reading Slack: {e}"


class SlackListChannelsTool(BaseTool):
    """List available Slack channels."""
    
    name: str = "slack_list_channels"
    description: str = """List available Slack channels.
    Input: none required (pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        from services.slack.client import get_slack_client
        
        try:
            client = get_slack_client()
            if not client.is_available:
                return "Slack not configured."
            
            channels = client.list_channels()
            
            if not channels:
                return "No channels found."
            
            lines = ["Available channels:\n"]
            for ch in channels[:20]:
                icon = "🔒" if ch.is_private else "#"
                lines.append(f"{icon} {ch.name} ({ch.member_count} members)")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class SlackQueueMessageTool(BaseTool):
    """Queue a Slack message using a canned response."""
    
    name: str = "slack_queue_send"
    description: str = """Queue a Slack message using a pre-approved canned response.
    
    IMPORTANT: 2-minute delay + approval required before sending.
    You can ONLY use pre-approved response templates.
    
    Input format: JSON with fields:
    - response_id: ID of the canned response to use (REQUIRED)
    - channel: channel name or ID (REQUIRED)
    - variables: dict of template variables (REQUIRED based on template)
    
    Example: {"response_id": "slack-status", "channel": "project-updates", "variables": {"project_name": "Website", "task_name": "Homepage", "status": "In Progress", "status_emoji": "🔄", "details": "Working on responsive layout"}}"""
    
    def _run(self, input_json: str) -> str:
        import json
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        response_id = data.get("response_id")
        channel = data.get("channel")
        variables = data.get("variables", {})
        
        if not response_id:
            return "Missing required field: response_id"
        if not channel:
            return "Missing required field: channel"
        
        try:
            # Get and render the canned response
            registry = get_response_registry()
            _, body = registry.use(response_id, variables)
            
            # Check text quality
            checker = get_text_checker()
            check_result = checker.check(body)
            if not check_result.is_clean:
                return f"Text quality issues:\n{check_result.format_issues()}"
            
            # Queue with 2-minute delay
            queue = get_message_queue()
            msg = queue.queue(
                msg_type=MessageType.SLACK_MESSAGE,
                channel=channel,
                content=body,
                metadata={
                    "response_id": response_id,
                    "variables": variables,
                },
                created_by="agent",
                delay_seconds=120,  # 2 minutes
                requires_approval=True,
            )
            
            get_audit_logger().log_tool_use(
                agent="communication",
                tool="slack_queue_send",
                input_data={"channel": channel, "response_id": response_id},
                output_data={"queue_id": msg.id},
            )
            
            return (
                f"✓ Slack message queued\n"
                f"Queue ID: {msg.id}\n"
                f"Channel: {channel}\n"
                f"Status: PENDING APPROVAL\n"
                f"Delay: 2 minutes after approval\n\n"
                "A human must approve before it sends."
            )
            
        except ValueError as e:
            return f"Error: {e}"


# =============================================================================
# Canned Response Tools
# =============================================================================

class ListCannedResponsesTool(BaseTool):
    """List available canned responses."""
    
    name: str = "list_canned_responses"
    description: str = """List all available pre-approved response templates.
    Input: optional filter - "email", "slack", or category name
    Leave empty to see all responses."""
    
    def _run(self, filter_by: str = "") -> str:
        registry = get_response_registry()
        
        if filter_by.lower() == "email":
            responses = registry.get_for_channel(ResponseChannel.EMAIL)
        elif filter_by.lower() == "slack":
            responses = registry.get_for_channel(ResponseChannel.SLACK)
        elif filter_by:
            try:
                category = ResponseCategory(filter_by.lower())
                responses = registry.get_by_category(category)
            except ValueError:
                responses = registry.search(filter_by)
        else:
            responses = registry.list_all()
        
        if not responses:
            return "No matching responses found."
        
        lines = ["Available canned responses:\n"]
        for r in responses:
            channel = "📧" if r.channel == ResponseChannel.EMAIL else "💬" if r.channel == ResponseChannel.SLACK else "📧💬"
            lines.append(f"{channel} {r.id}: {r.name}")
            lines.append(f"   Variables: {', '.join(r.variables) if r.variables else 'none'}")
        
        return "\n".join(lines)


class GetCannedResponseTool(BaseTool):
    """Get details of a specific canned response."""
    
    name: str = "get_canned_response"
    description: str = """Get full details of a canned response template.
    Input: response ID (e.g., "status-working")"""
    
    def _run(self, response_id: str) -> str:
        if not response_id:
            return "Please provide a response ID."
        
        registry = get_response_registry()
        response = registry.get(response_id.strip())
        
        if not response:
            return f"Response '{response_id}' not found. Use list_canned_responses to see available options."
        
        return (
            f"Response: {response.name}\n"
            f"ID: {response.id}\n"
            f"Category: {response.category.value}\n"
            f"Channel: {response.channel.value}\n"
            f"Subject: {response.subject_template or 'N/A'}\n"
            f"Body:\n{response.body_template}\n\n"
            f"Required variables: {', '.join(response.variables)}"
        )


# =============================================================================
# Message Queue Tools
# =============================================================================

class ListQueuedMessagesTool(BaseTool):
    """List messages waiting to be sent."""
    
    name: str = "list_queued_messages"
    description: str = """List all messages in the send queue.
    Input: none required (pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        queue = get_message_queue()
        pending = queue.list_pending()
        
        if not pending:
            return "No messages in queue."
        
        lines = ["Messages in queue:\n"]
        for msg in pending:
            status_icon = {
                MessageStatus.PENDING_APPROVAL: "⏳",
                MessageStatus.QUEUED: "📤",
                MessageStatus.APPROVED: "✅",
            }.get(msg.status, "❓")
            
            lines.append(
                f"{status_icon} [{msg.id}] {msg.type.value} → {msg.channel}\n"
                f"   Status: {msg.status.value}\n"
                f"   Sends in: {msg.seconds_until_send}s\n"
                f"   Preview: {msg.content[:50]}..."
            )
        
        return "\n".join(lines)


class CancelQueuedMessageTool(BaseTool):
    """Cancel a queued message."""
    
    name: str = "cancel_queued_message"
    description: str = """Cancel a message before it sends.
    Input: message ID from the queue"""
    
    def _run(self, msg_id: str) -> str:
        if not msg_id:
            return "Please provide a message ID."
        
        queue = get_message_queue()
        msg = queue.cancel(msg_id.strip(), cancelled_by="agent", reason="Agent requested cancellation")
        
        if msg:
            return f"✓ Message {msg_id} cancelled successfully."
        else:
            return f"Could not cancel message {msg_id}. It may have already been sent or doesn't exist."


# =============================================================================
# Text Quality Tool
# =============================================================================

class CheckTextQualityTool(BaseTool):
    """Check text for grammar and spelling issues."""
    
    name: str = "check_text_quality"
    description: str = """Check text for grammar, spelling, and style issues.
    Input: text to check"""
    
    def _run(self, text: str) -> str:
        if not text:
            return "Please provide text to check."
        
        checker = get_text_checker()
        result = checker.check(text)
        
        summary = result.get_summary()
        
        if result.is_clean:
            return f"✓ {summary}\n\nReadability: {checker.get_readability_score(text)}"
        
        return (
            f"{summary}\n\n"
            f"{result.format_issues()}\n\n"
            f"Readability: {checker.get_readability_score(text)}"
        )


# =============================================================================
# Export
# =============================================================================

def get_communication_tools() -> List[BaseTool]:
    """Get all communication tools for CrewAI agents."""
    return [
        # Gmail
        GmailReadTool(),
        GmailSearchTool(),
        GmailDraftTool(),
        
        # Slack
        SlackReadTool(),
        SlackListChannelsTool(),
        SlackQueueMessageTool(),
        
        # Canned Responses
        ListCannedResponsesTool(),
        GetCannedResponseTool(),
        
        # Message Queue
        ListQueuedMessagesTool(),
        CancelQueuedMessageTool(),
        
        # Text Quality
        CheckTextQualityTool(),
    ]
