"""
Queue Manager — Scoring Engine

Deterministic priority scoring. No LLM, no agents.
Score = severity + urgency + blocking + freshness + staleness + source_weight + ack_penalty

All components are 0-based with defined max weights.
Total score range: 0-100.

Score is EXPLAINABLE — every component is tracked with reasons.
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from queue.models import QueueItem, Severity, AckState, ScoreBreakdown


# ── Weight Constants ──────────────────────────────────────────

SEVERITY_WEIGHT = 30        # Max points from severity
URGENCY_WEIGHT = 25         # Max points from deadline proximity
BLOCKING_WEIGHT = 15        # Max points from blocking impact
FRESHNESS_WEIGHT = 10       # Max points from recent activity
STALENESS_WEIGHT = 10       # Max points from inactivity penalty
SOURCE_WEIGHT = 5           # Max points from source type
ACK_WEIGHT = 5              # Max points from unacknowledged state

# Total max: 100


# ── Severity Scores ───────────────────────────────────────────

SEVERITY_SCORES = {
    Severity.INFO: 5,
    Severity.ATTENTION: 15,
    Severity.HIGH: 25,
    Severity.CRITICAL: 30,
}


# ── SLA Tier Multipliers ─────────────────────────────────────

SLA_TIER_MULTIPLIER = {
    "gold": 1.0,
    "silver": 0.7,
    "bronze": 0.4,
    "internal": 0.1,
}


# ── Source Type Weights ───────────────────────────────────────
# Client-facing sources score higher than internal.

SOURCE_TYPE_SCORES = {
    "zendesk": 5,       # Client support ticket
    "gmail": 4,         # Client email
    "clickup": 3,       # Task (may or may not be client-facing)
    "github": 2,        # Code (usually internal)
    "slack": 2,         # Message
    "harvest": 1,       # Time tracking
    "proactive": 3,     # Agent finding
}


def compute_score(item: QueueItem) -> ScoreBreakdown:
    """
    Compute the priority score for a queue item.
    Returns a ScoreBreakdown with all components and reasons.
    """
    now = datetime.now(timezone.utc)
    reasons = []

    # ── 1. Severity (0-30) ────────────────────────────────
    severity_score = SEVERITY_SCORES.get(item.severity, 5)
    reasons.append(f"severity={item.severity.value} → {severity_score}pts")

    # ── 2. Urgency / Deadline proximity (0-25) ────────────
    urgency_score = 0.0
    deadline = item.sla_deadline_at or item.deadline_at

    if deadline:
        time_remaining = (deadline - now).total_seconds()
        total_window = 24 * 3600  # Normalize against 24h window

        if time_remaining <= 0:
            # Past deadline — max urgency
            urgency_score = URGENCY_WEIGHT
            reasons.append(f"deadline PASSED → {urgency_score}pts")
        else:
            # Exponential curve: urgency increases sharply near deadline
            ratio = max(0, 1 - (time_remaining / total_window))
            urgency_score = round((math.exp(3.0 * ratio) - 1.0) / (math.exp(3.0) - 1.0) * URGENCY_WEIGHT, 2)
            hours_left = time_remaining / 3600
            reasons.append(f"deadline in {hours_left:.1f}h → {urgency_score}pts")

    # Apply SLA tier multiplier
    tier_mult = SLA_TIER_MULTIPLIER.get(item.sla_tier or "internal", 0.1)
    urgency_score = round(urgency_score * tier_mult, 2)
    if tier_mult != 1.0:
        reasons.append(f"SLA tier {item.sla_tier} multiplier={tier_mult}")

    # ── 3. Blocking impact (0-15) ─────────────────────────
    blocking_score = 0.0
    if item.blocking:
        blocking_score = BLOCKING_WEIGHT
        reasons.append(f"blocking=true → {blocking_score}pts")
    if item.client_facing:
        blocking_score = max(blocking_score, BLOCKING_WEIGHT * 0.6)
        reasons.append(f"client_facing=true → min {BLOCKING_WEIGHT * 0.6}pts")

    # ── 4. Freshness (0-10) ───────────────────────────────
    # Recent activity bumps priority (someone is engaged)
    freshness_score = 0.0
    if item.last_activity_at:
        age_hours = (now - item.last_activity_at).total_seconds() / 3600
        if age_hours < 1:
            freshness_score = FRESHNESS_WEIGHT
            reasons.append(f"activity <1h ago → {freshness_score}pts")
        elif age_hours < 4:
            freshness_score = FRESHNESS_WEIGHT * 0.7
            reasons.append(f"activity {age_hours:.0f}h ago → {freshness_score}pts")
        elif age_hours < 24:
            freshness_score = FRESHNESS_WEIGHT * 0.3

    # ── 5. Staleness penalty (0-10) ───────────────────────
    # Items with no activity for a long time get bumped (attention needed)
    staleness_score = 0.0
    if item.updated_at:
        stale_days = (now - item.updated_at).total_seconds() / 86400
        if stale_days > 14:
            staleness_score = STALENESS_WEIGHT
            reasons.append(f"stale {stale_days:.0f}d → {staleness_score}pts")
        elif stale_days > 7:
            staleness_score = STALENESS_WEIGHT * 0.6
            reasons.append(f"stale {stale_days:.0f}d → {staleness_score}pts")
        elif stale_days > 3:
            staleness_score = STALENESS_WEIGHT * 0.3

    # ── 6. Source weight (0-5) ────────────────────────────
    source_score = SOURCE_TYPE_SCORES.get(item.source.value, 2)
    source_score = min(source_score, SOURCE_WEIGHT)

    # ── 7. Ack penalty (0-5) ─────────────────────────────
    ack_score = 0.0
    if item.ack_state == AckState.UNACKED:
        ack_score = ACK_WEIGHT
        reasons.append(f"unacknowledged → +{ack_score}pts")
    elif item.ack_state == AckState.SNOOZED:
        # Check if snooze has expired
        if item.notification.snoozed_until:
            try:
                snooze_end = datetime.fromisoformat(item.notification.snoozed_until)
                if now > snooze_end:
                    ack_score = ACK_WEIGHT  # Snooze expired, bump it back
                    reasons.append(f"snooze expired → +{ack_score}pts")
            except (ValueError, TypeError):
                pass

    # ── Total ─────────────────────────────────────────────
    total = round(
        severity_score + urgency_score + blocking_score +
        freshness_score + staleness_score + source_score + ack_score,
        2
    )

    return ScoreBreakdown(
        severity=round(severity_score, 2),
        urgency=round(urgency_score, 2),
        blocking=round(blocking_score, 2),
        freshness=round(freshness_score, 2),
        staleness_penalty=round(staleness_score, 2),
        source_weight=round(source_score, 2),
        ack_penalty=round(ack_score, 2),
        total=min(total, 100),  # Cap at 100
        reasons=reasons,
    )


def compute_severity(item: QueueItem) -> Severity:
    """
    Compute severity from item properties.
    Deterministic — no LLM.
    """
    # SLA breached → critical
    if item.sla_deadline_at:
        now = datetime.now(timezone.utc)
        remaining = (item.sla_deadline_at - now).total_seconds()
        if remaining <= 0:
            return Severity.CRITICAL
        # Less than 2 hours → high
        if remaining < 7200:
            return Severity.HIGH
        # Less than 25% of SLA window remaining → attention
        if item.created_at:
            total_window = (item.sla_deadline_at - item.created_at).total_seconds()
            if total_window > 0 and remaining / total_window < 0.25:
                return Severity.ATTENTION

    # Blocking + client-facing → high
    if item.blocking and item.client_facing:
        return Severity.HIGH

    # Client-facing with deadline today → high
    if item.client_facing and item.deadline_at:
        hours_left = (item.deadline_at - datetime.now(timezone.utc)).total_seconds() / 3600
        if hours_left < 8:
            return Severity.HIGH

    # Blocking anything → attention
    if item.blocking:
        return Severity.ATTENTION

    # Client-facing → attention
    if item.client_facing:
        return Severity.ATTENTION

    # Default
    return Severity.INFO
