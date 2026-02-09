"""
DEPRECATED - Use services.message_queue instead.

This local message queue has been superseded by the central Orchestrator
message queue at services/message_queue.py which provides:
- Atomic file writes
- Thread-safe operations
- Sender registration
- Approval workflow
- Queue cleanup

Usage:
    from services.message_queue import get_message_queue, MessageType
    queue = get_message_queue()
    queue.queue(msg_type=MessageType.SLACK_DM, channel=..., content=...)
"""

import warnings

warnings.warn(
    "agents.team_checkin.message_queue is deprecated. Use services.message_queue instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from central queue for backwards compatibility
from services.message_queue import (
    get_message_queue,
    MessageQueue,
    MessageType,
    MessageStatus,
    QueuedMessage,
)
