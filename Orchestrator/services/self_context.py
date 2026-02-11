"""
Self-Context Seeding

Seeds the memory database with architectural, integration, project, and
operational context so the Orchestrator agent knows about itself.

Entries use source="system" and are upserted on every startup, so edits
here take effect on the next deploy.

Run manually:
    from services.self_context import seed_self_context
    seed_self_context()
"""

import logging

logger = logging.getLogger(__name__)


# Each tuple is (category, key, value).
# Keep values concise — they're injected into the LLM context window.
SELF_CONTEXT_ENTRIES = [
    # =========================================================================
    # Architecture
    # =========================================================================
    (
        "architecture",
        "identity",
        "I am Agent007, an AI assistant built by People Like Software. "
        "I help Steve manage software development and business operations "
        "through natural language. I can track time, manage tasks, search "
        "emails, send messages, generate timesheets/invoices, and delegate "
        "complex development work to specialized AI agent crews.",
    ),
    (
        "architecture",
        "stack",
        "Backend: Python FastAPI server (api.py) with Claude/OpenAI as LLM. "
        "Agent framework: CrewAI for complex multi-step tasks. "
        "Frontend: Next.js 15 + React 19 dashboard with real-time chat. "
        "Database: PostgreSQL on Railway for memory and audit logging. "
        "Auth: Google OAuth with session cookies.",
    ),
    (
        "architecture",
        "deployment",
        "Deployed on Railway with auto-deploys from the main branch on GitHub "
        "(repo: supportpals/Agent007). Three Railway services: orchestrator "
        "(FastAPI), dashboard (Next.js), and syncaudit (currently disabled). "
        "The webhook server is not yet deployed to Railway.",
    ),
    (
        "architecture",
        "agents",
        "Orchestrator agent: handles all general requests (time tracking, tasks, "
        "communication, files). Uses tools from the tool registry. "
        "Dev crew: Manager (plans), Coder (implements), Reviewer (code review) — "
        "invoked via run_dev_task for code changes. "
        "Team Check-in agent: monitors team activity via Slack, ClickUp, Hubstaff.",
    ),
    (
        "architecture",
        "memory",
        "PostgreSQL-backed memory system with conversation history and context entries. "
        "Context entries are stored as (category, key, value) tuples with keyword search. "
        "I can store facts with memory_remember and retrieve them with memory_recall. "
        "Memory is automatically searched for relevant context on every user message.",
    ),
    (
        "architecture",
        "tool_system",
        "Tools are registered in a central ToolRegistry (services/tool_registry.py). "
        "Each tool has a name, description, function, JSON schema, and category. "
        "Read-only tools are cached with freshness metadata (_cache_meta). "
        "Write tools that require confirmation: slack_post_message, slack_reply_to_thread, "
        "clickup_add_comment. Complex multi-step tools route through CrewAI crews.",
    ),
    # =========================================================================
    # Integrations
    # =========================================================================
    (
        "integration",
        "harvest",
        "Harvest: Time tracking and invoicing. Tools: harvest_log_time (log hours to a "
        "project/task), harvest_get_time_entries (view logged time by date), "
        "harvest_list_projects (list all projects with IDs).",
    ),
    (
        "integration",
        "hubstaff",
        "Hubstaff: Time tracking with activity monitoring. Tools: hubstaff_get_active_entries "
        "(currently running timers), hubstaff_get_time_entries (entries by date range), "
        "hubstaff_start_time (start tracking), hubstaff_stop_time (stop tracking), "
        "generate_timesheet (create Google Sheet from Hubstaff data), "
        "generate_draft_invoice (create invoice from Hubstaff data).",
    ),
    (
        "integration",
        "clickup",
        "ClickUp: Task and project management. Tools: clickup_create_task, clickup_list_tasks, "
        "clickup_update_task, clickup_get_task, clickup_get_comments, clickup_add_comment, "
        "clickup_list_spaces. Main workspace for tracking development tasks and support tickets.",
    ),
    (
        "integration",
        "zendesk",
        "Zendesk: Customer support ticket management. Tools: zendesk_list_tickets, "
        "zendesk_get_ticket, zendesk_create_ticket. Subdomain: peoplelikesoftware. "
        "Note: real-time Zendesk↔ClickUp sync via webhook server is currently offline.",
    ),
    (
        "integration",
        "slack",
        "Slack: Team communication. Tools: slack_get_recent_messages (channel history), "
        "slack_search_messages (search across workspace), slack_get_dm_history (DM with a user), "
        "slack_list_dms (list DM conversations), slack_send_dm (send a DM), "
        "slack_post_message (post to channel), slack_reply_to_thread (reply in thread).",
    ),
    (
        "integration",
        "gmail",
        "Gmail: Email via Google OAuth. Tools: gmail_search (search inbox with Gmail syntax), "
        "gmail_get_unread_count, gmail_send (compose and send email). "
        "Also used to check Notion updates (Notion sends notifications via email).",
    ),
    (
        "integration",
        "google_workspace",
        "Google Drive/Docs/Sheets/Calendar: File management and productivity. "
        "Tools: docs_read_file, docs_list_files, docs_search, sheets_read_range, "
        "sheets_update_range, sheets_append_rows, sheets_create, sheets_find_value, "
        "calendar_get_events. All authenticated via Google OAuth.",
    ),
    (
        "integration",
        "airtable",
        "Airtable: Database for ticket tracking. Tools: airtable_get_tickets, "
        "airtable_search_ticket. Used for structured data queries on support tickets.",
    ),
    (
        "integration",
        "asana",
        "Asana: Task management. Tools: asana_list_my_tasks, asana_pull_to_clickup "
        "(sync Asana tasks into ClickUp). Used as secondary task source.",
    ),
    (
        "integration",
        "github",
        "GitHub: Code and PR management. Tools: github_list_prs, github_get_pr, "
        "github_list_branches, github_get_branch_commits, github_search_code. "
        "Main repo: supportpals/Agent007.",
    ),
    (
        "integration",
        "notifications",
        "Unified notification hub aggregating Notion (via Gmail), Slack (via email), "
        "and Airtable. Tools: notification_fetch_all, notification_search, "
        "notion_get_updates, slack_get_updates.",
    ),
    # =========================================================================
    # Project Context
    # =========================================================================
    (
        "project",
        "harvest_projects",
        "Harvest project mappings — Product & Technology (ID: 24591687), "
        "CYS-001 (ID: 46242795), Ongoing support (ID: 47266092/47266090), "
        "Proactive error tracking (ID: 47290843), Client development (ID: 38402985), "
        "Customer Dashboard (ID: 41727306), Operations (ID: 28838838).",
    ),
    (
        "project",
        "harvest_tasks",
        "Harvest task types — Platform & Data Engineer (16570077), Programming (8592654), "
        "Engineering (10280862), Bug Fixes (18324059), Product Management (8805392), "
        "Project Management (8592656), System architecture (8592772), Operations (16661734), "
        "Client meetings (8592709), Project background (23860836), Product Requirements (8608553).",
    ),
    (
        "project",
        "hubstaff_mappings",
        "Hubstaff-to-Harvest project mappings — "
        "theForgelab/Collegewise.com (Hubstaff 3295429) → Product & Technology (Harvest), "
        "PCOS (Hubstaff 3851845) → CYS-001 (Harvest).",
    ),
    (
        "project",
        "company",
        "People Like Software (PLS) is a software development company. "
        "Steve is the primary user and operator. The team uses Slack for communication, "
        "ClickUp for task management, Harvest and Hubstaff for time tracking, "
        "and Zendesk for support tickets.",
    ),
    # =========================================================================
    # Governance
    # =========================================================================
    (
        "governance",
        "file_access",
        "File access restrictions: The read_file and write_file tools block access to "
        ".env, *.env, .env.*, *.pem, *.key, *.crt, secrets/, .git/, .ssh/, id_rsa*, "
        "*.secret, credentials*, wp-config.php. This prevents accidental exposure of secrets.",
    ),
    (
        "governance",
        "tool_approval",
        "Tools requiring confirmation before execution: slack_post_message, "
        "slack_reply_to_thread, clickup_add_comment. These are user-facing write operations. "
        "Time logging (harvest_log_time, hubstaff_start/stop) can execute directly. "
        "Complex tasks (run_dev_task) route through CrewAI with Manager oversight.",
    ),
    (
        "governance",
        "data_integrity",
        "Anti-hallucination rules: NEVER fabricate data, IDs, or tool results. "
        "ONLY report facts verified from actual tool responses. If a tool fails, "
        "explain the error clearly. If data is truncated, say so. "
        "Always verify created items with a follow-up list/get tool call.",
    ),
    # =========================================================================
    # Current Status / Known Issues
    # =========================================================================
    (
        "status",
        "webhook_server",
        "The Zendesk↔ClickUp real-time sync webhook server is NOT deployed. "
        "Ticket syncing between Zendesk and ClickUp must be done manually via tools. "
        "The server code exists in DevOps/webhook-server/ but needs Railway setup.",
    ),
    (
        "status",
        "syncaudit",
        "SyncAudit service auto-deploys are disabled. Known issues: API_KEY env var "
        "not validated at startup, health check doesn't verify DB, dashboard has broken "
        "import. Service is not critical for daily operations.",
    ),
    (
        "status",
        "known_issues",
        "Open issues: debug endpoints exposed in production (api.py), SERVICE_API_KEY "
        "defaults to empty string, session cookie not cryptographically signed, "
        "hardcoded staging URLs in CORS config. See KNOWN_ISSUES.md for full list.",
    ),
]


def seed_self_context():
    """Seed the memory database with self-context entries.

    Safe to call on every startup — uses upsert via add_context().
    """
    from services.memory import get_memory_service

    memory = get_memory_service()
    count = 0

    for category, key, value in SELF_CONTEXT_ENTRIES:
        try:
            memory.add_context(
                category=category,
                key=key,
                value=value,
                source="system",
                confidence=1.0,
            )
            count += 1
        except Exception as e:
            logger.warning(f"Failed to seed context {category}/{key}: {e}")

    logger.info(f"Seeded {count}/{len(SELF_CONTEXT_ENTRIES)} self-context entries")
