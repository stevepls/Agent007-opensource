#!/usr/bin/env python3
"""
Airtable Comment Helper

A convenient wrapper for adding comments to Airtable tickets.
This script provides easy-to-use functions for common comment scenarios.

Usage:
    python add_comment.py --ticket TICKET_ID --comment "Your comment"
    python add_comment.py --ticket TICKET_ID --status-update "Completed: Payment plan updated"
    python add_comment.py --ticket TICKET_ID --work-summary "Updated payment dates from monthly to bi-annual"
"""

import argparse
import sys
from pathlib import Path
import os

# Add the src directory to the path so we can import our main fetcher
sys.path.append(str(Path(__file__).parent / "src"))

from fetch_airtable_tickets import AirtableTicketFetcher
from dotenv import load_dotenv

class AirtableCommentHelper:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Configuration
        self.base_id = os.getenv('AIRTABLE_BASE_ID', 'app37XFdl4xoMbvx3')
        self.table_id = os.getenv('AIRTABLE_TABLE_ID', 'tblFXfLF3tGjW9IXm')
        self.personal_access_token = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
        
        if not self.personal_access_token:
            print("❌ Error: AIRTABLE_PERSONAL_ACCESS_TOKEN not found in environment variables")
            sys.exit(1)
        
        # Initialize fetcher
        self.fetcher = AirtableTicketFetcher(
            self.base_id, 
            self.table_id, 
            self.personal_access_token
        )
    
    def add_status_update(self, ticket_id, status_message, author="AI Assistant"):
        """Add a status update comment"""
        comment = f"🔄 STATUS UPDATE: {status_message}"
        return self.fetcher.add_comment_to_ticket(ticket_id, comment, author)
    
    def add_work_summary(self, ticket_id, work_description, author="AI Assistant"):
        """Add a work completion summary"""
        comment = f"✅ WORK COMPLETED: {work_description}"
        return self.fetcher.add_comment_to_ticket(ticket_id, comment, author)
    
    def add_technical_note(self, ticket_id, technical_details, author="AI Assistant"):
        """Add technical implementation details"""
        comment = f"🔧 TECHNICAL DETAILS: {technical_details}"
        return self.fetcher.add_comment_to_ticket(ticket_id, comment, author)
    
    def add_database_change(self, ticket_id, db_changes, author="AI Assistant"):
        """Add database change documentation"""
        comment = f"🗄️ DATABASE CHANGES: {db_changes}"
        return self.fetcher.add_comment_to_ticket(ticket_id, comment, author)
    
    def add_verification_note(self, ticket_id, verification_info, author="AI Assistant"):
        """Add verification/testing information"""
        comment = f"✔️ VERIFICATION: {verification_info}"
        return self.fetcher.add_comment_to_ticket(ticket_id, verification_info, author)
    
    def add_generic_comment(self, ticket_id, comment_text, author="AI Assistant"):
        """Add a generic comment"""
        return self.fetcher.add_comment_to_ticket(ticket_id, comment_text, author)
    
    def update_status(self, ticket_id, new_status, author="AI Assistant"):
        """Update ticket status only"""
        return self.fetcher.update_ticket_status(ticket_id, new_status)
    
    def update_status_with_comment(self, ticket_id, new_status, comment_text, author="AI Assistant"):
        """Update ticket status and add comment"""
        return self.fetcher.update_ticket_status_and_comment(ticket_id, new_status, comment_text, author)

def main():
    parser = argparse.ArgumentParser(description='Add comments to Airtable tickets')
    parser.add_argument('--ticket', help='Ticket record ID (e.g., recVBzsYw4DiwnRD2)')
    parser.add_argument('--comment', help='Generic comment text')
    parser.add_argument('--status-update', help='Status update message')
    parser.add_argument('--work-summary', help='Work completion summary')
    parser.add_argument('--technical-note', help='Technical implementation details')
    parser.add_argument('--database-change', help='Database change documentation')
    parser.add_argument('--verification', help='Verification/testing information')
    parser.add_argument('--update-status', help='Update ticket status')
    parser.add_argument('--status-with-comment', nargs=2, metavar=('STATUS', 'COMMENT'), help='Update status and add comment')
    parser.add_argument('--author', default='AI Assistant', help='Author name for the comment')
    parser.add_argument('--list-fields', action='store_true', help='List available fields for the ticket')
    parser.add_argument('--list-statuses', action='store_true', help='List available status options')
    
    args = parser.parse_args()
    
    # Initialize helper
    helper = AirtableCommentHelper()
    
    # Handle status listing
    if args.list_statuses:
        print("📊 Available ticket statuses:")
        valid_statuses = [
            "Assigned - Small",
            "Assigned - Large", 
            "In Progress - Small",
            "In Progress - Large",
            "Done (Needs Review)",
            "Complete",
            "Waiting on Details from CW",
            "On Hold",
            "Backlog - Small",
            "Backlog - Large"
        ]
        for i, status in enumerate(valid_statuses, 1):
            print(f"  {i:2d}. {status}")
        return
    
    # Handle field listing
    if args.list_fields:
        if not args.ticket:
            print("❌ Error: --ticket is required for --list-fields")
            return
        print(f"📋 Listing fields for ticket: {args.ticket}")
        helper.fetcher.get_available_fields(args.ticket)
        return
    
    # Handle status updates first
    if args.status_with_comment:
        if not args.ticket:
            print("❌ Error: --ticket is required for --status-with-comment")
            return
        status, comment = args.status_with_comment
        print(f"🔄 Updating ticket {args.ticket} status to: {status}")
        result = helper.update_status_with_comment(args.ticket, status, comment, args.author)
        if result:
            print("🎉 Status and comment updated successfully!")
        else:
            print("❌ Failed to update status and comment")
        return
    
    if args.update_status:
        if not args.ticket:
            print("❌ Error: --ticket is required for --update-status")
            return
        print(f"🔄 Updating ticket {args.ticket} status to: {args.update_status}")
        result = helper.update_status(args.ticket, args.update_status, args.author)
        if result:
            print("🎉 Status updated successfully!")
        else:
            print("❌ Failed to update status")
        return
    
    # Determine which type of comment to add
    result = None
    
    if args.status_update:
        print(f"🔄 Adding status update to ticket {args.ticket}")
        result = helper.add_status_update(args.ticket, args.status_update, args.author)
    elif args.work_summary:
        print(f"✅ Adding work summary to ticket {args.ticket}")
        result = helper.add_work_summary(args.ticket, args.work_summary, args.author)
    elif args.technical_note:
        print(f"🔧 Adding technical note to ticket {args.ticket}")
        result = helper.add_technical_note(args.ticket, args.technical_note, args.author)
    elif args.database_change:
        print(f"🗄️ Adding database change note to ticket {args.ticket}")
        result = helper.add_database_change(args.ticket, args.database_change, args.author)
    elif args.verification:
        print(f"✔️ Adding verification note to ticket {args.ticket}")
        result = helper.add_verification_note(args.ticket, args.verification, args.author)
    elif args.comment:
        print(f"💬 Adding comment to ticket {args.ticket}")
        result = helper.add_generic_comment(args.ticket, args.comment, args.author)
    else:
        print("❌ Error: Please specify a comment type (--comment, --status-update, --work-summary, etc.)")
        parser.print_help()
        return
    
    if result:
        print("🎉 Comment added successfully!")
    else:
        print("❌ Failed to add comment")

if __name__ == "__main__":
    main() 