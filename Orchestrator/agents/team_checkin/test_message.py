#!/usr/bin/env python3
"""Test script to create a sample message for the approval UI."""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.message_queue import get_message_queue, MessageType, MessageStatus

def create_test_message():
    """Create a test message for demonstration."""
    queue = get_message_queue()
    
    # Create a test morning message
    msg = queue.queue(
        msg_type=MessageType.SLACK_DM,
        channel="U01234567",  # Test Slack user ID
        content="Hey John, good morning! Let me know when you're ready to start today.\n\nYour priorities:\n• Implement user authentication – due 2026-02-10\n• Fix payment gateway bug – due 2026-02-08\n\nDo you have an update on the payment gateway bug? This is blocking production.\n\nCan you please provide a brief update on the most important tasks and let me know what your game plan is?\n\nFocus on the payment gateway bug first because it's a critical production issue.\n\nStill on track for everything? Reply when you're online/starting and I'll update the ticket status and kick off your time tracking for you.",
        subject="Morning check-in for John Doe",
        metadata={
            "member_name": "John Doe",
            "message_type": "morning",
            "priority_tasks": [
                {"name": "Implement user authentication", "due_date": "2026-02-10"},
                {"name": "Fix payment gateway bug", "due_date": "2026-02-08"}
            ],
            "team_checkin": True
        },
        created_by="team_checkin_agent",
        requires_approval=True,
        delay_seconds=0
    )
    
    print(f"✅ Created test message with ID: {msg.id}")
    print(f"   Status: {msg.status.value}")
    print(f"   Member: {msg.metadata.get('member_name')}")
    print(f"   Type: {msg.metadata.get('message_type')}")
    print(f"\nView it at: http://localhost:8502/team-checkin/messages/pending")
    return msg.id

if __name__ == "__main__":
    create_test_message()
