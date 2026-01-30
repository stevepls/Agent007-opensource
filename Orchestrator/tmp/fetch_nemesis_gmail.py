#!/usr/bin/env python3
"""
Fetch Nemesis/Rob emails from Gmail.
Requires Gmail OAuth scopes - will prompt for authentication if needed.
"""

import os
import sys
import json
import base64
from pathlib import Path
from datetime import datetime

# Google API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Configuration
CONFIG_DIR = Path(os.path.expanduser("~/.config/agent007/google"))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
GMAIL_TOKEN_FILE = CONFIG_DIR / "gmail_token.json"

# Gmail scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
]


def get_gmail_service():
    """Authenticate and return Gmail service."""
    creds = None
    
    # Load existing token
    if GMAIL_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_FILE), SCOPES)
    
    # Refresh or get new token
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"ERROR: No credentials file at {CREDENTIALS_FILE}")
                print("Download OAuth credentials from Google Cloud Console.")
                sys.exit(1)
            
            print("Starting OAuth flow for Gmail...")
            print("A browser window will open for authentication.")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            # Use port 8080 to match redirect_uri in credentials.json
            creds = flow.run_local_server(port=8080)
        
        # Save token
        with open(GMAIL_TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
        print(f"Token saved to {GMAIL_TOKEN_FILE}")
    
    return build('gmail', 'v1', credentials=creds)


def search_emails(service, query, max_results=50):
    """Search emails and return message details."""
    print(f"Searching: {query}")
    
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results,
        ).execute()
        
        messages = results.get('messages', [])
        print(f"  Found {len(messages)} messages")
        
        detailed_messages = []
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId='me',
                id=msg_ref['id'],
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'Date'],
            ).execute()
            
            headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
            
            detailed_messages.append({
                'id': msg['id'],
                'thread_id': msg['threadId'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'snippet': msg.get('snippet', ''),
                'labels': msg.get('labelIds', []),
            })
        
        return detailed_messages
    
    except Exception as e:
        print(f"  Error: {e}")
        return []


def main():
    print("=" * 70)
    print("FETCHING NEMESIS/ROB GMAIL MESSAGES")
    print("=" * 70)
    
    service = get_gmail_service()
    print("✓ Connected to Gmail\n")
    
    all_messages = []
    seen_ids = set()
    
    # Search queries for Nemesis/Rob
    queries = [
        "from:rob@nem-ind.com",
        "to:rob@nem-ind.com",
        "from:rob.g@nem-ind.com",
        "to:rob.g@nem-ind.com",
        "subject:nemesis",
        "(nemesis OR nem-ind) in:anywhere",
    ]
    
    for query in queries:
        messages = search_emails(service, query)
        for msg in messages:
            if msg['id'] not in seen_ids:
                seen_ids.add(msg['id'])
                all_messages.append(msg)
    
    print(f"\n{'=' * 70}")
    print(f"Total unique messages: {len(all_messages)}")
    print("=" * 70)
    
    # Sort by date (newest first)
    all_messages.sort(key=lambda x: x['date'], reverse=True)
    
    # Show recent messages
    print("\nMost Recent Messages:")
    print("-" * 70)
    for msg in all_messages[:30]:
        print(f"\n📧 {msg['date'][:40]}")
        print(f"   From: {msg['from'][:60]}")
        print(f"   Subject: {msg['subject'][:70]}")
        print(f"   Preview: {msg['snippet'][:100]}...")
    
    # Categorize by year
    print("\n" + "=" * 70)
    print("MESSAGES BY YEAR")
    print("=" * 70)
    
    by_year = {}
    for msg in all_messages:
        try:
            # Parse year from date string
            date_str = msg['date']
            for year in ['2026', '2025', '2024', '2023', '2022', '2021']:
                if year in date_str:
                    by_year.setdefault(year, []).append(msg)
                    break
        except:
            pass
    
    for year in sorted(by_year.keys(), reverse=True):
        print(f"\n{year}: {len(by_year[year])} emails")
    
    # Save to file
    output = {
        'exported_at': datetime.now().isoformat(),
        'total_messages': len(all_messages),
        'messages': all_messages,
    }
    
    output_file = Path('/home/steve/Agent007/DevOps/client-projects/nemesis/gmail_export.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\n✓ Exported {len(all_messages)} messages to {output_file}")


if __name__ == "__main__":
    main()
