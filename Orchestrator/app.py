"""
Orchestrator - Streamlit UI

Single point of contact for AI-assisted development.
Submit tasks, review agent work, approve changes.

GOVERNANCE INTEGRATED:
- Pre-validation of tasks
- Policy enforcement visualization
- Audit log viewing
- Cost tracking dashboard

Usage:
    streamlit run app.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from governance.policies import POLICIES, should_escalate
from governance.validators import validate_before_execution, ValidationStatus
from governance.cost_tracker import get_cost_tracker
from governance.audit import get_audit_logger
from governance.allowlist import get_allowlist, Permission

# Focus workspace tools
try:
    from tools.devops import list_workspaces, FocusOpenTool
    FOCUS_AVAILABLE = True
except ImportError:
    FOCUS_AVAILABLE = False
    list_workspaces = lambda: []

# Harvest time tracking tools
try:
    from tools.harvest import (
        get_status as harvest_get_status,
        start_timer as harvest_start_timer,
        stop_timer as harvest_stop_timer,
        log_time as harvest_log_time,
        get_projects as harvest_get_projects,
    )
    HARVEST_AVAILABLE = True
except ImportError:
    HARVEST_AVAILABLE = False
    harvest_get_status = lambda: {"configured": False}

# Voice interface
try:
    from components.voice import render_voice_interface, text_to_speech
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

load_dotenv()

# =============================================================================
# Page Configuration
# =============================================================================

st.set_page_config(
    page_title="Orchestrator",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0d0d1f 100%);
    }
    
    .main-header {
        font-family: 'JetBrains Mono', monospace;
        color: #00ff88;
        text-shadow: 0 0 10px #00ff8855;
    }
    
    .status-running { color: #ffd93d; }
    .status-complete { color: #00d26a; }
    .status-error { color: #ff6b6b; }
    
    [data-testid="stMetric"] {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 15px;
    }
    
    .task-card {
        background: rgba(0,255,136,0.1);
        border: 1px solid #00ff88;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    
    .review-section {
        background: rgba(255,215,0,0.1);
        border: 1px solid #ffd700;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Session State
# =============================================================================

if "api_keys_set" not in st.session_state:
    st.session_state.api_keys_set = False

if "task_history" not in st.session_state:
    st.session_state.task_history = []

if "current_task" not in st.session_state:
    st.session_state.current_task = None

if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None


# =============================================================================
# Sidebar - Configuration
# =============================================================================

with st.sidebar:
    st.markdown("## 🔐 Configuration")
    
    # API Keys
    with st.expander("API Keys", expanded=not st.session_state.api_keys_set):
        anthropic_key = st.text_input(
            "Anthropic API Key",
            type="password",
            value=os.getenv("ANTHROPIC_API_KEY", ""),
            help="Required for Claude models"
        )
        
        openai_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=os.getenv("OPENAI_API_KEY", ""),
            help="Required for GPT models"
        )
        
        if anthropic_key or openai_key:
            if anthropic_key:
                os.environ["ANTHROPIC_API_KEY"] = anthropic_key
            if openai_key:
                os.environ["OPENAI_API_KEY"] = openai_key
            st.session_state.api_keys_set = True
            st.success("✓ API keys configured")
    
    st.divider()
    
    # Workspace
    workspace = st.text_input(
        "Workspace Root",
        value=os.getenv("WORKSPACE_ROOT", "/home/steve/Agent007"),
        help="Root directory for file operations"
    )
    os.environ["WORKSPACE_ROOT"] = workspace
    
    # Safety settings
    require_approval = st.checkbox(
        "Require human approval for file writes",
        value=True,
        help="Recommended: Review changes before they're applied"
    )
    os.environ["REQUIRE_APPROVAL"] = "true" if require_approval else "false"
    
    st.divider()
    
    # Quick stats
    st.markdown("### 📊 Session Stats")
    st.metric("Tasks Completed", len(st.session_state.task_history))
    
    if st.button("🔄 Clear History"):
        st.session_state.task_history = []
        st.session_state.current_task = None
        st.session_state.pending_approval = None
        st.rerun()


# =============================================================================
# Main Content
# =============================================================================

st.markdown('<h1 class="main-header">🤖 Orchestrator</h1>', unsafe_allow_html=True)
st.caption("AI-assisted development with human oversight")

# Tabs - Focus, Time, and Settings available without API keys
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🚀 New Task", "🎯 Focus", "⏱️ Time", "🎙️ Voice", "📋 History", "🛡️ Governance", "⚙️ Settings"])

# Check API keys (only blocks task execution, not viewing tabs)
api_keys_configured = st.session_state.api_keys_set


# =============================================================================
# Tab 1: New Task
# =============================================================================

with tab1:
    st.markdown("### Submit a Development Task")
    
    if not api_keys_configured:
        st.warning("⚠️ Please configure your API keys in the sidebar to execute tasks.")
    
    # Task input
    task_description = st.text_area(
        "What do you want to build or modify?",
        height=150,
        placeholder="""Example tasks:
- Create a Streamlit dashboard for visualizing sync events
- Add a new endpoint to the FastAPI backend
- Fix the calendar ID fallback issue in AcuitySyncService.php
- Review the APDriving booking flow for data integrity issues""",
    )
    
    # Context input
    with st.expander("📎 Additional Context (optional)"):
        context = st.text_area(
            "Paste relevant code, requirements, or context",
            height=200,
            placeholder="Paste existing code, error messages, or requirements here..."
        )
    
    # Options
    col1, col2, col3 = st.columns(3)
    with col1:
        require_review = st.checkbox("Include code review step", value=True)
    with col2:
        use_claude_cli = st.checkbox("Use Claude CLI for execution", value=True, 
                                      help="Hybrid mode: CrewAI plans, Claude CLI executes")
    with col3:
        verbose_output = st.checkbox("Show detailed agent output", value=True)
    
    # Pre-validation check (live)
    if task_description:
        pre_check = validate_before_execution(task=task_description)
        if pre_check.is_blocked:
            st.error(f"🚫 Task would be BLOCKED: {', '.join(i.message for i in pre_check.issues)}")
        elif pre_check.requires_escalation:
            st.warning(f"⚠️ Task requires APPROVAL: {', '.join(i.message for i in pre_check.issues)}")
        elif pre_check.has_warnings:
            st.info(f"⚡ Task has warnings: {', '.join(i.message for i in pre_check.issues)}")
    
    # Execute button
    if st.button("🚀 Execute Task", type="primary", disabled=not task_description or not api_keys_configured):
        with st.spinner("🤖 Agents are working..."):
            try:
                # Import here to avoid circular imports
                from crews import run_dev_task
                
                # Create status container
                status = st.status("Running task...", expanded=True)
                
                with status:
                    st.write("📋 Manager is planning...")
                    
                    result = run_dev_task(
                        task_description=task_description,
                        context=context if context else None,
                        require_review=require_review,
                        use_claude_cli=use_claude_cli,
                    )
                    
                    st.write("✅ Task completed!")
                
                # Store result
                task_record = {
                    "timestamp": datetime.now().isoformat(),
                    "description": task_description,
                    "result": result,
                    "status": "completed"
                }
                st.session_state.task_history.append(task_record)
                st.session_state.current_task = task_record
                
                # Show result
                st.success("Task completed!")
                
                with st.expander("📄 Full Result", expanded=True):
                    st.markdown(result["result"])
                
                # Human approval for file changes
                if result.get("needs_approval"):
                    st.session_state.pending_approval = task_record
                    st.warning("⚠️ This task modified files. Please review and approve.")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Approve Changes"):
                            st.session_state.pending_approval = None
                            st.success("Changes approved!")
                    with col2:
                        if st.button("❌ Reject Changes"):
                            st.session_state.pending_approval = None
                            st.error("Changes rejected. Files will be reverted.")
                
            except Exception as e:
                st.error(f"Error: {e}")
                import traceback
                st.code(traceback.format_exc())


# =============================================================================
# Tab 2: Focus - Workspace Switcher
# =============================================================================

with tab2:
    st.markdown("### 🎯 Project Workspaces")
    st.caption("Open dedicated Cursor workspaces for each client project")
    
    if not FOCUS_AVAILABLE:
        st.warning("Focus tools not available. Check tools/devops.py import.")
    else:
        workspaces = list_workspaces()
        
        if not workspaces:
            st.info("No workspaces found. Create .code-workspace files in DevOps/.cursor/workspaces/")
        else:
            # Open mode selector
            st.markdown("**Open Mode:**")
            open_mode = st.radio(
                "How do you want to open projects?",
                options=["🖥️ Cursor Window", "🌐 Agent in Browser"],
                horizontal=True,
                key="focus_open_mode",
                label_visibility="collapsed"
            )
            
            st.divider()
            st.markdown(f"**{len(workspaces)} workspaces available:**")
            
            # Display workspaces in a grid
            cols = st.columns(3)
            
            for i, ws in enumerate(workspaces):
                col = cols[i % 3]
                with col:
                    with st.container():
                        st.markdown(f"#### 📁 {ws['name']}")
                        st.caption(ws['description'])
                        
                        btn_label = "🚀 Open Window" if "Window" in open_mode else "🤖 Open Agent"
                        
                        if st.button(btn_label, key=f"focus_{ws['name']}"):
                            import subprocess
                            import webbrowser
                            
                            if "Window" in open_mode:
                                # Open Cursor desktop window
                                try:
                                    subprocess.Popen(
                                        ["cursor", "--no-sandbox", ws['path']],
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        start_new_session=True,
                                    )
                                    st.success(f"✓ Opening {ws['name']} in Cursor...")
                                except Exception as e:
                                    st.error(f"Failed to open: {e}")
                            else:
                                # Open Cursor Agent in browser tab
                                # Get the workspace folder path from the .code-workspace file
                                import json
                                try:
                                    with open(ws['path'], 'r') as f:
                                        ws_config = json.load(f)
                                    folders = ws_config.get('folders', [])
                                    if folders:
                                        folder_path = folders[0].get('path', '')
                                        # Resolve relative paths
                                        if not folder_path.startswith('/'):
                                            from pathlib import Path
                                            ws_dir = Path(ws['path']).parent
                                            folder_path = str((ws_dir / folder_path).resolve())
                                        
                                        # Cursor Agent URL format
                                        agent_url = f"https://cursor.com/agent?folder={folder_path}"
                                        st.markdown(f"[🤖 Open Agent Tab]({agent_url})")
                                        st.info(f"Click the link above to open {ws['name']} in Cursor Agent")
                                    else:
                                        st.error("No folders found in workspace config")
                                except Exception as e:
                                    st.error(f"Failed to parse workspace: {e}")
                        
                        st.markdown("---")
            
            # Quick open input
            st.markdown("### Quick Open")
            quick_open = st.text_input(
                "Project name:",
                placeholder="e.g., apdriving, odg-erp, lcp",
                key="focus_quick_open"
            )
            
            if quick_open:
                matching = [ws for ws in workspaces if quick_open.lower() in ws['name'].lower()]
                if matching:
                    ws = matching[0]
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"🖥️ Open {ws['name']} Window", type="primary"):
                            import subprocess
                            subprocess.Popen(
                                ["cursor", "--no-sandbox", ws['path']],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True,
                            )
                            st.success(f"✓ Opening {ws['name']} in Cursor...")
                    with col2:
                        import json
                        try:
                            with open(ws['path'], 'r') as f:
                                ws_config = json.load(f)
                            folders = ws_config.get('folders', [])
                            if folders:
                                folder_path = folders[0].get('path', '')
                                if not folder_path.startswith('/'):
                                    from pathlib import Path
                                    ws_dir = Path(ws['path']).parent
                                    folder_path = str((ws_dir / folder_path).resolve())
                                agent_url = f"https://cursor.com/agent?folder={folder_path}"
                                st.link_button(f"🤖 Open {ws['name']} Agent", agent_url)
                        except:
                            pass
                else:
                    st.warning(f"No workspace matching '{quick_open}'")


# =============================================================================
# Tab 3: Time Tracking (Harvest)
# =============================================================================

with tab3:
    st.markdown("### ⏱️ Time Tracking")
    st.caption("Track time on tickets using Harvest")
    
    if not HARVEST_AVAILABLE:
        st.warning("Harvest tools not available. Check tools/harvest.py import.")
    else:
        status = harvest_get_status()
        
        if not status.get("configured"):
            st.error("⚠️ Harvest not configured")
            st.markdown("""
            Add these to your `.env` file:
            ```
            HARVEST_ACCESS_TOKEN=your_token
            HARVEST_ACCOUNT_ID=your_account_id
            HARVEST_DEFAULT_PROJECT_ID=123456
            HARVEST_DEFAULT_TASK_ID=789012
            ```
            """)
        else:
            # Status display
            col1, col2, col3 = st.columns(3)
            with col1:
                running = status.get("running_timer")
                if running:
                    st.metric("Timer", "🟢 Running")
                else:
                    st.metric("Timer", "⏹️ Stopped")
            with col2:
                st.metric("Today's Hours", f"{status.get('today_hours', 0):.2f}h")
            with col3:
                st.metric("Entries Today", status.get("today_entries", 0))
            
            st.divider()
            
            # Running timer details
            if running:
                st.success(f"⏱️ Timer running: {running.get('notes', 'No notes')}")
                if st.button("⏹️ Stop Timer", type="primary"):
                    result = harvest_stop_timer()
                    if result.get("error"):
                        st.error(result["error"])
                    else:
                        st.success(f"Stopped! Logged {result.get('hours', 0)} hours")
                        st.rerun()
            
            st.divider()
            
            # Start timer section
            st.markdown("#### Start Timer")
            col1, col2 = st.columns([1, 3])
            with col1:
                timer_ticket = st.text_input("Ticket ID", placeholder="4962", key="timer_ticket")
            with col2:
                timer_notes = st.text_input("Notes", placeholder="Working on feature X", key="timer_notes")
            
            if st.button("▶️ Start Timer", disabled=not timer_ticket or not timer_notes):
                result = harvest_start_timer(timer_ticket, timer_notes)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.success(f"Started timer for ticket #{timer_ticket}")
                    st.rerun()
            
            st.divider()
            
            # Log time section
            st.markdown("#### Log Completed Time")
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                log_ticket = st.text_input("Ticket ID", placeholder="4962", key="log_ticket")
            with col2:
                log_hours = st.number_input("Hours", min_value=0.0, max_value=24.0, step=0.25, value=0.5, key="log_hours")
            with col3:
                log_notes = st.text_input("Notes", placeholder="Completed feature X", key="log_notes")
            
            if st.button("📊 Log Time", disabled=not log_ticket or not log_notes or log_hours <= 0):
                result = harvest_log_time(log_ticket, log_hours, log_notes)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.success(f"Logged {log_hours}h for ticket #{log_ticket}")
                    st.rerun()
            
            # Today's entries
            st.divider()
            st.markdown("#### Today's Time Entries")
            entries = status.get("entries", [])
            if entries:
                for entry in entries:
                    hours = entry.get("hours", 0)
                    notes = entry.get("notes", "No notes")
                    project = entry.get("project", {}).get("name", "Unknown")
                    st.markdown(f"• **{hours}h** - {notes[:60]}... ({project})")
            else:
                st.info("No entries logged today")


# =============================================================================
# Tab 4: Voice Interface
# =============================================================================

with tab4:
    if VOICE_AVAILABLE:
        st.markdown("### 🎙️ Voice Interface")
        st.caption("Use your voice to interact with the orchestrator")
        
        # Render voice interface
        voice_transcript = render_voice_interface()
        
        if voice_transcript:
            st.markdown("---")
            st.markdown("**Transcript:**")
            st.info(voice_transcript)
            
            if st.button("📤 Send to Task Input", key="send_voice_to_task"):
                st.session_state["voice_task"] = voice_transcript
                st.success("Transcript copied! Switch to 'New Task' tab to execute.")
        
        # TTS settings
        st.markdown("---")
        st.markdown("#### Text-to-Speech Settings")
        
        if st.session_state.get("tts_enabled"):
            test_text = st.text_input("Test TTS:", placeholder="Type something to test...")
            if test_text and st.button("🔊 Speak"):
                text_to_speech(test_text)
    else:
        st.warning("Voice components not available. Check components/voice.py import.")


# =============================================================================
# Tab 5: History
# =============================================================================

with tab5:
    st.markdown("### Task History")
    
    if not st.session_state.task_history:
        st.info("No tasks completed yet. Submit a task to get started!")
    else:
        for i, task in enumerate(reversed(st.session_state.task_history)):
            with st.expander(f"Task {len(st.session_state.task_history) - i}: {task['description'][:50]}..."):
                st.caption(f"Completed: {task['timestamp']}")
                st.markdown(task['result']['result'])


# =============================================================================
# Tab 6: Governance
# =============================================================================

with tab6:
    st.markdown("### Governance Dashboard")
    
    # Cost Tracker
    st.markdown("#### Cost Tracking")
    cost_tracker = get_cost_tracker()
    summary = cost_tracker.get_summary()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tokens Used", f"{summary['total_tokens']:,}", 
                  delta=f"{summary['usage_percentage']:.1f}%")
    with col2:
        st.metric("API Calls", summary['total_api_calls'], 
                  delta=f"/{summary['max_api_calls']} max")
    with col3:
        st.metric("Est. Cost", f"${summary['estimated_cost_usd']:.4f}")
    with col4:
        circuit_color = "🟢" if summary['circuit_state'] == "closed" else "🔴"
        st.metric("Circuit", f"{circuit_color} {summary['circuit_state'].title()}")
    
    if summary['warnings']:
        st.warning("⚠️ " + " | ".join(summary['warnings']))
    
    # Audit Log
    st.markdown("#### Recent Audit Events")
    audit_logger = get_audit_logger()
    if audit_logger.events:
        for event in reversed(audit_logger.events[-10:]):
            with st.expander(f"{event.action_type.value}: {event.description[:50]}...", expanded=False):
                st.json(event.to_dict())
    else:
        st.info("No audit events yet. Submit a task to see activity.")
    
    # Policy Validator
    st.markdown("#### Policy Validator")
    test_input = st.text_input("Test a task against policies:", 
                               placeholder="e.g., 'Update the production database'")
    if test_input:
        result = validate_before_execution(task=test_input)
        if result.is_blocked:
            st.error(f"🚫 BLOCKED: {', '.join(i.message for i in result.issues)}")
        elif result.requires_escalation:
            st.warning(f"⚠️ ESCALATE: {', '.join(i.message for i in result.issues)}")
        elif result.has_warnings:
            st.warning(f"⚡ WARNING: {', '.join(i.message for i in result.issues)}")
        else:
            st.success("✅ PASS: Task complies with all policies")
    
    # Active Policies
    st.markdown("#### Active Policies")
    with st.expander("Security Policies"):
        st.markdown("**Blocked Paths:**")
        st.code(", ".join(POLICIES["security"]["blocked_paths"][:10]) + "...")
        st.markdown("**Blocked Commands:**")
        st.code(", ".join(POLICIES["security"]["blocked_commands"][:5]) + "...")
    
    with st.expander("Cost Limits"):
        st.markdown(f"""
        - **Max tokens per task:** {POLICIES['cost']['max_tokens_per_task']:,}
        - **Max API calls per task:** {POLICIES['cost']['max_api_calls_per_task']}
        - **Circuit breaker threshold:** {POLICIES['cost']['circuit_breaker_threshold']} failures
        - **Rate limit:** {POLICIES['cost']['max_requests_per_minute']} req/min
        """)
    
    with st.expander("Escalation Triggers"):
        for trigger in POLICIES["escalation"]["auto_escalate_triggers"]:
            st.markdown(f"- {trigger}")
    
    # Allowlist Management
    st.markdown("#### Allowlist (Whitelist)")
    allowlist = get_allowlist()
    summary = allowlist.get_summary()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Allowed Paths", summary["paths"])
    with col2:
        st.metric("Allowed Commands", summary["commands"])
    with col3:
        st.metric("Pending Proposals", summary["pending_proposals"])
    
    # Pending proposals
    pending = [p for p in allowlist.proposed if p.status == "pending"]
    if pending:
        st.warning(f"⚠️ {len(pending)} pending allowlist proposals require review")
        
        for i, proposal in enumerate(pending):
            with st.expander(f"Proposal: {proposal.entry.pattern[:40]}..."):
                st.markdown(f"**Pattern:** `{proposal.entry.pattern}`")
                st.markdown(f"**Permission:** {proposal.entry.permission.value}")
                st.markdown(f"**Reason:** {proposal.reason}")
                st.markdown(f"**Risk:** {proposal.risk_assessment}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅ Approve", key=f"approve_{i}"):
                        allowlist.approve_proposal(i, "human")
                        st.success("Approved!")
                        st.rerun()
                with col2:
                    if st.button(f"❌ Reject", key=f"reject_{i}"):
                        allowlist.reject_proposal(i)
                        st.info("Rejected")
                        st.rerun()
    
    # View current allowlist
    with st.expander("View Allowlist Entries"):
        tab_env, tab_paths, tab_cmds, tab_tools = st.tabs(["Environments", "Paths", "Commands", "Tools"])
        
        with tab_env:
            for entry in allowlist.environments:
                st.markdown(f"- `{entry.pattern}` ({entry.permission.value}): {entry.description}")
        
        with tab_paths:
            for entry in allowlist.paths[:20]:  # Limit display
                st.markdown(f"- `{entry.pattern[:50]}...` ({entry.permission.value})")
            if len(allowlist.paths) > 20:
                st.caption(f"... and {len(allowlist.paths) - 20} more")
        
        with tab_cmds:
            for entry in allowlist.commands:
                st.markdown(f"- `{entry.pattern}` ({entry.permission.value})")
        
        with tab_tools:
            for entry in allowlist.tools:
                st.markdown(f"- `{entry.pattern}` ({entry.permission.value}): {entry.description}")


# =============================================================================
# Tab 7: Settings
# =============================================================================

with tab7:
    st.markdown("### Agent Configuration")
    
    st.markdown("#### Available Agents")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **📋 Manager**
        - Plans and coordinates
        - Decomposes complex tasks
        - Never writes code
        - Escalates when needed
        """)
    
    with col2:
        st.markdown("""
        **💻 Coder**
        - Writes complete code
        - Follows existing patterns
        - Uses file tools
        - No placeholders
        """)
    
    with col3:
        st.markdown("""
        **🔍 Reviewer**
        - Finds bugs & issues
        - Security focused
        - Brutally honest
        - Never suggests features
        """)
    
    st.divider()
    
    st.markdown("#### Workspace Files")
    workspace_path = Path(os.getenv("WORKSPACE_ROOT", "/home/steve/Agent007"))
    
    if workspace_path.exists():
        dirs = [d.name for d in workspace_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
        st.write("📁 " + ", ".join(sorted(dirs)[:10]))
    else:
        st.warning(f"Workspace not found: {workspace_path}")


# =============================================================================
# Footer
# =============================================================================

st.divider()
st.caption("Orchestrator v1.0 | Reliable AI-assisted development with human oversight")
