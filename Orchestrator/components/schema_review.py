"""
Schema Review Component

Renders UI for reviewing database schema changes.
Automatically prompts user when changes are detected.
"""

import streamlit as st
from typing import List, Optional

try:
    from services.schema_detector import (
        get_schema_detector,
        SchemaChange,
        SchemaChangeType,
    )
    DETECTOR_AVAILABLE = True
except ImportError:
    DETECTOR_AVAILABLE = False


# Type styling
TYPE_STYLES = {
    SchemaChangeType.CREATE_TABLE: {"icon": "🆕", "color": "#4caf50"},
    SchemaChangeType.ALTER_TABLE: {"icon": "✏️", "color": "#ff9800"},
    SchemaChangeType.DROP_TABLE: {"icon": "🗑️", "color": "#f44336"},
    SchemaChangeType.ADD_COLUMN: {"icon": "➕", "color": "#2196f3"},
    SchemaChangeType.DROP_COLUMN: {"icon": "➖", "color": "#ff5722"},
    SchemaChangeType.ADD_INDEX: {"icon": "📇", "color": "#9c27b0"},
    SchemaChangeType.DROP_INDEX: {"icon": "📉", "color": "#795548"},
    SchemaChangeType.ADD_CONSTRAINT: {"icon": "🔗", "color": "#607d8b"},
    SchemaChangeType.DROP_CONSTRAINT: {"icon": "🔓", "color": "#9e9e9e"},
    SchemaChangeType.MIGRATION: {"icon": "📦", "color": "#00bcd4"},
    SchemaChangeType.MODEL_CHANGE: {"icon": "🏗️", "color": "#3f51b5"},
    SchemaChangeType.UNKNOWN: {"icon": "❓", "color": "#757575"},
}


def render_schema_change(change: "SchemaChange"):
    """Render a single schema change card."""
    style = TYPE_STYLES.get(change.type, TYPE_STYLES[SchemaChangeType.UNKNOWN])
    
    with st.container():
        # Header
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            status = "✅ Reviewed" if change.reviewed else "⏳ Pending Review"
            st.markdown(f"""
            **{style['icon']} {change.type.value.replace('_', ' ').title()}** {status}
            
            `{change.file_path}`
            """)
        
        with col2:
            st.markdown(f"""
            <span style="color: green;">+{change.lines_added}</span> /
            <span style="color: red;">-{change.lines_removed}</span>
            """, unsafe_allow_html=True)
        
        with col3:
            st.caption(change.commit_date[:10])
        
        # Details
        with st.expander("View Details", expanded=not change.reviewed):
            st.markdown(f"""
            **Commit:** `{change.commit_hash[:8]}`
            
            **Message:** {change.commit_message}
            
            **Author:** {change.author}
            """)
            
            # Preview diff
            if change.preview:
                st.markdown("**Changes:**")
                st.code(change.preview, language="diff")
            
            # Actions
            if not change.reviewed:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("✅ Mark Reviewed", key=f"review_{change.id}"):
                        detector = get_schema_detector()
                        detector.mark_reviewed(change.id, "human")
                        st.success("Marked as reviewed!")
                        st.rerun()
                
                with col2:
                    if st.button("🔍 View Full Diff", key=f"diff_{change.id}"):
                        st.session_state.view_full_diff = change.commit_hash
                
                with col3:
                    if st.button("💬 Add Note", key=f"note_{change.id}"):
                        st.session_state.add_note_for = change.id
            else:
                st.info(f"Reviewed by {change.reviewed_by} at {change.reviewed_at}")
        
        st.divider()


def render_schema_alert():
    """Render an alert if there are unreviewed schema changes."""
    if not DETECTOR_AVAILABLE:
        return False
    
    detector = get_schema_detector()
    
    if detector.needs_attention():
        summary = detector.get_summary()
        
        st.warning(f"""
        ⚠️ **Schema Changes Detected**
        
        {summary['unreviewed']} unreviewed schema change(s) found in recent commits.
        Review them in the Database tab.
        """)
        
        if st.button("🔍 Review Now", key="goto_schema_review"):
            st.session_state.active_tab = "database"
            return True
    
    return False


def render_schema_review_panel(show_all: bool = False):
    """Render the full schema review panel."""
    if not DETECTOR_AVAILABLE:
        st.error("Schema detector not available.")
        return
    
    st.markdown("### 📊 Schema Changes")
    
    detector = get_schema_detector()
    
    # Controls
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        since = st.selectbox(
            "Time Range",
            ["7 days ago", "14 days ago", "30 days ago", "90 days ago"],
            index=0,
            key="schema_since"
        )
    
    with col2:
        include_reviewed = st.checkbox("Show Reviewed", value=show_all, key="schema_show_reviewed")
    
    with col3:
        if st.button("🔄 Refresh", key="schema_refresh"):
            detector.detect_changes(since=since)
            st.rerun()
    
    # Get changes
    changes = detector.detect_changes(since=since, include_reviewed=include_reviewed)
    
    if not changes:
        st.success("✅ No schema changes found in the selected time range.")
        return
    
    # Summary stats
    summary = detector.get_summary()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Changes", summary["total"])
    
    with col2:
        st.metric("Pending Review", summary["unreviewed"])
    
    with col3:
        st.metric("Reviewed", summary["total"] - summary["unreviewed"])
    
    with col4:
        # Most common type
        if summary["by_type"]:
            most_common = max(summary["by_type"].items(), key=lambda x: x[1])
            st.metric("Most Common", most_common[0].replace("_", " ").title())
    
    st.divider()
    
    # Pending first
    pending = [c for c in changes if not c.reviewed]
    reviewed = [c for c in changes if c.reviewed]
    
    if pending:
        st.markdown("#### ⏳ Pending Review")
        for change in pending:
            render_schema_change(change)
    
    if reviewed and include_reviewed:
        st.markdown("#### ✅ Already Reviewed")
        for change in reviewed:
            render_schema_change(change)
    
    # Bulk actions
    if pending:
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Mark All as Reviewed", key="review_all"):
                for change in pending:
                    detector.mark_reviewed(change.id, "human")
                st.success(f"Marked {len(pending)} changes as reviewed!")
                st.rerun()


def render_schema_mini_widget():
    """Render a compact schema status widget for the sidebar or dashboard."""
    if not DETECTOR_AVAILABLE:
        return
    
    detector = get_schema_detector()
    summary = detector.get_summary()
    
    if summary["unreviewed"] > 0:
        st.markdown(f"""
        <div style="
            background: rgba(255, 152, 0, 0.1);
            border: 1px solid #ff9800;
            border-radius: 8px;
            padding: 0.75rem;
            margin-bottom: 1rem;
        ">
            <span style="font-size: 1.2rem;">📊</span>
            <strong>{summary['unreviewed']}</strong> schema change(s) need review
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="
            background: rgba(76, 175, 80, 0.1);
            border: 1px solid #4caf50;
            border-radius: 8px;
            padding: 0.75rem;
            margin-bottom: 1rem;
        ">
            <span style="font-size: 1.2rem;">✅</span>
            Schema up to date
        </div>
        """, unsafe_allow_html=True)
