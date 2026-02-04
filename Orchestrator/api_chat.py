"""
Chat API Endpoint for Orchestrator

Provides streaming chat endpoint that the Next.js dashboard connects to.
Supports structured JSON output for dynamic UI updates.

This module extends the main api.py with chat capabilities.
"""

import os
import json
import asyncio
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Try to import Anthropic for direct Claude access
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Import services
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from services.schema_detector import get_schema_detector
from services.message_queue import get_message_queue
from services.memory import get_memory_service, MemoryService

# Import Harvest tools
try:
    from tools.harvest import get_harvest_client, get_status as get_harvest_status
    HARVEST_AVAILABLE = True
except ImportError:
    HARVEST_AVAILABLE = False
    get_harvest_client = None
    get_harvest_status = None

# Try to import harvest client
try:
    from services.harvest_client import get_harvest_client, is_harvest_configured
    HARVEST_AVAILABLE = True
except ImportError:
    HARVEST_AVAILABLE = False
    get_harvest_client = lambda: None
    is_harvest_configured = lambda: False

router = APIRouter(prefix="/api", tags=["Chat"])


# ============================================================================
# Models
# ============================================================================

class ChatMessage(BaseModel):
    """A single chat message."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request from the dashboard."""
    messages: List[ChatMessage]
    session_id: Optional[str] = Field(None, description="Session ID for memory persistence")
    stream: bool = Field(True, description="Stream the response")
    structured_output: bool = Field(True, description="Include UI JSON")


class UICard(BaseModel):
    """Status card for the dashboard."""
    id: str
    type: str  # info, success, warning, error, progress, metric
    title: str
    value: Optional[str] = None
    description: Optional[str] = None
    progress: Optional[int] = None
    priority: int = 5
    icon: Optional[str] = None


class PriorityUI(BaseModel):
    """UI update instructions."""
    cards: Optional[List[UICard]] = None
    show_progress_bar: Optional[bool] = None
    progress: Optional[int] = None
    highlight_agent: Optional[str] = None


class AgentStatus(BaseModel):
    """Agent status update."""
    id: str
    name: str
    status: str  # idle, active, busy, error, offline
    priority: int = 5
    current_task: Optional[str] = None


class ApprovalRequest(BaseModel):
    """Request for human approval."""
    id: str
    type: str  # deploy, database, message, payment, critical
    title: str
    description: str
    details: Optional[Dict[str, Any]] = None
    timeout_seconds: int = 60


class ChatResponse(BaseModel):
    """Structured chat response."""
    text: Optional[str] = None
    priority_ui: Optional[PriorityUI] = None
    agents: Optional[List[AgentStatus]] = None
    status_cards: Optional[List[UICard]] = None
    needs_approval: Optional[ApprovalRequest] = None


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are Agent007, an AI assistant that helps Steve manage software development and business operations.

## Available Tools

You have tools to interact with these services - USE THEM when the user asks:

### Communication & Productivity
- **Gmail**: `gmail_search`, `gmail_get_unread_count` - Search emails, check inbox
- **Calendar**: `calendar_get_events` - View upcoming meetings and events
- **Slack**: `slack_search_messages`, `slack_get_recent_messages` - Read messages
- **Google Sheets**: `sheets_get_info`, `sheets_read_range`, `sheets_update_range`, `sheets_append_rows`, `sheets_find_value` - Read/write spreadsheets
- **Google Docs/Drive**: `docs_list_files`, `docs_search`, `docs_read_file`, `docs_get_file_info` - Access files

### Unified Notifications (Notion + Slack + Airtable)
- **Notification Hub**: `notification_fetch_all`, `notification_search` - Get/search all notifications
- **Notion**: `notion_get_updates` - Get Notion page updates from email notifications (no direct API)
- **Slack via Email**: `slack_get_updates` - Get Slack messages from email notifications
- **Airtable**: `airtable_get_tickets`, `airtable_search_ticket` - Direct access to Airtable tickets

### Time & Task Management
- **Harvest**: `harvest_log_time`, `harvest_get_time_entries`, `harvest_list_projects` - Track time
- **ClickUp**: `clickup_create_task`, `clickup_list_tasks`, `clickup_update_task`, `clickup_get_task`, `clickup_add_comment`, `clickup_list_spaces` - Manage tasks and tickets
- **Zendesk**: `zendesk_list_tickets`, `zendesk_get_ticket`, `zendesk_create_ticket` - Support tickets

### Memory & Context
- **Memory**: `memory_remember`, `memory_recall` - Store and retrieve context

### AI Agent Crews (for complex tasks)
- **Agents**: `run_dev_task`, `get_agent_status` - Dispatch work to AI crews
  - Use `run_dev_task` for code changes, file operations, or multi-step development work
  - The crew includes Manager (planning), Coder (implementation), Reviewer (code review)

## When to Use Tools

- "Show my emails" → `gmail_search`
- "What did I work on?" → `harvest_get_time_entries`
- "Log 2 hours" → `harvest_log_time`
- "Check Slack" → `slack_get_recent_messages` or `slack_get_updates`
- "Create a task" → `clickup_create_task`
- "Show my tasks" → `clickup_list_tasks`
- "What meetings?" → `calendar_get_events`
- "Remember that..." → `memory_remember`
- "Build a feature" / "Write code" / "Fix bug" → `run_dev_task` (delegates to AI crew)
- "What's happening in Notion?" → `notion_get_updates`
- "Show all notifications" → `notification_fetch_all`
- "Find notifications about payment" → `notification_search`
- "Show my Airtable tickets" → `airtable_get_tickets`
- "Find the payment plan ticket" → `airtable_search_ticket`

## CRITICAL: Anti-Hallucination Rules

**NEVER make up data. NEVER assume tool results.**

When using tools:
1. ✅ ONLY report IDs, names, and data that appear in the ACTUAL tool response
2. ❌ NEVER fabricate task IDs, file IDs, or any identifiers
3. ✅ If a tool fails or returns truncated results, SAY SO explicitly
4. ✅ If you create multiple items, VERIFY them with a list/verify tool after
5. ❌ NEVER say "Created task X" unless you see the ID in the tool response
6. ✅ If unsure about data, ask for clarification instead of guessing

**If tool result is truncated or incomplete:**
- Say: "I created some tasks but the full list was truncated. Let me verify..."
- Use verification tools to get actual IDs
- DO NOT fill in gaps with assumed data

**Example - WRONG:**
"Created 20 tasks: task1 (ID: abc123), task2 (ID: abc124)..."
(when you only see task1's ID in the response)

**Example - CORRECT:**
"I attempted to create 20 tasks. I can confirm task1 was created (ID: abc123). 
Let me verify the others..."

## Response Style

- Be conversational and natural
- When you use a tool, summarize the results clearly
- Don't just dump raw data - interpret it for the user
- Keep responses concise
- ONLY state facts you can verify from tool responses

## Dashboard UI Updates

You can update the dashboard UI with JSON:

```json
{
  "priority_ui": {
    "cards": [{"id": "card-1", "type": "success", "title": "Done", "description": "Time logged"}]
  }
}
```

Card types: info, success, warning, error, progress, metric

## Important

- Steve manages multiple projects (Forge Lab, Agent007, Nemesis, etc.)
- Always use tools to get real data rather than guessing
- If a tool fails, explain the error and suggest fixes
- Use memory_remember to store important facts Steve tells you
- For complex development tasks, use run_dev_task to delegate to the AI crew"""


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Stream a chat response with structured UI updates.
    
    Connects to Claude API and streams the response while parsing
    for UI update JSON blocks. Persists conversation to memory.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")
    
    # Get the last user message
    last_message = request.messages[-1]
    if last_message.role != "user":
        raise HTTPException(status_code=400, detail="Last message must be from user")
    
    # Get or create session for memory persistence
    memory = get_memory_service()
    session_id = request.session_id
    if not session_id:
        session_id = memory.create_session()
    
    # Get relevant context from memory (before response, for injection)
    memory_context = memory.get_relevant_context(last_message.content, limit=5)
    
    # Note: Messages are persisted at the END of the response via persist_turn_context
    # This is more efficient than persisting before we have the full response
    
    # Check for Claude API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    if api_key and ANTHROPIC_AVAILABLE:
        # Use Claude API
        return StreamingResponse(
            stream_claude_response(request.messages, api_key, session_id, memory_context),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id},
        )
    else:
        # Use mock response
        return StreamingResponse(
            stream_mock_response(last_message.content, session_id, memory_context),
            media_type="text/plain; charset=utf-8",
            headers={"X-Session-ID": session_id},
        )


async def stream_claude_response(
    messages: List[ChatMessage],
    api_key: str,
    session_id: str = None,
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """Stream response from Claude API with tool calling."""
    from services.tool_registry import get_tool_definitions, execute_tool
    TOOL_DEFINITIONS = get_tool_definitions()
    
    client = anthropic.AsyncAnthropic(api_key=api_key)
    memory = get_memory_service()
    
    # Build context from current system state
    context = await build_context()
    
    # Add memory context
    if memory_context:
        context = memory_context + "\n\n" + context
    full_system = SYSTEM_PROMPT + "\n\nCurrent context:\n" + context
    
    # Convert messages
    api_messages = [
        {"role": m.role, "content": m.content}
        for m in messages
    ]
    
    max_iterations = 10  # Prevent infinite tool loops
    full_response = ""  # Collect full response for memory
    
    for _ in range(max_iterations):
        # Debug: Log tool count
        print(f"[DEBUG] Calling Claude with {len(TOOL_DEFINITIONS)} tools")
        print(f"[DEBUG] Tool names: {[t['name'] for t in TOOL_DEFINITIONS[:5]]}...")
        
        # Call Claude with tools
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=full_system,
            messages=api_messages,
            tools=TOOL_DEFINITIONS,
        )
        
        # Debug: Log response
        print(f"[DEBUG] Response stop_reason: {response.stop_reason}")
        print(f"[DEBUG] Content types: {[b.type for b in response.content]}")
        
        # Process response
        tool_calls = []
        text_content = ""
        
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(block)
        
        # If there's text, yield it
        if text_content:
            yield text_content
            full_response += text_content
        
        # If no tool calls, we're done
        if not tool_calls:
            break
        
        # Add assistant message with tool use ONCE (before processing results)
        api_messages.append({
            "role": "assistant",
            "content": response.content,
        })
        
        # Execute tool calls and collect results
        tool_results = []
        for tool_call in tool_calls:
            tool_msg = f"\n\n*Using {tool_call.name}...*\n"
            yield tool_msg
            full_response += tool_msg
            
            # Execute the tool
            result = execute_tool(tool_call.name, tool_call.input)
            
            # Check if tool requires confirmation
            if result.get("requires_confirmation"):
                confirmation_msg = (
                    f"\n\n⚠️ **CONFIRMATION REQUIRED**\n\n"
                    f"**Action:** {tool_call.name}\n"
                    f"**Danger Level:** {result.get('danger_level', 'medium').upper()}\n\n"
                    f"**Preview:**\n{result.get('preview', 'No preview available')}\n\n"
                    f"{result.get('warning', '')}\n\n"
                    f"*Please approve in the UI or respond with 'approve' to continue.*"
                )
                yield confirmation_msg
                full_response += confirmation_msg
                
                # Add a special marker for the UI to trigger approval dialog
                approval_json = json.dumps({
                    'needs_approval': {
                        'id': tool_call.id,
                        'type': 'message',  # Type for UI styling
                        'title': f"Approve {tool_call.name}",
                        'description': result.get('message', 'This action requires your approval'),
                        'tool': tool_call.name,
                        'args': tool_call.input,
                        'preview': result.get('preview'),
                        'timeout_seconds': 300  # 5 minute timeout
                    }
                })
                yield f"\n\n```json\n{approval_json}\n```\n"
                
                # Stop processing - wait for user approval
                # The result will indicate confirmation is needed
                result_str = json.dumps({"status": "pending_approval", "tool": tool_call.name})
                print(f"[INFO] Tool {tool_call.name} requires confirmation - waiting for user approval")
            else:
                # Log tool result
                result_str = json.dumps(result)
                print(f"[DEBUG] Tool {tool_call.name} result length: {len(result_str)} chars")
                if 'error' in result:
                    print(f"[DEBUG] Tool error: {result['error']}")
            
            # Truncate very large results to prevent context overflow
            if len(result_str) > 10000:
                # Extract just the summary/count for better context
                try:
                    result_obj = json.loads(result_str)
                    if 'tasks' in result_obj and isinstance(result_obj['tasks'], list):
                        # For bulk task operations, keep IDs but truncate details
                        summary = {
                            'count': result_obj.get('count', len(result_obj['tasks'])),
                            'task_ids': [t.get('id') for t in result_obj['tasks'] if 'id' in t],
                            'list_id': result_obj.get('list_id'),
                            'note': f'Full details truncated. Retrieved {len(result_obj["tasks"])} tasks.'
                        }
                        result_str = json.dumps(summary)
                        print(f"[WARN] Large result truncated - returning summary with {len(summary['task_ids'])} task IDs")
                    else:
                        result_str = result_str[:10000] + '... [TRUNCATED - use verification tool to see full data]'
                        print(f"[WARN] Result truncated from {len(result_str)} to 10000 chars - data may be incomplete!")
                except:
                    result_str = result_str[:10000] + '... [TRUNCATED]'
                    print(f"[WARN] Result truncated to 10000 chars")
            
            # Collect tool result
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": result_str,
            })
        
        # Add all tool results as a single user message
        api_messages.append({
            "role": "user",
            "content": tool_results,
        })
    
    # Persist conversation turn efficiently (batched write + fact extraction)
    if session_id and full_response:
        # Get the user message from the original messages list
        user_content = messages[-1].content if messages else ""
        memory.persist_turn_context(session_id, user_content, full_response)


async def stream_mock_response(
    user_message: str,
    session_id: str = None,
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """Generate a conversational response when Claude API is not available."""
    memory = get_memory_service()
    message_lower = user_message.lower()
    words = message_lower.split()
    
    # Get real system context
    context = await build_context()
    
    # Add memory context
    if memory_context:
        context = memory_context + "\n\n" + context
    
    # Analyze intent more naturally (strip punctuation for matching)
    import re
    clean_words = re.sub(r'[^\w\s]', '', message_lower).split()
    
    is_greeting = any(w in clean_words for w in ["hi", "hello", "hey", "yo", "sup", "hiya"])
    is_question = "?" in user_message or any(message_lower.startswith(w) for w in ["what", "how", "why", "when", "where", "who", "can", "could", "would", "is", "are", "do", "does"])
    is_thanks = any(w in clean_words for w in ["thanks", "thank", "thx", "ty", "appreciate"])
    wants_help = any(w in clean_words for w in ["help", "assist", "support"])
    
    # Build natural response
    response_text = ""
    json_data: Dict[str, Any] = {}
    
    # Handle greetings first (before keyword matching)
    if is_greeting:
        import random
        greetings = [
            "Hey! What can I help you with today?",
            "Hi there! Ready to help with deployments, time tracking, or anything else.",
            "Hello! I'm here - what do you need?",
        ]
        response_text = random.choice(greetings)
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]}
    
    elif is_thanks:
        thanks_responses = [
            "You're welcome! Let me know if you need anything else.",
            "No problem! I'm here if you need me.",
            "Anytime! 👍",
        ]
        import random
        response_text = random.choice(thanks_responses)
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "idle", "priority": 1}]}
    
    elif "deploy" in message_lower:
        response_text = "I'll initiate the deployment process. Let me run the pre-deployment checks first."
        json_data = {
            "priority_ui": {
                "show_progress_bar": True,
                "progress": 25,
                "cards": [
                    {
                        "id": "deploy-status",
                        "type": "progress",
                        "title": "Deployment",
                        "description": "Running pre-deployment checks...",
                        "progress": 25,
                        "priority": 1,
                    }
                ],
            },
            "agents": [
                {"id": "deployer", "name": "Deployer", "status": "active", "priority": 1, "current_task": "Running checks"}
            ],
            "needs_approval": {
                "id": f"deploy-{int(datetime.now().timestamp())}",
                "type": "deploy",
                "title": "Deploy to Production",
                "description": "All checks passed. Ready to deploy the latest code to production.",
                "details": {"branch": "main", "commit": "abc123", "environment": "production"},
                "timeout_seconds": 120,
            },
        }
        
    elif "ticket" in message_lower:
        response_text = "Here's a summary of your open tickets:"
        json_data = {
            "priority_ui": {
                "cards": [
                    {"id": "tickets-urgent", "type": "warning", "title": "3 Urgent Tickets", "description": "Require immediate attention", "priority": 1},
                    {"id": "tickets-normal", "type": "info", "title": "12 Open Tickets", "description": "Normal priority", "priority": 3},
                ]
            },
            "agents": [
                {"id": "ticket-manager", "name": "Ticket Manager", "status": "active", "current_task": "Fetching tickets"}
            ],
        }
        
    elif "time" in message_lower:
        # Try to get real Harvest data
        hours_today = 0.0
        hours_week = 0.0
        running_timer = None
        entries_count = 0
        harvest_configured = False
        
        if HARVEST_AVAILABLE and get_harvest_status:
            try:
                status = get_harvest_status()
                harvest_configured = status.get("configured", False)
                if harvest_configured:
                    hours_today = status.get("today_hours", 0)
                    entries_count = status.get("today_entries", 0)
                    running_timer = status.get("running_timer")
                    # Estimate week hours (today * days so far this week)
                    from datetime import date
                    days_this_week = date.today().weekday() + 1
                    hours_week = hours_today * days_this_week * 0.8  # rough estimate
            except Exception:
                pass
        
        if harvest_configured:
            response_text = f"Here's your time from Harvest:"
            timer_status = ""
            if running_timer:
                timer_notes = running_timer.get("notes", "")[:40]
                timer_status = f"\n\n⏱️ **Timer Running:** {timer_notes}..."
            
            response_text += f"\n\n• **Today:** {hours_today:.1f} hours ({entries_count} entries)"
            response_text += timer_status
            
            json_data = {
                "priority_ui": {
                    "cards": [
                        {"id": "time-today", "type": "metric", "title": "Hours Today", "value": f"{hours_today:.1f}", "description": f"{entries_count} time entries", "priority": 2, "icon": "clock"},
                    ]
                },
                "agents": [
                    {"id": "time-logger", "name": "Time Logger", "status": "active", "current_task": "Connected to Harvest"}
                ],
            }
            
            if running_timer:
                json_data["priority_ui"]["cards"].insert(0, {
                    "id": "timer-running", 
                    "type": "warning", 
                    "title": "Timer Running", 
                    "description": running_timer.get("notes", "")[:50],
                    "priority": 1, 
                    "icon": "clock"
                })
        else:
            response_text = "Harvest is not configured. To connect:\n\n"
            response_text += "1. Get your token from: https://id.getharvest.com/developers\n"
            response_text += "2. Set environment variables:\n"
            response_text += "   - `HARVEST_ACCESS_TOKEN`\n"
            response_text += "   - `HARVEST_ACCOUNT_ID`\n"
            response_text += "   - `HARVEST_DEFAULT_PROJECT_ID` (optional)\n"
            response_text += "   - `HARVEST_DEFAULT_TASK_ID` (optional)"
            
            json_data = {
                "priority_ui": {
                    "cards": [
                        {"id": "harvest-setup", "type": "warning", "title": "Harvest Not Configured", "description": "Set HARVEST_ACCESS_TOKEN and HARVEST_ACCOUNT_ID", "priority": 1},
                    ]
                },
                "agents": [
                    {"id": "time-logger", "name": "Time Logger", "status": "error", "current_task": "Not configured"}
                ],
            }
        
    elif "schema" in message_lower or "database" in message_lower:
        detector = get_schema_detector()
        summary = detector.get_summary()
        
        response_text = f"I found {summary['total']} schema changes, {summary['unreviewed']} need review."
        json_data = {
            "priority_ui": {
                "cards": [
                    {"id": "schema-pending", "type": "warning" if summary['unreviewed'] > 0 else "success", 
                     "title": f"{summary['unreviewed']} Pending Reviews", 
                     "description": f"Across {len(summary.get('by_project', {}))} projects", 
                     "priority": 1 if summary['unreviewed'] > 0 else 5},
                ]
            },
            "agents": [
                {"id": "orchestrator", "name": "Orchestrator", "status": "active", "current_task": "Schema detection"}
            ],
        }
        
    elif wants_help:
        response_text = f"""Sure, I can help! Here's what I can do:

**🚀 Deployments** - "deploy to production", "run checks"
**🎫 Tickets** - "show open tickets", "create a ticket"
**⏱️ Time** - "log time", "start timer", "what did I work on today?"
**📊 Database** - "check schema changes", "any pending reviews?"
**💬 General** - Just ask naturally, I'll figure it out

{context}

What would you like to do?"""
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]}
    
    # Handle questions about the system
    elif "status" in message_lower or "what's" in message_lower or "how are" in message_lower:
        response_text = f"Here's the current system status:\n\n{context}\n\nEverything looks good. What would you like me to do?"
        json_data = {
            "priority_ui": {"cards": [{"id": "status-ok", "type": "success", "title": "Systems Operational", "description": "All services running", "priority": 3}]},
            "agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]
        }
    
    # Handle project/work related questions
    elif any(w in message_lower for w in ["project", "work", "doing", "task"]):
        response_text = f"""I'm tracking several things for you:

{context}

Want me to show details on any of these? Or tell me what you're working on and I can start a timer."""
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "current_task": "Monitoring"}]}
    
    # More conversational fallback
    else:
        # Try to extract what they might want
        if is_question:
            response_text = f"""Good question! I'm not 100% sure what you're asking about, but here's what I know:

{context}

Could you be more specific? For example:
- "How much time did I log today?"
- "Are there any pending schema reviews?"
- "Deploy the latest changes"
"""
        else:
            response_text = f"""Got it. Here's what I can see right now:

{context}

Just tell me what you'd like to do - deploy, track time, check tickets, or something else."""
        
        json_data = {"agents": [{"id": "orchestrator", "name": "Orchestrator", "status": "active", "priority": 1}]}
    
    # Only include JSON if there's UI updates (not for simple conversations)
    if json_data.get("priority_ui") or json_data.get("needs_approval"):
        full_response = response_text + "\n\n```json\n" + json.dumps(json_data, indent=2) + "\n```"
    else:
        full_response = response_text
    
    # Stream more naturally (by sentence/phrase, not word)
    chunks = []
    current = ""
    for char in full_response:
        current += char
        if char in ".!?\n" and len(current) > 10:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    
    for chunk in chunks:
        yield chunk
        await asyncio.sleep(0.05)
    
    # Persist conversation turn efficiently (batched write + fact extraction)
    if session_id:
        memory.persist_turn_context(session_id, user_message, full_response)


async def build_context() -> str:
    """Build context from current system state."""
    import os
    context_parts = []
    
    # Connected integrations
    integrations = []
    if os.getenv("HARVEST_ACCESS_TOKEN"):
        integrations.append("Harvest (time tracking)")
    if os.getenv("ZENDESK_API_TOKEN"):
        integrations.append("Zendesk (tickets)")
    if os.getenv("CLICKUP_API_TOKEN"):
        integrations.append("ClickUp (tasks)")
    if os.getenv("AIRTABLE_PERSONAL_ACCESS_TOKEN"):
        integrations.append("Airtable (database)")
    if os.getenv("SLACK_BOT_TOKEN"):
        integrations.append("Slack (messages)")
    
    # Check Gmail
    gmail_token = os.path.expanduser("~/.config/agent007/google/token.json")
    if os.path.exists(gmail_token):
        integrations.append("Gmail (email)")
    
    if integrations:
        context_parts.append(f"Connected integrations: {', '.join(integrations)}")
    
    # Harvest status if available
    if HARVEST_AVAILABLE and get_harvest_status:
        try:
            status = get_harvest_status()
            if status.get("configured"):
                hours = status.get("today_hours", 0)
                entries = status.get("today_entries", 0)
                context_parts.append(f"Harvest: {hours:.1f}h logged today ({entries} entries)")
                if status.get("running_timer"):
                    context_parts.append(f"Active timer: {status['running_timer'].get('notes', 'running')[:40]}")
        except Exception:
            pass
    
    # Schema changes
    try:
        detector = get_schema_detector()
        summary = detector.get_summary()
        context_parts.append(f"Schema changes: {summary['total']} total, {summary['unreviewed']} pending review")
        context_parts.append(f"Monitored projects: {', '.join(summary.get('monitored_projects', []))}")
    except Exception:
        pass
    
    # Message queue
    try:
        queue = get_message_queue()
        pending = queue.list_pending()
        if pending:
            context_parts.append(f"Pending messages in queue: {len(pending)}")
    except Exception:
        pass
    
    context_parts.append(f"Current time: {datetime.now().isoformat()}")
    
    return "\n".join(context_parts)


# ============================================================================
# Approval Endpoint
# ============================================================================

class ApprovalAction(BaseModel):
    """Approval action request."""
    approval_id: str
    approved: bool


@router.post("/approve")
async def process_approval(action: ApprovalAction):
    """Process an approval or rejection."""
    # In a real implementation, this would:
    # 1. Look up the pending action by ID
    # 2. Execute or cancel based on approval status
    # 3. Return the result
    
    return {
        "success": True,
        "approval_id": action.approval_id,
        "status": "approved" if action.approved else "rejected",
        "message": f"Action {'approved and executed' if action.approved else 'rejected'}",
    }


# ============================================================================
# Memory Endpoints
# ============================================================================

class ContextEntry(BaseModel):
    """A context/memory entry."""
    category: str
    key: str
    value: str
    source: str = "user"
    confidence: float = 1.0
    expires_in_days: Optional[int] = None


@router.get("/memory/stats")
async def get_memory_stats():
    """Get memory database statistics."""
    memory = get_memory_service()
    return memory.get_stats()


@router.get("/memory/sessions")
async def list_sessions(limit: int = 20):
    """List recent conversation sessions."""
    memory = get_memory_service()
    return {"sessions": memory.list_sessions(limit=limit)}


@router.get("/memory/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details and conversation history."""
    memory = get_memory_service()
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    history = memory.get_conversation(session_id, limit=100)
    return {
        "session": session,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in history
        ],
    }


@router.get("/memory/context")
async def list_context(category: Optional[str] = None):
    """List stored context entries."""
    memory = get_memory_service()
    return {"entries": memory.list_context(category=category)}


@router.post("/memory/context")
async def add_context(entry: ContextEntry):
    """Add or update a context entry."""
    memory = get_memory_service()
    entry_id = memory.add_context(
        category=entry.category,
        key=entry.key,
        value=entry.value,
        source=entry.source,
        confidence=entry.confidence,
        expires_in_days=entry.expires_in_days,
    )
    return {"success": True, "id": entry_id}


@router.delete("/memory/context/{category}/{key}")
async def delete_context(category: str, key: str):
    """Delete a context entry."""
    memory = get_memory_service()
    deleted = memory.delete_context(category, key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Context entry not found")
    return {"success": True}


@router.get("/memory/search")
async def search_memory(q: str, limit: int = 10):
    """Search context entries."""
    memory = get_memory_service()
    results = memory.search_context(q, limit=limit)
    return {
        "results": [
            {
                "category": r.category,
                "key": r.key,
                "content": r.content,
                "relevance": r.relevance,
                "source": r.source,
            }
            for r in results
        ]
    }


@router.post("/memory/cleanup")
async def cleanup_memory():
    """Remove expired context entries."""
    memory = get_memory_service()
    removed = memory.cleanup_expired()
    return {"success": True, "removed": removed}


@router.get("/memory/export")
async def export_memory():
    """Export all context for backup."""
    memory = get_memory_service()
    return memory.export_context()


@router.post("/memory/import")
async def import_memory(data: Dict[str, Any]):
    """Import context from backup."""
    memory = get_memory_service()
    count = memory.import_context(data)
    return {"success": True, "imported": count}
