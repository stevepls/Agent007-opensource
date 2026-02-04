"""
Notion Email Parser Service

Extracts Notion data from Gmail notification emails since we don't have direct API access.
Cross-references with Airtable tickets for enriched context.
"""

import os
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import unescape

# Import Gmail service
try:
    from services.gmail import GmailService
except ImportError:
    GmailService = None

# Import Airtable service
try:
    from services.airtable import get_airtable_service, AirtableTicket
except ImportError:
    get_airtable_service = None
    AirtableTicket = None


@dataclass
class NotionUpdate:
    """Represents a parsed Notion notification."""
    id: str
    page_title: str
    page_url: Optional[str]
    page_id: Optional[str]
    update_type: str  # mention, comment, edit, invite, reminder
    who: str  # Who made the change
    when: datetime
    content_preview: str
    workspace: Optional[str]
    raw_subject: str
    raw_body: str
    # Cross-reference data
    related_tickets: List[Dict[str, Any]] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "page_title": self.page_title,
            "page_url": self.page_url,
            "page_id": self.page_id,
            "update_type": self.update_type,
            "who": self.who,
            "when": self.when.isoformat() if self.when else None,
            "content_preview": self.content_preview[:300] if self.content_preview else None,
            "workspace": self.workspace,
            "related_tickets": self.related_tickets,
            "keywords": self.keywords,
        }


class NotionEmailParser:
    """Parses Notion notification emails from Gmail."""
    
    NOTION_SENDERS = [
        'notify@mail.notion.so',
        'noreply@notion.so',
        'no-reply@notion.so',
    ]
    
    # Patterns to extract page IDs from Notion URLs
    PAGE_ID_PATTERN = re.compile(r'notion\.so/[^/]+/[^/]+-([a-f0-9]{32})')
    PAGE_URL_PATTERN = re.compile(r'(https?://(?:www\.)?notion\.so/[^\s<>"]+)')
    
    def __init__(self):
        self.gmail_service = None
        self.airtable_service = None
        self._initialize_services()
    
    def _initialize_services(self):
        """Initialize Gmail and Airtable services."""
        if GmailService:
            try:
                self.gmail_service = GmailService()
                if not self.gmail_service.authenticate():
                    self.gmail_service = None
            except Exception:
                pass
        
        if get_airtable_service:
            try:
                self.airtable_service = get_airtable_service()
            except Exception:
                pass
    
    def is_configured(self) -> bool:
        """Check if the parser is properly configured."""
        return self.gmail_service is not None
    
    def _detect_update_type(self, subject: str, body: str) -> str:
        """Detect the type of Notion notification."""
        subject_lower = subject.lower()
        body_lower = body.lower()
        
        if 'mentioned you' in subject_lower or '@' in subject_lower:
            return 'mention'
        elif 'commented' in subject_lower or 'comment' in body_lower:
            return 'comment'
        elif 'invited you' in subject_lower:
            return 'invite'
        elif 'reminder' in subject_lower:
            return 'reminder'
        elif 'updated' in subject_lower or 'edited' in subject_lower:
            return 'edit'
        elif 'shared' in subject_lower:
            return 'share'
        else:
            return 'notification'
    
    def _extract_who(self, subject: str, body: str, from_header: str) -> str:
        """Extract who made the change."""
        # Try to extract name from subject patterns like "John Doe mentioned you"
        patterns = [
            r'^([A-Za-z\s]+)\s+mentioned you',
            r'^([A-Za-z\s]+)\s+commented',
            r'^([A-Za-z\s]+)\s+invited you',
            r'^([A-Za-z\s]+)\s+updated',
            r'^([A-Za-z\s]+)\s+shared',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, subject)
            if match:
                return match.group(1).strip()
        
        # Try to extract from email body
        body_patterns = [
            r'from\s+([A-Za-z\s]+)',
            r'by\s+([A-Za-z\s]+)',
        ]
        
        for pattern in body_patterns:
            match = re.search(pattern, body[:200])
            if match:
                name = match.group(1).strip()
                if len(name) > 2 and len(name) < 50:
                    return name
        
        return 'Someone'
    
    def _extract_page_info(self, subject: str, body: str) -> Tuple[str, Optional[str], Optional[str]]:
        """Extract page title, URL, and ID from the notification."""
        # Try to extract page title from subject
        # Common patterns: "mentioned you in Page Title", "commented on Page Title"
        title_patterns = [
            r'in\s+"([^"]+)"',
            r'on\s+"([^"]+)"',
            r'in\s+([^:]+)$',
            r'on\s+([^:]+)$',
        ]
        
        page_title = None
        for pattern in title_patterns:
            match = re.search(pattern, subject)
            if match:
                page_title = match.group(1).strip()
                break
        
        if not page_title:
            # Use subject as fallback
            page_title = subject.split(' in ')[-1] if ' in ' in subject else subject
        
        # Extract URL from body
        page_url = None
        url_match = self.PAGE_URL_PATTERN.search(body)
        if url_match:
            page_url = url_match.group(1)
        
        # Extract page ID from URL
        page_id = None
        if page_url:
            id_match = self.PAGE_ID_PATTERN.search(page_url)
            if id_match:
                page_id = id_match.group(1)
        
        return page_title, page_url, page_id
    
    def _extract_content_preview(self, body: str) -> str:
        """Extract a content preview from the email body."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', body)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Unescape HTML entities
        text = unescape(text)
        # Take first 500 chars
        return text[:500].strip()
    
    def _extract_workspace(self, body: str, from_header: str) -> Optional[str]:
        """Extract workspace name if available."""
        # Look for workspace patterns in body
        patterns = [
            r'workspace[:\s]+([A-Za-z0-9\s]+)',
            r'in\s+([A-Za-z0-9\s]+)\s+workspace',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _extract_keywords(self, title: str, content: str) -> List[str]:
        """Extract potential keywords for cross-referencing."""
        text = f"{title} {content}".lower()
        
        # Common project/topic keywords
        keywords = []
        
        # Extract capitalized words (likely proper nouns/projects)
        caps = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', f"{title} {content}")
        keywords.extend([w.lower() for w in caps if len(w) > 2])
        
        # Look for ticket-like patterns
        ticket_patterns = [
            r'ticket[#\s]*(\d+)',
            r'issue[#\s]*(\d+)',
            r'bug[#\s]*(\d+)',
            r'#(\d+)',
        ]
        
        for pattern in ticket_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            keywords.extend([f"ticket-{m}" for m in matches])
        
        # Common tech keywords
        tech_keywords = [
            'payment', 'billing', 'api', 'database', 'migration',
            'deploy', 'bug', 'fix', 'feature', 'schema', 'order',
            'customer', 'subscription', 'invoice', 'magento', 'shopify'
        ]
        
        for kw in tech_keywords:
            if kw in text:
                keywords.append(kw)
        
        return list(set(keywords))
    
    def _cross_reference_airtable(self, update: NotionUpdate) -> List[Dict[str, Any]]:
        """Find related Airtable tickets based on keywords and content."""
        if not self.airtable_service or not self.airtable_service.is_configured():
            return []
        
        related = []
        
        # Search by keywords
        if update.keywords:
            tickets = self.airtable_service.search_by_keywords(update.keywords)
            for ticket in tickets[:5]:  # Limit to 5 results
                related.append({
                    "ticket_id": ticket.ticket_id,
                    "record_id": ticket.record_id,
                    "name": ticket.name,
                    "status": ticket.status,
                    "match_type": "keyword",
                })
        
        # Search by page title
        if update.page_title and len(update.page_title) > 3:
            # Extract potential ticket identifiers from title
            title_tickets = self.airtable_service.search_tickets(update.page_title)
            for ticket in title_tickets[:3]:
                if not any(r['record_id'] == ticket.record_id for r in related):
                    related.append({
                        "ticket_id": ticket.ticket_id,
                        "record_id": ticket.record_id,
                        "name": ticket.name,
                        "status": ticket.status,
                        "match_type": "title",
                    })
        
        return related
    
    def parse_email(self, email_data: Dict[str, Any]) -> Optional[NotionUpdate]:
        """Parse a single email into a NotionUpdate."""
        try:
            email_id = email_data.get('id', '')
            subject = email_data.get('subject', '')
            body = email_data.get('body', email_data.get('snippet', ''))
            from_header = email_data.get('from', '')
            date_str = email_data.get('date', '')
            
            # Parse date
            when = datetime.now()
            if date_str:
                try:
                    # Handle various date formats
                    for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S']:
                        try:
                            when = datetime.strptime(date_str.strip(), fmt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            
            # Extract information
            update_type = self._detect_update_type(subject, body)
            who = self._extract_who(subject, body, from_header)
            page_title, page_url, page_id = self._extract_page_info(subject, body)
            content_preview = self._extract_content_preview(body)
            workspace = self._extract_workspace(body, from_header)
            keywords = self._extract_keywords(page_title or '', content_preview)
            
            update = NotionUpdate(
                id=email_id,
                page_title=page_title or subject,
                page_url=page_url,
                page_id=page_id,
                update_type=update_type,
                who=who,
                when=when,
                content_preview=content_preview,
                workspace=workspace,
                raw_subject=subject,
                raw_body=body[:1000],
                keywords=keywords,
            )
            
            # Cross-reference with Airtable
            update.related_tickets = self._cross_reference_airtable(update)
            
            return update
            
        except Exception as e:
            print(f"Error parsing Notion email: {e}")
            return None
    
    def fetch_notion_updates(
        self,
        days_back: int = 7,
        limit: int = 50,
        update_types: Optional[List[str]] = None
    ) -> List[NotionUpdate]:
        """Fetch and parse Notion notification emails."""
        if not self.is_configured():
            return []
        
        updates = []
        
        # Build search query
        sender_query = ' OR '.join([f'from:{s}' for s in self.NOTION_SENDERS])
        date_query = f'newer_than:{days_back}d'
        query = f'({sender_query}) {date_query}'
        
        try:
            # Search Gmail
            emails = self.gmail_service.search_emails(query, max_results=limit)
            
            for email in emails:
                update = self.parse_email(email)
                if update:
                    # Filter by type if specified
                    if update_types and update.update_type not in update_types:
                        continue
                    updates.append(update)
            
            # Sort by date (newest first)
            updates.sort(key=lambda x: x.when, reverse=True)
            
        except Exception as e:
            print(f"Error fetching Notion updates: {e}")
        
        return updates
    
    def get_updates_summary(self, days_back: int = 7) -> Dict[str, Any]:
        """Get a summary of Notion updates."""
        updates = self.fetch_notion_updates(days_back=days_back)
        
        # Group by type
        by_type = {}
        for update in updates:
            t = update.update_type
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(update)
        
        # Group by who
        by_person = {}
        for update in updates:
            who = update.who
            if who not in by_person:
                by_person[who] = []
            by_person[who].append(update)
        
        # Group by page
        by_page = {}
        for update in updates:
            title = update.page_title
            if title not in by_page:
                by_page[title] = []
            by_page[title].append(update)
        
        # Find related tickets
        all_tickets = []
        for update in updates:
            for ticket in update.related_tickets:
                if not any(t['record_id'] == ticket['record_id'] for t in all_tickets):
                    all_tickets.append(ticket)
        
        return {
            "total_updates": len(updates),
            "days_covered": days_back,
            "by_type": {k: len(v) for k, v in by_type.items()},
            "by_person": {k: len(v) for k, v in by_person.items()},
            "top_pages": sorted(
                [(k, len(v)) for k, v in by_page.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10],
            "related_airtable_tickets": all_tickets[:10],
            "recent_updates": [u.to_dict() for u in updates[:10]],
        }
    
    def search_notion_updates(
        self,
        query: str,
        days_back: int = 30
    ) -> List[NotionUpdate]:
        """Search Notion updates by keyword."""
        updates = self.fetch_notion_updates(days_back=days_back, limit=100)
        query_lower = query.lower()
        
        results = []
        for update in updates:
            searchable = f"{update.page_title} {update.content_preview} {update.who}".lower()
            if query_lower in searchable:
                results.append(update)
        
        return results


# Singleton instance
_notion_parser: Optional[NotionEmailParser] = None


def get_notion_email_parser() -> NotionEmailParser:
    """Get the singleton Notion email parser instance."""
    global _notion_parser
    if _notion_parser is None:
        _notion_parser = NotionEmailParser()
    return _notion_parser
