#!/bin/bash

# Airtable Ticket Comment Helper Script
# 
# Usage examples:
#   ./comment_ticket.sh rec123 "work-summary" "Fixed payment plan dates"
#   ./comment_ticket.sh rec123 "status-update" "Completed database changes"
#   ./comment_ticket.sh rec123 "comment" "General comment text"
#   ./comment_ticket.sh rec123 "status" "Complete"
#   ./comment_ticket.sh rec123 "status-with-comment" "Complete" "All work finished and tested"

# Check if we have the minimum required arguments
if [ $# -lt 2 ]; then
    echo "❌ Error: Not enough arguments"
    echo ""
    echo "Usage: $0 <ticket_id> <action_type> [args...] [author]"
    echo ""
    echo "Action types:"
    echo "  - comment <text>: Generic comment"
    echo "  - status-update <text>: Status update comment"
    echo "  - work-summary <text>: Work completion summary"
    echo "  - technical-note <text>: Technical details"
    echo "  - database-change <text>: Database changes"
    echo "  - verification <text>: Verification/testing info"
    echo "  - status <status>: Update ticket status only"
    echo "  - status-with-comment <status> <comment>: Update status and add comment"
    echo "  - list-statuses: Show available status options"
    echo ""
    echo "Examples:"
    echo "  $0 recABC123 work-summary 'Updated payment plan dates'"
    echo "  $0 recABC123 status 'Complete'"
    echo "  $0 recABC123 status-with-comment 'Complete' 'All work finished and tested'"
    echo "  $0 recABC123 list-statuses"
    exit 1
fi

TICKET_ID="$1"
ACTION_TYPE="$2"

# Handle special case for list-statuses
if [ "$ACTION_TYPE" = "list-statuses" ]; then
    AUTHOR="${3:-AI Assistant}"
else
    COMMENT_TEXT="$3"
    AUTHOR="${4:-AI Assistant}"
fi

# Set up environment
cd "$(dirname "$0")"
source src/venv/bin/activate 2>/dev/null || {
    echo "❌ Error: Could not activate virtual environment"
    echo "Make sure you're in the airtable-fetcher directory and venv exists"
    exit 1
}

# Load environment variables from credentials.env
if [ -f "credentials.env" ]; then
    source credentials.env
fi

# Validate required credentials
if [ -z "$AIRTABLE_PERSONAL_ACCESS_TOKEN" ]; then
    echo "❌ Error: AIRTABLE_PERSONAL_ACCESS_TOKEN not set"
    echo "Please add it to credentials.env"
    exit 1
fi

# Build the command based on action type
case "$ACTION_TYPE" in
    "comment")
        CMD="python add_comment.py --ticket $TICKET_ID --comment \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "status-update")
        CMD="python add_comment.py --ticket $TICKET_ID --status-update \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "work-summary")
        CMD="python add_comment.py --ticket $TICKET_ID --work-summary \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "technical-note")
        CMD="python add_comment.py --ticket $TICKET_ID --technical-note \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "database-change")
        CMD="python add_comment.py --ticket $TICKET_ID --database-change \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "verification")
        CMD="python add_comment.py --ticket $TICKET_ID --verification \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "status")
        CMD="python add_comment.py --ticket $TICKET_ID --update-status \"$COMMENT_TEXT\" --author \"$AUTHOR\""
        ;;
    "status-with-comment")
        STATUS="$COMMENT_TEXT"
        COMMENT="$4"
        AUTHOR="${5:-AI Assistant}"
        CMD="python add_comment.py --ticket $TICKET_ID --status-with-comment \"$STATUS\" \"$COMMENT\" --author \"$AUTHOR\""
        ;;
    "list-statuses")
        CMD="python add_comment.py --list-statuses"
        ;;
    *)
        echo "❌ Error: Unknown action type '$ACTION_TYPE'"
        echo "Valid types: comment, status-update, work-summary, technical-note, database-change, verification, status, status-with-comment, list-statuses"
        exit 1
        ;;
esac

# Execute the command
if [ "$ACTION_TYPE" = "list-statuses" ]; then
    echo "📊 Listing available statuses..."
elif [ "$ACTION_TYPE" = "status" ]; then
    echo "🔄 Updating status for ticket $TICKET_ID"
    echo "📊 New Status: $COMMENT_TEXT"
    echo "👤 Author: $AUTHOR"
elif [ "$ACTION_TYPE" = "status-with-comment" ]; then
    echo "🔄 Updating status and adding comment for ticket $TICKET_ID"
    echo "📊 New Status: $STATUS"
    echo "📝 Comment: $COMMENT"
    echo "👤 Author: $AUTHOR"
else
    echo "🎯 Adding $ACTION_TYPE to ticket $TICKET_ID"
    echo "📝 Comment: $COMMENT_TEXT"
    echo "👤 Author: $AUTHOR"
fi
echo ""

eval $CMD 