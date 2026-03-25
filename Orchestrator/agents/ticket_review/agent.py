"""
Ticket Review Agent — Quality gate and ticket hygiene.

Enriches tickets without being destructive.
Escalates only when truly needed.

Runs every 30 minutes. Three passes per run:
1. Intake Quality — new/recent tickets (tags, STR, duplicates, priority)
2. Active Ticket Updates — in-progress tickets (assignee, staleness)
3. Closure Gate — completed tickets (evidence, PR links, summaries)

Design rules:
- NEVER overwrite good scaffolder output
- Enrich and refine, not destructively rewrite
- Only escalate to Steve when his attention is truly required
- Follow up with assigned dev or CX agent first
- Use Haiku for classification tasks (fast, cheap)
"""

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("ticket_review")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Tags to auto-apply based on project stack
STACK_TAGS = {
    "php": ["php"],
    "magento": ["magento", "magento2"],
    "magento2": ["magento2"],
    "mysql": ["mysql", "database"],
    "javascript": ["javascript", "js"],
    "react": ["react", "frontend"],
    "next.js": ["nextjs", "frontend"],
    "python": ["python"],
    "node": ["nodejs"],
    "wordpress": ["wordpress", "wp"],
    "woocommerce": ["woocommerce", "ecommerce"],
}

# Keywords that indicate steps to reproduce are present
STR_INDICATORS = [
    "steps to reproduce", "how to reproduce", "reproduction steps",
    "steps:", "to reproduce:", "1.", "step 1",
    "given", "when", "then", "expected", "actual",
]

# Keywords that indicate a bug (needs steps to reproduce)
BUG_KEYWORDS = [
    "bug", "error", "broken", "not working", "crash", "fix",
    "issue", "defect", "problem", "fails", "failure",
]

# Evidence patterns in comments
PR_PATTERN = re.compile(
    r'github\.com/[^\s]+/pull/\d+|github\.com/[^\s]+/commit/[a-f0-9]+',
    re.IGNORECASE,
)
IMAGE_PATTERN = re.compile(
    r'\.(png|jpg|jpeg|gif|webp|svg|screenshot)',
    re.IGNORECASE,
)
VIDEO_PATTERN = re.compile(
    r'\.(mp4|mov|webm|loom\.com|screencast)',
    re.IGNORECASE,
)

# Staleness thresholds by SLA tier (days without update)
STALE_STATUS_THRESHOLDS = {
    "gold": 2,
    "silver": 5,
    "bronze": 7,
    "internal": 14,
}

# UI-related keywords (closure gate: screenshots expected)
UI_KEYWORDS = [
    "ui", "frontend", "css", "layout", "design", "page",
    "form", "button", "modal", "dropdown", "menu", "header",
]

# Code-change keywords (closure gate: PR link expected)
CODE_KEYWORDS = [
    "fix", "implement", "refactor", "update", "add", "remove",
    "change", "migrate", "upgrade", "patch",
]

# Stop words excluded from title overlap calculation
STOP_WORDS = frozenset({
    "the", "a", "an", "is", "in", "on", "to", "for", "of",
    "and", "or", "it", "not", "be", "with", "this", "that",
    "-", "—", "|", "/",
})

# Duplicate detection threshold (0-1)
DUPLICATE_OVERLAP_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_bug_ticket(title: str, description: str, tags: List[str]) -> bool:
    """Check if this ticket is likely a bug report."""
    blob = f"{title} {description} {' '.join(tags)}".lower()
    return any(kw in blob for kw in BUG_KEYWORDS)


def _has_steps_to_reproduce(description: str, comments: List[Dict]) -> bool:
    """Check if steps to reproduce exist in description or comments."""
    blob = f"{description} {' '.join(c.get('text', '') for c in comments)}".lower()
    return any(indicator in blob for indicator in STR_INDICATORS)


def _has_pr_link(comments: List[Dict]) -> bool:
    """Check if any comment contains a GitHub PR or commit link."""
    for c in comments:
        if PR_PATTERN.search(c.get("text", "")):
            return True
    return False


def _has_screenshot_or_video(comments: List[Dict]) -> Tuple[bool, bool]:
    """Check if comments contain screenshot/video evidence. Returns (has_screenshot, has_video)."""
    has_img = False
    has_vid = False
    for c in comments:
        text = c.get("text", "")
        if IMAGE_PATTERN.search(text):
            has_img = True
        if VIDEO_PATTERN.search(text):
            has_vid = True
    return has_img, has_vid


def _has_closure_summary(comments: List[Dict]) -> bool:
    """Check if the last comment contains a closure summary."""
    if not comments:
        return False
    last = comments[-1].get("text", "").lower()
    closure_indicators = [
        "complete", "done", "resolved", "fixed", "deployed",
        "scaffolding complete", "work done", "implemented",
        "merged", "released", "shipped",
    ]
    return any(ind in last for ind in closure_indicators)


def _was_scaffolder_active(comments: List[Dict]) -> bool:
    """Check if the scaffolder agent has commented on this ticket."""
    for c in comments:
        if "ScaffoldingAgent" in c.get("text", ""):
            return True
    return False


def _was_already_reviewed(comments: List[Dict]) -> bool:
    """Check if this agent already reviewed this ticket."""
    for c in comments:
        if "TicketReviewAgent" in c.get("text", ""):
            return True
    return False


def _title_overlap(title1: str, title2: str) -> float:
    """Simple word overlap ratio between two titles (stop words excluded)."""
    words1 = set(title1.lower().split()) - STOP_WORDS
    words2 = set(title2.lower().split()) - STOP_WORDS
    if not words1 or not words2:
        return 0.0
    meaningful = words1 & words2
    return len(meaningful) / max(len(words1), len(words2), 1)


def _get_clickup_client():
    """Get the ClickUp client directly (for richer task data)."""
    from services.tickets.clickup_client import get_clickup_client
    return get_clickup_client()


def _fetch_comments(registry, task_id: str) -> List[Dict]:
    """Fetch comments for a task via the tool registry."""
    try:
        result = registry.execute("clickup_get_comments", {
            "task_id": task_id,
        }, skip_confirmation=True)
        if isinstance(result, dict) and "comments" in result:
            return result["comments"]
    except Exception as e:
        logger.debug(f"Failed to fetch comments for {task_id}: {e}")
    return []


def _add_comment(registry, task_id: str, text: str) -> bool:
    """Add a comment to a task. Returns True on success."""
    try:
        result = registry.execute("clickup_add_comment", {
            "task_id": task_id,
            "comment": text,
        }, skip_confirmation=True)
        return isinstance(result, dict) and result.get("success", False)
    except Exception as e:
        logger.debug(f"Failed to comment on {task_id}: {e}")
        return False


def _update_task_status(registry, task_id: str, status: str) -> bool:
    """Update a task's status. Returns True on success."""
    try:
        result = registry.execute("clickup_update_task", {
            "task_id": task_id,
            "status": status,
        }, skip_confirmation=True)
        return isinstance(result, dict) and result.get("success", False)
    except Exception as e:
        logger.debug(f"Failed to update status on {task_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

def run_ticket_review() -> dict:
    """
    Ticket Review Agent — quality gate and ticket hygiene.

    Three passes:
    1. Intake quality (new tickets)
    2. Active ticket updates (in-progress)
    3. Closure gate (completed tickets)

    Returns a dict matching the AgentResult pattern.
    """
    try:
        from services.tool_registry import get_registry
        from services.project_context.project_registry import get_project_registry

        registry = get_registry()
        project_reg = get_project_registry()

        now = datetime.now(timezone.utc)
        findings: List[Dict[str, Any]] = []
        items_processed = 0
        actions_taken: List[str] = []

        # Use the ClickUp client directly for richer task data
        # (the tool registry wrapper strips assignees, tags, description)
        clickup_token = os.getenv("CLICKUP_API_TOKEN")
        client = None
        if clickup_token:
            try:
                client = _get_clickup_client()
            except Exception as e:
                logger.warning(f"Could not init ClickUp client: {e}")

        if not client:
            return {
                "agent": "ticket_review",
                "timestamp": now.isoformat(),
                "items_processed": 0,
                "items_found": 0,
                "summary": "Skipped: ClickUp not configured",
                "details": [],
                "actions_taken": [],
                "error": None,
            }

        # Get all active client projects
        client_projects = project_reg.get_client_projects()

        for project in client_projects:
            if not project.clickup_list_id:
                continue

            # Fetch tasks using client directly (full ClickUpTask objects)
            try:
                open_tasks = client.list_tasks(
                    project.clickup_list_id, include_closed=False,
                )
            except Exception as e:
                logger.warning(f"Failed to fetch open tasks for {project.name}: {e}")
                continue

            # Also fetch recently completed tasks for the closure gate
            closed_tasks = []
            try:
                closed_tasks = client.list_tasks(
                    project.clickup_list_id, include_closed=True,
                    statuses=["complete", "done", "closed", "resolved"],
                )
            except Exception as e:
                logger.debug(f"Failed to fetch closed tasks for {project.name}: {e}")

            all_tasks = open_tasks + closed_tasks
            # Deduplicate by ID
            seen_ids = set()
            deduped_tasks = []
            for t in all_tasks:
                if t.id not in seen_ids:
                    seen_ids.add(t.id)
                    deduped_tasks.append(t)
            all_tasks = deduped_tasks

            for task in all_tasks:
                items_processed += 1
                task_id = task.id
                title = task.name or ""
                description = task.description or ""
                status = (task.status or "").lower()
                tags = task.tags if task.tags else []
                assignees = task.assignees if task.assignees else []

                # Fetch comments for this task
                comments = _fetch_comments(registry, task_id)

                # Skip if we already reviewed this ticket recently
                if _was_already_reviewed(comments):
                    continue

                # ═══════════════════════════════════════════
                # PASS 1: Intake Quality (open/new tickets)
                # ═══════════════════════════════════════════

                if status in ("open", "to do", "pending ai scaffolding"):
                    is_bug = _is_bug_ticket(title, description, tags)

                    # Check steps to reproduce (bugs only)
                    if is_bug and not _has_steps_to_reproduce(description, comments):
                        findings.append({
                            "task_id": task_id,
                            "project": project.name,
                            "title": title,
                            "issue": "missing_steps_to_reproduce",
                            "action": "flagged",
                            "severity": "attention",
                        })
                        commented = _add_comment(registry, task_id, (
                            "**TicketReviewAgent -- Missing Steps to Reproduce**\n\n"
                            "This appears to be a bug report but doesn't include "
                            "clear steps to reproduce. Please add:\n"
                            "1. Steps to trigger the issue\n"
                            "2. Expected behavior\n"
                            "3. Actual behavior\n"
                            "4. Environment details (if relevant)\n\n"
                            "_This enriches the ticket for faster resolution._"
                        ))
                        if commented:
                            actions_taken.append(
                                f"Flagged {task_id} for missing steps to reproduce"
                            )

                    # Check priority
                    priority = task.priority
                    if not priority:
                        # Suggest based on SLA tier + bug severity
                        suggested = "normal"
                        if project.sla_tier == "gold":
                            suggested = "high" if is_bug else "normal"
                        elif project.sla_tier == "silver":
                            suggested = "normal"

                        findings.append({
                            "task_id": task_id,
                            "project": project.name,
                            "title": title,
                            "issue": "no_priority_set",
                            "suggested_priority": suggested,
                        })

                    # Check for duplicates (simple title overlap with other tasks in same project)
                    for other_task in open_tasks:
                        if other_task.id == task_id:
                            continue
                        overlap = _title_overlap(title, other_task.name or "")
                        if overlap > DUPLICATE_OVERLAP_THRESHOLD:
                            findings.append({
                                "task_id": task_id,
                                "project": project.name,
                                "title": title,
                                "issue": "possible_duplicate",
                                "duplicate_of": other_task.id,
                                "duplicate_title": other_task.name,
                                "overlap": round(overlap, 2),
                            })
                            # Add comment linking to potential duplicate
                            _add_comment(registry, task_id, (
                                "**TicketReviewAgent -- Possible Duplicate Detected**\n\n"
                                f"This ticket may overlap with: "
                                f"**{other_task.name}** ({other_task.url or other_task.id})\n"
                                f"Similarity: {round(overlap * 100)}%\n\n"
                                "_Please verify and merge if appropriate. "
                                "This agent will NOT close either ticket._"
                            ))
                            actions_taken.append(
                                f"Flagged {task_id} as possible duplicate of {other_task.id}"
                            )
                            break  # Only flag the strongest match

                # ═══════════════════════════════════════════
                # PASS 2: Active Ticket Updates
                # ═══════════════════════════════════════════

                if status in ("in progress", "in_progress", "in review", "internal review"):
                    # Respect scaffolder work — don't touch if scaffolder was active
                    if _was_scaffolder_active(comments):
                        continue

                    # Check if assignee is set
                    if not assignees:
                        severity = "attention"
                        # Escalate to Steve only if high/critical
                        priority_name = getattr(task, "priority_name", None) or ""
                        if priority_name.lower() in ("urgent", "high"):
                            severity = "escalate_steve"

                        findings.append({
                            "task_id": task_id,
                            "project": project.name,
                            "title": title,
                            "issue": "no_assignee",
                            "status": status,
                            "severity": severity,
                        })
                        actions_taken.append(
                            f"Flagged {task_id} — in '{status}' with no assignee"
                        )

                    # Check if ticket has been in the same status too long
                    stale_days = STALE_STATUS_THRESHOLDS.get(
                        project.sla_tier, 7,
                    )
                    # Use date_updated from the task if available
                    updated_at = getattr(task, "date_updated", None)
                    if updated_at and isinstance(updated_at, datetime):
                        age = now - updated_at
                        if age > timedelta(days=stale_days):
                            findings.append({
                                "task_id": task_id,
                                "project": project.name,
                                "title": title,
                                "issue": "stale_in_progress",
                                "status": status,
                                "days_stale": round(age.total_seconds() / 86400, 1),
                                "threshold_days": stale_days,
                                "severity": "attention",
                            })

                # ═══════════════════════════════════════════
                # PASS 3: Closure Gate
                # ═══════════════════════════════════════════

                if status in ("done", "complete", "closed", "resolved"):
                    missing_evidence = []

                    has_img, has_vid = _has_screenshot_or_video(comments)
                    has_pr = _has_pr_link(comments)
                    has_summary = _has_closure_summary(comments)

                    # UI changes should have screenshots
                    blob = f"{title} {description}".lower()
                    is_ui_change = any(kw in blob for kw in UI_KEYWORDS)
                    if is_ui_change and not has_img:
                        missing_evidence.append("screenshot (UI change)")

                    # Code changes should have PR link
                    is_code_change = any(kw in blob for kw in CODE_KEYWORDS)
                    if is_code_change and not has_pr:
                        missing_evidence.append("PR link (code change)")

                    # All closures need a summary
                    if not has_summary:
                        missing_evidence.append("closure summary")

                    if missing_evidence:
                        evidence_list = ", ".join(missing_evidence)
                        findings.append({
                            "task_id": task_id,
                            "project": project.name,
                            "title": title,
                            "issue": "incomplete_closure",
                            "missing": missing_evidence,
                            "severity": "high",
                        })

                        # Reopen the ticket (move back to "in review")
                        reopened = _update_task_status(
                            registry, task_id, "in review",
                        )
                        commented = _add_comment(registry, task_id, (
                            f"**TicketReviewAgent -- Closure Evidence Missing**\n\n"
                            f"This ticket was closed but is missing: "
                            f"**{evidence_list}**\n\n"
                            f"Moving back to 'In Review'. Please add the "
                            f"missing evidence before closing.\n\n"
                            f"_This ensures quality and auditability._"
                        ))
                        if reopened or commented:
                            actions_taken.append(
                                f"Reopened {task_id} -- missing {evidence_list}"
                            )

                        # Check if we need to escalate (no one responding)
                        if not assignees:
                            findings.append({
                                "task_id": task_id,
                                "project": project.name,
                                "title": title,
                                "issue": "closure_blocked_no_assignee",
                                "severity": "escalate_steve",
                            })

        # ───────────────────────────────────────────────────────
        # Build summary
        # ───────────────────────────────────────────────────────
        issue_counts: Dict[str, int] = {}
        for f in findings:
            issue = f.get("issue", "unknown")
            issue_counts[issue] = issue_counts.get(issue, 0) + 1

        summary_parts = [
            f"{count} {issue.replace('_', ' ')}"
            for issue, count in issue_counts.items()
        ]

        return {
            "agent": "ticket_review",
            "timestamp": now.isoformat(),
            "items_processed": items_processed,
            "items_found": len(findings),
            "summary": (
                "; ".join(summary_parts)
                if summary_parts
                else f"Reviewed {items_processed} tickets, all clean"
            ),
            "details": findings[:20],
            "actions_taken": actions_taken,
            "error": None,
        }

    except Exception as e:
        logger.exception("Ticket review agent failed")
        return {
            "agent": "ticket_review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "items_processed": 0,
            "items_found": 0,
            "summary": f"Failed: {e}",
            "details": [],
            "actions_taken": [],
            "error": str(e),
        }
