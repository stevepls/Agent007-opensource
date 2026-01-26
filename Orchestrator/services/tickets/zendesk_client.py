"""
Zendesk API Client

Python wrapper for Zendesk API operations.
Leverages existing DevOps/lib/tickets/zendesk.sh patterns.

SECURITY:
- API token from environment only
- All writes require confirmation
- Rate limiting respected
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import subprocess

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration from environment
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_API_TOKEN = os.getenv("ZENDESK_API_TOKEN")
ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN")

ZENDESK_API_VERSION = "v2"
ZENDESK_MAX_RETRIES = 3
ZENDESK_RATE_LIMIT_WAIT = 60


@dataclass
class ZendeskTicket:
    """Represents a Zendesk ticket."""
    id: int
    subject: str
    description: str
    status: str
    priority: str
    requester_id: int
    assignee_id: Optional[int]
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    url: str
    
    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "ZendeskTicket":
        return cls(
            id=data["id"],
            subject=data.get("subject", ""),
            description=data.get("description", ""),
            status=data.get("status", "new"),
            priority=data.get("priority", "normal"),
            requester_id=data.get("requester_id", 0),
            assignee_id=data.get("assignee_id"),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            url=data.get("url", ""),
        )


@dataclass
class ZendeskComment:
    """Represents a Zendesk ticket comment."""
    id: int
    body: str
    author_id: int
    public: bool
    created_at: datetime


class ZendeskClient:
    """Zendesk API client with safety controls."""
    
    def __init__(
        self,
        email: str = None,
        api_token: str = None,
        subdomain: str = None,
    ):
        self._email = email or ZENDESK_EMAIL
        self._token = api_token or ZENDESK_API_TOKEN
        self._subdomain = subdomain or ZENDESK_SUBDOMAIN
        self._session = None
    
    @property
    def is_available(self) -> bool:
        return REQUESTS_AVAILABLE and all([
            self._email,
            self._token,
            self._subdomain,
        ])
    
    @property
    def base_url(self) -> str:
        return f"https://{self._subdomain}.zendesk.com/api/{ZENDESK_API_VERSION}"
    
    @property
    def _auth_header(self) -> str:
        auth_string = f"{self._email}/token:{self._token}"
        encoded = base64.b64encode(auth_string.encode()).decode()
        return f"Basic {encoded}"
    
    def _get_session(self) -> "requests.Session":
        if not REQUESTS_AVAILABLE:
            raise ImportError("requests library required: pip install requests")
        
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
            })
        return self._session
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """Make an API request with retry logic."""
        if not self.is_available:
            raise ValueError("Zendesk not configured. Set ZENDESK_EMAIL, ZENDESK_API_TOKEN, ZENDESK_SUBDOMAIN")
        
        session = self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = session.get(url)
            elif method == "POST":
                response = session.post(url, json=data)
            elif method == "PUT":
                response = session.put(url, json=data)
            elif method == "DELETE":
                response = session.delete(url)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            # Handle rate limiting
            if response.status_code == 429:
                if retry_count < ZENDESK_MAX_RETRIES:
                    import time
                    wait_time = ZENDESK_RATE_LIMIT_WAIT * (retry_count + 1)
                    time.sleep(wait_time)
                    return self._request(method, endpoint, data, retry_count + 1)
                raise Exception("Rate limited - max retries exceeded")
            
            response.raise_for_status()
            return response.json() if response.text else {}
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Zendesk API error: {e}")
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            result = self._request("GET", "/users/me.json")
            return "user" in result
        except Exception:
            return False
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def get_ticket(self, ticket_id: int) -> Optional[ZendeskTicket]:
        """Get a single ticket by ID."""
        try:
            result = self._request("GET", f"/tickets/{ticket_id}.json")
            if "ticket" in result:
                return ZendeskTicket.from_api(result["ticket"])
        except Exception:
            pass
        return None
    
    def search_tickets(
        self,
        query: str = None,
        status: str = None,
        priority: str = None,
        tags: List[str] = None,
        since: str = None,
        limit: int = 100,
    ) -> List[ZendeskTicket]:
        """Search for tickets."""
        parts = ["type:ticket"]
        
        if query:
            parts.append(query)
        if status:
            parts.append(f"status:{status}")
        if priority:
            parts.append(f"priority:{priority}")
        if tags:
            for tag in tags:
                parts.append(f"tags:{tag}")
        if since:
            parts.append(f"updated>{since}")
        
        search_query = " ".join(parts)
        
        from urllib.parse import quote
        encoded_query = quote(search_query)
        
        result = self._request(
            "GET",
            f"/search.json?query={encoded_query}&sort_by=updated_at&sort_order=desc"
        )
        
        tickets = []
        for item in result.get("results", [])[:limit]:
            if item.get("result_type") == "ticket":
                tickets.append(ZendeskTicket.from_api(item))
        
        return tickets
    
    def get_recent_tickets(self, limit: int = 25) -> List[ZendeskTicket]:
        """Get recently updated tickets."""
        return self.search_tickets(limit=limit)
    
    def get_ticket_comments(self, ticket_id: int) -> List[ZendeskComment]:
        """Get comments for a ticket."""
        result = self._request("GET", f"/tickets/{ticket_id}/comments.json")
        
        comments = []
        for item in result.get("comments", []):
            comments.append(ZendeskComment(
                id=item["id"],
                body=item.get("body", ""),
                author_id=item.get("author_id", 0),
                public=item.get("public", True),
                created_at=datetime.fromisoformat(
                    item["created_at"].replace("Z", "+00:00")
                ),
            ))
        
        return comments
    
    # =========================================================================
    # WRITE OPERATIONS (require confirmation)
    # =========================================================================
    
    def create_ticket(
        self,
        subject: str,
        description: str,
        priority: str = "normal",
        tags: List[str] = None,
        requester_email: str = None,
    ) -> Optional[ZendeskTicket]:
        """Create a new ticket. Requires confirmation."""
        payload = {
            "ticket": {
                "subject": subject,
                "comment": {"body": description},
                "priority": priority,
            }
        }
        
        if tags:
            payload["ticket"]["tags"] = tags
        if requester_email:
            payload["ticket"]["requester"] = {"email": requester_email}
        
        result = self._request("POST", "/tickets.json", payload)
        if "ticket" in result:
            return ZendeskTicket.from_api(result["ticket"])
        return None
    
    def update_ticket(
        self,
        ticket_id: int,
        subject: str = None,
        status: str = None,
        priority: str = None,
        tags: List[str] = None,
        comment: str = None,
        public: bool = True,
    ) -> bool:
        """Update a ticket. Requires confirmation."""
        payload = {"ticket": {}}
        
        if subject:
            payload["ticket"]["subject"] = subject
        if status:
            payload["ticket"]["status"] = status
        if priority:
            payload["ticket"]["priority"] = priority
        if tags:
            payload["ticket"]["tags"] = tags
        if comment:
            payload["ticket"]["comment"] = {
                "body": comment,
                "public": public,
            }
        
        try:
            self._request("PUT", f"/tickets/{ticket_id}.json", payload)
            return True
        except Exception:
            return False
    
    def add_comment(
        self,
        ticket_id: int,
        body: str,
        public: bool = True,
    ) -> bool:
        """Add a comment to a ticket."""
        return self.update_ticket(ticket_id, comment=body, public=public)
    
    def add_internal_note(self, ticket_id: int, body: str) -> bool:
        """Add an internal note (private comment)."""
        return self.add_comment(ticket_id, body, public=False)


# Global instance
_client: Optional[ZendeskClient] = None


def get_zendesk_client() -> ZendeskClient:
    """Get the global Zendesk client."""
    global _client
    if _client is None:
        _client = ZendeskClient()
    return _client
