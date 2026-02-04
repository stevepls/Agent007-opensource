"""
Notification Hub Service

Unified notification parser that scrapes and cross-references:
- Notion email notifications (from notify@mail.notion.so)
- Slack email notifications (from notifications@slack.com)
- Airtable tickets (direct API access)

Provides a single interface for all team communications and task updates.
"""

import os
import re
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import html
from html.parser import HTMLParser


class NotificationSource(Enum):
    NOTION = "notion"
    SLACK = "slack"
    AIRTABLE = "airtable"


class NotificationType(Enum):
    MENTION = "mention"
    COMMENT = "comment"
    PAGE_EDIT = "page_edit"
    PAGE_CREATED = "page_created"
    TASK_UPDATE = "task_update"
    MESSAGE = "message"
    DM = "dm"
    CHANNEL_MESSAGE = "channel_message"
    TICKET_UPDATE = "ticket_update"
    INVITATION = "invitation"
    UNKNOWN = "unknown"


@dataclass
class Notification:
    """Unified notification object."""
    id: str
    source: NotificationSource
    type: NotificationType
    title: str
    content: str
    sender: str
    sender_email: Optional[str] = None
    timestamp: Optional[datetime] = None
    url: Optional[str] = None
    page_or_channel: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # Cross-reference fields
    related_ticket_id: Optional[str] = None
    related_ticket_name: Optional[str] = None
    related_project: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source.value,
            "type": self.type.value,
            "title": self.title,
            "content": self.content,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "url": self.url,
            "page_or_channel": self.page_or_channel,
            "related_ticket_id": self.related_ticket_id,
            "related_ticket_name": self.related_ticket_name,
            "related_project": self.related_project,
        }


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        
    def handle_data(self, data):
        self.text_parts.append(data)
        
    def get_text(self) -> str:
        return ' '.join(self.text_parts).strip()


def extract_text_from_html(html_content: str) -> str:
    """Extract plain text from HTML content."""
    if not html_content:
        return ""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html.unescape(html_content))
        return parser.get_text()
    except:
        # Fallback: strip tags with regex
        return re.sub(r'<[^>]+>', '', html_content)


class NotificationHub:
    """
    Unified notification hub that aggregates notifications from multiple sources.
    """
    
    def __init__(self, gmail_client=None):
        """
        Initialize the notification hub.
        
        Args:
            gmail_client: Optional Gmail client instance. If not provided,
                         will try to import from services.gmail
        """
        self.gmail_client = gmail_client
        self._airtable_config = self._load_airtable_config()
        self._notifications_cache: List[Notification] = []
        self._last_fetch: Optional[datetime] = None
        
        # Known team members for cross-referencing
        self.team_members = {
            "erik": {"email": "erik@theforgelab.com", "projects": ["cysterhood", "nemesis"]},
            "andrew": {"email": "andrew@collegewise.com", "projects": ["collegewise", "cysterhood"]},
            "robbie": {"email": "robbie@collegewise.com", "projects": ["collegewise"]},
            "sirak": {"email": "sirak@collegewise.com", "projects": ["collegewise"]},
            "sean": {"email": "sean@collegewise.com", "projects": ["collegewise"]},
        }
    
    def _load_airtable_config(self) -> Dict[str, str]:
        """Load Airtable configuration from environment."""
        return {
            "base_id": os.getenv("AIRTABLE_BASE_ID", ""),
            "table_id": os.getenv("AIRTABLE_TABLE_ID", ""),
            "token": os.getenv("AIRTABLE_PERSONAL_ACCESS_TOKEN", ""),
        }
    
    def _get_gmail_client(self):
        """Get or create Gmail client."""
        if self.gmail_client:
            return self.gmail_client
        try:
            from services.gmail import GmailClient
            self.gmail_client = GmailClient()
            self.gmail_client.authenticate()
            return self.gmail_client
        except Exception as e:
            print(f"Warning: Could not initialize Gmail client: {e}")
            return None
    
    # =========================================================================
    # NOTION EMAIL PARSING
    # =========================================================================
    
    def fetch_notion_notifications(self, days: int = 7) -> List[Notification]:
        """
        Fetch and parse Notion email notifications.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of parsed Notification objects
        """
        gmail = self._get_gmail_client()
        if not gmail:
            return []
        
        notifications = []
        
        # Search for Notion emails
        query = f"from:notify@mail.notion.so newer_than:{days}d"
        try:
            emails = gmail.search_emails(query, max_results=50)
        except Exception as e:
            print(f"Error fetching Notion emails: {e}")
            return []
        
        for email in emails:
            notification = self._parse_notion_email(email)
            if notification:
                notifications.append(notification)
        
        return notifications
    
    def _parse_notion_email(self, email: Dict[str, Any]) -> Optional[Notification]:
        """Parse a Notion notification email."""
        try:
            subject = email.get("subject", "")
            body = email.get("body", "") or email.get("snippet", "")
            sender = email.get("from", "Notion")
            date_str = email.get("date", "")
            message_id = email.get("id", "")
            
            # Extract text from HTML if needed
            if "<" in body:
                body = extract_text_from_html(body)
            
            # Determine notification type from subject
            notif_type = NotificationType.UNKNOWN
            page_name = ""
            
            if "mentioned you" in subject.lower():
                notif_type = NotificationType.MENTION
            elif "commented" in subject.lower():
                notif_type = NotificationType.COMMENT
            elif "edited" in subject.lower() or "updated" in subject.lower():
                notif_type = NotificationType.PAGE_EDIT
            elif "created" in subject.lower():
                notif_type = NotificationType.PAGE_CREATED
            elif "invited you" in subject.lower():
                notif_type = NotificationType.INVITATION
            
            # Extract page name from subject
            # Common patterns: "X mentioned you in PageName", "X commented on PageName"
            page_match = re.search(r'(?:in|on)\s+"?([^"]+)"?$', subject)
            if page_match:
                page_name = page_match.group(1).strip()
            
            # Extract sender name
            sender_name = "Unknown"
            sender_match = re.match(r'^([^<]+)', sender)
            if sender_match:
                sender_name = sender_match.group(1).strip()
            
            # Also check subject for sender
            subj_sender_match = re.match(r'^([A-Za-z\s]+)\s+(?:mentioned|commented|edited|created|invited)', subject)
            if subj_sender_match:
                sender_name = subj_sender_match.group(1).strip()
            
            # Extract Notion URL from body
            url = None
            url_match = re.search(r'(https://(?:www\.)?notion\.so/[^\s<>"]+)', body)
            if url_match:
                url = url_match.group(1)
            
            # Parse timestamp
            timestamp = None
            if date_str:
                try:
                    # Handle various date formats
                    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"]:
                        try:
                            timestamp = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            return Notification(
                id=f"notion_{message_id}",
                source=NotificationSource.NOTION,
                type=notif_type,
                title=subject,
                content=body[:500] if body else "",  # Truncate long content
                sender=sender_name,
                timestamp=timestamp,
                url=url,
                page_or_channel=page_name,
                raw_data={"email_id": message_id, "subject": subject},
            )
            
        except Exception as e:
            print(f"Error parsing Notion email: {e}")
            return None
    
    # =========================================================================
    # SLACK EMAIL PARSING
    # =========================================================================
    
    def fetch_slack_notifications(self, days: int = 7) -> List[Notification]:
        """
        Fetch and parse Slack email notifications.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of parsed Notification objects
        """
        gmail = self._get_gmail_client()
        if not gmail:
            return []
        
        notifications = []
        
        # Search for Slack emails
        query = f"from:notifications@slack.com newer_than:{days}d"
        try:
            emails = gmail.search_emails(query, max_results=50)
        except Exception as e:
            print(f"Error fetching Slack emails: {e}")
            return []
        
        for email in emails:
            notification = self._parse_slack_email(email)
            if notification:
                notifications.append(notification)
        
        return notifications
    
    def _parse_slack_email(self, email: Dict[str, Any]) -> Optional[Notification]:
        """Parse a Slack notification email."""
        try:
            subject = email.get("subject", "")
            body = email.get("body", "") or email.get("snippet", "")
            date_str = email.get("date", "")
            message_id = email.get("id", "")
            
            # Extract text from HTML
            if "<" in body:
                body = extract_text_from_html(body)
            
            # Determine notification type
            notif_type = NotificationType.MESSAGE
            channel = ""
            sender_name = ""
            
            # Pattern: "[Workspace] Message from Sender in #channel"
            # or "[Workspace] Direct message from Sender"
            
            if "direct message" in subject.lower():
                notif_type = NotificationType.DM
                dm_match = re.search(r'from\s+([^:]+)', subject, re.IGNORECASE)
                if dm_match:
                    sender_name = dm_match.group(1).strip()
            elif "#" in subject:
                notif_type = NotificationType.CHANNEL_MESSAGE
                channel_match = re.search(r'#(\w+[-\w]*)', subject)
                if channel_match:
                    channel = channel_match.group(1)
                sender_match = re.search(r'from\s+([^i]+)\s+in', subject, re.IGNORECASE)
                if sender_match:
                    sender_name = sender_match.group(1).strip()
            elif "mentioned you" in subject.lower():
                notif_type = NotificationType.MENTION
            
            # Parse timestamp
            timestamp = None
            if date_str:
                try:
                    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"]:
                        try:
                            timestamp = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            return Notification(
                id=f"slack_{message_id}",
                source=NotificationSource.SLACK,
                type=notif_type,
                title=subject,
                content=body[:500] if body else "",
                sender=sender_name or "Slack",
                timestamp=timestamp,
                page_or_channel=channel,
                raw_data={"email_id": message_id, "subject": subject},
            )
            
        except Exception as e:
            print(f"Error parsing Slack email: {e}")
            return None
    
    # =========================================================================
    # AIRTABLE INTEGRATION
    # =========================================================================
    
    def fetch_airtable_tickets(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch tickets from Airtable.
        
        Args:
            status_filter: Optional status to filter by (e.g., "In Progress")
            
        Returns:
            List of ticket dictionaries
        """
        if not self._airtable_config["token"]:
            print("Warning: Airtable not configured")
            return []
        
        base_id = self._airtable_config["base_id"]
        table_id = self._airtable_config["table_id"]
        token = self._airtable_config["token"]
        
        url = f"https://api.airtable.com/v0/{base_id}/{table_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        all_records = []
        offset = None
        
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            if status_filter:
                params["filterByFormula"] = f"FIND('{status_filter}', {{Ticket Status}})"
            
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                all_records.extend(data.get("records", []))
                offset = data.get("offset")
                
                if not offset:
                    break
                    
            except Exception as e:
                print(f"Error fetching Airtable tickets: {e}")
                break
        
        return all_records
    
    def get_ticket_by_name(self, name_fragment: str) -> Optional[Dict[str, Any]]:
        """
        Find a ticket by partial name match.
        
        Args:
            name_fragment: Part of the ticket name to search for
            
        Returns:
            Ticket record or None
        """
        tickets = self.fetch_airtable_tickets()
        name_lower = name_fragment.lower()
        
        for ticket in tickets:
            ticket_name = ticket.get("fields", {}).get("Ticket Name", "")
            if name_lower in ticket_name.lower():
                return ticket
        
        return None
    
    def convert_ticket_to_notification(self, ticket: Dict[str, Any]) -> Notification:
        """Convert an Airtable ticket to a Notification object."""
        fields = ticket.get("fields", {})
        record_id = ticket.get("id", "")
        
        # Get ticket details
        ticket_name = fields.get("Ticket Name", "Untitled")
        status = fields.get("Ticket Status", "Unknown")
        description = fields.get("Issue Description", "")
        priority = fields.get("Priority", "")
        
        # Get assignees
        assigned_to = fields.get("Assigned To", [])
        assignee_names = []
        for assignee in assigned_to:
            if isinstance(assignee, dict):
                assignee_names.append(assignee.get("name", "Unknown"))
        
        return Notification(
            id=f"airtable_{record_id}",
            source=NotificationSource.AIRTABLE,
            type=NotificationType.TICKET_UPDATE,
            title=f"[{status}] {ticket_name}",
            content=description[:500] if description else "",
            sender=", ".join(assignee_names) if assignee_names else "Unassigned",
            raw_data={
                "record_id": record_id,
                "status": status,
                "priority": priority,
                "full_fields": fields,
            },
            related_ticket_id=record_id,
            related_ticket_name=ticket_name,
        )
    
    # =========================================================================
    # CROSS-REFERENCING
    # =========================================================================
    
    def cross_reference_notification(self, notification: Notification) -> Notification:
        """
        Cross-reference a notification with Airtable tickets.
        
        Looks for ticket references in the notification content and links them.
        
        Args:
            notification: The notification to cross-reference
            
        Returns:
            Updated notification with ticket references
        """
        # Skip if already from Airtable
        if notification.source == NotificationSource.AIRTABLE:
            return notification
        
        # Combine title and content for searching
        search_text = f"{notification.title} {notification.content}".lower()
        
        # Try to find related tickets
        tickets = self.fetch_airtable_tickets()
        
        for ticket in tickets:
            ticket_name = ticket.get("fields", {}).get("Ticket Name", "")
            if not ticket_name:
                continue
            
            # Check if ticket name appears in notification
            # Use fuzzy matching - check for key words
            ticket_words = [w for w in ticket_name.lower().split() if len(w) > 3]
            matches = sum(1 for w in ticket_words if w in search_text)
            
            if matches >= 2 or ticket_name.lower() in search_text:
                notification.related_ticket_id = ticket.get("id")
                notification.related_ticket_name = ticket_name
                break
        
        # Try to identify project from sender/content
        for member, info in self.team_members.items():
            if member in notification.sender.lower():
                if info.get("projects"):
                    notification.related_project = info["projects"][0]
                break
        
        return notification
    
    # =========================================================================
    # UNIFIED FETCH
    # =========================================================================
    
    def fetch_all_notifications(
        self,
        days: int = 7,
        include_notion: bool = True,
        include_slack: bool = True,
        include_airtable: bool = True,
        cross_reference: bool = True,
    ) -> List[Notification]:
        """
        Fetch all notifications from all sources.
        
        Args:
            days: Number of days to look back for emails
            include_notion: Include Notion notifications
            include_slack: Include Slack notifications
            include_airtable: Include Airtable tickets
            cross_reference: Cross-reference notifications with tickets
            
        Returns:
            List of all notifications, sorted by timestamp
        """
        all_notifications = []
        
        # Fetch from each source
        if include_notion:
            notion_notifs = self.fetch_notion_notifications(days)
            all_notifications.extend(notion_notifs)
            print(f"📝 Fetched {len(notion_notifs)} Notion notifications")
        
        if include_slack:
            slack_notifs = self.fetch_slack_notifications(days)
            all_notifications.extend(slack_notifs)
            print(f"💬 Fetched {len(slack_notifs)} Slack notifications")
        
        if include_airtable:
            tickets = self.fetch_airtable_tickets()
            # Only include active tickets
            active_statuses = ["Assigned", "In Progress", "Waiting"]
            for ticket in tickets:
                status = ticket.get("fields", {}).get("Ticket Status", "")
                if any(s in status for s in active_statuses):
                    notif = self.convert_ticket_to_notification(ticket)
                    all_notifications.append(notif)
            print(f"🎫 Fetched {len(tickets)} Airtable tickets")
        
        # Cross-reference
        if cross_reference:
            all_notifications = [
                self.cross_reference_notification(n) for n in all_notifications
            ]
        
        # Sort by timestamp (most recent first)
        all_notifications.sort(
            key=lambda n: n.timestamp or datetime.min,
            reverse=True
        )
        
        # Cache results
        self._notifications_cache = all_notifications
        self._last_fetch = datetime.now()
        
        return all_notifications
    
    def get_notifications_summary(self, notifications: List[Notification]) -> Dict[str, Any]:
        """
        Generate a summary of notifications.
        
        Args:
            notifications: List of notifications to summarize
            
        Returns:
            Summary dictionary
        """
        summary = {
            "total": len(notifications),
            "by_source": {},
            "by_type": {},
            "by_sender": {},
            "by_project": {},
            "recent_mentions": [],
            "active_tickets": [],
        }
        
        for notif in notifications:
            # Count by source
            source = notif.source.value
            summary["by_source"][source] = summary["by_source"].get(source, 0) + 1
            
            # Count by type
            ntype = notif.type.value
            summary["by_type"][ntype] = summary["by_type"].get(ntype, 0) + 1
            
            # Count by sender
            sender = notif.sender
            summary["by_sender"][sender] = summary["by_sender"].get(sender, 0) + 1
            
            # Count by project
            if notif.related_project:
                proj = notif.related_project
                summary["by_project"][proj] = summary["by_project"].get(proj, 0) + 1
            
            # Collect mentions
            if notif.type == NotificationType.MENTION:
                summary["recent_mentions"].append({
                    "title": notif.title,
                    "sender": notif.sender,
                    "source": notif.source.value,
                })
            
            # Collect active tickets
            if notif.source == NotificationSource.AIRTABLE:
                summary["active_tickets"].append({
                    "title": notif.title,
                    "ticket_id": notif.related_ticket_id,
                })
        
        # Limit lists
        summary["recent_mentions"] = summary["recent_mentions"][:5]
        summary["active_tickets"] = summary["active_tickets"][:10]
        
        return summary
    
    def search_notifications(
        self,
        query: str,
        notifications: Optional[List[Notification]] = None,
    ) -> List[Notification]:
        """
        Search notifications by keyword.
        
        Args:
            query: Search query
            notifications: List to search (uses cache if not provided)
            
        Returns:
            Matching notifications
        """
        if notifications is None:
            notifications = self._notifications_cache
        
        query_lower = query.lower()
        
        return [
            n for n in notifications
            if query_lower in n.title.lower()
            or query_lower in n.content.lower()
            or query_lower in n.sender.lower()
            or (n.page_or_channel and query_lower in n.page_or_channel.lower())
        ]


# =========================================================================
# SINGLETON INSTANCE
# =========================================================================

_notification_hub: Optional[NotificationHub] = None


def get_notification_hub() -> NotificationHub:
    """Get the singleton NotificationHub instance."""
    global _notification_hub
    if _notification_hub is None:
        _notification_hub = NotificationHub()
    return _notification_hub


# =========================================================================
# TOOL FUNCTIONS (for tool_registry)
# =========================================================================

def notification_fetch_all(days: int = 7) -> Dict[str, Any]:
    """
    Fetch all notifications from Notion, Slack, and Airtable.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Summary and notifications
    """
    hub = get_notification_hub()
    notifications = hub.fetch_all_notifications(days=days)
    summary = hub.get_notifications_summary(notifications)
    
    return {
        "summary": summary,
        "notifications": [n.to_dict() for n in notifications[:20]],  # Limit response
    }


def notification_search(query: str, days: int = 7) -> Dict[str, Any]:
    """
    Search notifications across all sources.
    
    Args:
        query: Search query
        days: Days to look back if cache is stale
        
    Returns:
        Matching notifications
    """
    hub = get_notification_hub()
    
    # Refresh if needed
    if not hub._notifications_cache or not hub._last_fetch or \
       (datetime.now() - hub._last_fetch).seconds > 300:
        hub.fetch_all_notifications(days=days)
    
    results = hub.search_notifications(query)
    
    return {
        "query": query,
        "count": len(results),
        "results": [n.to_dict() for n in results[:15]],
    }


def notion_get_updates(days: int = 7) -> Dict[str, Any]:
    """
    Get Notion updates from email notifications.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Notion notifications grouped by type
    """
    hub = get_notification_hub()
    notifications = hub.fetch_notion_notifications(days=days)
    
    # Group by type
    by_type = {}
    for notif in notifications:
        ntype = notif.type.value
        if ntype not in by_type:
            by_type[ntype] = []
        by_type[ntype].append(notif.to_dict())
    
    return {
        "total": len(notifications),
        "by_type": by_type,
        "pages_updated": list(set(n.page_or_channel for n in notifications if n.page_or_channel)),
    }


def slack_get_updates(days: int = 7) -> Dict[str, Any]:
    """
    Get Slack updates from email notifications.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Slack notifications grouped by channel
    """
    hub = get_notification_hub()
    notifications = hub.fetch_slack_notifications(days=days)
    
    # Group by channel
    by_channel = {}
    dms = []
    
    for notif in notifications:
        if notif.type == NotificationType.DM:
            dms.append(notif.to_dict())
        elif notif.page_or_channel:
            channel = notif.page_or_channel
            if channel not in by_channel:
                by_channel[channel] = []
            by_channel[channel].append(notif.to_dict())
    
    return {
        "total": len(notifications),
        "by_channel": by_channel,
        "direct_messages": dms[:10],
    }


def airtable_get_tickets(status: Optional[str] = None) -> Dict[str, Any]:
    """
    Get Airtable tickets.
    
    Args:
        status: Optional status filter (e.g., "In Progress")
        
    Returns:
        Tickets list with summary
    """
    hub = get_notification_hub()
    tickets = hub.fetch_airtable_tickets(status_filter=status)
    
    # Convert to notifications for consistent format
    notifications = [hub.convert_ticket_to_notification(t) for t in tickets]
    
    # Group by status
    by_status = {}
    for ticket in tickets:
        status = ticket.get("fields", {}).get("Ticket Status", "Unknown")
        if status not in by_status:
            by_status[status] = []
        by_status[status].append({
            "id": ticket.get("id"),
            "name": ticket.get("fields", {}).get("Ticket Name", ""),
            "priority": ticket.get("fields", {}).get("Priority", ""),
        })
    
    return {
        "total": len(tickets),
        "by_status": by_status,
        "tickets": [n.to_dict() for n in notifications[:20]],
    }


if __name__ == "__main__":
    # Test the notification hub
    hub = get_notification_hub()
    
    print("Fetching all notifications...")
    notifications = hub.fetch_all_notifications(days=7)
    
    print(f"\nTotal: {len(notifications)} notifications")
    
    summary = hub.get_notifications_summary(notifications)
    print(f"\nBy source: {summary['by_source']}")
    print(f"By type: {summary['by_type']}")
    print(f"\nRecent mentions: {len(summary['recent_mentions'])}")
    print(f"Active tickets: {len(summary['active_tickets'])}")
