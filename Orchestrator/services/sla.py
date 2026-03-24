"""
SLA & Priority Scoring System

Defines SLA tiers, task type classifications, and a composite priority
scoring function used by the proactive scheduler and ticket managers
to rank work items by urgency.

All times use calendar hours (24/7).
# TODO: Add business-hours support (Mon-Fri 9-5) for SLA window calculations.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# SLA Tiers
# ---------------------------------------------------------------------------

class SLATier(Enum):
    """Service-level agreement tiers assigned to clients or accounts."""
    GOLD = "gold"          # 4h first response, 24h resolution
    SILVER = "silver"      # 8h first response, 48h resolution
    BRONZE = "bronze"      # 24h first response, 72h resolution
    INTERNAL = "internal"  # Best effort, no hard deadlines


SLA_TIER_CONFIG: Dict[SLATier, Dict[str, float]] = {
    SLATier.GOLD:     {"first_response_hours": 4,  "resolution_hours": 24},
    SLATier.SILVER:   {"first_response_hours": 8,  "resolution_hours": 48},
    SLATier.BRONZE:   {"first_response_hours": 24, "resolution_hours": 72},
    SLATier.INTERNAL: {"first_response_hours": 0,  "resolution_hours": 0},
}

# Weight used in the priority score (0-1)
SLA_TIER_WEIGHTS: Dict[SLATier, float] = {
    SLATier.GOLD: 1.0,
    SLATier.SILVER: 0.7,
    SLATier.BRONZE: 0.4,
    SLATier.INTERNAL: 0.1,
}


# ---------------------------------------------------------------------------
# Task Type Classifications
# ---------------------------------------------------------------------------

class TaskType(Enum):
    """Categorisation of a work item by its nature."""
    CRITICAL_BUG = "critical_bug"
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    QUESTION = "question"
    MAINTENANCE = "maintenance"
    INTERNAL = "internal"


@dataclass(frozen=True)
class TaskTypeConfig:
    """Immutable config for a single task type."""
    severity_weight: float   # 0-1, used in priority score
    target_hours: float      # default resolution target in hours


TASK_TYPE_CONFIGS: Dict[TaskType, TaskTypeConfig] = {
    TaskType.CRITICAL_BUG:    TaskTypeConfig(severity_weight=1.0, target_hours=2),
    TaskType.BUG:             TaskTypeConfig(severity_weight=0.7, target_hours=8),
    TaskType.FEATURE_REQUEST: TaskTypeConfig(severity_weight=0.3, target_hours=48),
    TaskType.QUESTION:        TaskTypeConfig(severity_weight=0.4, target_hours=24),
    TaskType.MAINTENANCE:     TaskTypeConfig(severity_weight=0.2, target_hours=72),
    TaskType.INTERNAL:        TaskTypeConfig(severity_weight=0.1, target_hours=0),
}


# ---------------------------------------------------------------------------
# SLA Status
# ---------------------------------------------------------------------------

class SLAStatus(Enum):
    """How close an item is to breaching its SLA window."""
    WITHIN = "within_sla"        # < 75% of window used
    APPROACHING = "approaching"  # 75-90% of window used
    BREACHING = "breaching"      # 90-100% of window used
    BREACHED = "breached"        # > 100% of window used
    NO_SLA = "no_sla"            # Internal / best-effort items


# ---------------------------------------------------------------------------
# Priority Score Result
# ---------------------------------------------------------------------------

@dataclass
class PriorityScore:
    """Result of the composite priority calculation."""
    score: float                       # 0-100, higher = more urgent
    sla_status: SLAStatus
    sla_deadline: Optional[datetime]   # None for NO_SLA items
    time_remaining: Optional[timedelta]
    components: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _effective_resolution_hours(tier: SLATier, task_type: TaskType) -> float:
    """Return the tighter of the SLA tier window and the task-type target.

    For INTERNAL tier or INTERNAL task type (target_hours == 0), returns 0
    to signal best-effort / no hard deadline.
    """
    tier_hours = SLA_TIER_CONFIG[tier]["resolution_hours"]
    task_hours = TASK_TYPE_CONFIGS[task_type].target_hours

    # Best-effort when either side has no deadline
    if tier_hours == 0 or task_hours == 0:
        return 0.0

    return min(tier_hours, task_hours)


def get_sla_deadline(
    tier: SLATier,
    task_type: TaskType,
    created_at: datetime,
) -> Optional[datetime]:
    """Calculate when the SLA breaches based on tier and task type.

    Returns ``None`` for best-effort items that have no hard deadline.
    """
    hours = _effective_resolution_hours(tier, task_type)
    if hours == 0:
        return None
    return created_at + timedelta(hours=hours)


def get_sla_status(
    tier: SLATier,
    task_type: TaskType,
    created_at: datetime,
    now: Optional[datetime] = None,
) -> SLAStatus:
    """Get current SLA status for an item."""
    deadline = get_sla_deadline(tier, task_type, created_at)
    if deadline is None:
        return SLAStatus.NO_SLA

    now = now or datetime.now(timezone.utc)
    total_window = (deadline - created_at).total_seconds()
    elapsed = (now - created_at).total_seconds()

    if total_window <= 0:
        return SLAStatus.BREACHED

    ratio = elapsed / total_window

    if ratio > 1.0:
        return SLAStatus.BREACHED
    if ratio >= 0.9:
        return SLAStatus.BREACHING
    if ratio >= 0.75:
        return SLAStatus.APPROACHING
    return SLAStatus.WITHIN


# ---------------------------------------------------------------------------
# Priority Scoring
# ---------------------------------------------------------------------------

# Staleness normalisation window (days)
_STALENESS_WINDOW_DAYS = 14


def calculate_priority_score(
    sla_tier: SLATier,
    task_type: TaskType,
    created_at: datetime,
    first_responded_at: Optional[datetime] = None,
    due_date: Optional[datetime] = None,
) -> PriorityScore:
    """Compute a composite priority score for a work item.

    The score ranges from 0 to 100 (higher = more urgent) and is built
    from four weighted components:

    - **SLA deadline proximity (40%)** — exponential urgency curve as
      the deadline approaches; breached items receive the maximum.
    - **Client tier weight (25%)** — GOLD > SILVER > BRONZE > INTERNAL.
    - **Task type severity (20%)** — driven by ``severity_weight``.
    - **Age / staleness (15%)** — older items score higher, normalised
      against a 14-day window.

    Parameters
    ----------
    sla_tier:
        The client's SLA tier.
    task_type:
        The classified task type.
    created_at:
        When the item was created (tz-aware recommended).
    first_responded_at:
        When the first response was sent (used for future first-response
        SLA tracking — currently informational only).
    due_date:
        Optional explicit due date that overrides the calculated SLA
        deadline when it is *earlier* than the tier/type window.

    Returns
    -------
    PriorityScore
        Dataclass with the overall ``score``, ``sla_status``, deadline
        info, and a ``components`` breakdown.
    """
    now = datetime.now(timezone.utc)

    # --- Resolve effective deadline ---
    sla_deadline = get_sla_deadline(sla_tier, task_type, created_at)

    # An explicit due_date wins if it's earlier
    if due_date is not None:
        if sla_deadline is None or due_date < sla_deadline:
            sla_deadline = due_date

    # --- SLA status ---
    if sla_deadline is None:
        sla_status = SLAStatus.NO_SLA
    else:
        sla_status = get_sla_status(sla_tier, task_type, created_at, now)
        # Re-derive if due_date shifted the effective deadline
        if due_date is not None and sla_deadline == due_date:
            total = (sla_deadline - created_at).total_seconds()
            elapsed = (now - created_at).total_seconds()
            if total <= 0:
                sla_status = SLAStatus.BREACHED
            else:
                ratio = elapsed / total
                if ratio > 1.0:
                    sla_status = SLAStatus.BREACHED
                elif ratio >= 0.9:
                    sla_status = SLAStatus.BREACHING
                elif ratio >= 0.75:
                    sla_status = SLAStatus.APPROACHING
                else:
                    sla_status = SLAStatus.WITHIN

    # --- Time remaining ---
    time_remaining: Optional[timedelta] = None
    if sla_deadline is not None:
        time_remaining = sla_deadline - now

    # ---------------------------------------------------------------
    # Component 1: SLA deadline proximity (40%)
    # ---------------------------------------------------------------
    if sla_deadline is None:
        # No SLA — low baseline urgency
        sla_proximity_score = 0.1
    else:
        total_window = (sla_deadline - created_at).total_seconds()
        elapsed = (now - created_at).total_seconds()

        if total_window <= 0 or elapsed >= total_window:
            # Already breached
            sla_proximity_score = 1.0
        else:
            ratio = elapsed / total_window
            # Exponential urgency: stays low early, ramps sharply near end
            # e^(3*ratio) normalised to [0, 1] over ratio in [0, 1]
            sla_proximity_score = (math.exp(3.0 * ratio) - 1.0) / (math.exp(3.0) - 1.0)

    # ---------------------------------------------------------------
    # Component 2: Client tier weight (25%)
    # ---------------------------------------------------------------
    tier_weight_score = SLA_TIER_WEIGHTS[sla_tier]

    # ---------------------------------------------------------------
    # Component 3: Task type severity (20%)
    # ---------------------------------------------------------------
    severity_score = TASK_TYPE_CONFIGS[task_type].severity_weight

    # ---------------------------------------------------------------
    # Component 4: Age / staleness (15%)
    # ---------------------------------------------------------------
    age_seconds = (now - created_at).total_seconds()
    staleness_window = _STALENESS_WINDOW_DAYS * 24 * 3600
    staleness_score = min(age_seconds / staleness_window, 1.0)

    # ---------------------------------------------------------------
    # Composite score
    # ---------------------------------------------------------------
    raw_score = (
        0.40 * sla_proximity_score
        + 0.25 * tier_weight_score
        + 0.20 * severity_score
        + 0.15 * staleness_score
    )

    # Scale to 0-100
    final_score = round(raw_score * 100, 2)

    components = {
        "sla_proximity": round(sla_proximity_score * 100, 2),
        "tier_weight": round(tier_weight_score * 100, 2),
        "severity": round(severity_score * 100, 2),
        "staleness": round(staleness_score * 100, 2),
    }

    return PriorityScore(
        score=final_score,
        sla_status=sla_status,
        sla_deadline=sla_deadline,
        time_remaining=time_remaining,
        components=components,
    )


# ---------------------------------------------------------------------------
# Task Type Classifier
# ---------------------------------------------------------------------------

# Ordered from most specific → least specific so the first match wins.
_CLASSIFICATION_KEYWORDS: List[tuple] = [
    (TaskType.CRITICAL_BUG, [
        "critical", "urgent", "down", "broken", "outage", "p0", "emergency",
    ]),
    (TaskType.BUG, [
        "bug", "error", "fix", "issue", "broken", "not working", "defect",
    ]),
    (TaskType.FEATURE_REQUEST, [
        "feature", "add", "new", "enhancement", "request", "implement",
    ]),
    (TaskType.QUESTION, [
        "question", "how", "help", "clarify", "explain", "what is",
    ]),
    (TaskType.MAINTENANCE, [
        "maintenance", "update", "upgrade", "migration", "refactor", "cleanup",
    ]),
]


def classify_task_type(
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
) -> TaskType:
    """Infer a ``TaskType`` from ticket/task text using keyword matching.

    The classifier checks title, description, and tags against keyword
    lists ordered from highest to lowest severity.  The first matching
    category wins.  If nothing matches the item is classified as
    ``TaskType.INTERNAL``.

    Parameters
    ----------
    title:
        The ticket or task title / subject line.
    description:
        Optional longer description or body text.
    tags:
        Optional list of tags / labels attached to the item.

    Returns
    -------
    TaskType
        The inferred task type.
    """
    # Build a single searchable blob, lowercased
    parts = [title.lower(), description.lower()]
    if tags:
        parts.extend(t.lower() for t in tags)
    blob = " ".join(parts)

    for task_type, keywords in _CLASSIFICATION_KEYWORDS:
        for kw in keywords:
            # Use word-boundary-aware search for single words; plain
            # substring match for multi-word phrases like "not working".
            if " " in kw:
                if kw in blob:
                    return task_type
            else:
                if re.search(rf"\b{re.escape(kw)}\b", blob):
                    return task_type

    return TaskType.INTERNAL
