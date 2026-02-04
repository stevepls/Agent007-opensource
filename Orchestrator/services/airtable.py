"""
Airtable API Service

Provides access to Airtable tickets with search and cross-reference capabilities.
"""

import os
import re
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AirtableTicket:
    """Represents an Airtable ticket."""
    record_id: str
    ticket_id: Optional[int]
    name: str
    status: str
    priority: Optional[str]
    description: str
    assigned_to: List[str]
    created_at: str
    raw_fields: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "ticket_id": self.ticket_id,
            "name": self.name,
            "status": self.status,
            "priority": self.priority,
            "description": self.description[:500] if self.description else None,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at,
        }


class AirtableService:
    """Service for interacting with Airtable API."""
    
    def __init__(self):
        self.base_id = os.getenv('AIRTABLE_BASE_ID', 'app37XFdl4xoMbvx3')
        self.table_id = os.getenv('AIRTABLE_TABLE_ID', 'tblFXfLF3tGjW9IXm')
        self.token = os.getenv('AIRTABLE_PERSONAL_ACCESS_TOKEN')
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_id}"
        self._tickets_cache: Optional[List[AirtableTicket]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes
        
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def is_configured(self) -> bool:
        """Check if Airtable is properly configured."""
        return bool(self.token)
    
    def _parse_ticket(self, record: Dict[str, Any]) -> AirtableTicket:
        """Parse a raw Airtable record into a Ticket object."""
        fields = record.get('fields', {})
        
        # Extract assigned users
        assigned_to = []
        for assignee in fields.get('Assigned To', []):
            if isinstance(assignee, dict):
                name = assignee.get('name', assignee.get('email', 'Unknown'))
                assigned_to.append(name)
        
        return AirtableTicket(
            record_id=record.get('id', ''),
            ticket_id=fields.get('ID'),
            name=fields.get('Ticket Name', 'Untitled'),
            status=fields.get('Ticket Status', 'Unknown'),
            priority=fields.get('Priority'),
            description=fields.get('Issue Description', ''),
            assigned_to=assigned_to,
            created_at=record.get('createdTime', ''),
            raw_fields=fields,
        )
    
    def fetch_all_tickets(self, force_refresh: bool = False) -> List[AirtableTicket]:
        """Fetch all tickets from Airtable with caching."""
        if not self.is_configured():
            return []
        
        # Check cache
        if not force_refresh and self._tickets_cache and self._cache_time:
            elapsed = (datetime.now() - self._cache_time).total_seconds()
            if elapsed < self._cache_ttl:
                return self._tickets_cache
        
        all_records = []
        offset = None
        
        while True:
            params = {'pageSize': 100}
            if offset:
                params['offset'] = offset
            
            try:
                response = requests.get(self.base_url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                records = data.get('records', [])
                all_records.extend(records)
                
                offset = data.get('offset')
                if not offset:
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error fetching Airtable tickets: {e}")
                break
        
        tickets = [self._parse_ticket(r) for r in all_records]
        
        # Update cache
        self._tickets_cache = tickets
        self._cache_time = datetime.now()
        
        return tickets
    
    def get_ticket_by_id(self, ticket_id: int) -> Optional[AirtableTicket]:
        """Get a ticket by its numeric ID."""
        if not self.is_configured():
            return None
        
        params = {
            'filterByFormula': f"{{ID}} = {ticket_id}",
            'maxRecords': 1
        }
        
        try:
            response = requests.get(self.base_url, headers=self.headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            records = data.get('records', [])
            
            if records:
                return self._parse_ticket(records[0])
            return None
            
        except requests.exceptions.RequestException:
            return None
    
    def get_ticket_by_record_id(self, record_id: str) -> Optional[AirtableTicket]:
        """Get a ticket by its Airtable record ID."""
        if not self.is_configured():
            return None
        
        url = f"{self.base_url}/{record_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return self._parse_ticket(response.json())
        except requests.exceptions.RequestException:
            return None
    
    def search_tickets(self, query: str, status: Optional[str] = None) -> List[AirtableTicket]:
        """Search tickets by name or description."""
        tickets = self.fetch_all_tickets()
        query_lower = query.lower()
        
        results = []
        for ticket in tickets:
            # Match on name or description
            if (query_lower in ticket.name.lower() or 
                query_lower in (ticket.description or '').lower()):
                
                # Filter by status if specified
                if status and ticket.status != status:
                    continue
                    
                results.append(ticket)
        
        return results
    
    def search_by_keywords(self, keywords: List[str]) -> List[AirtableTicket]:
        """Search tickets matching any of the given keywords."""
        tickets = self.fetch_all_tickets()
        
        results = []
        for ticket in tickets:
            text = f"{ticket.name} {ticket.description or ''}".lower()
            
            for keyword in keywords:
                if keyword.lower() in text:
                    results.append(ticket)
                    break
        
        return results
    
    def get_tickets_by_status(self, status: str) -> List[AirtableTicket]:
        """Get all tickets with a specific status."""
        tickets = self.fetch_all_tickets()
        return [t for t in tickets if t.status == status]
    
    def get_active_tickets(self) -> List[AirtableTicket]:
        """Get all non-completed tickets."""
        tickets = self.fetch_all_tickets()
        completed_statuses = {'Complete', 'Done', 'Closed'}
        return [t for t in tickets if t.status not in completed_statuses]
    
    def add_comment(self, record_id: str, comment: str, author: str = "Agent007") -> bool:
        """Add a comment to a ticket."""
        if not self.is_configured():
            return False
        
        url = f"{self.base_url}/{record_id}"
        
        try:
            # Get current record
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            current = response.json()
            
            fields = current.get('fields', {})
            
            # Find comment field
            comment_fields = ['Comments', 'Notes', 'Internal Notes', 'Description']
            comment_field = None
            current_comments = ''
            
            for field_name in comment_fields:
                if field_name in fields:
                    comment_field = field_name
                    current_comments = fields.get(field_name, '')
                    break
            
            if not comment_field:
                comment_field = 'Description'
                current_comments = fields.get('Description', '')
            
            # Format new comment
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_comment = f"[{timestamp}] {author}: {comment}"
            
            if current_comments:
                updated = f"{current_comments}\n\n{new_comment}"
            else:
                updated = new_comment
            
            # Update
            update_data = {"fields": {comment_field: updated}}
            update_response = requests.patch(url, headers=self.headers, json=update_data)
            update_response.raise_for_status()
            
            return True
            
        except requests.exceptions.RequestException:
            return False
    
    def update_status(self, record_id: str, new_status: str) -> bool:
        """Update a ticket's status."""
        if not self.is_configured():
            return False
        
        valid_statuses = [
            "Assigned - Small", "Assigned - Large",
            "In Progress - Small", "In Progress - Large",
            "Done (Needs Review)", "Complete",
            "Waiting on Details from CW", "On Hold",
            "Backlog - Small", "Backlog - Large"
        ]
        
        if new_status not in valid_statuses:
            return False
        
        url = f"{self.base_url}/{record_id}"
        
        try:
            update_data = {"fields": {"Ticket Status": new_status}}
            response = requests.patch(url, headers=self.headers, json=update_data)
            response.raise_for_status()
            
            # Invalidate cache
            self._tickets_cache = None
            
            return True
            
        except requests.exceptions.RequestException:
            return False


# Singleton instance
_airtable_service: Optional[AirtableService] = None


def get_airtable_service() -> AirtableService:
    """Get the singleton Airtable service instance."""
    global _airtable_service
    if _airtable_service is None:
        _airtable_service = AirtableService()
    return _airtable_service
