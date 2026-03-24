"""Comms Gap Detector — finds projects with no recent client communication."""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("comms_gap_detector")

# Days without communication before flagging, by SLA tier
COMMS_THRESHOLDS = {
    "gold": 3,
    "silver": 5,
    "bronze": 10,
    "internal": 999,  # Don't flag internal projects
}


def run_comms_gap_detector() -> dict:
    """Check each client project for communication gaps."""
    try:
        from services.tool_registry import get_registry
        from services.project_context.project_registry import get_project_registry

        registry = get_registry()
        project_reg = get_project_registry()

        client_projects = project_reg.get_client_projects()
        gaps = []

        for project in client_projects:
            threshold = COMMS_THRESHOLDS.get(project.sla_tier, 7)
            if threshold >= 999:
                continue

            # Check Gmail for recent emails related to this project
            last_email_days = None
            try:
                search_terms = [project.name] + project.aliases[:2]
                query = " OR ".join(f'"{t}"' for t in search_terms[:3])
                result = registry.execute("gmail_search", {
                    "query": f"({query}) newer_than:30d",
                    "max_results": 1,
                }, skip_confirmation=True)

                emails = []
                if isinstance(result, dict):
                    emails = result.get("emails", result.get("messages", []))
                elif isinstance(result, list):
                    emails = result

                if emails:
                    # Parse the date of the most recent email
                    latest = emails[0]
                    date_str = latest.get("date", latest.get("internalDate", ""))
                    if date_str:
                        try:
                            from email.utils import parsedate_to_datetime
                            email_date = parsedate_to_datetime(date_str)
                            last_email_days = (datetime.now(timezone.utc) - email_date.astimezone(timezone.utc)).days
                        except Exception:
                            pass
            except Exception as e:
                logger.debug(f"Gmail check failed for {project.name}: {e}")

            # Check Slack for recent messages in project channel
            last_slack_days = None
            if project.slack_channel_id:
                try:
                    result = registry.execute("slack_get_recent_messages", {
                        "channel": project.slack_channel_id,
                        "limit": 1,
                    }, skip_confirmation=True)

                    messages = []
                    if isinstance(result, dict):
                        messages = result.get("messages", [])

                    if messages:
                        ts = messages[0].get("ts", "")
                        if ts:
                            msg_date = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                            last_slack_days = (datetime.now(timezone.utc) - msg_date).days
                except Exception as e:
                    logger.debug(f"Slack check failed for {project.name}: {e}")

            # Use the most recent communication across channels
            last_comms_days = None
            if last_email_days is not None and last_slack_days is not None:
                last_comms_days = min(last_email_days, last_slack_days)
            elif last_email_days is not None:
                last_comms_days = last_email_days
            elif last_slack_days is not None:
                last_comms_days = last_slack_days

            if last_comms_days is not None and last_comms_days > threshold:
                gaps.append({
                    "project": project.name,
                    "sla_tier": project.sla_tier,
                    "days_silent": last_comms_days,
                    "threshold": threshold,
                    "last_email_days": last_email_days,
                    "last_slack_days": last_slack_days,
                })
            elif last_comms_days is None:
                gaps.append({
                    "project": project.name,
                    "sla_tier": project.sla_tier,
                    "days_silent": None,
                    "threshold": threshold,
                    "last_email_days": None,
                    "last_slack_days": None,
                    "note": "No communication records found",
                })

        gaps.sort(key=lambda x: x.get("days_silent") or 999, reverse=True)

        return {
            "agent": "comms_gap_detector",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": len(client_projects),
            "items_found": len(gaps),
            "summary": f"{len(gaps)} projects with communication gaps" if gaps else f"All {len(client_projects)} client projects have recent communication",
            "details": gaps,
            "error": None,
        }
    except Exception as e:
        logger.exception("Comms gap detector failed")
        return {
            "agent": "comms_gap_detector",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "error": str(e),
        }
