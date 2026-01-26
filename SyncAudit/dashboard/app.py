"""
SyncAudit Dashboard - Streamlit UI

View sync events, mismatches, and statistics across all projects.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import get_session
from models.sync_event import SyncEventDB, SyncStatus, EventType

# =============================================================================
# Page Configuration
# =============================================================================

st.set_page_config(
    page_title="SyncAudit Dashboard",
    page_icon="🔄",
    layout="wide",
)

st.title("🔄 SyncAudit Dashboard")
st.caption("Monitor sync events and data mismatches across all projects")

# =============================================================================
# Sidebar - Filters
# =============================================================================

with st.sidebar:
    st.header("Filters")

    # Project filter
    project_filter = st.text_input("Project", placeholder="e.g., apdriving")

    # Status filter
    status_options = ["All"] + [s.value for s in SyncStatus]
    status_filter = st.selectbox("Status", status_options)

    # Date range
    days_back = st.slider("Days back", 1, 30, 7)

    st.divider()

    if st.button("🔄 Refresh"):
        st.rerun()

# =============================================================================
# Main Content
# =============================================================================

try:
    session = get_session()

    # Build query
    query = session.query(SyncEventDB)

    if project_filter:
        query = query.filter(SyncEventDB.project == project_filter)

    if status_filter != "All":
        query = query.filter(SyncEventDB.status == status_filter)

    since = datetime.utcnow() - timedelta(days=days_back)
    query = query.filter(SyncEventDB.created_at >= since)

    events = query.order_by(SyncEventDB.created_at.desc()).limit(100).all()

    # Stats
    col1, col2, col3, col4 = st.columns(4)

    total = len(events)
    synced = len([e for e in events if e.status == SyncStatus.SYNCED.value])
    failed = len([e for e in events if e.status == SyncStatus.FAILED.value])
    mismatches = len([e for e in events if e.status == SyncStatus.MISMATCH.value])

    with col1:
        st.metric("Total Events", total)
    with col2:
        st.metric("Synced", synced, delta=f"{(synced/total*100):.0f}%" if total else "0%")
    with col3:
        st.metric("Failed", failed)
    with col4:
        st.metric("Mismatches", mismatches)

    st.divider()

    # Events table
    st.subheader("Recent Events")

    if not events:
        st.info("No events found matching filters.")
    else:
        for event in events:
            status_icon = {
                "synced": "✅",
                "failed": "❌",
                "mismatch": "⚠️",
                "pending": "⏳",
                "skipped": "⏭️",
            }.get(event.status, "❓")

            with st.expander(
                f"{status_icon} {event.project} | {event.source_system} → {event.target_system} | {event.source_id}",
                expanded=event.status in ["failed", "mismatch"]
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**Event Type:** {event.event_type}")
                    st.markdown(f"**Status:** {event.status}")
                    st.markdown(f"**Created:** {event.created_at}")
                    if event.triggered_by:
                        st.markdown(f"**Triggered By:** {event.triggered_by}")

                with col2:
                    st.markdown(f"**Source ID:** {event.source_id}")
                    st.markdown(f"**Target ID:** {event.target_id or 'N/A'}")
                    if event.synced_at:
                        st.markdown(f"**Synced At:** {event.synced_at}")

                if event.error_message:
                    st.error(f"**Error:** {event.error_message}")

                if event.mismatches:
                    st.warning(f"**Mismatches ({event.mismatch_count}):**")
                    for m in event.mismatches:
                        st.markdown(f"- `{m.get('field')}`: {m.get('source_value')} ≠ {m.get('target_value')}")

                if event.notes:
                    st.info(f"**Notes:** {event.notes}")

    session.close()

except Exception as e:
    st.error(f"Database connection error: {e}")
    st.info("Make sure the database is configured. Check your .env file.")

# =============================================================================
# Footer
# =============================================================================

st.divider()
st.caption("SyncAudit - Universal sync monitoring for all projects")
