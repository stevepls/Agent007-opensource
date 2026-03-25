"""
Customer Experience (CX) Agent — Proactive Client Communication

A stateful proactive agent that runs every 2 hours.  It scores client health,
detects communication triggers, and queues draft messages for Steve's review
via the message queue (requires_approval=True — nothing ever sends without
human sign-off).

State is persisted to Orchestrator/data/cx_agent/state.json.

Usage:
    from agents.cx_agent.agent import run_cx_agent
    result = run_cx_agent()
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("cx_agent")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_AGENT_DIR = Path(__file__).parent
_ORCHESTRATOR_ROOT = _AGENT_DIR.parent.parent
_STATE_DIR = _ORCHESTRATOR_ROOT / "data" / "cx_agent"
_STATE_FILE = _STATE_DIR / "state.json"

# ---------------------------------------------------------------------------
# Rate-limit / policy constants
# ---------------------------------------------------------------------------

MAX_OUTREACH_PER_CLIENT_HOURS = 48     # Min hours between outreach to same client
MAX_OUTREACH_PER_RUN = 5               # Total messages queued in a single run
SENT_LOG_RETAIN_DAYS = 30              # How long to keep entries in sent_log

# Communication freshness thresholds (days) by SLA tier
COMMS_THRESHOLDS: Dict[str, int] = {
    "gold": 3,
    "silver": 5,
    "bronze": 10,
    "internal": 999,
}

# ---------------------------------------------------------------------------
# Health-score weights
# ---------------------------------------------------------------------------

HEALTH_WEIGHTS = {
    "task_completion_rate": 0.25,
    "overdue_ratio": 0.20,
    "comms_freshness": 0.20,
    "sla_compliance": 0.20,
    "open_ticket_age": 0.15,
}


# ============================================================================
# State helpers
# ============================================================================

def _load_state() -> Dict[str, Any]:
    """Load persisted agent state from disk, returning a blank state on error."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE) as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load CX agent state, starting fresh: %s", exc)
    return {"clients": {}, "sent_log": []}


def _save_state(state: Dict[str, Any]) -> None:
    """Atomically persist agent state to disk."""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=_STATE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2, default=str)
        os.replace(tmp_path, _STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        # Fallback: direct write
        with open(_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)


def _prune_sent_log(state: Dict[str, Any]) -> None:
    """Remove sent_log entries older than SENT_LOG_RETAIN_DAYS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=SENT_LOG_RETAIN_DAYS)).isoformat()
    state["sent_log"] = [
        entry for entry in state.get("sent_log", [])
        if entry.get("timestamp", "") >= cutoff
    ]


# ============================================================================
# Health scoring
# ============================================================================

def _score_band(value: float, healthy_thresh: float, warning_thresh: float, *, invert: bool = False) -> float:
    """Return 0-100 sub-score given a value and threshold boundaries.

    When *invert* is False the scale is: value >= healthy → 100,
    value <= warning → 0, linear in between.

    When *invert* is True the polarity is reversed (lower is better).
    """
    if invert:
        if value <= healthy_thresh:
            return 100.0
        if value >= warning_thresh:
            return 0.0
        span = warning_thresh - healthy_thresh
        if span == 0:
            return 50.0
        return max(0.0, min(100.0, 100.0 * (1 - (value - healthy_thresh) / span)))
    else:
        if value >= healthy_thresh:
            return 100.0
        if value <= warning_thresh:
            return 0.0
        span = healthy_thresh - warning_thresh
        if span == 0:
            return 50.0
        return max(0.0, min(100.0, 100.0 * (value - warning_thresh) / span))


def _compute_health(
    items: list,
    last_comms_days: Optional[float],
    sla_tier: str,
) -> Tuple[float, Dict[str, Any]]:
    """Compute a 0-100 health score for a single client project.

    Returns (score, breakdown_dict).
    """
    breakdown: Dict[str, Any] = {}
    now = datetime.now(timezone.utc)

    # --- Task completion rate (30d) ----------------------------------------
    total_tasks = len(items)
    if total_tasks > 0:
        moving = sum(1 for i in items if i.status in ("in_progress", "review", "done"))
        rate = moving / total_tasks
    else:
        rate = 1.0  # No tasks = healthy (nothing to worry about)
    sub = _score_band(rate, healthy_thresh=0.70, warning_thresh=0.40)
    breakdown["task_completion_rate"] = {"value": round(rate, 2), "score": round(sub, 1)}

    # --- Overdue ratio -----------------------------------------------------
    overdue = 0
    for item in items:
        if item.status == "done":
            continue
        if item.due_date and item.due_date < now:
            overdue += 1
    active = sum(1 for i in items if i.status != "done") or 1
    overdue_ratio = overdue / active
    sub = _score_band(overdue_ratio, healthy_thresh=0.10, warning_thresh=0.30, invert=True)
    breakdown["overdue_ratio"] = {"value": round(overdue_ratio, 2), "overdue": overdue, "score": round(sub, 1)}

    # --- Communication freshness -------------------------------------------
    if last_comms_days is not None:
        sub = _score_band(last_comms_days, healthy_thresh=3, warning_thresh=7, invert=True)
    else:
        sub = 50.0  # Unknown → neutral
    breakdown["comms_freshness"] = {"days": last_comms_days, "score": round(sub, 1)}

    # --- SLA compliance ----------------------------------------------------
    breaching = sum(
        1 for i in items
        if hasattr(i, "priority_score")
        and i.priority_score.sla_status.value in ("breaching", "breached")
    )
    approaching = sum(
        1 for i in items
        if hasattr(i, "priority_score")
        and i.priority_score.sla_status.value == "approaching"
    )
    if total_tasks > 0:
        compliance = 1.0 - (breaching + 0.5 * approaching) / total_tasks
    else:
        compliance = 1.0
    sub = _score_band(compliance, healthy_thresh=0.90, warning_thresh=0.60)
    breakdown["sla_compliance"] = {
        "compliance": round(compliance, 2),
        "breaching": breaching,
        "approaching": approaching,
        "score": round(sub, 1),
    }

    # --- Open ticket age ---------------------------------------------------
    open_items = [i for i in items if i.status not in ("done",)]
    if open_items:
        avg_age_days = sum((now - i.created_at).total_seconds() for i in open_items) / len(open_items) / 86400
    else:
        avg_age_days = 0
    sub = _score_band(avg_age_days, healthy_thresh=5, warning_thresh=14, invert=True)
    breakdown["open_ticket_age"] = {"avg_days": round(avg_age_days, 1), "score": round(sub, 1)}

    # --- Weighted total ----------------------------------------------------
    total = sum(
        HEALTH_WEIGHTS[k] * breakdown[k]["score"]
        for k in HEALTH_WEIGHTS
    )
    return round(total, 1), breakdown


# ============================================================================
# Communication helpers
# ============================================================================

def _last_comms_days_for_project(project) -> Optional[float]:
    """Check Gmail + Slack for the most recent communication with a client project.

    Returns days since last communication, or None if unknown.
    """
    try:
        from services.tool_registry import get_registry
        registry = get_registry()
    except Exception:
        return None

    now = datetime.now(timezone.utc)
    last_email_days: Optional[float] = None
    last_slack_days: Optional[float] = None

    # --- Gmail -------------------------------------------------------------
    try:
        search_terms = [project.name] + project.aliases[:2]
        query = " OR ".join(f'"{t}"' for t in search_terms[:3])
        result = registry.execute("gmail_search", {
            "query": f"({query}) newer_than:30d",
            "max_results": 1,
        }, skip_confirmation=True)

        emails: list = []
        if isinstance(result, dict):
            emails = result.get("emails", result.get("messages", []))
        elif isinstance(result, list):
            emails = result

        if emails:
            latest = emails[0]
            date_str = latest.get("date", latest.get("internalDate", ""))
            if date_str:
                try:
                    from email.utils import parsedate_to_datetime
                    email_date = parsedate_to_datetime(date_str)
                    last_email_days = (now - email_date.astimezone(timezone.utc)).total_seconds() / 86400
                except Exception:
                    pass
    except Exception as exc:
        logger.debug("Gmail check failed for %s: %s", project.name, exc)

    # --- Slack -------------------------------------------------------------
    if project.slack_channel_id:
        try:
            result = registry.execute("slack_get_recent_messages", {
                "channel": project.slack_channel_id,
                "limit": 1,
            }, skip_confirmation=True)

            messages: list = []
            if isinstance(result, dict):
                messages = result.get("messages", [])

            if messages:
                ts = messages[0].get("ts", "")
                if ts:
                    msg_date = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    last_slack_days = (now - msg_date).total_seconds() / 86400
        except Exception as exc:
            logger.debug("Slack check failed for %s: %s", project.name, exc)

    # --- Pick most recent --------------------------------------------------
    candidates = [d for d in (last_email_days, last_slack_days) if d is not None]
    return min(candidates) if candidates else None


def _render_cx_template(template_id: str, variables: Dict[str, str]) -> Tuple[str, str]:
    """Render a CX-specific template from templates.py.

    Returns (subject, body).
    """
    from agents.cx_agent.templates import CX_TEMPLATES

    tmpl = CX_TEMPLATES.get(template_id)
    if tmpl is None:
        raise ValueError(f"CX template '{template_id}' not found")

    subject = tmpl["subject"]
    body = tmpl["body"]

    for key, value in variables.items():
        subject = subject.replace(f"{{{key}}}", str(value))
        body = body.replace(f"{{{key}}}", str(value))

    return subject, body


def _try_canned_response(response_id: str, variables: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """Try to render from the global canned-response registry.

    Returns (subject, body) or None on any failure.
    """
    try:
        from services.canned_responses import get_response_registry
        registry = get_response_registry()
        return registry.use(response_id, variables)
    except Exception as exc:
        logger.debug("Canned response '%s' unavailable: %s", response_id, exc)
        return None


# ============================================================================
# Rate-limit helpers
# ============================================================================

def _can_outreach(client_name: str, state: Dict[str, Any]) -> bool:
    """Return True if outreach to *client_name* is allowed by rate limits."""
    client_state = state.get("clients", {}).get(client_name, {})

    # Check suppress_until
    suppress = client_state.get("suppress_until")
    if suppress:
        try:
            if datetime.fromisoformat(suppress) > datetime.now(timezone.utc):
                logger.info("Skipping %s — suppressed until %s", client_name, suppress)
                return False
        except (ValueError, TypeError):
            pass

    # Check last outreach time
    last_outreach = client_state.get("last_outreach")
    if last_outreach:
        try:
            last_dt = datetime.fromisoformat(last_outreach)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            if hours_since < MAX_OUTREACH_PER_CLIENT_HOURS:
                logger.info(
                    "Skipping %s — last outreach %.1fh ago (limit %dh)",
                    client_name, hours_since, MAX_OUTREACH_PER_CLIENT_HOURS,
                )
                return False
        except (ValueError, TypeError):
            pass

    return True


def _record_outreach(
    client_name: str,
    outreach_type: str,
    channel: str,
    message_id: str,
    state: Dict[str, Any],
) -> None:
    """Update state after queuing an outreach."""
    now_iso = datetime.now(timezone.utc).isoformat()

    # Per-client state
    clients = state.setdefault("clients", {})
    cs = clients.setdefault(client_name, {})
    cs["last_outreach"] = now_iso
    cs["last_outreach_type"] = outreach_type

    # Rolling 7-day counter
    count_7d = cs.get("outreach_count_7d", 0)
    cs["outreach_count_7d"] = count_7d + 1

    # Sent log
    state.setdefault("sent_log", []).append({
        "client": client_name,
        "type": outreach_type,
        "channel": channel,
        "timestamp": now_iso,
        "message_id": message_id,
    })


# ============================================================================
# Trigger detection
# ============================================================================

def _detect_triggers(
    project,
    items: list,
    last_comms_days: Optional[float],
    health_score: float,
    health_breakdown: Dict[str, Any],
    state: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Evaluate all communication triggers for a single project.

    Returns a list of trigger dicts, each with keys: trigger, action, channel,
    template, variables.
    """
    triggers: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    # --- Task completed (recently closed items) ----------------------------
    for item in items:
        if item.status != "done":
            continue
        # Consider "recently completed" = updated in last 4 hours
        age_hours = (now - item.updated_at).total_seconds() / 3600
        if age_hours <= 4:
            triggers.append({
                "trigger": "task_completed",
                "description": f"Task '{item.title}' completed",
                "action": "Send completion notice",
                "channel": "email",
                "template": "status-completed",
                "template_type": "canned",
                "variables": {
                    "recipient_name": project.name.split("/")[0].strip(),
                    "sender_name": "Steve",
                    "task_name": item.title,
                    "project_name": project.name,
                    "details": "Please review and let me know if any changes are needed.",
                },
            })
            break  # One completion notice per run per project

    # --- Task status changed to "in review" --------------------------------
    review_items = [i for i in items if i.status == "review"]
    for item in review_items:
        age_hours = (now - item.updated_at).total_seconds() / 3600
        if age_hours <= 4:
            triggers.append({
                "trigger": "task_in_review",
                "description": f"Task '{item.title}' is ready for review",
                "action": "Notify client work is ready for review",
                "channel": "email",
                "template": "status-working",
                "template_type": "canned",
                "variables": {
                    "recipient_name": project.name.split("/")[0].strip(),
                    "sender_name": "Steve",
                    "project_name": project.name,
                    "task_description": item.title,
                    "eta": "ready for your review now",
                },
            })
            break

    # --- SLA approaching for client ticket ---------------------------------
    for item in items:
        if item.status == "done":
            continue
        if not hasattr(item, "priority_score"):
            continue
        sla_status = item.priority_score.sla_status.value
        if sla_status in ("approaching", "breaching"):
            triggers.append({
                "trigger": "sla_approaching",
                "description": f"SLA {sla_status} for '{item.title}'",
                "action": "Proactive SLA update",
                "channel": "email",
                "template": "cx-sla-proactive",
                "template_type": "cx",
                "variables": {
                    "client_name": project.name.split("/")[0].strip(),
                    "ticket_subject": item.title,
                    "status": "In progress — being actively worked on",
                    "update_detail": f"This item has SLA status: {sla_status}.",
                    "eta": "within the next business day",
                },
            })
            break  # One SLA notice per project per run

    # --- No communication in >N days (by SLA tier) -------------------------
    threshold = COMMS_THRESHOLDS.get(project.sla_tier, 7)
    if threshold < 999 and last_comms_days is not None and last_comms_days > threshold:
        # Gather quick stats for the check-in template
        active_count = sum(1 for i in items if i.status not in ("done",))
        completed_count = sum(1 for i in items if i.status == "done")
        review_count = sum(1 for i in items if i.status == "review")
        triggers.append({
            "trigger": "comms_gap",
            "description": f"No communication in {last_comms_days:.0f} days (threshold {threshold}d)",
            "action": "Draft check-in",
            "channel": "email",
            "template": "cx-check-in",
            "template_type": "cx",
            "variables": {
                "client_name": project.name.split("/")[0].strip(),
                "project_name": project.name,
                "active_count": str(active_count),
                "completed_count": str(completed_count),
                "review_count": str(review_count),
                "custom_note": "",
            },
        })

    # --- Overdue tasks >3 --------------------------------------------------
    overdue_count = health_breakdown.get("overdue_ratio", {}).get("overdue", 0)
    if overdue_count > 3:
        overdue_items = [
            i for i in items
            if i.status != "done" and i.due_date and i.due_date < now
        ]
        plan_lines = []
        for oi in overdue_items[:5]:
            plan_lines.append(f"- {oi.title}: targeting completion this week")
        next_update = (now + timedelta(days=3)).strftime("%A, %B %d")
        triggers.append({
            "trigger": "overdue_tasks",
            "description": f"{overdue_count} overdue tasks",
            "action": "Send status update with plan",
            "channel": "email",
            "template": "cx-overdue-plan",
            "template_type": "cx",
            "variables": {
                "client_name": project.name.split("/")[0].strip(),
                "project_name": project.name,
                "overdue_count": str(overdue_count),
                "plan_detail": "\n".join(plan_lines) if plan_lines else "Reprioritizing to address overdue items.",
                "next_update_date": next_update,
            },
        })

    # --- Invoice reminder (from Harvest via business advisor) ---------------
    try:
        from services.business_advisor import get_advisor, Category
        advisor = get_advisor()
        advisories = advisor.get_advisories(refresh=False)
        for adv in advisories:
            if adv.category == Category.REVENUE and "invoice" in adv.title.lower():
                # Check if this advisory relates to our project
                adv_data = adv.data or {}
                if project.name.lower() in adv.detail.lower() or project.name.lower() in str(adv_data).lower():
                    triggers.append({
                        "trigger": "invoice_reminder",
                        "description": adv.title,
                        "action": "Send payment reminder",
                        "channel": "email",
                        "template": "invoice-reminder",
                        "template_type": "canned",
                        "variables": {
                            "recipient_name": project.name.split("/")[0].strip(),
                            "sender_name": "Steve",
                            "invoice_number": adv_data.get("invoice_number", "N/A"),
                            "amount": adv_data.get("amount", "N/A"),
                            "due_date": adv_data.get("due_date", "N/A"),
                        },
                    })
                    break
    except Exception as exc:
        logger.debug("Invoice trigger check failed: %s", exc)

    # --- Ticket resolved (Zendesk items recently moved to done) ------------
    for item in items:
        if item.source != "zendesk":
            continue
        if item.status != "done":
            continue
        age_hours = (now - item.updated_at).total_seconds() / 3600
        if age_hours <= 4:
            triggers.append({
                "trigger": "ticket_resolved",
                "description": f"Zendesk ticket '{item.title}' resolved",
                "action": "Send resolution summary",
                "channel": "email",
                "template": "cx-resolution-summary",
                "template_type": "cx",
                "variables": {
                    "client_name": project.name.split("/")[0].strip(),
                    "ticket_subject": item.title,
                    "resolution_summary": "The issue has been investigated and resolved.",
                },
            })
            break

    return triggers


# ============================================================================
# Message queueing
# ============================================================================

def _queue_communication(
    trigger: Dict[str, Any],
    project,
    state: Dict[str, Any],
) -> Optional[str]:
    """Render and queue a single communication.  Returns the message ID or None."""
    from services.message_queue import get_message_queue, MessageType

    template_id = trigger["template"]
    template_type = trigger.get("template_type", "cx")
    variables = trigger["variables"]
    channel = trigger.get("channel", "email")

    # --- Render the message ------------------------------------------------
    subject: Optional[str] = None
    body: str = ""

    if template_type == "canned":
        result = _try_canned_response(template_id, variables)
        if result:
            subject, body = result
        else:
            # Fall back to CX templates if canned response unavailable
            try:
                subject, body = _render_cx_template(template_id, variables)
            except ValueError:
                logger.warning(
                    "No template found for '%s', skipping trigger '%s'",
                    template_id, trigger["trigger"],
                )
                return None
    else:
        try:
            subject, body = _render_cx_template(template_id, variables)
        except ValueError as exc:
            logger.warning("CX template render failed: %s", exc)
            return None

    if not body:
        logger.warning("Empty body for trigger '%s', skipping", trigger["trigger"])
        return None

    # --- Determine message type and channel address ------------------------
    msg_type = MessageType.EMAIL_SEND
    channel_addr = "client"  # Placeholder — Steve will fill in during approval

    if channel == "slack" and project.slack_channel_id:
        msg_type = MessageType.SLACK_MESSAGE
        channel_addr = project.slack_channel_id

    # --- Queue it ----------------------------------------------------------
    mq = get_message_queue()
    msg = mq.queue(
        msg_type=msg_type,
        channel=channel_addr,
        content=body,
        subject=subject,
        metadata={
            "cx_trigger": trigger["trigger"],
            "project": project.name,
            "sla_tier": project.sla_tier,
            "description": trigger.get("description", ""),
        },
        created_by="cx_agent",
        requires_approval=True,
    )

    logger.info(
        "Queued %s for %s (trigger=%s, msg_id=%s)",
        trigger["trigger"], project.name, trigger["trigger"], msg.id,
    )
    return msg.id


# ============================================================================
# Main entry point
# ============================================================================

def run_cx_agent() -> dict:
    """Customer Experience agent — proactive client communication.

    1. Load state from disk
    2. For each client project: score health, detect triggers, queue comms
    3. Save state
    4. Return AgentResult dict
    """
    now = datetime.now(timezone.utc)
    decisions: List[str] = []
    queued_messages: List[Dict[str, Any]] = []
    client_health: Dict[str, Any] = {}
    total_outreach_this_run = 0

    try:
        from services.project_context.project_registry import get_project_registry
        from services.queue_aggregator import get_queue_aggregator

        state = _load_state()
        _prune_sent_log(state)

        project_reg = get_project_registry()
        client_projects = project_reg.get_client_projects()

        qa = get_queue_aggregator()
        # Use cache if fresh enough; avoid hammering APIs on every run
        try:
            qa.force_refresh()
        except Exception as exc:
            logger.warning("Queue refresh failed, using stale cache: %s", exc)

        for project in client_projects:
            pname = project.name

            # Skip internal projects (belt-and-suspenders — get_client_projects
            # already filters, but be explicit)
            if project.sla_tier == "internal":
                decisions.append(f"{pname}: skipped (internal)")
                continue

            # ------------------------------------------------------------------
            # 1. Gather data
            # ------------------------------------------------------------------
            items = qa.get_by_project(pname)
            last_comms_days = _last_comms_days_for_project(project)

            # ------------------------------------------------------------------
            # 2. Compute health score
            # ------------------------------------------------------------------
            health_score, health_breakdown = _compute_health(items, last_comms_days, project.sla_tier)
            client_health[pname] = {
                "health_score": health_score,
                "breakdown": health_breakdown,
                "item_count": len(items),
                "last_comms_days": round(last_comms_days, 1) if last_comms_days is not None else None,
            }

            # Persist health score in state
            cs = state.setdefault("clients", {}).setdefault(pname, {})
            cs["health_score"] = health_score
            cs["last_health_check"] = now.isoformat()

            # ------------------------------------------------------------------
            # 3. Check triggers
            # ------------------------------------------------------------------
            if total_outreach_this_run >= MAX_OUTREACH_PER_RUN:
                decisions.append(
                    f"{pname}: health={health_score}, triggers skipped (run limit {MAX_OUTREACH_PER_RUN} reached)"
                )
                continue

            if not _can_outreach(pname, state):
                decisions.append(
                    f"{pname}: health={health_score}, "
                    f"comms={last_comms_days:.0f}d ago, "
                    f"action=skip (rate-limited or suppressed)"
                    if last_comms_days is not None
                    else f"{pname}: health={health_score}, comms=unknown, action=skip (rate-limited or suppressed)"
                )
                continue

            triggers = _detect_triggers(
                project, items, last_comms_days, health_score, health_breakdown, state,
            )

            if not triggers:
                comms_str = f"{last_comms_days:.0f}d ago" if last_comms_days is not None else "unknown"
                decisions.append(
                    f"{pname}: health={health_score}, comms={comms_str}, trigger=none, action=skip"
                )
                continue

            # ------------------------------------------------------------------
            # 4. Queue the highest-priority trigger
            # ------------------------------------------------------------------
            # Priority order: sla_approaching > overdue > comms_gap > task_completed > task_in_review > others
            trigger_priority = [
                "sla_approaching", "overdue_tasks", "comms_gap",
                "task_completed", "task_in_review", "invoice_reminder",
                "ticket_resolved",
            ]
            triggers.sort(
                key=lambda t: trigger_priority.index(t["trigger"])
                if t["trigger"] in trigger_priority else 99
            )

            fired = triggers[0]
            msg_id = _queue_communication(fired, project, state)

            if msg_id:
                total_outreach_this_run += 1
                _record_outreach(pname, fired["trigger"], fired["channel"], msg_id, state)
                queued_messages.append({
                    "client": pname,
                    "trigger": fired["trigger"],
                    "action": fired["action"],
                    "channel": fired["channel"],
                    "message_id": msg_id,
                })
                comms_str = f"{last_comms_days:.0f}d ago" if last_comms_days is not None else "unknown"
                decisions.append(
                    f"{pname}: health={health_score}, comms={comms_str}, "
                    f"trigger={fired['trigger']}, action=queued (msg {msg_id})"
                )
            else:
                comms_str = f"{last_comms_days:.0f}d ago" if last_comms_days is not None else "unknown"
                decisions.append(
                    f"{pname}: health={health_score}, comms={comms_str}, "
                    f"trigger={fired['trigger']}, action=failed-to-queue"
                )

        # ------------------------------------------------------------------
        # 5. Save state
        # ------------------------------------------------------------------
        _save_state(state)

        # ------------------------------------------------------------------
        # 6. Build result
        # ------------------------------------------------------------------
        summary_parts = [f"{len(client_projects)} clients checked"]
        if queued_messages:
            summary_parts.append(f"{len(queued_messages)} messages queued for review")
        else:
            summary_parts.append("no actions needed")

        return {
            "agent": "cx_agent",
            "timestamp": now.isoformat(),
            "items_processed": len(client_projects),
            "items_found": len(queued_messages),
            "summary": "; ".join(summary_parts),
            "details": {
                "decisions": decisions,
                "queued_messages": queued_messages,
                "client_health": client_health,
            },
            "error": None,
        }

    except Exception as exc:
        logger.exception("CX agent failed")
        return {
            "agent": "cx_agent",
            "timestamp": now.isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {exc}",
            "details": {"decisions": decisions},
            "error": str(exc),
        }
