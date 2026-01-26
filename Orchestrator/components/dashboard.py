"""
Dynamic Dashboard Component

Renders a proactive, briefing-style dashboard that surfaces
what the user needs to see. Like having a smart assistant
in a constant meeting, updating you on what matters.
"""

import streamlit as st
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional

# Try to import briefing engine
try:
    from services.briefing import (
        get_briefing_engine,
        BriefingItem,
        Priority,
        ItemType,
    )
    BRIEFING_AVAILABLE = True
except ImportError:
    BRIEFING_AVAILABLE = False


# Priority styling
PRIORITY_STYLES = {
    Priority.CRITICAL: {
        "icon": "🚨",
        "color": "#ff4444",
        "bg": "rgba(255, 68, 68, 0.1)",
        "border": "2px solid #ff4444",
    },
    Priority.HIGH: {
        "icon": "⚠️",
        "color": "#ff9800",
        "bg": "rgba(255, 152, 0, 0.1)",
        "border": "1px solid #ff9800",
    },
    Priority.MEDIUM: {
        "icon": "📋",
        "color": "#2196f3",
        "bg": "rgba(33, 150, 243, 0.05)",
        "border": "1px solid rgba(33, 150, 243, 0.3)",
    },
    Priority.LOW: {
        "icon": "💡",
        "color": "#4caf50",
        "bg": "rgba(76, 175, 80, 0.05)",
        "border": "1px solid rgba(76, 175, 80, 0.2)",
    },
    Priority.INFO: {
        "icon": "ℹ️",
        "color": "#9e9e9e",
        "bg": "rgba(158, 158, 158, 0.05)",
        "border": "1px solid rgba(158, 158, 158, 0.2)",
    },
}

TYPE_ICONS = {
    ItemType.SCHEMA_CHANGE: "📊",
    ItemType.PENDING_APPROVAL: "⏳",
    ItemType.CODE_REVIEW: "💻",
    ItemType.MESSAGE_QUEUE: "📬",
    ItemType.ERROR: "🔴",
    ItemType.TODO: "📝",
    ItemType.MEETING: "📅",
    ItemType.DEADLINE: "⏰",
    ItemType.INSIGHT: "💡",
    ItemType.SUGGESTION: "✨",
}


def render_dashboard_css():
    """Inject custom CSS for the dashboard."""
    st.markdown("""
    <style>
    /* Dashboard container */
    .dashboard-container {
        padding: 1rem;
    }
    
    /* Greeting banner */
    .greeting-banner {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    
    .greeting-text {
        font-size: 1.4rem;
        font-weight: 500;
        margin: 0;
    }
    
    .greeting-time {
        font-size: 0.9rem;
        opacity: 0.8;
        margin-top: 0.3rem;
    }
    
    /* Briefing item card */
    .briefing-card {
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 0.75rem;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    
    .briefing-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    .briefing-title {
        font-size: 1rem;
        font-weight: 600;
        margin: 0 0 0.3rem 0;
    }
    
    .briefing-description {
        font-size: 0.85rem;
        opacity: 0.8;
        margin: 0;
        line-height: 1.4;
    }
    
    .briefing-meta {
        font-size: 0.75rem;
        opacity: 0.6;
        margin-top: 0.5rem;
    }
    
    /* Stats row */
    .stats-row {
        display: flex;
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    
    .stat-card {
        flex: 1;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
    
    .stat-value {
        font-size: 2rem;
        font-weight: 700;
    }
    
    .stat-label {
        font-size: 0.8rem;
        opacity: 0.6;
        text-transform: uppercase;
    }
    
    /* Section headers */
    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        margin: 0;
    }
    
    /* Quick actions */
    .quick-action {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 20px;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .quick-action:hover {
        background: rgba(255,255,255,0.1);
        border-color: rgba(255,255,255,0.2);
    }
    
    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 3rem;
        opacity: 0.6;
    }
    
    .empty-state-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)


def render_greeting():
    """Render the greeting banner."""
    if not BRIEFING_AVAILABLE:
        st.info("Briefing engine not available.")
        return
    
    engine = get_briefing_engine()
    greeting = engine.get_greeting()
    now = datetime.now()
    
    st.markdown(f"""
    <div class="greeting-banner">
        <p class="greeting-text">{greeting}</p>
        <p class="greeting-time">{now.strftime('%A, %B %d • %I:%M %p')}</p>
    </div>
    """, unsafe_allow_html=True)


def render_stats():
    """Render quick stats overview."""
    if not BRIEFING_AVAILABLE:
        return
    
    engine = get_briefing_engine()
    summary = engine.get_summary()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "🚨 Critical",
            summary.get("critical_count", 0),
            delta=None,
            help="Items requiring immediate attention"
        )
    
    with col2:
        st.metric(
            "⚠️ High Priority",
            summary.get("high_count", 0),
            help="Important items to review"
        )
    
    with col3:
        st.metric(
            "📋 Total Items",
            summary.get("total_items", 0),
            help="All items needing attention"
        )
    
    with col4:
        # Show status
        if summary.get("needs_attention"):
            st.metric("Status", "⚡ Action Needed")
        else:
            st.metric("Status", "✅ All Clear")


def render_briefing_item(item: "BriefingItem", action_handlers: Dict[str, Callable] = None):
    """Render a single briefing item as an interactive card."""
    style = PRIORITY_STYLES.get(item.priority, PRIORITY_STYLES[Priority.INFO])
    type_icon = TYPE_ICONS.get(item.type, "📌")
    
    # Create unique key for this item
    key_prefix = f"item_{item.id}"
    
    with st.container():
        st.markdown(f"""
        <div class="briefing-card" style="background: {style['bg']}; border: {style['border']};">
            <p class="briefing-title">{style['icon']} {type_icon} {item.title}</p>
            <p class="briefing-description">{item.description[:200]}</p>
            <p class="briefing-meta">From: {item.source} • {item.created_at[:16]}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Action buttons
        if item.action_label:
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                if st.button(f"✅ {item.action_label}", key=f"{key_prefix}_action", type="primary"):
                    if action_handlers and item.action_callback in action_handlers:
                        action_handlers[item.action_callback](item.action_data)
                    else:
                        st.info(f"Action: {item.action_callback}")
            
            with col2:
                if st.button("👁️ Details", key=f"{key_prefix}_details"):
                    st.json(item.metadata)
            
            with col3:
                if st.button("❌ Dismiss", key=f"{key_prefix}_dismiss"):
                    engine = get_briefing_engine()
                    engine.dismiss_item(item.id)
                    st.rerun()


def render_briefing_list(items: List["BriefingItem"], action_handlers: Dict[str, Callable] = None):
    """Render the full briefing list."""
    if not items:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-state-icon">🎉</div>
            <p>All clear! No items need your attention.</p>
        </div>
        """, unsafe_allow_html=True)
        return
    
    # Group by priority
    critical = [i for i in items if i.priority == Priority.CRITICAL]
    high = [i for i in items if i.priority == Priority.HIGH]
    other = [i for i in items if i.priority not in (Priority.CRITICAL, Priority.HIGH)]
    
    if critical:
        st.markdown("### 🚨 Requires Immediate Attention")
        for item in critical:
            render_briefing_item(item, action_handlers)
    
    if high:
        st.markdown("### ⚠️ High Priority")
        for item in high:
            render_briefing_item(item, action_handlers)
    
    if other:
        with st.expander(f"📋 Other Items ({len(other)})", expanded=False):
            for item in other:
                render_briefing_item(item, action_handlers)


def render_quick_actions():
    """Render quick action buttons."""
    st.markdown("### ⚡ Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔄 Refresh", use_container_width=True):
            if BRIEFING_AVAILABLE:
                engine = get_briefing_engine()
                engine.get_briefing(refresh=True)
            st.rerun()
    
    with col2:
        if st.button("📊 View Diff", use_container_width=True):
            st.session_state.quick_action = "view_diff"
    
    with col3:
        if st.button("📝 New Todo", use_container_width=True):
            st.session_state.quick_action = "new_todo"
    
    with col4:
        if st.button("🎙️ Voice Input", use_container_width=True):
            st.session_state.quick_action = "voice"


def render_context_panel():
    """Render the conversation context panel."""
    if not BRIEFING_AVAILABLE:
        return
    
    engine = get_briefing_engine()
    ctx = engine.context
    
    with st.expander("🎯 Current Context", expanded=False):
        if ctx.current_project:
            st.markdown(f"**Project:** {ctx.current_project}")
        if ctx.current_task:
            st.markdown(f"**Task:** {ctx.current_task}")
        if ctx.recent_topics:
            st.markdown(f"**Recent Topics:** {', '.join(ctx.recent_topics[:5])}")
        if ctx.last_action:
            st.markdown(f"**Last Action:** {ctx.last_action}")


def render_full_dashboard(action_handlers: Dict[str, Callable] = None):
    """Render the complete dashboard."""
    render_dashboard_css()
    
    # Greeting
    render_greeting()
    
    # Schema change alert
    try:
        from components.schema_review import render_schema_mini_widget, render_schema_alert
        render_schema_alert()
        render_schema_mini_widget()
    except ImportError:
        pass
    
    # Stats
    render_stats()
    
    st.divider()
    
    # Quick actions
    render_quick_actions()
    
    # Handle quick action modals
    if st.session_state.get("quick_action") == "new_todo":
        with st.form("quick_todo_form"):
            st.markdown("#### Quick Todo")
            title = st.text_input("What needs to be done?")
            priority = st.select_slider("Priority", options=["low", "medium", "high", "urgent"])
            if st.form_submit_button("Add Todo"):
                try:
                    from utils.todos import add_todo
                    add_todo(title, priority=priority)
                    st.success("Todo added!")
                    st.session_state.quick_action = None
                    st.rerun()
                except ImportError:
                    st.error("Todo system not available.")
    
    if st.session_state.get("quick_action") == "view_diff":
        try:
            from services.github.client import get_github_client
            gh = get_github_client()
            diffs = gh.get_unstaged_diff()
            if diffs:
                st.code(gh.format_diff_for_review(diffs), language="diff")
            else:
                st.info("No unstaged changes.")
        except ImportError:
            st.error("GitHub integration not available.")
        
        if st.button("Close"):
            st.session_state.quick_action = None
            st.rerun()
    
    st.divider()
    
    # Main briefing
    st.markdown("### 📋 Your Briefing")
    
    if BRIEFING_AVAILABLE:
        engine = get_briefing_engine()
        items = engine.get_briefing(max_items=10)
        render_briefing_list(items, action_handlers)
    else:
        st.warning("Briefing engine not available.")
    
    # Context panel
    render_context_panel()


def create_action_handlers():
    """Create default action handlers."""
    handlers = {}
    
    def approve_message(data):
        try:
            from services.message_queue import get_message_queue
            queue = get_message_queue()
            queue.approve(data["message_id"], "human")
            st.success("Message approved!")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
    
    def review_query(data):
        st.session_state.review_query_id = data["request_id"]
        st.info("Navigate to Database tab to review this query.")
    
    def complete_todo(data):
        try:
            from utils.todos import complete_todo
            complete_todo(data["todo_id"], "human")
            st.success("Todo completed!")
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
    
    def review_schema_changes(data):
        st.info(f"📊 {data.get('count', 'Multiple')} schema changes need review. Navigate to Database > Schema Review tab.")
    
    handlers["approve_message"] = approve_message
    handlers["review_query"] = review_query
    handlers["complete_todo"] = complete_todo
    handlers["review_schema_changes"] = review_schema_changes
    
    return handlers
