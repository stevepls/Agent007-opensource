"""
Queue Manager — Snapshots

A QueueSnapshot is the current ordered state of the queue.
The Orchestrator consumes snapshots to build the SurfaceResponse.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from queue.models import QueueItem


@dataclass
class QueueSnapshot:
    """Point-in-time snapshot of the queue state."""

    # Ordered items (highest score first)
    items: List[QueueItem]

    # Summary stats
    total: int = 0
    critical_count: int = 0
    high_count: int = 0
    unacked_count: int = 0

    # Groupings
    by_project: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)

    # Top promoted item (if any)
    promoted_item: Optional[QueueItem] = None
    promoted_reason: Optional[str] = None

    # Metadata
    version: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    compute_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "unacked_count": self.unacked_count,
            "by_project": self.by_project,
            "by_severity": self.by_severity,
            "by_source": self.by_source,
            "promoted_item": self.promoted_item.to_dict() if self.promoted_item else None,
            "promoted_reason": self.promoted_reason,
            "items": [item.to_dict() for item in self.items],
            "version": self.version,
            "timestamp": self.timestamp,
            "compute_time_ms": round(self.compute_time_ms, 2),
        }

    def top(self, n: int = 10) -> List[QueueItem]:
        """Get the top N items."""
        return self.items[:n]

    def for_project(self, project_name: str) -> List[QueueItem]:
        """Get items for a specific project."""
        return [i for i in self.items if i.project_name == project_name]

    def unacked(self) -> List[QueueItem]:
        """Get all unacknowledged items."""
        from queue.models import AckState
        return [i for i in self.items if i.ack_state == AckState.UNACKED]
