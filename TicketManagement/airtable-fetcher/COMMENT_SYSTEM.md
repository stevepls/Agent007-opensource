# Integrated Airtable + Harvest Ticket Management System

This system provides a unified interface for managing tickets with both Airtable comments/status updates and Harvest time tracking. It supports both numeric ticket IDs (e.g., 5098) and record IDs (e.g., recDKObpxCxQ9KqWC) for maximum convenience.

## Features

- ✅ Add comments to any Airtable ticket using ticket ID or record ID
- 🔧 Multiple comment types with automatic formatting
- 📊 Update ticket status with validation
- 🔄 Combined status update + comment in one operation
- ⏱️ Harvest time tracking integration (start/stop timers, log time)
- 🎯 Unified workflow: start timer → work → update status → stop timer
- 📝 Automatic timestamps and author attribution
- 🔍 Smart field detection (uses Description field)
- 🚀 Easy-to-use command line interface

## Usage Methods

### Method 1: Python Script (Detailed)

```bash
# Activate environment first
source src/venv/bin/activate
export AIRTABLE_PERSONAL_ACCESS_TOKEN=REDACTED-AIRTABLE-PAT
export AIRTABLE_BASE_ID=app37XFdl4xoMbvx3
export AIRTABLE_TABLE_ID=tblFXfLF3tGjW9IXm

# Add different types of comments
python add_comment.py --ticket recABC123 --work-summary "Updated payment plan dates" --author "Your Name"
python add_comment.py --ticket recABC123 --status-update "Completed and ready for review"
python add_comment.py --ticket recABC123 --database-change "Updated payment_plan table fields"
python add_comment.py --ticket recABC123 --technical-note "Used n98-magerun2 for database access"
python add_comment.py --ticket recABC123 --verification "Tested with order #52000000484"
python add_comment.py --ticket recABC123 --comment "Generic comment text"

# Status management
python add_comment.py --ticket recABC123 --update-status "Complete"
python add_comment.py --ticket recABC123 --status-with-comment "Complete" "All work finished and tested"
python add_comment.py --list-statuses
```

### Method 2: Integrated Ticket Manager (Recommended)

```bash
# Complete workflow with time tracking
./ticket_manager.sh 5098 start "Working on payment plan update"
./ticket_manager.sh 5098 work-summary "Updated payment plan dates"
./ticket_manager.sh 5098 complete "All work finished and tested"

# Time tracking
./ticket_manager.sh 5098 log-time 2.5 "Database updates and testing"
./ticket_manager.sh 5098 stop

# Status management
./ticket_manager.sh 5098 status "Complete"
./ticket_manager.sh 5098 in-progress
```

### Method 3: Individual Scripts (Advanced)

```bash
# Airtable comments only
./comment_ticket.sh 5098 work-summary "Updated payment plan dates"
./comment_ticket.sh 5098 status "Complete"

# Harvest time tracking only
python harvest_integration.py --ticket 5098 --start "Working on ticket"
python harvest_integration.py --ticket 5098 --stop
```

## Comment Types

| Type | Format | Use Case |
|------|--------|----------|
| `work-summary` | ✅ WORK COMPLETED: ... | Document completed work |
| `status-update` | 🔄 STATUS UPDATE: ... | Update ticket status |
| `database-change` | 🗄️ DATABASE CHANGES: ... | Document DB modifications |
| `technical-note` | 🔧 TECHNICAL DETAILS: ... | Technical implementation details |
| `verification` | ✔️ VERIFICATION: ... | Testing and verification info |
| `comment` | (no prefix) | Generic comments |

## Status Options

| Status | Description |
|--------|-------------|
| `Assigned - Small` | Small task assigned to developer |
| `Assigned - Large` | Large task assigned to developer |
| `In Progress - Small` | Small task currently being worked on |
| `In Progress - Large` | Large task currently being worked on |
| `Done (Needs Review)` | Work completed, awaiting review |
| `Complete` | Task fully completed and verified |
| `Waiting on Details from CW` | Waiting for more information |
| `On Hold` | Task temporarily paused |
| `Backlog - Small` | Small task in backlog |
| `Backlog - Large` | Large task in backlog |

## Complete Workflow Example

### Typical Ticket Workflow
```bash
# 1. Start working on ticket (starts timer + updates status)
./ticket_manager.sh 5098 start "Working on payment plan update"

# 2. Document progress as you work
./ticket_manager.sh 5098 work-summary "Updated database schema for bi-annual payments"
./ticket_manager.sh 5098 database-change "Modified payment_plan table, updated dates"

# 3. Complete the work (stops timer + marks complete)
./ticket_manager.sh 5098 complete "Payment plan successfully updated to bi-annual schedule"

# Alternative: Log time separately if you forgot to start timer
./ticket_manager.sh 5098 log-time 3.25 "Complete payment plan update with testing"
```

## Real Examples

### Payment Plan Update Example
```bash
# Complete workflow for Colin Li payment plan (Ticket 5098)
./ticket_manager.sh 5098 start "Working on payment plan update for Colin Li"
./ticket_manager.sh 5098 database-change \
  "Updated payment plan ID 15139 for student Colin Li. Changed from monthly to bi-annual: 2026-01-15, 2026-07-15" \
  "Steve Bien-Aime"
./ticket_manager.sh 5098 complete \
  "Payment plan successfully updated and all changes verified" "Steve Bien-Aime"

# Alternative: Individual comment approach
./comment_ticket.sh 5098 database-change \
  "Updated payment plan ID 15139 for student Colin Li" "Steve Bien-Aime"
./comment_ticket.sh 5098 status "Complete"
```

### Email Template Update Example
```bash
# Complete workflow for enrollment email update (Ticket 4962)
./ticket_manager.sh 4962 start "Updating enrollment email template"
./ticket_manager.sh 4962 work-summary \
  "Updated enrollment email to remove individual product prices and show service/finance fees as separate line items"
./ticket_manager.sh 4962 verification \
  "All changes tested and verified in staging environment"
./ticket_manager.sh 4962 complete "Email template updates completed and deployed"
```

## How It Works

1. **Field Detection**: Automatically finds the best field to use for comments (tries Comments, Notes, Description, etc.)
2. **Timestamp**: Adds automatic timestamp `[2025-06-22 12:30:45]`
3. **Author**: Includes author name (defaults to "AI Assistant")
4. **Formatting**: Adds emoji prefixes and consistent formatting
5. **Appending**: Appends to existing content rather than overwriting

## Integration with Workflow

This comment system integrates perfectly with our existing ticket workflow:

1. **Fetch tickets**: `python src/fetch_airtable_tickets.py`
2. **Work on ticket**: Do the actual development work
3. **Document work**: Use comment system to add structured updates
4. **Status update**: Add final status update when complete

## Field Mapping

The system automatically detects and uses these fields in order of preference:
1. Comments
2. Notes  
3. Internal Notes
4. Status Comments
5. Work Notes
6. Description (fallback)

## Error Handling

- ❌ Invalid ticket IDs: Clear error messages
- ❌ Permission issues: Helpful debugging info
- ❌ Network issues: Retry suggestions
- ✅ Success confirmation: Shows which field was used

## Quick Reference

```bash
# Most common usage patterns:
./comment_ticket.sh TICKET_ID work-summary "What you accomplished"
./comment_ticket.sh TICKET_ID status-update "Current status"
./comment_ticket.sh TICKET_ID database-change "DB changes made"

# Status management patterns:
./comment_ticket.sh TICKET_ID status "Complete"
./comment_ticket.sh TICKET_ID status-with-comment "Complete" "Final summary"
./comment_ticket.sh any list-statuses
```

This system makes it easy to maintain detailed ticket history and communicate progress to the team! 