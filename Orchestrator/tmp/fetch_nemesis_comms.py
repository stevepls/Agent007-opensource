#!/usr/bin/env python3
"""
Fetch Nemesis/Rob communications from Zendesk and Gmail
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# ============================================================================
# ZENDESK TICKETS
# ============================================================================

def fetch_zendesk_tickets():
    """Fetch Zendesk tickets related to Nemesis/Rob."""
    print("=" * 70)
    print("FETCHING ZENDESK TICKETS")
    print("=" * 70)
    
    from services.tickets.zendesk_client import get_zendesk_client, ZendeskTicket
    
    client = get_zendesk_client()
    
    if not client.is_available:
        print("ERROR: Zendesk not configured")
        return []
    
    print(f"Zendesk subdomain: {client._subdomain}")
    print("Testing connection...")
    
    if not client.test_connection():
        print("ERROR: Failed to connect to Zendesk")
        return []
    
    print("✓ Connected to Zendesk\n")
    
    # Search for Nemesis tickets
    all_tickets = []
    
    # Search queries
    queries = [
        "nemesis",
        "nem-ind",
        "rob@nem-ind.com",
        "nemesis industries",
    ]
    
    for query in queries:
        print(f"Searching: {query}")
        try:
            tickets = client.search_tickets(query=query, limit=50)
            print(f"  Found {len(tickets)} tickets")
            for t in tickets:
                if t.id not in [x.id for x in all_tickets]:
                    all_tickets.append(t)
        except Exception as e:
            print(f"  Error: {e}")
    
    print(f"\nTotal unique tickets: {len(all_tickets)}")
    
    # Get details for each ticket
    ticket_data = []
    for ticket in all_tickets:
        print(f"\n--- Ticket #{ticket.id}: {ticket.subject[:60]} ---")
        print(f"Status: {ticket.status}, Priority: {ticket.priority}")
        print(f"Created: {ticket.created_at}, Updated: {ticket.updated_at}")
        print(f"Tags: {', '.join(ticket.tags)}")
        
        # Get comments
        try:
            comments = client.get_ticket_comments(ticket.id)
            print(f"Comments: {len(comments)}")
        except Exception as e:
            comments = []
            print(f"Comments error: {e}")
        
        ticket_data.append({
            'id': ticket.id,
            'subject': ticket.subject,
            'description': ticket.description[:500] if ticket.description else '',
            'status': ticket.status,
            'priority': ticket.priority,
            'tags': ticket.tags,
            'created_at': ticket.created_at.isoformat(),
            'updated_at': ticket.updated_at.isoformat(),
            'url': ticket.url,
            'comment_count': len(comments),
        })
    
    return ticket_data


# ============================================================================
# GMAIL MESSAGES
# ============================================================================

def fetch_gmail_messages():
    """Fetch Gmail messages related to Nemesis/Rob."""
    print("\n" + "=" * 70)
    print("FETCHING GMAIL MESSAGES")
    print("=" * 70)
    
    # Use unified token for Gmail
    os.environ["GOOGLE_CONFIG_DIR"] = os.path.expanduser("~/.config/agent007/google")
    
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import base64
    
    UNIFIED_TOKEN = Path(os.path.expanduser("~/.config/agent007/google/unified_token.json"))
    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
    ]
    
    if not UNIFIED_TOKEN.exists():
        print("ERROR: No unified token found")
        return []
    
    # Load credentials
    creds = Credentials.from_authorized_user_file(str(UNIFIED_TOKEN), SCOPES)
    
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    
    service = build('gmail', 'v1', credentials=creds)
    print("✓ Connected to Gmail\n")
    
    all_messages = []
    
    # Search queries
    queries = [
        "from:rob@nem-ind.com",
        "to:rob@nem-ind.com",
        "from:nemesis",
        "subject:nemesis",
        "from:rob nemesis",
    ]
    
    for query in queries:
        print(f"Searching: {query}")
        try:
            results = service.users().messages().list(
                userId='me',
                q=query,
                maxResults=50,
            ).execute()
            
            messages = results.get('messages', [])
            print(f"  Found {len(messages)} messages")
            
            for msg_ref in messages:
                if msg_ref['id'] not in [m['id'] for m in all_messages]:
                    # Get full message
                    msg = service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='metadata',
                        metadataHeaders=['From', 'To', 'Subject', 'Date'],
                    ).execute()
                    
                    headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
                    
                    all_messages.append({
                        'id': msg['id'],
                        'thread_id': msg['threadId'],
                        'from': headers.get('From', ''),
                        'to': headers.get('To', ''),
                        'subject': headers.get('Subject', ''),
                        'date': headers.get('Date', ''),
                        'snippet': msg.get('snippet', ''),
                        'labels': msg.get('labelIds', []),
                    })
        except Exception as e:
            print(f"  Error: {e}")
    
    print(f"\nTotal unique messages: {len(all_messages)}")
    
    # Show recent messages
    for msg in sorted(all_messages, key=lambda x: x['date'], reverse=True)[:20]:
        print(f"\n--- {msg['date'][:30]} ---")
        print(f"From: {msg['from'][:50]}")
        print(f"Subject: {msg['subject'][:60]}")
        print(f"Snippet: {msg['snippet'][:100]}...")
    
    return all_messages


# ============================================================================
# MAIN
# ============================================================================

def main():
    output = {
        'exported_at': datetime.now().isoformat(),
        'zendesk_tickets': [],
        'gmail_messages': [],
    }
    
    try:
        output['zendesk_tickets'] = fetch_zendesk_tickets()
    except Exception as e:
        print(f"Zendesk error: {e}")
    
    try:
        output['gmail_messages'] = fetch_gmail_messages()
    except Exception as e:
        print(f"Gmail error: {e}")
    
    # Save to file
    output_file = Path('/home/steve/Agent007/DevOps/client-projects/nemesis/communications_export.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\n{'=' * 70}")
    print(f"EXPORT COMPLETE")
    print(f"{'=' * 70}")
    print(f"Zendesk tickets: {len(output['zendesk_tickets'])}")
    print(f"Gmail messages: {len(output['gmail_messages'])}")
    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
