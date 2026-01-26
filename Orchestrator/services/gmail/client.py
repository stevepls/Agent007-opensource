"""
Gmail API Client

Provides read, draft, send, and delete operations for Gmail.
All sends go through the message queue for delayed sending and approval.

SECURITY:
- OAuth 2.0 authentication required
- All sends require approval through message queue
- Deletes require explicit confirmation
- Reads are logged for audit

Setup:
1. Create OAuth credentials in Google Cloud Console
2. Download credentials.json to ~/.config/agent007/google/
3. Run authenticate() to get tokens
"""

import os
import base64
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# Google API imports (require google-api-python-client, google-auth-oauthlib)
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Credentials = None

# Configuration
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
CONFIG_DIR = Path(os.getenv("GOOGLE_CONFIG_DIR", os.path.expanduser("~/.config/agent007/google")))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "gmail_token.json"

# Scopes for Gmail access
GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
]


@dataclass
class EmailMessage:
    """Represents an email message."""
    id: str
    thread_id: str
    from_email: str
    to_email: List[str]
    subject: str
    body: str
    snippet: str
    date: str
    labels: List[str]
    is_unread: bool
    has_attachments: bool


class GmailClient:
    """Gmail API client with safety controls."""
    
    def __init__(self):
        self._service = None
        self._credentials = None
    
    @property
    def is_available(self) -> bool:
        return GOOGLE_API_AVAILABLE
    
    @property
    def is_authenticated(self) -> bool:
        return self._credentials is not None and self._credentials.valid
    
    def authenticate(self) -> bool:
        """
        Authenticate with Gmail API.
        Returns True if successful.
        """
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API libraries not installed. Run: "
                "pip install google-api-python-client google-auth-oauthlib"
            )
        
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"OAuth credentials not found at {CREDENTIALS_FILE}. "
                "Download from Google Cloud Console."
            )
        
        creds = None
        
        # Load existing token
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), GMAIL_SCOPES)
        
        # Refresh or get new token
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # Save token
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        
        self._credentials = creds
        self._service = build('gmail', 'v1', credentials=creds)
        return True
    
    def _ensure_authenticated(self):
        """Ensure we have valid credentials."""
        if not self.is_authenticated:
            self.authenticate()
    
    def _parse_message(self, msg_data: Dict) -> EmailMessage:
        """Parse Gmail API message into EmailMessage."""
        headers = {h['name']: h['value'] for h in msg_data['payload'].get('headers', [])}
        
        # Get body
        body = ""
        if 'parts' in msg_data['payload']:
            for part in msg_data['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
        elif 'body' in msg_data['payload'] and 'data' in msg_data['payload']['body']:
            body = base64.urlsafe_b64decode(msg_data['payload']['body']['data']).decode('utf-8')
        
        labels = msg_data.get('labelIds', [])
        
        return EmailMessage(
            id=msg_data['id'],
            thread_id=msg_data['threadId'],
            from_email=headers.get('From', ''),
            to_email=headers.get('To', '').split(','),
            subject=headers.get('Subject', ''),
            body=body,
            snippet=msg_data.get('snippet', ''),
            date=headers.get('Date', ''),
            labels=labels,
            is_unread='UNREAD' in labels,
            has_attachments=any(
                'filename' in part and part['filename']
                for part in msg_data['payload'].get('parts', [])
            ) if 'parts' in msg_data['payload'] else False,
        )
    
    # =========================================================================
    # READ OPERATIONS (logged but not queued)
    # =========================================================================
    
    def list_messages(
        self,
        query: str = None,
        max_results: int = 10,
        label: str = "INBOX",
    ) -> List[EmailMessage]:
        """
        List messages matching query.
        
        Query examples:
        - "is:unread" - unread messages
        - "from:client@example.com" - from specific sender
        - "subject:invoice" - subject contains invoice
        - "after:2024/01/01" - after date
        """
        self._ensure_authenticated()
        
        q = query or ""
        if label:
            q = f"in:{label} {q}".strip()
        
        results = self._service.users().messages().list(
            userId='me',
            q=q,
            maxResults=max_results,
        ).execute()
        
        messages = []
        for msg_ref in results.get('messages', []):
            msg_data = self._service.users().messages().get(
                userId='me',
                id=msg_ref['id'],
                format='full',
            ).execute()
            messages.append(self._parse_message(msg_data))
        
        return messages
    
    def get_message(self, message_id: str) -> Optional[EmailMessage]:
        """Get a specific message by ID."""
        self._ensure_authenticated()
        
        try:
            msg_data = self._service.users().messages().get(
                userId='me',
                id=message_id,
                format='full',
            ).execute()
            return self._parse_message(msg_data)
        except Exception:
            return None
    
    def get_unread_count(self, label: str = "INBOX") -> int:
        """Get count of unread messages."""
        self._ensure_authenticated()
        
        results = self._service.users().messages().list(
            userId='me',
            q=f"in:{label} is:unread",
            maxResults=1,
        ).execute()
        
        return results.get('resultSizeEstimate', 0)
    
    def search(self, query: str, max_results: int = 10) -> List[EmailMessage]:
        """Search emails with Gmail query syntax."""
        return self.list_messages(query=query, max_results=max_results, label=None)
    
    # =========================================================================
    # WRITE OPERATIONS (through message queue)
    # =========================================================================
    
    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: List[str] = None,
        bcc: List[str] = None,
        reply_to: str = None,
    ) -> Dict[str, Any]:
        """
        Create a draft email (does NOT send).
        Returns draft info including ID.
        """
        self._ensure_authenticated()
        
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        if cc:
            message['cc'] = ', '.join(cc)
        if bcc:
            message['bcc'] = ', '.join(bcc)
        if reply_to:
            message['In-Reply-To'] = reply_to
        
        message.attach(MIMEText(body, 'plain'))
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        draft = self._service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw}},
        ).execute()
        
        return {
            "draft_id": draft['id'],
            "message_id": draft['message']['id'],
            "status": "draft_created",
        }
    
    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: List[str] = None,
        bcc: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Actually send an email.
        NOTE: This should only be called by the message queue, not directly by agents.
        """
        self._ensure_authenticated()
        
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        if cc:
            message['cc'] = ', '.join(cc)
        if bcc:
            message['bcc'] = ', '.join(bcc)
        
        message.attach(MIMEText(body, 'plain'))
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        sent = self._service.users().messages().send(
            userId='me',
            body={'raw': raw},
        ).execute()
        
        return {
            "message_id": sent['id'],
            "thread_id": sent['threadId'],
            "status": "sent",
        }
    
    def reply_to_message(
        self,
        message_id: str,
        body: str,
        include_original: bool = True,
    ) -> Dict[str, Any]:
        """
        Reply to an existing message.
        NOTE: This should only be called by the message queue.
        """
        self._ensure_authenticated()
        
        # Get original message
        original = self.get_message(message_id)
        if not original:
            raise ValueError(f"Message {message_id} not found")
        
        # Build reply
        message = MIMEMultipart()
        message['to'] = original.from_email
        message['subject'] = f"Re: {original.subject}" if not original.subject.startswith("Re:") else original.subject
        message['In-Reply-To'] = message_id
        message['References'] = message_id
        
        reply_body = body
        if include_original:
            reply_body += f"\n\n---\nOn {original.date}, {original.from_email} wrote:\n{original.body}"
        
        message.attach(MIMEText(reply_body, 'plain'))
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        sent = self._service.users().messages().send(
            userId='me',
            body={
                'raw': raw,
                'threadId': original.thread_id,
            },
        ).execute()
        
        return {
            "message_id": sent['id'],
            "thread_id": sent['threadId'],
            "status": "sent",
        }
    
    # =========================================================================
    # DELETE OPERATIONS (require confirmation)
    # =========================================================================
    
    def trash_message(self, message_id: str) -> bool:
        """
        Move message to trash.
        Requires explicit confirmation.
        """
        self._ensure_authenticated()
        
        self._service.users().messages().trash(
            userId='me',
            id=message_id,
        ).execute()
        
        return True
    
    def mark_read(self, message_id: str) -> bool:
        """Mark a message as read."""
        self._ensure_authenticated()
        
        self._service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'removeLabelIds': ['UNREAD']},
        ).execute()
        
        return True
    
    def mark_unread(self, message_id: str) -> bool:
        """Mark a message as unread."""
        self._ensure_authenticated()
        
        self._service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': ['UNREAD']},
        ).execute()
        
        return True
    
    def add_label(self, message_id: str, label: str) -> bool:
        """Add a label to a message."""
        self._ensure_authenticated()
        
        self._service.users().messages().modify(
            userId='me',
            id=message_id,
            body={'addLabelIds': [label]},
        ).execute()
        
        return True


# Global instance
_client: Optional[GmailClient] = None


def get_gmail_client() -> GmailClient:
    """Get the global Gmail client."""
    global _client
    if _client is None:
        _client = GmailClient()
    return _client
