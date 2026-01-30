"""
Orchestrator Services

External service integrations wrapped for Orchestrator use.
All outgoing communications go through message queue with delays.
All sensitive operations require manual confirmation.
"""

# Accounting
from .accounting import UpworkSyncClient, get_sync_client

# Message Queue (all sends go through here)
from .message_queue import (
    MessageQueue,
    MessageType,
    MessageStatus,
    QueuedMessage,
    get_message_queue,
)

# Canned Responses (agents can only use pre-approved templates)
from .canned_responses import (
    CannedResponseRegistry,
    ResponseCategory,
    ResponseChannel,
    get_response_registry,
    use_canned_response,
)

# Schema Detection (monitors all projects for DB changes)
from .schema_detector import (
    get_schema_detector,
    add_client_project,
    SchemaChange,
    SchemaChangeType,
    SchemaChangeDetector,
)

__all__ = [
    # Accounting
    "UpworkSyncClient",
    "get_sync_client",
    
    # Message Queue
    "MessageQueue",
    "MessageType",
    "MessageStatus",
    "QueuedMessage",
    "get_message_queue",
    
    # Canned Responses
    "CannedResponseRegistry",
    "ResponseCategory",
    "ResponseChannel",
    "get_response_registry",
    "use_canned_response",
    
    # Schema Detection
    "get_schema_detector",
    "add_client_project",
    "SchemaChange",
    "SchemaChangeType",
    "SchemaChangeDetector",
]
