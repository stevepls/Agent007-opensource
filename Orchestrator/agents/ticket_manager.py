"""
Ticket Manager Agent

AI-powered agent for intelligent ticket management including:
- Semantic duplicate detection (even if subjects differ)
- Ticket categorization and prioritization
- Related ticket grouping
- Smart routing recommendations

Uses LLM for context-aware comparison rather than exact string matching.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Try to import CrewAI
try:
    from crewai import Agent, Task, Crew
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    Agent = None
    Task = None
    Crew = None
    BaseTool = None

# Try to import OpenAI for embeddings
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

# Local imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.tickets.clickup_client import get_clickup_client, ClickUpTask
from services.tickets.zendesk_client import get_zendesk_client, ZendeskTicket


class DuplicateConfidence(Enum):
    """Confidence level for duplicate detection."""
    DEFINITE = "definite"      # 95%+ - Almost certainly the same issue
    LIKELY = "likely"          # 75-95% - Probably the same issue
    POSSIBLE = "possible"      # 50-75% - Might be related
    UNLIKELY = "unlikely"      # 25-50% - Probably different
    NOT_DUPLICATE = "not"      # <25% - Different issues


@dataclass
class DuplicateMatch:
    """Represents a potential duplicate match."""
    source_subject: str
    source_body: str
    match_id: str
    match_subject: str
    match_body: str
    match_url: str
    confidence: DuplicateConfidence
    confidence_score: float  # 0.0 - 1.0
    reasoning: str
    match_type: str  # "clickup" or "zendesk"


@dataclass
class TicketAnalysis:
    """Analysis result for a potential ticket."""
    subject: str
    body: str
    sender: str
    is_duplicate: bool
    duplicate_matches: List[DuplicateMatch] = field(default_factory=list)
    recommended_action: str = "create"  # "create", "merge", "skip", "comment"
    suggested_category: Optional[str] = None
    suggested_priority: Optional[str] = None
    related_tickets: List[str] = field(default_factory=list)
    analysis_notes: str = ""


class TicketManagerAgent:
    """
    AI-powered ticket manager for intelligent deduplication and routing.
    
    Uses semantic similarity to detect duplicates even when:
    - Subjects are worded differently
    - Same issue reported by different people
    - Follow-up emails about existing issues
    - Partial information matches
    """
    
    def __init__(self, use_embeddings: bool = True):
        self._clickup = None
        self._zendesk = None
        self._openai = None
        self._use_embeddings = use_embeddings and OPENAI_AVAILABLE
        
        # Cache for embeddings
        self._embedding_cache: Dict[str, List[float]] = {}
        
        # LLM model for analysis
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    @property
    def clickup(self):
        if self._clickup is None:
            self._clickup = get_clickup_client()
        return self._clickup
    
    @property
    def zendesk(self):
        if self._zendesk is None:
            try:
                self._zendesk = get_zendesk_client()
            except (ValueError, Exception):
                return None
        return self._zendesk
    
    @property
    def openai(self):
        if self._openai is None and OPENAI_AVAILABLE:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self._openai = OpenAI(api_key=api_key)
        return self._openai
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector for text."""
        if not self._use_embeddings or not self.openai:
            return None
        
        # Check cache
        cache_key = text[:500]  # Use first 500 chars as key
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]
        
        try:
            response = self.openai.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000],  # Limit input length
            )
            embedding = response.data[0].embedding
            self._embedding_cache[cache_key] = embedding
            return embedding
        except Exception as e:
            print(f"Error getting embedding: {e}")
            return None
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        import math
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def analyze_with_llm(
        self,
        new_ticket: Dict[str, str],
        existing_tickets: List[Dict[str, Any]],
    ) -> TicketAnalysis:
        """
        Use LLM to analyze if new ticket is duplicate of existing ones.
        
        This is the core AI-powered analysis that understands context.
        """
        if not self.openai:
            return self._fallback_analysis(new_ticket, existing_tickets)
        
        # Build context for LLM
        existing_summary = []
        for i, ticket in enumerate(existing_tickets[:10]):  # Limit to 10 candidates
            existing_summary.append(
                f"{i+1}. [{ticket['type']}] ID: {ticket['id']}\n"
                f"   Subject: {ticket['subject']}\n"
                f"   Description: {ticket['body'][:300]}..."
            )
        
        prompt = f"""You are a ticket deduplication expert. Analyze if the NEW ticket is a duplicate of any EXISTING tickets.

NEW TICKET:
Subject: {new_ticket['subject']}
From: {new_ticket.get('sender', 'Unknown')}
Body: {new_ticket['body'][:1000]}

EXISTING TICKETS:
{chr(10).join(existing_summary) if existing_summary else "No existing tickets to compare."}

Analyze and respond in JSON format:
{{
    "is_duplicate": true/false,
    "duplicate_of": null or ticket number (1-10) if duplicate,
    "confidence": "definite" | "likely" | "possible" | "unlikely" | "not",
    "confidence_score": 0.0-1.0,
    "reasoning": "explanation of why this is/isn't a duplicate",
    "recommended_action": "create" | "merge" | "skip" | "comment",
    "related_tickets": [list of ticket numbers that are related but not duplicates],
    "suggested_category": "bug" | "feature" | "question" | "support" | null,
    "suggested_priority": "urgent" | "high" | "normal" | "low" | null
}}

Consider these as duplicates:
- Same issue reported with different wording
- Follow-up about an existing issue
- Same error/problem even if described differently
- Same customer reporting same issue again

NOT duplicates:
- Different issues from same customer
- Similar but distinct problems
- General questions about same topic but different specifics
"""

        try:
            response = self.openai.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a ticket analysis expert. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Build analysis result
            analysis = TicketAnalysis(
                subject=new_ticket['subject'],
                body=new_ticket['body'],
                sender=new_ticket.get('sender', ''),
                is_duplicate=result.get('is_duplicate', False),
                recommended_action=result.get('recommended_action', 'create'),
                suggested_category=result.get('suggested_category'),
                suggested_priority=result.get('suggested_priority'),
                analysis_notes=result.get('reasoning', ''),
            )
            
            # Add duplicate match if found
            if result.get('is_duplicate') and result.get('duplicate_of'):
                match_idx = result['duplicate_of'] - 1
                if 0 <= match_idx < len(existing_tickets):
                    matched = existing_tickets[match_idx]
                    analysis.duplicate_matches.append(DuplicateMatch(
                        source_subject=new_ticket['subject'],
                        source_body=new_ticket['body'][:500],
                        match_id=str(matched['id']),
                        match_subject=matched['subject'],
                        match_body=matched['body'][:500] if matched.get('body') else '',
                        match_url=matched.get('url', ''),
                        confidence=DuplicateConfidence(result.get('confidence', 'possible')),
                        confidence_score=result.get('confidence_score', 0.5),
                        reasoning=result.get('reasoning', ''),
                        match_type=matched['type'],
                    ))
            
            # Add related tickets
            for rel_idx in result.get('related_tickets', []):
                if isinstance(rel_idx, int) and 0 < rel_idx <= len(existing_tickets):
                    analysis.related_tickets.append(str(existing_tickets[rel_idx - 1]['id']))
            
            return analysis
            
        except Exception as e:
            print(f"LLM analysis error: {e}")
            return self._fallback_analysis(new_ticket, existing_tickets)
    
    def _fallback_analysis(
        self,
        new_ticket: Dict[str, str],
        existing_tickets: List[Dict[str, Any]],
    ) -> TicketAnalysis:
        """Fallback analysis using embeddings or simple matching."""
        analysis = TicketAnalysis(
            subject=new_ticket['subject'],
            body=new_ticket['body'],
            sender=new_ticket.get('sender', ''),
            is_duplicate=False,
        )
        
        if not existing_tickets:
            return analysis
        
        # Try embedding-based similarity
        new_text = f"{new_ticket['subject']} {new_ticket['body'][:500]}"
        new_embedding = self.get_embedding(new_text)
        
        best_match = None
        best_score = 0.0
        
        for ticket in existing_tickets:
            existing_text = f"{ticket['subject']} {ticket.get('body', '')[:500]}"
            
            if new_embedding:
                existing_embedding = self.get_embedding(existing_text)
                if existing_embedding:
                    score = self.cosine_similarity(new_embedding, existing_embedding)
                    if score > best_score:
                        best_score = score
                        best_match = ticket
            else:
                # Simple text matching fallback
                score = self._simple_similarity(new_text.lower(), existing_text.lower())
                if score > best_score:
                    best_score = score
                    best_match = ticket
        
        if best_match and best_score > 0.7:
            analysis.is_duplicate = True
            analysis.recommended_action = "merge" if best_score > 0.85 else "comment"
            
            confidence = DuplicateConfidence.DEFINITE if best_score > 0.9 else \
                        DuplicateConfidence.LIKELY if best_score > 0.8 else \
                        DuplicateConfidence.POSSIBLE
            
            analysis.duplicate_matches.append(DuplicateMatch(
                source_subject=new_ticket['subject'],
                source_body=new_ticket['body'][:500],
                match_id=str(best_match['id']),
                match_subject=best_match['subject'],
                match_body=best_match.get('body', '')[:500],
                match_url=best_match.get('url', ''),
                confidence=confidence,
                confidence_score=best_score,
                reasoning=f"Similarity score: {best_score:.2%}",
                match_type=best_match['type'],
            ))
        
        return analysis
    
    def _simple_similarity(self, text1: str, text2: str) -> float:
        """Simple word overlap similarity."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def fetch_recent_tickets(
        self,
        client_id: str = None,
        days_back: int = 30,
        include_clickup: bool = True,
        include_zendesk: bool = True,
        clickup_list_id: str = None,
    ) -> List[Dict[str, Any]]:
        """Fetch recent tickets from ClickUp and Zendesk for comparison."""
        tickets = []
        
        # Fetch from ClickUp
        if include_clickup and self.clickup and clickup_list_id:
            try:
                tasks = self.clickup.get_tasks(
                    list_id=clickup_list_id,
                    include_closed=False,
                )
                for task in tasks[:50]:  # Limit
                    tickets.append({
                        'id': task.id,
                        'type': 'clickup',
                        'subject': task.name,
                        'body': task.description or '',
                        'status': task.status,
                        'created_at': task.created_at.isoformat() if task.created_at else '',
                        'url': task.url,
                    })
            except Exception as e:
                print(f"Error fetching ClickUp tasks: {e}")
        
        # Fetch from Zendesk
        if include_zendesk and self.zendesk:
            try:
                zd_tickets = self.zendesk.search_tickets(
                    query=f"created>{(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')}",
                    limit=50,
                )
                for ticket in zd_tickets:
                    tickets.append({
                        'id': ticket.id,
                        'type': 'zendesk',
                        'subject': ticket.subject,
                        'body': ticket.description or '',
                        'status': ticket.status,
                        'created_at': ticket.created_at.isoformat() if ticket.created_at else '',
                        'url': f"https://{self.zendesk.subdomain}.zendesk.com/agent/tickets/{ticket.id}",
                    })
            except Exception as e:
                print(f"Error fetching Zendesk tickets: {e}")
        
        return tickets
    
    def check_duplicate(
        self,
        subject: str,
        body: str,
        sender: str = "",
        client_id: str = None,
        clickup_list_id: str = None,
        days_back: int = 30,
    ) -> TicketAnalysis:
        """
        Check if a potential ticket is a duplicate of existing ones.
        
        Args:
            subject: Ticket subject/title
            body: Ticket body/description
            sender: Sender email (optional)
            client_id: Client identifier (optional)
            clickup_list_id: ClickUp list to check (optional)
            days_back: How far back to look
        
        Returns:
            TicketAnalysis with duplicate detection results
        """
        # Fetch existing tickets
        existing = self.fetch_recent_tickets(
            client_id=client_id,
            days_back=days_back,
            clickup_list_id=clickup_list_id,
        )
        
        new_ticket = {
            'subject': subject,
            'body': body,
            'sender': sender,
        }
        
        # Analyze with LLM
        return self.analyze_with_llm(new_ticket, existing)
    
    def bulk_check_duplicates(
        self,
        tickets: List[Dict[str, str]],
        clickup_list_id: str = None,
        days_back: int = 30,
    ) -> List[TicketAnalysis]:
        """
        Check multiple potential tickets for duplicates.
        
        More efficient than checking one at a time as it fetches
        existing tickets once.
        """
        # Fetch existing tickets once
        existing = self.fetch_recent_tickets(
            days_back=days_back,
            clickup_list_id=clickup_list_id,
        )
        
        results = []
        for ticket in tickets:
            analysis = self.analyze_with_llm(ticket, existing)
            results.append(analysis)
            
            # If not a duplicate, add to existing for next iteration
            # (to catch duplicates within the batch)
            if not analysis.is_duplicate:
                existing.append({
                    'id': f"new-{len(existing)}",
                    'type': 'pending',
                    'subject': ticket['subject'],
                    'body': ticket['body'],
                    'status': 'new',
                    'url': '',
                })
        
        return results


# =============================================================================
# Convenience Functions
# =============================================================================

_agent: Optional[TicketManagerAgent] = None


def get_ticket_manager() -> TicketManagerAgent:
    """Get or create the ticket manager agent."""
    global _agent
    if _agent is None:
        _agent = TicketManagerAgent()
    return _agent


def check_duplicate(
    subject: str,
    body: str,
    sender: str = "",
    clickup_list_id: str = None,
) -> TicketAnalysis:
    """Check if a ticket is a duplicate."""
    return get_ticket_manager().check_duplicate(
        subject=subject,
        body=body,
        sender=sender,
        clickup_list_id=clickup_list_id,
    )


def analyze_email_for_ticket(
    subject: str,
    body: str,
    sender_email: str,
    clickup_list_id: str = None,
) -> Dict[str, Any]:
    """
    Analyze an email to determine if it should become a ticket.
    
    Returns a dict with:
    - should_create: bool
    - is_duplicate: bool
    - duplicate_of: ticket ID if duplicate
    - confidence: confidence level
    - reasoning: explanation
    - recommended_action: what to do
    """
    analysis = get_ticket_manager().check_duplicate(
        subject=subject,
        body=body,
        sender=sender_email,
        clickup_list_id=clickup_list_id,
    )
    
    result = {
        'should_create': not analysis.is_duplicate,
        'is_duplicate': analysis.is_duplicate,
        'duplicate_of': None,
        'confidence': None,
        'confidence_score': 0.0,
        'reasoning': analysis.analysis_notes,
        'recommended_action': analysis.recommended_action,
        'suggested_category': analysis.suggested_category,
        'suggested_priority': analysis.suggested_priority,
        'related_tickets': analysis.related_tickets,
    }
    
    if analysis.duplicate_matches:
        match = analysis.duplicate_matches[0]
        result['duplicate_of'] = match.match_id
        result['confidence'] = match.confidence.value
        result['confidence_score'] = match.confidence_score
        result['duplicate_url'] = match.match_url
    
    return result


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ticket Manager Agent")
    parser.add_argument("--subject", "-s", required=True, help="Ticket subject")
    parser.add_argument("--body", "-b", default="", help="Ticket body")
    parser.add_argument("--sender", default="", help="Sender email")
    parser.add_argument("--list-id", help="ClickUp list ID to check")
    parser.add_argument("--days", type=int, default=30, help="Days to look back")
    
    args = parser.parse_args()
    
    print(f"🔍 Analyzing ticket for duplicates...")
    print(f"   Subject: {args.subject[:50]}...")
    print()
    
    result = analyze_email_for_ticket(
        subject=args.subject,
        body=args.body,
        sender_email=args.sender,
        clickup_list_id=args.list_id,
    )
    
    print("📊 Analysis Result:")
    print(f"   Should Create: {'❌ No' if result['is_duplicate'] else '✅ Yes'}")
    print(f"   Is Duplicate: {result['is_duplicate']}")
    
    if result['is_duplicate']:
        print(f"   Duplicate Of: {result['duplicate_of']}")
        print(f"   Confidence: {result['confidence']} ({result['confidence_score']:.0%})")
        if result.get('duplicate_url'):
            print(f"   URL: {result['duplicate_url']}")
    
    print(f"   Recommended Action: {result['recommended_action']}")
    print(f"   Reasoning: {result['reasoning']}")
