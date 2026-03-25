"""CX Agent — additional communication templates."""

CX_TEMPLATES = {
    "cx-check-in": {
        "subject": "Quick check-in — {project_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Just checking in on {project_name}. Here's a quick status:\n\n"
            "- Active tasks: {active_count}\n"
            "- Completed this week: {completed_count}\n"
            "- In review: {review_count}\n\n"
            "{custom_note}"
            "Let me know if you have any questions or if priorities have shifted.\n\n"
            "Best,\nSteve"
        ),
        "channel": "email",
        "category": "status_update",
    },
    "cx-onboarding-welcome": {
        "subject": "Welcome to People Like Software — {project_name}",
        "body": (
            "Hi {client_name},\n\n"
            "Welcome! We're excited to get started on {project_name}.\n\n"
            "Here's what to expect:\n"
            "1. We'll set up your project workspace in ClickUp (you'll get an invite shortly)\n"
            "2. You can reach us anytime via email or your dedicated Slack channel\n"
            "3. We'll send regular status updates as work progresses\n"
            "4. For support issues, email support@peoplelikesoftware.com or use our help desk\n\n"
            "Your primary contact is Steve (steve@peoplelikesoftware.com).\n\n"
            "Looking forward to working together!\n\n"
            "Best,\nSteve"
        ),
        "channel": "email",
        "category": "onboarding",
    },
    "cx-resolution-summary": {
        "subject": "Resolved: {ticket_subject}",
        "body": (
            "Hi {client_name},\n\n"
            "Your ticket \"{ticket_subject}\" has been resolved.\n\n"
            "**What was done:**\n{resolution_summary}\n\n"
            "If you have any further issues or questions, don't hesitate to reach out.\n\n"
            "Best,\nSteve"
        ),
        "channel": "email",
        "category": "completion_notice",
    },
    "cx-sla-proactive": {
        "subject": "Update on {ticket_subject}",
        "body": (
            "Hi {client_name},\n\n"
            "I wanted to give you a quick update on \"{ticket_subject}\".\n\n"
            "Current status: {status}\n"
            "{update_detail}\n\n"
            "We're aiming to have this resolved by {eta}. I'll follow up once it's done.\n\n"
            "Best,\nSteve"
        ),
        "channel": "email",
        "category": "status_update",
    },
    "cx-overdue-plan": {
        "subject": "Status update — {project_name} tasks",
        "body": (
            "Hi {client_name},\n\n"
            "I wanted to proactively reach out about {project_name}.\n\n"
            "We have {overdue_count} task(s) that are past their target dates. "
            "Here's our plan to get back on track:\n\n"
            "{plan_detail}\n\n"
            "I'll send another update by {next_update_date}.\n\n"
            "Best,\nSteve"
        ),
        "channel": "email",
        "category": "delay_notification",
    },
    "cx-slack-status": {
        "subject": "",
        "body": (
            "\U0001f4cb *{project_name} — Quick Update*\n\n"
            "Active: {active_count} | Completed this week: {completed_count} | In review: {review_count}\n\n"
            "{custom_note}"
        ),
        "channel": "slack",
        "category": "status_update",
    },
}
