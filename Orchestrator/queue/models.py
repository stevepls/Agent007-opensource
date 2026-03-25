"""
Queue Manager — Normalized Item Model

Every work item from every source is normalized into a QueueItem.
This is the single canonical shape for the queue.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum


class Severity(Enum):
    """Item severity — determines notification channel and escalation."""
    INFO = "info"               # FYI, logs, completed work
    ATTENTION = "attention"     # Needs action within 24h
    HIGH = "high"               # Needs action within 4h, may be blocking
    CRITICAL = "critical"       # Needs action NOW


class SourceType(Enum):
    CLICKUP = "clickup"
    ZENDESK = "zendesk"
    GITHUB = "github"
    GMAIL = "gmail"
    SLACK = "slack"
    HARVEST = "harvest"
    PROACTIVE = "proactive"     # Agent findings


class AckState(Enum):
    UNACKED = "unacked"
    OPENED = "opened"           # User saw it in queue
    SNOOZED = "snoozed"        # Deferred
    ACTING = "acting"           # User is working on it (focus mode)
    RESOLVED = "resolved"       # Action completed


@dataclass
class ScoreBreakdown:
    """Explainable score components."""
    severity: float = 0.0           # 0-30
    urgency: float = 0.0            # 0-25 (deadline proximity)
    blocking: float = 0.0           # 0-15 (blocks other work)
    freshness: float = 0.0          # 0-10 (new activity)
    staleness_penalty: float = 0.0  # 0-10 (inactivity penalty)
    source_weight: float = 0.0      # 0-5 (client-facing > internal)
    ack_penalty: float = 0.0        # 0-5 (unacked items score higher)
    total: float = 0.0
    reasons: List[str] = field(default_factory=list)


@dataclass
class NotificationState:
    """Tracks notification/escalation state per item."""
    severity: Severity = Severity.INFO
    severity_reason: str = ""
    acknowledgment_required: bool = False
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None       # "queue_open" | "snooze" | "action" | "dismiss"
    acknowledged_via: Optional[str] = None      # "dashboard" | "slack" | "email" | "text"
    escalation_stage: int = 0
    channels_attempted: List[str] = field(default_factory=list)
    last_notified_at: Optional[str] = None
    last_notified_channel: Optional[str] = None
    next_escalation_at: Optional[str] = None
    escalation_paused: bool = False
    escalation_paused_until: Optional[str] = None
    call_eligible: bool = False
    snoozed: bool = False
    snoozed_until: Optional[str] = None
    snooze_count: int = 0
    notifications: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class QueueItem:
    """
    Normalized work item. The single canonical shape for the queue.
    Every source adapter produces these. The scoring engine ranks them.
    """
    # Identity
    id: str                                 # "clickup-868h4jwu3" or "zendesk-12345"
    source: SourceType
    source_id: str                          # ID in the source system
    source_url: Optional[str] = None

    # Content
    title: str = ""
    summary: Optional[str] = None           # Short description
    project_id: Optional[str] = None        # From project registry
    project_name: Optional[str] = None

    # Classification
    severity: Severity = Severity.INFO
    item_type: str = ""                     # "task", "ticket", "pr", "email", "insight"

    # Urgency signals
    deadline_at: Optional[datetime] = None
    sla_deadline_at: Optional[datetime] = None
    sla_tier: Optional[str] = None          # "gold", "silver", "bronze", "internal"
    blocking: bool = False                  # Blocks other work
    client_facing: bool = False             # Visible to client

    # Activity
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None

    # Assignment
    assignee: Optional[str] = None
    status: str = ""                        # Normalized: open, in_progress, review, done

    # Tags/metadata
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Scoring (computed by scoring engine)
    score: float = 0.0
    score_breakdown: Optional[ScoreBreakdown] = None
    score_computed_at: Optional[str] = None

    # Acknowledgment & notification
    ack_state: AckState = AckState.UNACKED
    notification: NotificationState = field(default_factory=NotificationState)

    # Promotion
    promotion_eligible: bool = False
    recommended_mode: Optional[str] = None  # "focus", "review", "compose", etc.
    recommended_actions: List[Dict[str, Any]] = field(default_factory=list)

    # Preview
    preview_available: bool = False
    open_url: Optional[str] = None          # Deep link in source system

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.value,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "title": self.title,
            "summary": self.summary,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "severity": self.severity.value,
            "item_type": self.item_type,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "sla_deadline_at": self.sla_deadline_at.isoformat() if self.sla_deadline_at else None,
            "sla_tier": self.sla_tier,
            "blocking": self.blocking,
            "client_facing": self.client_facing,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "assignee": self.assignee,
            "status": self.status,
            "tags": self.tags,
            "score": round(self.score, 2),
            "score_breakdown": {
                "severity": self.score_breakdown.severity,
                "urgency": self.score_breakdown.urgency,
                "blocking": self.score_breakdown.blocking,
                "freshness": self.score_breakdown.freshness,
                "staleness_penalty": self.score_breakdown.staleness_penalty,
                "source_weight": self.score_breakdown.source_weight,
                "ack_penalty": self.score_breakdown.ack_penalty,
                "total": self.score_breakdown.total,
                "reasons": self.score_breakdown.reasons,
            } if self.score_breakdown else None,
            "ack_state": self.ack_state.value,
            "notification": {
                "severity": self.notification.severity.value,
                "escalation_stage": self.notification.escalation_stage,
                "channels_attempted": self.notification.channels_attempted,
                "acknowledged": self.notification.acknowledged,
                "next_escalation_at": self.notification.next_escalation_at,
                "snoozed_until": self.notification.snoozed_until,
            },
            "promotion_eligible": self.promotion_eligible,
            "recommended_mode": self.recommended_mode,
            "recommended_actions": self.recommended_actions,
        }
