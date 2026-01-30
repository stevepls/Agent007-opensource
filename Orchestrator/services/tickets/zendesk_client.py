"""
Zendesk API Client

Python wrapper around the DevOps Zendesk shell library.
Provides typed interfaces for ticket management.

Required env vars:
- ZENDESK_EMAIL
- ZENDESK_API_TOKEN
- ZENDESK_SUBDOMAIN
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

# DevOps library path
DEVOPS_ROOT = Path(__file__).parent.parent.parent.parent / "DevOps"
ZENDESK_LIB = DEVOPS_ROOT / "lib" / "tickets" / "zendesk.sh"


@dataclass
class ZendeskTicket:
    """Represents a Zendesk ticket."""
    id: int
    subject: str
    description: str
    status: str
    priority: str
    requester_email: str
    assignee_email: Optional[str]
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    url: str
    organization_id: Optional[int] = None
    custom_fields: Dict[str, Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZendeskTicket":
        ticket = data.get("ticket", data)
        return cls(
            id=ticket["id"],
            subject=ticket.get("subject", ""),
            description=ticket.get("description", ""),
            status=ticket.get("status", "new"),
            priority=ticket.get("priority", "normal"),
            requester_email=ticket.get("requester", {}).get("email", ""),
            assignee_email=ticket.get("assignee", {}).get("email"),
            tags=ticket.get("tags", []),
            created_at=datetime.fromisoformat(
                ticket.get("created_at", "").replace("Z", "+00:00")
            ) if ticket.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(
                ticket.get("updated_at", "").replace("Z", "+00:00")
            ) if ticket.get("updated_at") else datetime.now(),
            url=ticket.get("url", ""),
            organization_id=ticket.get("organization_id"),
            custom_fields=ticket.get("custom_fields"),
        )


@dataclass
class ZendeskComment:
    """Represents a Zendesk ticket comment."""
    id: int
    body: str
    author_email: str
    public: bool
    created_at: datetime


class ZendeskClient:
    """Zendesk API client."""

    def __init__(
        self,
        email: str = None,
        api_token: str = None,
        subdomain: str = None,
    ):
        self.email = email or os.getenv("ZENDESK_EMAIL")
        self.api_token = api_token or os.getenv("ZENDESK_API_TOKEN")
        self.subdomain = subdomain or os.getenv("ZENDESK_SUBDOMAIN")

        if not all([self.email, self.api_token, self.subdomain]):
            raise ValueError(
                "Missing Zendesk credentials. Set ZENDESK_EMAIL, "
                "ZENDESK_API_TOKEN, and ZENDESK_SUBDOMAIN environment variables."
            )

    def _run_shell_function(
        self,
        function: str,
        *args: str,
    ) -> Optional[str]:
        """Run a shell function from the Zendesk library."""
        if not ZENDESK_LIB.exists():
            raise FileNotFoundError(f"Zendesk library not found: {ZENDESK_LIB}")

        # Build shell command
        cmd = f"""
            source "{ZENDESK_LIB}"
            export ZENDESK_EMAIL="{self.email}"
            export ZENDESK_API_TOKEN="{self.api_token}"
            {function} {' '.join(f'"{a}"' for a in args)}
        """

        try:
            result = subprocess.run(
                ["bash", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except subprocess.TimeoutExpired:
            return None

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
    ) -> Optional[Dict]:
        """Make a direct API request using curl."""
        import base64

        auth = base64.b64encode(
            f"{self.email}/token:{self.api_token}".encode()
        ).decode()

        url = f"https://{self.subdomain}.zendesk.com/api/v2{endpoint}"

        cmd = [
            "curl", "-sS", "-X", method,
            "-H", f"Authorization: Basic {auth}",
            "-H", "Content-Type: application/json",
        ]

        if data:
            cmd.extend(["-d", json.dumps(data)])

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.stdout:
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return None

    # =========================================================================
    # Ticket Operations
    # =========================================================================

    def get_ticket(self, ticket_id: int) -> Optional[ZendeskTicket]:
        """Get a ticket by ID."""
        result = self._api_request("GET", f"/tickets/{ticket_id}.json")
        if result and "ticket" in result:
            return ZendeskTicket.from_dict(result)
        return None

    def list_tickets(
        self,
        status: str = None,
        since: str = None,
        tags: List[str] = None,
        limit: int = 100,
    ) -> List[ZendeskTicket]:
        """List tickets with optional filters."""
        query_parts = ["type:ticket"]

        if status:
            query_parts.append(f"status:{status}")
        if since:
            query_parts.append(f"updated>{since}")
        if tags:
            for tag in tags:
                query_parts.append(f"tags:{tag}")

        query = " ".join(query_parts)
        encoded = subprocess.run(
            ["python3", "-c", f"import urllib.parse; print(urllib.parse.quote('{query}'))"],
            capture_output=True, text=True
        ).stdout.strip()

        result = self._api_request(
            "GET",
            f"/search.json?query={encoded}&per_page={limit}"
        )

        tickets = []
        if result and "results" in result:
            for item in result["results"]:
                try:
                    tickets.append(ZendeskTicket.from_dict({"ticket": item}))
                except Exception:
                    pass
        return tickets

    def create_ticket(
        self,
        subject: str,
        description: str,
        priority: str = "normal",
        tags: List[str] = None,
        requester_email: str = None,
    ) -> Optional[ZendeskTicket]:
        """Create a new ticket."""
        data = {
            "ticket": {
                "subject": subject,
                "comment": {"body": description},
                "priority": priority,
            }
        }

        if tags:
            data["ticket"]["tags"] = tags
        if requester_email:
            data["ticket"]["requester"] = {"email": requester_email}

        result = self._api_request("POST", "/tickets.json", data)
        if result and "ticket" in result:
            return ZendeskTicket.from_dict(result)
        return None

    def update_ticket(
        self,
        ticket_id: int,
        status: str = None,
        priority: str = None,
        tags: List[str] = None,
        comment: str = None,
        public: bool = True,
    ) -> Optional[ZendeskTicket]:
        """Update an existing ticket."""
        data = {"ticket": {}}

        if status:
            data["ticket"]["status"] = status
        if priority:
            data["ticket"]["priority"] = priority
        if tags:
            data["ticket"]["tags"] = tags
        if comment:
            data["ticket"]["comment"] = {"body": comment, "public": public}

        result = self._api_request("PUT", f"/tickets/{ticket_id}.json", data)
        if result and "ticket" in result:
            return ZendeskTicket.from_dict(result)
        return None

    def add_comment(
        self,
        ticket_id: int,
        body: str,
        public: bool = True,
    ) -> bool:
        """Add a comment to a ticket."""
        result = self.update_ticket(ticket_id, comment=body, public=public)
        return result is not None

    def add_internal_note(self, ticket_id: int, body: str) -> bool:
        """Add an internal note (private comment) to a ticket."""
        return self.add_comment(ticket_id, body, public=False)

    # =========================================================================
    # Search & Queries
    # =========================================================================

    def search(self, query: str) -> List[ZendeskTicket]:
        """Search tickets with a raw query."""
        encoded = subprocess.run(
            ["python3", "-c", f"import urllib.parse; print(urllib.parse.quote('''{query}'''))"],
            capture_output=True, text=True
        ).stdout.strip()

        result = self._api_request("GET", f"/search.json?query={encoded}")

        tickets = []
        if result and "results" in result:
            for item in result["results"]:
                if item.get("result_type") == "ticket":
                    try:
                        tickets.append(ZendeskTicket.from_dict({"ticket": item}))
                    except Exception:
                        pass
        return tickets

    def get_open_tickets(self) -> List[ZendeskTicket]:
        """Get all open tickets."""
        return self.list_tickets(status="open")

    def get_pending_tickets(self) -> List[ZendeskTicket]:
        """Get all pending tickets."""
        return self.list_tickets(status="pending")

    def get_tickets_by_tag(self, tag: str) -> List[ZendeskTicket]:
        """Get tickets with a specific tag."""
        return self.list_tickets(tags=[tag])

    # =========================================================================
    # Comments
    # =========================================================================

    def get_comments(self, ticket_id: int) -> List[ZendeskComment]:
        """Get all comments for a ticket."""
        result = self._api_request("GET", f"/tickets/{ticket_id}/comments.json")

        comments = []
        if result and "comments" in result:
            for c in result["comments"]:
                try:
                    comments.append(ZendeskComment(
                        id=c["id"],
                        body=c.get("body", ""),
                        author_email=c.get("author", {}).get("email", ""),
                        public=c.get("public", True),
                        created_at=datetime.fromisoformat(
                            c.get("created_at", "").replace("Z", "+00:00")
                        ) if c.get("created_at") else datetime.now(),
                    ))
                except Exception:
                    pass
        return comments

    # =========================================================================
    # Connection Test
    # =========================================================================

    def test_connection(self) -> bool:
        """Test the Zendesk connection."""
        result = self._api_request("GET", "/users/me.json")
        return result is not None and "user" in result

    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get the current authenticated user."""
        result = self._api_request("GET", "/users/me.json")
        return result.get("user") if result else None


# Global instance
_client: Optional[ZendeskClient] = None


def get_zendesk_client() -> ZendeskClient:
    """Get the global Zendesk client."""
    global _client
    if _client is None:
        _client = ZendeskClient()
    return _client
