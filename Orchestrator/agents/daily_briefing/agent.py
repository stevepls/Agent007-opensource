"""
Daily Briefing Agent

Generates a morning briefing and delivers it via Slack DM.

Flow:
    1. Call briefing engine for prioritised items
    2. Call queue aggregator for SLA summary
    3. Call business advisor for advisories
    4. Format everything into Slack Block Kit message
    5. Send via message queue as a Slack DM (no approval needed)
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("daily_briefing")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BRIEFING_SLACK_USER = os.getenv("BRIEFING_SLACK_USER", "steve")

# Limits
MAX_BRIEFING_ITEMS = 8
MIN_BRIEFING_ITEMS = 5
MAX_ADVISORIES = 3
MAX_MESSAGE_CHARS = 4000

# Emoji map for briefing item types
_TYPE_EMOJI = {
    "schema_change": ":database:",
    "pending_approval": ":inbox_tray:",
    "code_review": ":mag:",
    "message_queue": ":envelope:",
    "error": ":x:",
    "todo": ":ballot_box_with_check:",
    "meeting": ":calendar:",
    "deadline": ":alarm_clock:",
    "insight": ":bulb:",
    "suggestion": ":thought_balloon:",
}

# Priority labels
_PRIORITY_LABELS = {
    0: ":red_circle: *CRITICAL*",
    1: ":large_orange_diamond: *HIGH*",
    2: ":white_circle: *MEDIUM*",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = 100) -> str:
    """Truncate text to max_len, appending ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _today_str() -> str:
    """Return today's date in a human-friendly format."""
    return datetime.now().strftime("%A, %B %-d, %Y")


def _estimate_block_text_len(blocks: List[Dict]) -> int:
    """Rough character count across all block text fields."""
    total = 0
    for block in blocks:
        if "text" in block and isinstance(block["text"], dict):
            total += len(block["text"].get("text", ""))
        if "fields" in block:
            for f in block["fields"]:
                total += len(f.get("text", ""))
        if "elements" in block:
            for e in block["elements"]:
                total += len(e.get("text", ""))
    return total


# ---------------------------------------------------------------------------
# Block Kit Builders
# ---------------------------------------------------------------------------

def _build_header_block(greeting: str) -> Dict:
    """Header block with greeting and date."""
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"{greeting}",
            "emoji": True,
        },
    }


def _build_date_context() -> Dict:
    """Context block showing today's date."""
    return {
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f":spiral_calendar_pad: {_today_str()}"},
        ],
    }


def _build_divider() -> Dict:
    return {"type": "divider"}


def _build_sla_section(breaching_items: List) -> List[Dict]:
    """Build SLA alert section from breaching WorkItems."""
    blocks: List[Dict] = []
    if not breaching_items:
        return blocks

    lines: List[str] = [":rotating_light: *SLA Alerts*"]
    for item in breaching_items:
        sla_status = item.priority_score.sla_status.value
        if sla_status == "breached":
            emoji = ":red_circle:"
        else:
            emoji = ":large_yellow_circle:"
        title = _truncate(item.title, 60)
        project = item.project_name or "Unknown"
        link = f"<{item.source_url}|View>" if item.source_url else ""
        lines.append(f"{emoji} {title} \u2014 _{project}_ {link}")

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    })
    return blocks


def _build_queue_summary_section(summary: Dict[str, Any]) -> List[Dict]:
    """Build queue summary section."""
    blocks: List[Dict] = []

    total = summary.get("total", 0)
    by_project = summary.get("by_project", {})
    project_count = len(by_project)

    headline = f":card_index_dividers: *Queue Summary* \u2014 {total} item{'s' if total != 1 else ''} across {project_count} project{'s' if project_count != 1 else ''}"
    project_lines: List[str] = []
    for proj, count in sorted(by_project.items(), key=lambda kv: kv[1], reverse=True):
        project_lines.append(f"\u2022 {proj}: {count}")

    text = headline
    if project_lines:
        text += "\n" + "\n".join(project_lines)

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
    })
    return blocks


def _build_briefing_items_section(items: List) -> List[Dict]:
    """Build prioritised briefing items grouped by priority."""
    blocks: List[Dict] = []
    if not items:
        return blocks

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": ":clipboard: *Top Items*"},
    })

    # Group by priority value (lower = higher priority)
    grouped: Dict[int, List] = {}
    for item in items:
        pval = item.priority.value if hasattr(item.priority, "value") else item.priority
        grouped.setdefault(pval, []).append(item)

    for pval in sorted(grouped.keys()):
        label = _PRIORITY_LABELS.get(pval)
        if label:
            lines: List[str] = [label]
        else:
            lines = []

        for item in grouped[pval]:
            item_type = item.type.value if hasattr(item.type, "value") else item.type
            emoji = _TYPE_EMOJI.get(item_type, ":small_blue_diamond:")
            desc = _truncate(item.description)
            lines.append(f"{emoji} *{item.title}*\n      {desc}")

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        })

    return blocks


def _build_advisories_section(advisories: List) -> List[Dict]:
    """Build business advisories section (CRITICAL and WARNING only)."""
    blocks: List[Dict] = []
    filtered = []
    for a in advisories:
        sev = a.severity.value if hasattr(a.severity, "value") else a.severity
        if sev in ("critical", "warning"):
            filtered.append(a)
        if len(filtered) >= MAX_ADVISORIES:
            break

    if not filtered:
        return blocks

    lines: List[str] = [":crystal_ball: *Business Advisories*"]
    for a in filtered:
        sev = a.severity.value if hasattr(a.severity, "value") else a.severity
        emoji = ":red_circle:" if sev == "critical" else ":warning:"
        lines.append(f"{emoji} *{a.title}*\n      {_truncate(a.recommendation)}")

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)},
    })
    return blocks


def _build_footer() -> Dict:
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "Generated by Agent007 \u2022 Use `/briefing` in chat for latest",
            }
        ],
    }


def _build_all_clear_blocks(greeting: str) -> List[Dict]:
    """Minimal message when there is nothing to report."""
    return [
        _build_header_block(greeting),
        _build_date_context(),
        _build_divider(),
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":white_check_mark: *All clear!* No critical items, SLA breaches, or advisories this morning. Enjoy your day.",
            },
        },
        _build_footer(),
    ]


# ---------------------------------------------------------------------------
# Trim helper — ensure Slack char limit is respected
# ---------------------------------------------------------------------------

def _trim_blocks_to_limit(blocks: List[Dict], limit: int = MAX_MESSAGE_CHARS) -> List[Dict]:
    """Drop trailing content sections until we are under the char limit.

    We never remove the header, date context, first divider, or footer.
    """
    while _estimate_block_text_len(blocks) > limit and len(blocks) > 4:
        # Remove the block just before the footer (last block)
        blocks.pop(-2)
    return blocks


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_daily_briefing() -> dict:
    """Generate and deliver morning briefing via Slack DM.

    Returns:
        dict with keys: success (bool), items_found (int), details (list),
        error (str or None).  Follows the AgentResult pattern used by other
        proactive agents.
    """
    details: List[str] = []
    total_items = 0

    # ------------------------------------------------------------------
    # 1. Briefing items
    # ------------------------------------------------------------------
    briefing_items: List = []
    greeting = "Good morning"
    try:
        from services.briefing import get_briefing_engine

        engine = get_briefing_engine()
        briefing_items = engine.get_briefing(max_items=15, refresh=True)
        greeting = engine.get_greeting()
        details.append(f"Briefing engine returned {len(briefing_items)} items")
    except Exception as exc:
        logger.error("Daily briefing: briefing engine failed: %s", exc, exc_info=True)
        details.append(f"Briefing engine error: {exc}")

    # ------------------------------------------------------------------
    # 2. Queue / SLA summary
    # ------------------------------------------------------------------
    queue_summary: Dict[str, Any] = {}
    breaching_items: List = []
    try:
        from services.queue_aggregator import get_queue_aggregator

        queue_agg = get_queue_aggregator()
        queue_summary = queue_agg.get_summary()
        breaching_items = queue_agg.get_breaching()
        total_items += queue_summary.get("total", 0)
        details.append(
            f"Queue: {queue_summary.get('total', 0)} items, "
            f"{len(breaching_items)} breaching/approaching"
        )
    except Exception as exc:
        logger.error("Daily briefing: queue aggregator failed: %s", exc, exc_info=True)
        details.append(f"Queue aggregator error: {exc}")

    # ------------------------------------------------------------------
    # 3. Business advisories
    # ------------------------------------------------------------------
    advisories: List = []
    try:
        from services.business_advisor import get_advisor

        advisor = get_advisor()
        advisories = advisor.get_advisories(refresh=True)
        details.append(f"Business advisor returned {len(advisories)} advisories")
    except Exception as exc:
        logger.error("Daily briefing: business advisor failed: %s", exc, exc_info=True)
        details.append(f"Business advisor error: {exc}")

    # ------------------------------------------------------------------
    # 4. Decide if there's anything to report
    # ------------------------------------------------------------------
    has_content = bool(briefing_items or breaching_items or advisories or queue_summary.get("total"))
    total_items += len(briefing_items) + len(advisories)

    # ------------------------------------------------------------------
    # 5. Build Slack Block Kit message
    # ------------------------------------------------------------------
    if has_content:
        blocks: List[Dict] = [
            _build_header_block(greeting),
            _build_date_context(),
            _build_divider(),
        ]

        # SLA alerts
        sla_blocks = _build_sla_section(breaching_items)
        if sla_blocks:
            blocks.extend(sla_blocks)
            blocks.append(_build_divider())

        # Queue summary
        if queue_summary:
            blocks.extend(_build_queue_summary_section(queue_summary))
            blocks.append(_build_divider())

        # Top briefing items (5-8)
        display_count = min(MAX_BRIEFING_ITEMS, max(MIN_BRIEFING_ITEMS, len(briefing_items)))
        top_items = briefing_items[:display_count]
        item_blocks = _build_briefing_items_section(top_items)
        if item_blocks:
            blocks.extend(item_blocks)
            blocks.append(_build_divider())

        # Business advisories
        advisory_blocks = _build_advisories_section(advisories)
        if advisory_blocks:
            blocks.extend(advisory_blocks)
            blocks.append(_build_divider())

        # Footer
        blocks.append(_build_footer())

        # Trim to Slack limit
        blocks = _trim_blocks_to_limit(blocks)
    else:
        blocks = _build_all_clear_blocks(greeting)

    # Build a plain-text fallback from the greeting
    plain_text = f"{greeting} \u2014 {_today_str()}"

    # ------------------------------------------------------------------
    # 6. Send via message queue
    # ------------------------------------------------------------------
    try:
        from services.message_queue import get_message_queue, MessageType

        mq = get_message_queue()
        msg = mq.queue(
            msg_type=MessageType.SLACK_DM,
            channel=BRIEFING_SLACK_USER,
            content=plain_text,
            metadata={"blocks": blocks},
            created_by="daily_briefing_agent",
            delay_seconds=0,
            requires_approval=False,
        )
        details.append(f"Queued Slack DM id={msg.id}")
        logger.info("Daily briefing queued as message %s", msg.id)
    except Exception as exc:
        logger.error("Daily briefing: message queue failed: %s", exc, exc_info=True)
        details.append(f"Message queue error: {exc}")
        return {
            "success": False,
            "items_found": total_items,
            "details": details,
            "error": str(exc),
        }

    return {
        "success": True,
        "items_found": total_items,
        "details": details,
        "error": None,
    }
