"""
Canned Response System

Agents can ONLY send pre-approved responses from this registry.
This prevents agents from crafting arbitrary messages that could:
- Damage client relationships
- Expose sensitive information
- Make unauthorized commitments

Responses can be:
- Static templates
- Templates with variable substitution
- Approved by category (e.g., "status_update", "meeting_request")
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field, asdict
from enum import Enum


# Configuration
SERVICES_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
RESPONSES_DIR = Path(os.getenv("CANNED_RESPONSES_DIR", str(ORCHESTRATOR_ROOT / "data" / "canned_responses")))


class ResponseCategory(Enum):
    """Categories of canned responses."""
    STATUS_UPDATE = "status_update"
    MEETING_REQUEST = "meeting_request"
    MEETING_CONFIRMATION = "meeting_confirmation"
    MEETING_RESCHEDULE = "meeting_reschedule"
    PROJECT_UPDATE = "project_update"
    INVOICE_REMINDER = "invoice_reminder"
    THANK_YOU = "thank_you"
    ACKNOWLEDGMENT = "acknowledgment"
    QUESTION = "question"
    DELAY_NOTIFICATION = "delay_notification"
    COMPLETION_NOTICE = "completion_notice"
    ERROR_REPORT = "error_report"
    CUSTOM = "custom"  # Requires explicit approval


class ResponseChannel(Enum):
    """Where the response can be used."""
    EMAIL = "email"
    SLACK = "slack"
    BOTH = "both"


@dataclass
class CannedResponse:
    """A pre-approved response template."""
    id: str
    name: str
    category: ResponseCategory
    channel: ResponseChannel
    subject_template: Optional[str]  # For emails
    body_template: str
    variables: List[str]  # Required variables like {client_name}, {project_name}
    created_at: str
    created_by: str
    approved: bool = True
    use_count: int = 0
    last_used: Optional[str] = None
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["channel"] = self.channel.value
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CannedResponse":
        data = data.copy()
        data["category"] = ResponseCategory(data["category"])
        data["channel"] = ResponseChannel(data["channel"])
        return cls(**data)
    
    def render(self, variables: Dict[str, str]) -> tuple[Optional[str], str]:
        """
        Render the template with provided variables.
        Returns (subject, body) tuple.
        Raises ValueError if required variables are missing.
        """
        missing = set(self.variables) - set(variables.keys())
        if missing:
            raise ValueError(f"Missing required variables: {missing}")
        
        subject = None
        if self.subject_template:
            subject = self.subject_template
            for key, value in variables.items():
                subject = subject.replace(f"{{{key}}}", str(value))
        
        body = self.body_template
        for key, value in variables.items():
            body = body.replace(f"{{{key}}}", str(value))
        
        return subject, body
    
    def extract_variables(self) -> List[str]:
        """Extract variable names from templates."""
        pattern = r'\{(\w+)\}'
        vars_set = set()
        
        if self.subject_template:
            vars_set.update(re.findall(pattern, self.subject_template))
        vars_set.update(re.findall(pattern, self.body_template))
        
        return list(vars_set)


class CannedResponseRegistry:
    """Manages pre-approved response templates."""
    
    _instance: Optional["CannedResponseRegistry"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.responses: Dict[str, CannedResponse] = {}
        
        RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
        self._load()
        
        # Initialize with default responses if empty
        if not self.responses:
            self._init_defaults()
    
    def _load(self):
        """Load responses from disk."""
        responses_file = RESPONSES_DIR / "responses.json"
        if responses_file.exists():
            try:
                with open(responses_file) as f:
                    data = json.load(f)
                for resp_data in data.get("responses", []):
                    resp = CannedResponse.from_dict(resp_data)
                    self.responses[resp.id] = resp
            except Exception as e:
                print(f"Error loading canned responses: {e}")
    
    def _save(self):
        """Save responses to disk."""
        responses_file = RESPONSES_DIR / "responses.json"
        data = {
            "updated_at": datetime.utcnow().isoformat(),
            "responses": [r.to_dict() for r in self.responses.values()]
        }
        with open(responses_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _init_defaults(self):
        """Initialize with common default responses."""
        defaults = [
            CannedResponse(
                id="ack-received",
                name="Acknowledge Receipt",
                category=ResponseCategory.ACKNOWLEDGMENT,
                channel=ResponseChannel.BOTH,
                subject_template="Re: {original_subject}",
                body_template="Hi {recipient_name},\n\nThank you for your message. I've received it and will review shortly.\n\nBest,\n{sender_name}",
                variables=["recipient_name", "sender_name", "original_subject"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="status-working",
                name="Status Update - Working On It",
                category=ResponseCategory.STATUS_UPDATE,
                channel=ResponseChannel.BOTH,
                subject_template="Update: {project_name}",
                body_template="Hi {recipient_name},\n\nQuick update on {project_name}: I'm currently working on {task_description}. Expected completion: {eta}.\n\nLet me know if you have any questions.\n\nBest,\n{sender_name}",
                variables=["recipient_name", "project_name", "task_description", "eta", "sender_name"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="status-completed",
                name="Task Completed",
                category=ResponseCategory.COMPLETION_NOTICE,
                channel=ResponseChannel.BOTH,
                subject_template="Completed: {task_name}",
                body_template="Hi {recipient_name},\n\nI've completed {task_name} for {project_name}.\n\n{details}\n\nPlease review and let me know if any changes are needed.\n\nBest,\n{sender_name}",
                variables=["recipient_name", "task_name", "project_name", "details", "sender_name"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="delay-notify",
                name="Delay Notification",
                category=ResponseCategory.DELAY_NOTIFICATION,
                channel=ResponseChannel.BOTH,
                subject_template="Update: {project_name} - Timeline Adjustment",
                body_template="Hi {recipient_name},\n\nI wanted to let you know about a timeline adjustment for {project_name}.\n\nOriginal deadline: {original_deadline}\nNew expected completion: {new_deadline}\nReason: {reason}\n\nI apologize for any inconvenience. Please let me know if this impacts your plans.\n\nBest,\n{sender_name}",
                variables=["recipient_name", "project_name", "original_deadline", "new_deadline", "reason", "sender_name"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="meeting-request",
                name="Meeting Request",
                category=ResponseCategory.MEETING_REQUEST,
                channel=ResponseChannel.EMAIL,
                subject_template="Meeting Request: {topic}",
                body_template="Hi {recipient_name},\n\nI'd like to schedule a meeting to discuss {topic}.\n\nProposed times:\n{proposed_times}\n\nDuration: {duration}\n\nPlease let me know which time works best for you.\n\nBest,\n{sender_name}",
                variables=["recipient_name", "topic", "proposed_times", "duration", "sender_name"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="invoice-reminder",
                name="Invoice Reminder",
                category=ResponseCategory.INVOICE_REMINDER,
                channel=ResponseChannel.EMAIL,
                subject_template="Reminder: Invoice #{invoice_number}",
                body_template="Hi {recipient_name},\n\nThis is a friendly reminder that Invoice #{invoice_number} for ${amount} is due on {due_date}.\n\nIf you've already sent payment, please disregard this message.\n\nPayment details are included in the original invoice. Please let me know if you have any questions.\n\nBest,\n{sender_name}",
                variables=["recipient_name", "invoice_number", "amount", "due_date", "sender_name"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="thank-you-general",
                name="Thank You - General",
                category=ResponseCategory.THANK_YOU,
                channel=ResponseChannel.BOTH,
                subject_template="Thank you!",
                body_template="Hi {recipient_name},\n\nThank you for {reason}. I really appreciate it!\n\nBest,\n{sender_name}",
                variables=["recipient_name", "reason", "sender_name"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="slack-status",
                name="Slack Status Update",
                category=ResponseCategory.STATUS_UPDATE,
                channel=ResponseChannel.SLACK,
                subject_template=None,
                body_template="📊 *{project_name} Update*\n\n{status_emoji} {task_name}: {status}\n\n{details}",
                variables=["project_name", "task_name", "status", "status_emoji", "details"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
            CannedResponse(
                id="slack-question",
                name="Slack Question",
                category=ResponseCategory.QUESTION,
                channel=ResponseChannel.SLACK,
                subject_template=None,
                body_template="Hey {recipient_name}, quick question about {topic}:\n\n{question}",
                variables=["recipient_name", "topic", "question"],
                created_at=datetime.utcnow().isoformat(),
                created_by="system",
            ),
        ]
        
        for resp in defaults:
            self.responses[resp.id] = resp
        
        self._save()
    
    def get(self, response_id: str) -> Optional[CannedResponse]:
        """Get a response by ID."""
        return self.responses.get(response_id)
    
    def get_by_category(self, category: ResponseCategory) -> List[CannedResponse]:
        """Get all responses in a category."""
        return [r for r in self.responses.values() if r.category == category and r.approved]
    
    def get_for_channel(self, channel: ResponseChannel) -> List[CannedResponse]:
        """Get all responses usable on a channel."""
        return [
            r for r in self.responses.values()
            if r.approved and (r.channel == channel or r.channel == ResponseChannel.BOTH)
        ]
    
    def add(
        self,
        id: str,
        name: str,
        category: ResponseCategory,
        channel: ResponseChannel,
        body_template: str,
        subject_template: str = None,
        created_by: str = "human",
        approved: bool = False,  # New responses require approval
        notes: str = "",
    ) -> CannedResponse:
        """Add a new canned response."""
        # Extract variables from templates
        pattern = r'\{(\w+)\}'
        variables = set()
        if subject_template:
            variables.update(re.findall(pattern, subject_template))
        variables.update(re.findall(pattern, body_template))
        
        resp = CannedResponse(
            id=id,
            name=name,
            category=category,
            channel=channel,
            subject_template=subject_template,
            body_template=body_template,
            variables=list(variables),
            created_at=datetime.utcnow().isoformat(),
            created_by=created_by,
            approved=approved,
            notes=notes,
        )
        
        self.responses[id] = resp
        self._save()
        return resp
    
    def approve(self, response_id: str) -> Optional[CannedResponse]:
        """Approve a response for use."""
        resp = self.responses.get(response_id)
        if resp:
            resp.approved = True
            self._save()
        return resp
    
    def use(self, response_id: str, variables: Dict[str, str]) -> tuple[Optional[str], str]:
        """
        Use a canned response with provided variables.
        Returns (subject, body) tuple.
        Raises ValueError if response not found or not approved.
        """
        resp = self.responses.get(response_id)
        if not resp:
            raise ValueError(f"Response '{response_id}' not found")
        if not resp.approved:
            raise ValueError(f"Response '{response_id}' is not approved for use")
        
        # Render and track usage
        subject, body = resp.render(variables)
        resp.use_count += 1
        resp.last_used = datetime.utcnow().isoformat()
        self._save()
        
        return subject, body
    
    def list_all(self, approved_only: bool = True) -> List[CannedResponse]:
        """List all responses."""
        if approved_only:
            return [r for r in self.responses.values() if r.approved]
        return list(self.responses.values())
    
    def search(self, query: str) -> List[CannedResponse]:
        """Search responses by name or content."""
        query = query.lower()
        return [
            r for r in self.responses.values()
            if r.approved and (
                query in r.name.lower() or
                query in r.body_template.lower() or
                (r.subject_template and query in r.subject_template.lower())
            )
        ]


# Global access
_registry: Optional[CannedResponseRegistry] = None


def get_response_registry() -> CannedResponseRegistry:
    """Get the global canned response registry."""
    global _registry
    if _registry is None:
        _registry = CannedResponseRegistry()
    return _registry


def use_canned_response(response_id: str, variables: Dict[str, str]) -> tuple[Optional[str], str]:
    """Convenience function to use a canned response."""
    return get_response_registry().use(response_id, variables)
