"""
Gmail to ClickUp Ticket Creator

Searches Gmail for client emails matching keywords/domains and creates
ClickUp tickets from them, avoiding duplicates.

Usage:
    from services.gmail_to_clickup import GmailToClickUp
    
    g2c = GmailToClickUp()
    results = g2c.process_client_emails(
        client_id="ap-driving",
        keywords=["bug", "issue", "problem", "error"],
        days_back=30,
    )
"""

import os
import re
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

# Local imports
from services.google_auth import get_google_auth
from services.tickets.clickup_client import get_clickup_client, ClickUpTask
from services.tickets.zendesk_client import get_zendesk_client, ZendeskTicket

# Try to import Ticket Manager Agent for smart deduplication
try:
    from agents.ticket_manager import get_ticket_manager, TicketManagerAgent
    TICKET_MANAGER_AVAILABLE = True
except ImportError:
    TICKET_MANAGER_AVAILABLE = False
    get_ticket_manager = None


# Configuration
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
PROCESSED_EMAILS_FILE = DATA_DIR / "processed_gmail_to_clickup.json"


@dataclass
class ClientConfig:
    """Configuration for a client."""
    id: str
    name: str
    domains: List[str]  # e.g., ["apdriving.com", "apdrivingschool.com"]
    clickup_list_id: str
    clickup_space_id: Optional[str] = None
    emails: List[str] = field(default_factory=list)  # Specific email addresses
    vip_emails: List[str] = field(default_factory=list)  # VIP emails (no keyword filter)
    keywords: List[str] = field(default_factory=list)  # Optional default keywords
    exclude_subjects: List[str] = field(default_factory=list)  # Subjects to exclude
    exclude_senders: List[str] = field(default_factory=list)  # Sender patterns to exclude
    priority: int = 3  # Default priority (1=urgent, 4=low)
    auto_create: bool = True  # Whether to auto-create tickets


# Default exclusion patterns for automated emails
DEFAULT_EXCLUDE_SUBJECTS = [
    "order is now complete",
    "order confirmation",
    "payment received",
    "receipt for your payment",
    "subscription renewed",
    "password reset",
    "verify your email",
    "welcome to",
    "thank you for your order",
    "invoice",
    "automatic reply",
    "out of office",
    "undeliverable",
    "delivery status",
]

DEFAULT_EXCLUDE_SENDERS = [
    "noreply@",
    "no-reply@",
    "donotreply@",
    "mailer-daemon@",
    "postmaster@",
    "notifications@",
    "alert@",
    "system@",
]


@dataclass
class EmailToTicket:
    """Represents an email that can become a ticket."""
    email_id: str
    thread_id: str
    subject: str
    body: str
    sender_email: str
    sender_name: str
    date: str
    is_duplicate: bool = False
    duplicate_task_id: Optional[str] = None
    created_task_id: Optional[str] = None
    created_zendesk_id: Optional[int] = None  # Zendesk ticket ID
    skipped_reason: Optional[str] = None
    
    @property
    def fingerprint(self) -> str:
        """Generate a fingerprint for duplicate detection."""
        # Use subject + sender + date for fingerprint
        content = f"{self.subject}|{self.sender_email}|{self.date[:10]}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


@dataclass
class ProcessingResult:
    """Result of processing client emails."""
    client_id: str
    emails_found: int
    tickets_created: int
    zendesk_tickets_created: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    emails: List[EmailToTicket] = field(default_factory=list)
    created_tasks: List[ClickUpTask] = field(default_factory=list)
    created_zendesk_tickets: List[Any] = field(default_factory=list)  # ZendeskTicket objects


class GmailToClickUp:
    """
    Processes Gmail emails from clients and creates ClickUp tickets.
    
    Features:
    - Search by domain and keywords
    - 30-day lookback (configurable)
    - Duplicate detection using:
      - Subject line matching
      - Previously processed email IDs
      - Fingerprint hashing
    - Tags created tickets with "from-gmail"
    """
    
    def __init__(self, use_smart_dedup: bool = True):
        self._google_auth = None
        self._gmail_service = None
        self._clickup = None
        self._zendesk = None
        self._ticket_manager = None
        self._use_smart_dedup = use_smart_dedup and TICKET_MANAGER_AVAILABLE
        self._processed_ids: Dict[str, Dict] = {}
        
        # Load client configurations
        self._clients: Dict[str, ClientConfig] = {}
        self._load_client_configs()
        self._load_processed_emails()
    
    def _load_client_configs(self):
        """Load client configurations."""
        # Default clients - can be extended from config file
        self._clients = {
            "ap-driving": ClientConfig(
                id="ap-driving",
                name="AP Driving",
                domains=["apdriving.com", "apdrivingschool.com"],
                clickup_list_id=os.getenv("CLICKUP_AP_DRIVING_LIST_ID", ""),
                clickup_space_id=os.getenv("CLICKUP_AP_DRIVING_SPACE_ID", ""),
                keywords=["issue", "problem", "error", "bug", "not working", "help", "urgent"],
                priority=2,
            ),
            "collegewise": ClientConfig(
                id="collegewise",
                name="Collegewise",
                domains=["collegewise.com"],
                clickup_list_id=os.getenv("CLICKUP_COLLEGEWISE_LIST_ID", ""),
                clickup_space_id=os.getenv("CLICKUP_COLLEGEWISE_SPACE_ID", ""),
                keywords=["issue", "problem", "error", "bug", "not working", "help"],
                priority=3,
            ),
            "cysterhood": ClientConfig(
                id="cysterhood",
                name="Cysterhood",
                domains=["cysterhood.com", "pcos.com"],
                clickup_list_id=os.getenv("CLICKUP_CYSTERHOOD_LIST_ID", ""),
                clickup_space_id=os.getenv("CLICKUP_CYSTERHOOD_SPACE_ID", ""),
                keywords=["issue", "problem", "error", "bug", "api", "help"],
                priority=3,
            ),
        }
        
        # Try to load from config file
        config_path = DATA_DIR / "gmail_to_clickup_clients.json"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                for client_data in data.get("clients", []):
                    client = ClientConfig(**client_data)
                    self._clients[client.id] = client
            except Exception as e:
                print(f"Error loading client configs: {e}")
    
    def _load_processed_emails(self):
        """Load previously processed email IDs."""
        if PROCESSED_EMAILS_FILE.exists():
            try:
                with open(PROCESSED_EMAILS_FILE) as f:
                    self._processed_ids = json.load(f)
            except Exception:
                self._processed_ids = {}
    
    def _save_processed_emails(self):
        """Save processed email IDs."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(PROCESSED_EMAILS_FILE, 'w') as f:
            json.dump(self._processed_ids, f, indent=2)
    
    @property
    def google_auth(self):
        if self._google_auth is None:
            self._google_auth = get_google_auth()
        return self._google_auth
    
    @property
    def gmail_service(self):
        if self._gmail_service is None:
            if not self.google_auth.is_authenticated:
                self.google_auth.authenticate()
            self._gmail_service = self.google_auth.get_gmail_service()
        return self._gmail_service
    
    @property
    def clickup(self):
        if self._clickup is None:
            self._clickup = get_clickup_client()
        return self._clickup
    
    @property
    def zendesk(self):
        if self._zendesk is None:
            self._zendesk = get_zendesk_client()
        return self._zendesk
    
    @property
    def ticket_manager(self):
        if self._ticket_manager is None and self._use_smart_dedup:
            self._ticket_manager = get_ticket_manager()
        return self._ticket_manager
    
    def list_clients(self) -> List[ClientConfig]:
        """List all configured clients."""
        return list(self._clients.values())
    
    def get_client(self, client_id: str) -> Optional[ClientConfig]:
        """Get a specific client configuration."""
        return self._clients.get(client_id)
    
    def add_client(self, config: ClientConfig):
        """Add or update a client configuration."""
        self._clients[config.id] = config
        self._save_client_configs()
    
    def _save_client_configs(self):
        """Save client configurations."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        config_path = DATA_DIR / "gmail_to_clickup_clients.json"
        data = {
            "updated_at": datetime.utcnow().isoformat(),
            "clients": [
                {
                    "id": c.id,
                    "name": c.name,
                    "domains": c.domains,
                    "emails": c.emails,
                    "vip_emails": c.vip_emails,
                    "clickup_list_id": c.clickup_list_id,
                    "clickup_space_id": c.clickup_space_id,
                    "keywords": c.keywords,
                    "exclude_subjects": c.exclude_subjects,
                    "exclude_senders": c.exclude_senders,
                    "priority": c.priority,
                    "auto_create": c.auto_create,
                }
                for c in self._clients.values()
            ]
        }
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def search_client_emails(
        self,
        client_id: str,
        keywords: List[str] = None,
        days_back: int = 30,
        max_results: int = 100,
    ) -> List[EmailToTicket]:
        """
        Search Gmail for emails from a client.
        
        Args:
            client_id: Client identifier
            keywords: Keywords to search for (optional, uses client defaults)
            days_back: Number of days to look back (default 30)
            max_results: Maximum emails to return
        
        Returns:
            List of EmailToTicket objects
        """
        client = self.get_client(client_id)
        if not client:
            raise ValueError(f"Unknown client: {client_id}")
        
        emails = []
        seen_ids = set()
        after_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        
        # Search 1: VIP emails (no keyword filter - get all emails from VIPs)
        if client.vip_emails:
            vip_query_parts = [f"from:{email}" for email in client.vip_emails]
            vip_query = f"({' OR '.join(vip_query_parts)}) after:{after_date}"
            
            print(f"Searching VIP emails: {vip_query}")
            
            try:
                results = self.gmail_service.users().messages().list(
                    userId='me',
                    q=vip_query,
                    maxResults=max_results // 2,  # Half for VIPs
                ).execute()
                
                for msg_ref in results.get('messages', []):
                    if msg_ref['id'] in seen_ids:
                        continue
                    seen_ids.add(msg_ref['id'])
                    
                    msg_data = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='full',
                    ).execute()
                    
                    email = self._parse_email(msg_data)
                    emails.append(email)
                    
            except Exception as e:
                print(f"Error searching VIP emails: {e}")
        
        # Search 2: Domain/regular emails with keyword filter
        from_parts = []
        
        for domain in client.domains:
            from_parts.append(f"from:@{domain}")
        
        for email in (client.emails or []):
            from_parts.append(f"from:{email}")
        
        if from_parts:
            domain_query = " OR ".join(from_parts)
            if len(from_parts) > 1:
                domain_query = f"({domain_query})"
            
            use_keywords = keywords if keywords else client.keywords
            keyword_query = ""
            if use_keywords:
                keyword_query = " OR ".join([f'"{kw}"' for kw in use_keywords])
                keyword_query = f"({keyword_query})"
            
            if keyword_query:
                query = f"{domain_query} {keyword_query} after:{after_date}"
            else:
                query = f"{domain_query} after:{after_date}"
            
            print(f"Searching domain emails: {query}")
            
            try:
                results = self.gmail_service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=max_results,
                ).execute()
                
                for msg_ref in results.get('messages', []):
                    if msg_ref['id'] in seen_ids:
                        continue
                    seen_ids.add(msg_ref['id'])
                    
                    msg_data = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='full',
                    ).execute()
                    
                    email = self._parse_email(msg_data)
                    emails.append(email)
                    
            except Exception as e:
                print(f"Error searching domain emails: {e}")
        
        return emails
    
    def _parse_email(self, msg_data: Dict) -> EmailToTicket:
        """Parse Gmail API message into EmailToTicket."""
        headers = {h['name'].lower(): h['value'] for h in msg_data.get('payload', {}).get('headers', [])}
        
        # Extract sender
        from_header = headers.get('from', '')
        sender_name = from_header
        sender_email = from_header
        
        # Parse "Name <email@domain.com>" format
        match = re.match(r'(.+?)\s*<(.+?)>', from_header)
        if match:
            sender_name = match.group(1).strip().strip('"')
            sender_email = match.group(2).strip()
        elif '<' not in from_header and '@' in from_header:
            sender_email = from_header.strip()
            sender_name = sender_email.split('@')[0]
        
        # Extract body
        body = ""
        payload = msg_data.get('payload', {})
        
        if 'body' in payload and payload['body'].get('data'):
            import base64
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        elif 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                    import base64
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                    break
        
        # Clean body (limit length, remove signatures)
        body = self._clean_body(body)
        
        return EmailToTicket(
            email_id=msg_data['id'],
            thread_id=msg_data['threadId'],
            subject=headers.get('subject', '(No Subject)'),
            body=body,
            sender_email=sender_email,
            sender_name=sender_name,
            date=headers.get('date', ''),
        )
    
    def _clean_body(self, body: str, max_length: int = 2000) -> str:
        """Clean email body for ticket description."""
        if not body:
            return ""
        
        # Remove common email signatures
        signature_patterns = [
            r'--\s*\n.*',  # Standard signature delimiter
            r'Sent from my iPhone.*',
            r'Sent from my Android.*',
            r'Get Outlook for.*',
            r'On .+ wrote:.*',  # Reply quote
            r'From: .+\nSent: .+\nTo: .+\nSubject:.*',  # Outlook format
        ]
        
        for pattern in signature_patterns:
            body = re.sub(pattern, '', body, flags=re.DOTALL | re.IGNORECASE)
        
        # Limit length
        body = body.strip()
        if len(body) > max_length:
            body = body[:max_length] + "\n\n... (truncated)"
        
        return body
    
    def smart_check_duplicate(
        self,
        email: EmailToTicket,
        client: ClientConfig,
    ) -> bool:
        """
        Use AI-powered Ticket Manager for semantic duplicate detection.
        
        This can detect duplicates even when:
        - Subjects are worded differently
        - Same issue reported by different people
        - Follow-ups about existing issues
        
        Returns True if duplicate (should skip), False if new.
        """
        if not self.ticket_manager:
            return False  # Fall back to basic check
        
        try:
            analysis = self.ticket_manager.check_duplicate(
                subject=email.subject,
                body=email.body or "",
                sender=email.sender_email,
                clickup_list_id=client.clickup_list_id,
                days_back=30,
            )
            
            if analysis.is_duplicate and analysis.duplicate_matches:
                match = analysis.duplicate_matches[0]
                email.is_duplicate = True
                email.duplicate_task_id = match.match_id
                email.skipped_reason = (
                    f"AI detected duplicate ({match.confidence.value}, {match.confidence_score:.0%}): "
                    f"{match.reasoning[:100]}"
                )
                return True
            
            # Also check if it should be added as comment instead of new ticket
            if analysis.recommended_action == "comment" and analysis.related_tickets:
                email.skipped_reason = (
                    f"AI recommends adding as comment to #{analysis.related_tickets[0]}: "
                    f"{analysis.analysis_notes[:100]}"
                )
                # Don't mark as duplicate - let the calling code decide
                return False
                
        except Exception as e:
            print(f"Smart dedup error: {e}")
        
        return False
    
    def should_exclude(self, email: EmailToTicket, client: ClientConfig) -> bool:
        """
        Check if email should be excluded (automated/system emails).
        
        Returns True if should be excluded.
        """
        subject_lower = email.subject.lower()
        sender_lower = email.sender_email.lower()
        
        # Check excluded subjects
        exclude_subjects = client.exclude_subjects or DEFAULT_EXCLUDE_SUBJECTS
        for pattern in exclude_subjects:
            if pattern.lower() in subject_lower:
                email.skipped_reason = f"Excluded subject pattern: {pattern}"
                return True
        
        # Check excluded senders
        exclude_senders = client.exclude_senders or DEFAULT_EXCLUDE_SENDERS
        for pattern in exclude_senders:
            if pattern.lower() in sender_lower:
                email.skipped_reason = f"Excluded sender pattern: {pattern}"
                return True
        
        return False
    
    def check_duplicate(
        self,
        email: EmailToTicket,
        client: ClientConfig,
        existing_tasks: List[ClickUpTask] = None,
    ) -> bool:
        """
        Check if email has already been processed or matches existing task.
        
        Returns True if duplicate (should skip), False if new.
        """
        # Check 1: Already processed this email ID
        if email.email_id in self._processed_ids.get(client.id, {}):
            email.is_duplicate = True
            email.duplicate_task_id = self._processed_ids[client.id][email.email_id].get('task_id')
            email.skipped_reason = "Email already processed"
            return True
        
        # Check 2: Fingerprint match
        fingerprint = email.fingerprint
        for email_id, data in self._processed_ids.get(client.id, {}).items():
            if data.get('fingerprint') == fingerprint:
                email.is_duplicate = True
                email.duplicate_task_id = data.get('task_id')
                email.skipped_reason = "Similar email already processed"
                return True
        
        # Check 3: Subject match in existing ClickUp tasks
        if existing_tasks:
            clean_subject = email.subject.lower().strip()
            for task in existing_tasks:
                # Check if subject appears in task name or description
                if clean_subject in task.name.lower():
                    email.is_duplicate = True
                    email.duplicate_task_id = task.id
                    email.skipped_reason = f"Matches existing task: {task.name[:50]}"
                    return True
                
                # Check if email ID is referenced in task description
                if email.email_id in (task.description or ''):
                    email.is_duplicate = True
                    email.duplicate_task_id = task.id
                    email.skipped_reason = "Email ID found in existing task"
                    return True
        
        return False
    
    def create_ticket(
        self,
        email: EmailToTicket,
        client: ClientConfig,
        dry_run: bool = False,
        create_zendesk: bool = True,
    ) -> Optional[ClickUpTask]:
        """
        Create a Zendesk ticket (with customer as reporter) and ClickUp task (linked).
        
        Args:
            email: Email to create ticket from
            client: Client configuration
            dry_run: If True, don't actually create (preview only)
            create_zendesk: If True, also create linked Zendesk ticket
        
        Returns:
            Created ClickUpTask or None
        """
        if not client.clickup_list_id:
            print(f"No ClickUp list configured for {client.id}")
            return None
        
        # Build task/ticket name
        task_name = f"[Email] {email.subject}"
        if len(task_name) > 200:
            task_name = task_name[:197] + "..."
        
        zendesk_ticket = None
        zendesk_url = ""
        
        # Step 1: Create Zendesk ticket first (customer as reporter)
        zendesk_ready = self.zendesk and hasattr(self.zendesk, 'is_configured') and self.zendesk.is_configured
        if create_zendesk and zendesk_ready:
            zendesk_description = f"""Email received from customer:

**From:** {email.sender_name} <{email.sender_email}>
**Date:** {email.date}

---

{email.body}

---

*Auto-created from Gmail by Agent007*
*Email ID: {email.email_id}*
"""
            
            if dry_run:
                print(f"[DRY RUN] Would create Zendesk ticket with requester: {email.sender_email}")
            else:
                try:
                    zendesk_ticket = self.zendesk.create_ticket(
                        subject=email.subject,
                        description=zendesk_description,
                        priority="normal",
                        tags=["from-gmail", "auto-created", client.id],
                        requester_email=email.sender_email,  # Customer as reporter!
                    )
                    
                    if zendesk_ticket:
                        email.created_zendesk_id = zendesk_ticket.id
                        zendesk_url = f"https://{self.zendesk.subdomain}.zendesk.com/agent/tickets/{zendesk_ticket.id}"
                        print(f"  ✅ Created Zendesk #{zendesk_ticket.id} (requester: {email.sender_email})")
                        
                except Exception as e:
                    print(f"  ⚠️ Error creating Zendesk ticket: {e}")
        
        # Step 2: Build ClickUp description with Zendesk link
        description = f"""## Email from Client

**From:** {email.sender_name} <{email.sender_email}>
**Date:** {email.date}
**Subject:** {email.subject}
"""
        
        # Add Zendesk link if created
        if zendesk_ticket:
            description += f"""
### 🎫 Zendesk Ticket
**Ticket:** [#{zendesk_ticket.id}]({zendesk_url})
**Requester:** {email.sender_email}
**Status:** New
"""
        
        description += f"""
---

{email.body}

---

*Created from Gmail email ID: `{email.email_id}`*
*Thread ID: `{email.thread_id}`*
"""
        
        if dry_run:
            print(f"[DRY RUN] Would create task: {task_name[:60]}...")
            return None
        
        # Step 3: Create ClickUp task
        try:
            task = self.clickup.create_task(
                list_id=client.clickup_list_id,
                name=task_name,
                description=description,
                priority=client.priority,
                tags=["from-gmail"],
            )
            
            if task:
                email.created_task_id = task.id
                print(f"  ✅ Created ClickUp task {task.id}")
                
                # Step 4: Add ClickUp link back to Zendesk as internal note
                if zendesk_ticket and self.zendesk:
                    clickup_url = task.url if hasattr(task, 'url') else f"https://app.clickup.com/t/{task.id}"
                    self.zendesk.add_internal_note(
                        zendesk_ticket.id,
                        f"📋 **ClickUp Task Created**\n\n[View in ClickUp]({clickup_url})\n\nTask ID: {task.id}"
                    )
                
                # Record as processed
                if client.id not in self._processed_ids:
                    self._processed_ids[client.id] = {}
                
                self._processed_ids[client.id][email.email_id] = {
                    "task_id": task.id,
                    "zendesk_id": zendesk_ticket.id if zendesk_ticket else None,
                    "fingerprint": email.fingerprint,
                    "subject": email.subject[:100],
                    "processed_at": datetime.utcnow().isoformat(),
                }
                self._save_processed_emails()
                
                return task
            
        except Exception as e:
            print(f"Error creating ClickUp task: {e}")
        
        return None
    
    def process_client_emails(
        self,
        client_id: str,
        keywords: List[str] = None,
        days_back: int = 30,
        max_results: int = 100,
        dry_run: bool = False,
        skip_duplicates: bool = True,
        use_smart_dedup: bool = True,
    ) -> ProcessingResult:
        """
        Process emails from a client and create ClickUp tickets.
        
        Args:
            client_id: Client identifier
            keywords: Keywords to filter emails (optional)
            days_back: Days to look back (default 30)
            max_results: Max emails to process
            dry_run: If True, don't create tickets (preview only)
            skip_duplicates: If True, skip duplicate detection
        
        Returns:
            ProcessingResult with summary and details
        """
        client = self.get_client(client_id)
        if not client:
            raise ValueError(f"Unknown client: {client_id}")
        
        result = ProcessingResult(
            client_id=client_id,
            emails_found=0,
            tickets_created=0,
            duplicates_skipped=0,
            errors=0,
        )
        
        # Search for emails
        emails = self.search_client_emails(
            client_id=client_id,
            keywords=keywords,
            days_back=days_back,
            max_results=max_results,
        )
        
        result.emails_found = len(emails)
        result.emails = emails
        
        if not emails:
            return result
        
        # Get existing tasks for duplicate detection
        existing_tasks = []
        if skip_duplicates and self.clickup and client.clickup_list_id:
            try:
                existing_tasks = self.clickup.get_tasks(
                    list_id=client.clickup_list_id,
                    include_closed=True,
                )
            except Exception as e:
                print(f"Warning: Could not fetch existing tasks: {e}")
        
        # Process each email
        for email in emails:
            # Check exclusions first (automated emails)
            if self.should_exclude(email, client):
                result.duplicates_skipped += 1
                continue
            
            # Smart AI-powered duplicate detection
            if use_smart_dedup and self._use_smart_dedup and self.ticket_manager:
                if self.smart_check_duplicate(email, client):
                    result.duplicates_skipped += 1
                    print(f"  🤖 AI detected duplicate: {email.subject[:40]}...")
                    continue
            
            # Basic duplicate check (email ID, fingerprint, subject match)
            if skip_duplicates and self.check_duplicate(email, client, existing_tasks):
                result.duplicates_skipped += 1
                continue
            
            # Create ticket (Zendesk + ClickUp)
            task = self.create_ticket(email, client, dry_run=dry_run)
            
            if task:
                result.tickets_created += 1
                result.created_tasks.append(task)
                
                # Track Zendesk ticket if created
                if email.created_zendesk_id:
                    result.zendesk_tickets_created += 1
            elif not dry_run:
                result.errors += 1
        
        return result
    
    def process_all_clients(
        self,
        keywords: List[str] = None,
        days_back: int = 30,
        dry_run: bool = True,
    ) -> Dict[str, ProcessingResult]:
        """
        Process emails for all configured clients.
        
        Args:
            keywords: Keywords to filter (uses client defaults if None)
            days_back: Days to look back
            dry_run: If True, don't create tickets
        
        Returns:
            Dict mapping client_id to ProcessingResult
        """
        results = {}
        
        for client in self.list_clients():
            if not client.auto_create:
                continue
            
            if not client.clickup_list_id:
                print(f"Skipping {client.id}: No ClickUp list configured")
                continue
            
            try:
                result = self.process_client_emails(
                    client_id=client.id,
                    keywords=keywords,
                    days_back=days_back,
                    dry_run=dry_run,
                )
                results[client.id] = result
            except Exception as e:
                print(f"Error processing {client.id}: {e}")
                results[client.id] = ProcessingResult(
                    client_id=client.id,
                    emails_found=0,
                    tickets_created=0,
                    duplicates_skipped=0,
                    errors=1,
                )
        
        return results


# =============================================================================
# Convenience Functions
# =============================================================================

_instance: Optional[GmailToClickUp] = None


def get_gmail_to_clickup() -> GmailToClickUp:
    """Get or create GmailToClickUp instance."""
    global _instance
    if _instance is None:
        _instance = GmailToClickUp()
    return _instance


def search_client_emails(
    client_id: str,
    keywords: List[str] = None,
    days_back: int = 30,
) -> List[EmailToTicket]:
    """Search for client emails."""
    return get_gmail_to_clickup().search_client_emails(
        client_id=client_id,
        keywords=keywords,
        days_back=days_back,
    )


def create_tickets_from_emails(
    client_id: str,
    keywords: List[str] = None,
    days_back: int = 30,
    dry_run: bool = True,
) -> ProcessingResult:
    """Process client emails and create tickets."""
    return get_gmail_to_clickup().process_client_emails(
        client_id=client_id,
        keywords=keywords,
        days_back=days_back,
        dry_run=dry_run,
    )


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create ClickUp tickets from Gmail emails")
    parser.add_argument("--client", "-c", help="Client ID to process")
    parser.add_argument("--keywords", "-k", nargs="+", help="Keywords to search for")
    parser.add_argument("--days", "-d", type=int, default=30, help="Days to look back")
    parser.add_argument("--max", "-m", type=int, default=50, help="Max emails to process")
    parser.add_argument("--create", action="store_true", help="Actually create tickets (default is dry run)")
    parser.add_argument("--list-clients", action="store_true", help="List configured clients")
    parser.add_argument("--search-only", action="store_true", help="Only search, don't process")
    
    args = parser.parse_args()
    
    g2c = GmailToClickUp()
    
    if args.list_clients:
        print("\n📋 Configured Clients:")
        print("-" * 60)
        for client in g2c.list_clients():
            status = "✅" if client.clickup_list_id else "⚠️ No ClickUp list"
            print(f"  {client.id}: {client.name}")
            print(f"    Domains: {', '.join(client.domains)}")
            print(f"    Keywords: {', '.join(client.keywords[:5])}...")
            print(f"    Status: {status}")
            print()
        exit(0)
    
    if not args.client:
        print("Error: --client required. Use --list-clients to see available clients.")
        exit(1)
    
    client = g2c.get_client(args.client)
    if not client:
        print(f"Error: Unknown client '{args.client}'")
        exit(1)
    
    print(f"\n📧 Processing emails for: {client.name}")
    print(f"   Domains: {', '.join(client.domains)}")
    print(f"   Looking back: {args.days} days")
    print(f"   Keywords: {args.keywords or client.keywords}")
    print()
    
    if args.search_only:
        emails = g2c.search_client_emails(
            client_id=args.client,
            keywords=args.keywords,
            days_back=args.days,
            max_results=args.max,
        )
        
        print(f"Found {len(emails)} emails:\n")
        for email in emails[:20]:
            print(f"  [{email.date[:16]}] {email.sender_name}")
            print(f"  Subject: {email.subject[:60]}...")
            print()
    else:
        result = g2c.process_client_emails(
            client_id=args.client,
            keywords=args.keywords,
            days_back=args.days,
            max_results=args.max,
            dry_run=not args.create,
        )
        
        print("=" * 60)
        print(f"Results for {client.name}")
        print("=" * 60)
        print(f"  Emails found:      {result.emails_found}")
        print(f"  Duplicates skipped: {result.duplicates_skipped}")
        print(f"  Tickets created:   {result.tickets_created}")
        print(f"  Errors:            {result.errors}")
        print()
        
        if result.created_tasks:
            print("Created tickets:")
            for task in result.created_tasks:
                print(f"  - {task.name[:50]}... ({task.url})")
        
        if not args.create:
            print("\n⚠️  DRY RUN - No tickets were actually created.")
            print("   Use --create to create tickets.")
