#!/bin/bash

# Integrated Ticket Manager with Airtable + Harvest
# 
# This script provides a unified interface for managing tickets with both
# Airtable comments/status updates and Harvest time tracking.
#
# Usage examples:
#   ./ticket_manager.sh 4962 start "Working on payment plan update"
#   ./ticket_manager.sh 4962 work-summary "Updated database schema"
#   ./ticket_manager.sh 4962 complete "All work finished and tested"
#   ./ticket_manager.sh 4962 stop
#   ./ticket_manager.sh 4962 log-time 2.5 "Database updates and testing"

# Check if we have the minimum required arguments
if [ $# -lt 2 ]; then
    echo "❌ Error: Not enough arguments"
    echo ""
    echo "Usage: $0 <ticket_id> <action> [args...] [author]"
    echo ""
    echo "Actions:"
    echo "  Time Tracking:"
    echo "    start <notes>                    - Start Harvest timer"
    echo "    stop                            - Stop Harvest timer"
    echo "    log-time <hours> <notes>        - Log completed time"
    echo ""
    echo "  Airtable Comments:"
    echo "    comment <text>                  - Add generic comment"
    echo "    work-summary <text>             - Add work completion summary"
    echo "    status-update <text>            - Add status update comment"
    echo "    technical-note <text>           - Add technical details"
    echo "    database-change <text>          - Document database changes"
    echo "    verification <text>             - Add verification info"
    echo ""
    echo "  Status Management:"
    echo "    status <status>                 - Update ticket status"
    echo "    complete <summary>              - Mark complete with summary"
    echo "    in-progress                     - Mark as in progress"
    echo ""
    echo "  Information:"
    echo "    list-statuses                   - Show available statuses"
    echo "    list-projects                   - Show Harvest projects"
    echo "    list-tasks                      - Show Harvest tasks"
    echo ""
    echo "Examples:"
    echo "  $0 4962 start 'Working on payment plan update'"
    echo "  $0 4962 work-summary 'Updated payment dates'"
    echo "  $0 4962 complete 'All work finished and tested'"
    echo "  $0 4962 log-time 2.5 'Database updates and testing'"
    exit 1
fi

TICKET_ID="$1"
ACTION="$2"

# Set up environment
cd "$(dirname "$0")"
source src/venv/bin/activate 2>/dev/null || {
    echo "❌ Error: Could not activate virtual environment"
    echo "Make sure you're in the airtable-fetcher directory and venv exists"
    exit 1
}

# Export environment variables for both Airtable and Harvest
export AIRTABLE_PERSONAL_ACCESS_TOKEN=REDACTED_AIRTABLE_TOKEN
export AIRTABLE_BASE_ID=REDACTED_BASE_ID
export AIRTABLE_TABLE_ID=REDACTED_TABLE_ID
export HARVEST_ACCESS_TOKEN=REDACTED_HARVEST_TOKEN
export HARVEST_ACCOUNT_ID=REDACTED_ACCOUNT_ID

# Helper function to execute commands with proper error handling
execute_command() {
    local cmd="$1"
    local success_msg="$2"
    local error_msg="$3"
    
    echo "🔄 Executing: $cmd"
    if eval "$cmd"; then
        echo "✅ $success_msg"
        return 0
    else
        echo "❌ $error_msg"
        return 1
    fi
}

# Build the command based on action type
case "$ACTION" in
    # Time tracking actions
    "start")
        if [ $# -lt 3 ]; then
            echo "❌ Error: Notes required for start action"
            echo "Usage: $0 $TICKET_ID start '<notes>'"
            exit 1
        fi
        NOTES="$3"
        echo "⏱️ Starting timer for ticket #$TICKET_ID"
        echo "📝 Notes: $NOTES"
        echo ""
        
        # Start Harvest timer
        CMD="python harvest_integration.py --ticket $TICKET_ID --start \"$NOTES\""
        execute_command "$CMD" "Timer started successfully" "Failed to start timer"
        
        # Add status update to Airtable
        if [ $? -eq 0 ]; then
            echo ""
            echo "📋 Updating Airtable status..."
            AIRTABLE_CMD="python add_comment.py --ticket $TICKET_ID --status-with-comment \"In Progress - Small\" \"Started working: $NOTES\" --author \"AI Assistant\""
            execute_command "$AIRTABLE_CMD" "Airtable updated" "Failed to update Airtable"
        fi
        ;;
        
    "stop")
        echo "⏹️ Stopping timer for ticket #$TICKET_ID"
        echo ""
        
        # Stop Harvest timer
        CMD="python harvest_integration.py --ticket $TICKET_ID --stop"
        execute_command "$CMD" "Timer stopped successfully" "Failed to stop timer"
        ;;
        
    "log-time")
        if [ $# -lt 4 ]; then
            echo "❌ Error: Hours and notes required for log-time action"
            echo "Usage: $0 $TICKET_ID log-time <hours> '<notes>'"
            exit 1
        fi
        HOURS="$3"
        NOTES="$4"
        echo "📊 Logging $HOURS hours for ticket #$TICKET_ID"
        echo "📝 Notes: $NOTES"
        echo ""
        
        # Log time to Harvest
        CMD="python harvest_integration.py --ticket $TICKET_ID --log-time $HOURS --notes \"$NOTES\""
        execute_command "$CMD" "Time logged successfully" "Failed to log time"
        ;;
        
    # Airtable comment actions
    "comment"|"work-summary"|"status-update"|"technical-note"|"database-change"|"verification")
        if [ $# -lt 3 ]; then
            echo "❌ Error: Text required for $ACTION"
            echo "Usage: $0 $TICKET_ID $ACTION '<text>'"
            exit 1
        fi
        TEXT="$3"
        AUTHOR="${4:-AI Assistant}"
        
        echo "📝 Adding $ACTION to ticket #$TICKET_ID"
        echo "💬 Text: $TEXT"
        echo "👤 Author: $AUTHOR"
        echo ""
        
        CMD="python add_comment.py --ticket $TICKET_ID --$ACTION \"$TEXT\" --author \"$AUTHOR\""
        execute_command "$CMD" "Comment added successfully" "Failed to add comment"
        ;;
        
    # Status management actions
    "status")
        if [ $# -lt 3 ]; then
            echo "❌ Error: Status required"
            echo "Usage: $0 $TICKET_ID status '<status>'"
            exit 1
        fi
        STATUS="$3"
        AUTHOR="${4:-AI Assistant}"
        
        echo "🔄 Updating ticket #$TICKET_ID status to: $STATUS"
        echo "👤 Author: $AUTHOR"
        echo ""
        
        CMD="python add_comment.py --ticket $TICKET_ID --update-status \"$STATUS\" --author \"$AUTHOR\""
        execute_command "$CMD" "Status updated successfully" "Failed to update status"
        ;;
        
    "complete")
        if [ $# -lt 3 ]; then
            echo "❌ Error: Summary required for complete action"
            echo "Usage: $0 $TICKET_ID complete '<summary>'"
            exit 1
        fi
        SUMMARY="$3"
        AUTHOR="${4:-AI Assistant}"
        
        echo "✅ Marking ticket #$TICKET_ID as complete"
        echo "📝 Summary: $SUMMARY"
        echo "👤 Author: $AUTHOR"
        echo ""
        
        # Stop any running timer first
        echo "⏹️ Stopping any running timer..."
        python harvest_integration.py --ticket $TICKET_ID --stop 2>/dev/null
        
        # Update status and add completion comment
        CMD="python add_comment.py --ticket $TICKET_ID --status-with-comment \"Complete\" \"✅ COMPLETED: $SUMMARY\" --author \"$AUTHOR\""
        execute_command "$CMD" "Ticket marked as complete" "Failed to mark as complete"
        ;;
        
    "in-progress")
        AUTHOR="${3:-AI Assistant}"
        
        echo "🔄 Marking ticket #$TICKET_ID as in progress"
        echo "👤 Author: $AUTHOR"
        echo ""
        
        CMD="python add_comment.py --ticket $TICKET_ID --update-status \"In Progress - Small\" --author \"$AUTHOR\""
        execute_command "$CMD" "Status updated to in progress" "Failed to update status"
        ;;
        
    # Information actions
    "list-statuses")
        echo "📊 Available ticket statuses:"
        python add_comment.py --list-statuses
        ;;
        
    "list-projects")
        echo "📋 Available Harvest projects:"
        python harvest_integration.py --list-projects
        ;;
        
    "list-tasks")
        echo "📋 Available Harvest tasks:"
        python harvest_integration.py --list-tasks
        ;;
        
    *)
        echo "❌ Error: Unknown action '$ACTION'"
        echo ""
        echo "Valid actions:"
        echo "  Time: start, stop, log-time"
        echo "  Comments: comment, work-summary, status-update, technical-note, database-change, verification"
        echo "  Status: status, complete, in-progress"
        echo "  Info: list-statuses, list-projects, list-tasks"
        exit 1
        ;;
esac

echo ""
echo "🎉 Action completed for ticket #$TICKET_ID" 