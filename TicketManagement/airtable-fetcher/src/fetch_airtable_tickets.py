#!/usr/bin/env python3
"""
Airtable Ticket Fetcher

This script fetches tickets from Airtable and organizes them by creation date.
It can fetch all tickets assigned to a specific email or a single ticket by record ID.
It can also add comments to tickets.

Usage:
    python fetch_airtable_tickets.py [--record-id RECORD_ID] [--add-comment "comment text"]
    
Examples:
    # Fetch all tickets assigned to the configured email
    python fetch_airtable_tickets.py
    
    # Fetch a specific ticket by record ID
    python fetch_airtable_tickets.py --record-id recVBzsYw4DiwnRD2
    
    # Add a comment to a specific ticket
    python fetch_airtable_tickets.py --record-id recVBzsYw4DiwnRD2 --add-comment "Payment plan updated successfully"
"""

import os
import json
import requests
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

class AirtableTicketFetcher:
    def __init__(self, base_id, table_id, personal_access_token, assigned_email=None):
        self.base_id = base_id
        self.table_id = table_id
        self.personal_access_token = personal_access_token
        self.assigned_email = assigned_email
        self.base_url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        self.headers = {
            "Authorization": f"Bearer {personal_access_token}",
            "Content-Type": "application/json"
        }
        
    def update_ticket_status(self, ticket_id_or_record_id, new_status):
        """Update the status of a specific ticket"""
        # Convert ticket ID to record ID if needed
        if str(ticket_id_or_record_id).startswith('rec'):
            record_id = ticket_id_or_record_id
        else:
            record_id = self.get_record_id_from_ticket_id(ticket_id_or_record_id)
            if not record_id:
                return None
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}/{record_id}"
        
        # Valid status options based on observed data
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
        
        if new_status not in valid_statuses:
            print(f"❌ Error: Invalid status '{new_status}'")
            print(f"Valid statuses: {', '.join(valid_statuses)}")
            return None
        
        try:
            update_data = {
                "fields": {
                    "Ticket Status": new_status
                }
            }
            
            response = requests.patch(url, headers=self.headers, json=update_data)
            response.raise_for_status()
            
            print(f"✅ Successfully updated ticket {ticket_id_or_record_id} status to: {new_status}")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error updating ticket status {record_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
    
    def update_ticket_status_and_comment(self, ticket_id_or_record_id, new_status, comment_text, author="AI Assistant"):
        """Update ticket status and add a comment in one operation"""
        # Convert ticket ID to record ID if needed
        if str(ticket_id_or_record_id).startswith('rec'):
            record_id = ticket_id_or_record_id
        else:
            record_id = self.get_record_id_from_ticket_id(ticket_id_or_record_id)
            if not record_id:
                return None
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}/{record_id}"
        
        # Valid status options
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
        
        if new_status not in valid_statuses:
            print(f"❌ Error: Invalid status '{new_status}'")
            print(f"Valid statuses: {', '.join(valid_statuses)}")
            return None
        
        try:
            # First, get current record to append to comments
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            current_record = response.json()
            
            # Get current comments field
            fields = current_record.get('fields', {})
            
            # Try different possible comment field names
            comment_fields_to_try = ['Comments', 'Notes', 'Internal Notes', 'Status Comments', 'Work Notes', 'Description']
            
            # Try to determine which field exists by checking current fields
            comment_field = None
            current_comments = ''
            
            for field_name in comment_fields_to_try:
                if field_name in fields:
                    comment_field = field_name
                    current_comments = fields.get(field_name, '')
                    break
            
            if not comment_field:
                # Default to 'Description' since it exists in the schema
                comment_field = 'Description'
                current_comments = fields.get('Description', '')
            
            # Format new comment with timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            status_comment = f"[{timestamp}] {author}: 🔄 STATUS CHANGED TO: {new_status}"
            if comment_text:
                status_comment += f"\n[{timestamp}] {author}: {comment_text}"
            
            # Append to existing comments
            if current_comments:
                updated_comments = f"{current_comments}\n\n{status_comment}"
            else:
                updated_comments = status_comment
            
            # Update both status and comments
            update_data = {
                "fields": {
                    "Ticket Status": new_status,
                    comment_field: updated_comments
                }
            }
            
            update_response = requests.patch(url, headers=self.headers, json=update_data)
            update_response.raise_for_status()
            
            print(f"✅ Successfully updated ticket {ticket_id_or_record_id}")
            print(f"📊 Status changed to: {new_status}")
            print(f"📝 Comment added: {comment_text}")
            print(f"📍 Field used: {comment_field}")
            
            return update_response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error updating ticket {record_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
    
    def add_comment_to_ticket(self, ticket_id_or_record_id, comment_text, author="AI Assistant"):
        """Add a comment to a specific ticket"""
        # Convert ticket ID to record ID if needed
        if str(ticket_id_or_record_id).startswith('rec'):
            record_id = ticket_id_or_record_id
        else:
            record_id = self.get_record_id_from_ticket_id(ticket_id_or_record_id)
            if not record_id:
                return None
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}/{record_id}"
        
        # First, get the current ticket to see existing comments
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            current_record = response.json()
            
            # Get current comments field (might be named differently)
            fields = current_record.get('fields', {})
            
            # Try different possible comment field names based on what we found
            comment_fields_to_try = ['Comments', 'Notes', 'Internal Notes', 'Status Comments', 'Work Notes', 'Description']
            
            # Try to determine which field exists by checking current fields
            comment_field = None
            current_comments = ''
            
            for field_name in comment_fields_to_try:
                if field_name in fields:
                    comment_field = field_name
                    current_comments = fields.get(field_name, '')
                    break
            
            if not comment_field:
                # Default to 'Description' since it exists in the schema
                comment_field = 'Description'
                current_comments = fields.get('Description', '')
            
            # Format new comment with timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_comment = f"[{timestamp}] {author}: {comment_text}"
            
            # Append to existing comments
            if current_comments:
                updated_comments = f"{current_comments}\n\n{new_comment}"
            else:
                updated_comments = new_comment
            
            # Update the record
            update_data = {"fields": {}}
            
            update_data["fields"][comment_field] = updated_comments
            
            # Send update request
            update_response = requests.patch(url, headers=self.headers, json=update_data)
            update_response.raise_for_status()
            
            print(f"✅ Successfully added comment to ticket {ticket_id_or_record_id}")
            print(f"📝 Comment: {comment_text}")
            print(f"📍 Field used: {comment_field}")
            
            return update_response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error adding comment to ticket {record_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
    
    def get_available_fields(self, record_id):
        """Get all available fields for a ticket to help identify comment fields"""
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}/{record_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            record = response.json()
            fields = record.get('fields', {})
            
            print(f"📋 Available fields for ticket {record_id}:")
            for field_name, field_value in fields.items():
                field_type = type(field_value).__name__
                print(f"  - {field_name}: {field_type}")
            
            return list(fields.keys())
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching fields for ticket {record_id}: {e}")
            return []
        
    def get_record_id_from_ticket_id(self, ticket_id):
        """Get record ID from numeric ticket ID"""
        try:
            # Search for ticket with matching ID field
            params = {
                'filterByFormula': f"{{ID}} = {ticket_id}",
                'maxRecords': 1
            }
            
            response = requests.get(self.base_url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('records', [])
            
            if not records:
                print(f"❌ No ticket found with ID: {ticket_id}")
                return None
                
            record_id = records[0].get('id')
            print(f"✅ Found ticket {ticket_id} -> record {record_id}")
            return record_id
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error finding ticket {ticket_id}: {e}")
            return None
    
    def fetch_single_ticket(self, ticket_id_or_record_id):
        """Fetch a single ticket by ticket ID (numeric) or record ID (recXXX)"""
        # Check if it's a numeric ticket ID or record ID
        if str(ticket_id_or_record_id).startswith('rec'):
            # It's a record ID, use directly
            record_id = ticket_id_or_record_id
        else:
            # It's a numeric ticket ID, convert to record ID
            record_id = self.get_record_id_from_ticket_id(ticket_id_or_record_id)
            if not record_id:
                return []
        
        url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}/{record_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            record = response.json()
            ticket_id = record.get('fields', {}).get('ID', 'Unknown')
            print(f"✅ Successfully fetched ticket: {ticket_id} (record: {record_id})")
            return [record]  # Return as list for consistency with fetch_all_tickets
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching ticket {record_id}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return []
    
    def fetch_all_tickets(self):
        """Fetch all tickets from Airtable"""
        all_records = []
        offset = None
        
        while True:
            params = {
                'pageSize': 100,
            }
            if offset:
                params['offset'] = offset
                
            try:
                response = requests.get(self.base_url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                records = data.get('records', [])
                all_records.extend(records)
                
                print(f"📥 Fetched {len(records)} tickets (Total: {len(all_records)})")
                
                offset = data.get('offset')
                if not offset:
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Error fetching tickets: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response: {e.response.text}")
                break
        
        print(f"✅ Total tickets fetched: {len(all_records)}")
        return all_records
    
    def filter_tickets_by_email(self, records):
        """Filter tickets assigned to the specified email"""
        if not self.assigned_email:
            return records
            
        filtered_tickets = []
        
        for record in records:
            fields = record.get('fields', {})
            assigned_to = fields.get('Assigned To', [])
            
            # Check if any of the assigned users has the target email
            for assignee in assigned_to:
                if isinstance(assignee, dict) and assignee.get('email') == self.assigned_email:
                    filtered_tickets.append(record)
                    break
        
        print(f"📧 Filtered to {len(filtered_tickets)} tickets assigned to {self.assigned_email}")
        return filtered_tickets
    
    def organize_tickets_by_date(self, tickets):
        """Organize tickets by creation date and save them"""
        output_dir = Path("output/airtable-tickets")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        date_folders = {}
        
        for ticket in tickets:
            # Extract creation date
            created_time = ticket.get('createdTime', '')
            if created_time:
                date_obj = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                date_str = date_obj.strftime('%Y-%m-%d')
            else:
                date_str = 'unknown-date'
            
            # Create date folder
            date_folder = output_dir / date_str
            date_folder.mkdir(exist_ok=True)
            
            if date_str not in date_folders:
                date_folders[date_str] = []
            date_folders[date_str].append(ticket)
            
            # Generate filename
            record_id = ticket.get('id', 'unknown')
            ticket_name = ticket.get('fields', {}).get('Ticket Name', 'Untitled')
            # Clean filename
            safe_name = "".join(c for c in ticket_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_name = safe_name.replace(' ', ' ')[:50]  # Limit length
            filename = f"{record_id}_{safe_name}"
            
            # Save as JSON
            json_file = date_folder / f"{filename}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(ticket, f, indent=2, ensure_ascii=False)
            
            # Save as readable text
            txt_file = date_folder / f"{filename}.txt"
            with open(txt_file, 'w', encoding='utf-8') as f:
                fields = ticket.get('fields', {})
                f.write(f"Ticket ID: {record_id}\n")
                f.write(f"Title: {fields.get('Ticket Name', 'N/A')}\n")
                f.write(f"Status: {fields.get('Ticket Status', 'N/A')}\n")
                f.write(f"Priority: {fields.get('Priority', 'N/A')}\n")
                f.write(f"Created: {created_time}\n")
                
                # Assigned To
                assigned_to = fields.get('Assigned To', [])
                if assigned_to:
                    f.write("Assigned To:\n")
                    for assignee in assigned_to:
                        if isinstance(assignee, dict):
                            name = assignee.get('name', 'Unknown')
                            email = assignee.get('email', 'Unknown')
                            f.write(f"  - {name} ({email})\n")
                
                f.write(f"\nDescription:\n{fields.get('Issue Description', 'No description')}\n")
        
        return date_folders
    
    def generate_summary(self, date_folders, total_fetched, mode="all"):
        """Generate a summary report"""
        summary_file = Path("output/airtable-tickets/SUMMARY.md")
        
        with open(summary_file, 'w') as f:
            f.write("# Airtable Tickets Summary\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if mode == "single":
                f.write(f"**Mode:** Single ticket fetch\n")
            else:
                f.write(f"**Total Tickets Fetched:** {total_fetched}\n")
                if self.assigned_email:
                    f.write(f"**Filtered for:** {self.assigned_email}\n")
                f.write(f"**Tickets After Filtering:** {sum(len(tickets) for tickets in date_folders.values())}\n")
            f.write(f"**Date Folders Created:** {len(date_folders)}\n\n")
            
            f.write("## Tickets by Date\n\n")
            for date_str in sorted(date_folders.keys(), reverse=True):
                tickets = date_folders[date_str]
                f.write(f"### {date_str} ({len(tickets)} tickets)\n\n")
                for ticket in tickets:
                    fields = ticket.get('fields', {})
                    title = fields.get('Ticket Name', 'Untitled')
                    status = fields.get('Ticket Status', 'Unknown')
                    record_id = ticket.get('id', 'unknown')
                    f.write(f"- **{title}** (Status: {status}) - `{record_id}`\n")
                f.write("\n")
        
        print(f"📋 Summary saved to: {summary_file}")

def main():
    parser = argparse.ArgumentParser(description='Fetch Airtable tickets and manage comments')
    parser.add_argument('--record-id', help='Fetch a specific ticket by record ID')
    parser.add_argument('--add-comment', help='Add a comment to the specified ticket')
    parser.add_argument('--update-status', help='Update ticket status')
    parser.add_argument('--status-with-comment', nargs=2, metavar=('STATUS', 'COMMENT'), help='Update status and add comment')
    parser.add_argument('--list-fields', action='store_true', help='List available fields for the specified ticket')
    parser.add_argument('--list-statuses', action='store_true', help='List available status options')
    parser.add_argument('--author', default='AI Assistant', help='Author name for comments (default: AI Assistant)')
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Configuration
    BASE_ID = os.getenv('AIRTABLE_BASE_ID', 'REDACTED_BASE_ID')
    TABLE_ID = os.getenv('AIRTABLE_TABLE_ID', 'REDACTED_TABLE_ID')
    PERSONAL_ACCESS_TOKEN = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
    ASSIGNED_EMAIL = os.getenv('ASSIGNED_EMAIL', 'cw-testing@theforgelab.com')
    
    if not PERSONAL_ACCESS_TOKEN:
        print("❌ Error: AIRTABLE_PERSONAL_ACCESS_TOKEN not found in environment variables")
        print("Please check your credentials.env file")
        return
    
    # Initialize fetcher
    fetcher = AirtableTicketFetcher(BASE_ID, TABLE_ID, PERSONAL_ACCESS_TOKEN, ASSIGNED_EMAIL)
    
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
    
    # Handle status update with comment
    if args.status_with_comment and args.record_id:
        status, comment = args.status_with_comment
        print(f"🔄 Updating ticket {args.record_id} status to: {status}")
        result = fetcher.update_ticket_status_and_comment(args.record_id, status, comment, args.author)
        if result:
            print("✅ Status and comment updated successfully!")
        return
    
    # Handle status update only
    if args.update_status and args.record_id:
        print(f"🔄 Updating ticket {args.record_id} status to: {args.update_status}")
        result = fetcher.update_ticket_status(args.record_id, args.update_status)
        if result:
            print("✅ Status updated successfully!")
        return
    
    # Handle comment addition
    if args.add_comment and args.record_id:
        print(f"💬 Adding comment to ticket: {args.record_id}")
        result = fetcher.add_comment_to_ticket(args.record_id, args.add_comment, args.author)
        if result:
            print("✅ Comment added successfully!")
        return
    
    # Handle field listing
    if args.list_fields and args.record_id:
        print(f"📋 Listing fields for ticket: {args.record_id}")
        fetcher.get_available_fields(args.record_id)
        return
    
    if args.record_id:
        # Fetch single ticket
        print(f"🎯 Fetching single ticket: {args.record_id}")
        tickets = fetcher.fetch_single_ticket(args.record_id)
        mode = "single"
        total_fetched = 1 if tickets else 0
    else:
        # Fetch all tickets and filter
        print(f"🚀 Starting Airtable ticket fetch...")
        print(f"📧 Target email: {ASSIGNED_EMAIL}")
        
        all_tickets = fetcher.fetch_all_tickets()
        tickets = fetcher.filter_tickets_by_email(all_tickets)
        mode = "all"
        total_fetched = len(all_tickets)
    
    if not tickets:
        print("❌ No tickets found")
        return
    
    # Organize and save tickets
    print(f"📁 Organizing {len(tickets)} tickets by date...")
    date_folders = fetcher.organize_tickets_by_date(tickets)
    
    # Generate summary
    fetcher.generate_summary(date_folders, total_fetched, mode)
    
    print(f"✅ Process completed! Check the 'output/airtable-tickets' directory")
    print(f"📊 Organized into {len(date_folders)} date folders")

if __name__ == "__main__":
    main() 