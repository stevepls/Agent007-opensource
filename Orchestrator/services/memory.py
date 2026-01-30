"""
Memory Service - Context Preservation with SQLite

Provides persistent memory for the Agent007 system:
- Conversation history
- Context/facts about projects, preferences
- Semantic search for relevant memories
- Session management

Usage:
    from services.memory import get_memory_service
    
    memory = get_memory_service()
    
    # Store a conversation turn
    memory.add_message(session_id, role="user", content="Deploy to prod")
    memory.add_message(session_id, role="assistant", content="Starting deployment...")
    
    # Store a fact/context
    memory.add_context("project", "nemesis", "Magento 2 ecommerce site on AWS")
    
    # Retrieve relevant context for a query
    context = memory.get_relevant_context("deploy nemesis to production")
    
    # Get conversation history
    history = memory.get_conversation(session_id, limit=10)
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Boolean,
    Float,
    ForeignKey,
    JSON,
    Index,
    func,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
    Session,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", Path(__file__).parent.parent / "data" / "memory"))
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("MEMORY_DATABASE_URL", f"sqlite:///{MEMORY_DIR}/memory.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# =============================================================================
# DATABASE MODELS
# =============================================================================

class ConversationSession(Base):
    """A conversation session with the user."""
    __tablename__ = "conversation_sessions"
    
    id = Column(String(64), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    extra_data = Column(JSON, default=dict)  # renamed from 'metadata' (reserved)
    
    # Relationships
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_sessions_updated", "updated_at"),
    )


class Message(Base):
    """A single message in a conversation."""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), ForeignKey("conversation_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system, tool
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON, default=dict)  # tool calls, tokens, etc.
    
    # Relationships
    session = relationship("ConversationSession", back_populates="messages")
    
    __table_args__ = (
        Index("ix_messages_session", "session_id", "created_at"),
    )


class ContextEntry(Base):
    """A piece of context/memory about the world."""
    __tablename__ = "context_entries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)  # project, preference, fact, person, etc.
    key = Column(String(100), nullable=False)  # unique identifier within category
    value = Column(Text, nullable=False)  # the actual content
    source = Column(String(50), default="user")  # user, inferred, system
    confidence = Column(Float, default=1.0)  # 0-1 confidence score
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # optional expiration
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, nullable=True)
    extra_data = Column(JSON, default=dict)
    
    __table_args__ = (
        Index("ix_context_category_key", "category", "key", unique=True),
        Index("ix_context_search", "category", "value"),
    )


class SearchIndex(Base):
    """Simple keyword-based search index for memories."""
    __tablename__ = "search_index"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    entry_type = Column(String(20), nullable=False)  # message, context
    entry_id = Column(Integer, nullable=False)
    keyword = Column(String(100), nullable=False)
    weight = Column(Float, default=1.0)
    
    __table_args__ = (
        Index("ix_search_keyword", "keyword"),
        Index("ix_search_entry", "entry_type", "entry_id"),
    )


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MemoryResult:
    """A result from memory retrieval."""
    content: str
    category: str
    key: str
    relevance: float
    source: str
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ConversationTurn:
    """A single turn in a conversation."""
    role: str
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# MEMORY SERVICE
# =============================================================================

class MemoryService:
    """Manages persistent memory and context."""
    
    _instance: Optional["MemoryService"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._init_db()
        self._load_stopwords()
    
    def _init_db(self):
        """Initialize the database tables."""
        Base.metadata.create_all(bind=engine)
    
    def _load_stopwords(self):
        """Load common stopwords for search."""
        self.stopwords = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
            "be", "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "may", "might", "must", "shall", "can", "need",
            "it", "its", "this", "that", "these", "those", "i", "you", "he",
            "she", "we", "they", "what", "which", "who", "when", "where", "why",
            "how", "all", "each", "every", "both", "few", "more", "most", "other",
            "some", "such", "no", "not", "only", "own", "same", "so", "than",
            "too", "very", "just", "also", "now", "here", "there", "then",
        }
    
    @contextmanager
    def _get_session(self):
        """Get a database session."""
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # =========================================================================
    # SESSION MANAGEMENT
    # =========================================================================
    
    def create_session(self, session_id: Optional[str] = None, title: Optional[str] = None) -> str:
        """Create a new conversation session."""
        if session_id is None:
            session_id = hashlib.sha256(
                f"{datetime.utcnow().isoformat()}-{os.urandom(8).hex()}".encode()
            ).hexdigest()[:16]
        
        with self._get_session() as db:
            session = ConversationSession(
                id=session_id,
                title=title or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            )
            db.add(session)
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details."""
        with self._get_session() as db:
            session = db.query(ConversationSession).filter_by(id=session_id).first()
            if session:
                return {
                    "id": session.id,
                    "title": session.title,
                    "summary": session.summary,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "message_count": len(session.messages),
                    "extra_data": session.extra_data or {},
                }
        return None
    
    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """List recent sessions."""
        with self._get_session() as db:
            sessions = (
                db.query(ConversationSession)
                .order_by(ConversationSession.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "summary": s.summary,
                    "updated_at": s.updated_at.isoformat(),
                    "message_count": len(s.messages),
                }
                for s in sessions
            ]
    
    def update_session_summary(self, session_id: str, summary: str):
        """Update session summary (can be generated by LLM)."""
        with self._get_session() as db:
            session = db.query(ConversationSession).filter_by(id=session_id).first()
            if session:
                session.summary = summary
    
    # =========================================================================
    # MESSAGE MANAGEMENT
    # =========================================================================
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add a message to a conversation."""
        with self._get_session() as db:
            # Create session if it doesn't exist
            session = db.query(ConversationSession).filter_by(id=session_id).first()
            if not session:
                session = ConversationSession(id=session_id)
                db.add(session)
                db.flush()
            
            # Add message
            message = Message(
                session_id=session_id,
                role=role,
                content=content,
                metadata=metadata or {},
            )
            db.add(message)
            db.flush()
            
            # Index for search
            self._index_text(db, "message", message.id, content)
            
            return message.id
    
    def get_conversation(
        self,
        session_id: str,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> List[ConversationTurn]:
        """Get conversation history."""
        with self._get_session() as db:
            query = (
                db.query(Message)
                .filter(Message.session_id == session_id)
            )
            
            if before:
                query = query.filter(Message.created_at < before)
            
            messages = (
                query.order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            
            # Return in chronological order
            return [
                ConversationTurn(
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                    metadata=m.extra_data or {},
                )
                for m in reversed(messages)
            ]
    
    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent messages across all sessions."""
        with self._get_session() as db:
            messages = (
                db.query(Message)
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "session_id": m.session_id,
                    "role": m.role,
                    "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ]
    
    # =========================================================================
    # CONTEXT/MEMORY MANAGEMENT
    # =========================================================================
    
    def add_context(
        self,
        category: str,
        key: str,
        value: str,
        source: str = "user",
        confidence: float = 1.0,
        expires_in_days: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add or update a context entry."""
        with self._get_session() as db:
            # Check if exists
            existing = (
                db.query(ContextEntry)
                .filter_by(category=category, key=key)
                .first()
            )
            
            expires_at = None
            if expires_in_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
            
            if existing:
                existing.value = value
                existing.source = source
                existing.confidence = confidence
                existing.expires_at = expires_at
                existing.extra_data = metadata or existing.extra_data
                entry_id = existing.id
            else:
                entry = ContextEntry(
                    category=category,
                    key=key,
                    value=value,
                    source=source,
                    confidence=confidence,
                    expires_at=expires_at,
                    metadata=metadata or {},
                )
                db.add(entry)
                db.flush()
                entry_id = entry.id
            
            # Index for search
            self._index_text(db, "context", entry_id, f"{category} {key} {value}")
            
            return entry_id
    
    def get_context(self, category: str, key: str) -> Optional[str]:
        """Get a specific context entry."""
        with self._get_session() as db:
            entry = (
                db.query(ContextEntry)
                .filter_by(category=category, key=key)
                .first()
            )
            
            if entry:
                # Check expiration
                if entry.expires_at and entry.expires_at < datetime.utcnow():
                    return None
                
                # Update access tracking
                entry.access_count += 1
                entry.last_accessed = datetime.utcnow()
                
                return entry.value
        
        return None
    
    def list_context(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List context entries."""
        with self._get_session() as db:
            query = db.query(ContextEntry)
            
            if category:
                query = query.filter_by(category=category)
            
            entries = query.order_by(ContextEntry.updated_at.desc()).all()
            
            return [
                {
                    "category": e.category,
                    "key": e.key,
                    "value": e.value[:100] + "..." if len(e.value) > 100 else e.value,
                    "source": e.source,
                    "confidence": e.confidence,
                    "updated_at": e.updated_at.isoformat(),
                }
                for e in entries
                if not e.expires_at or e.expires_at > datetime.utcnow()
            ]
    
    def delete_context(self, category: str, key: str) -> bool:
        """Delete a context entry."""
        with self._get_session() as db:
            entry = (
                db.query(ContextEntry)
                .filter_by(category=category, key=key)
                .first()
            )
            if entry:
                # Remove from search index
                db.query(SearchIndex).filter_by(
                    entry_type="context", entry_id=entry.id
                ).delete()
                db.delete(entry)
                return True
        return False
    
    # =========================================================================
    # SEARCH & RETRIEVAL
    # =========================================================================
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract searchable keywords from text."""
        import re
        # Lowercase and split on non-alphanumeric
        words = re.findall(r'\b[a-z0-9]+\b', text.lower())
        # Filter stopwords and short words
        return [w for w in words if w not in self.stopwords and len(w) > 2]
    
    def _index_text(self, db: Session, entry_type: str, entry_id: int, text: str):
        """Index text for search."""
        # Remove old index entries
        db.query(SearchIndex).filter_by(
            entry_type=entry_type, entry_id=entry_id
        ).delete()
        
        # Extract and index keywords
        keywords = self._extract_keywords(text)
        keyword_counts: Dict[str, int] = {}
        for kw in keywords:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        
        for keyword, count in keyword_counts.items():
            db.add(SearchIndex(
                entry_type=entry_type,
                entry_id=entry_id,
                keyword=keyword,
                weight=min(count, 5) / 5.0,  # Cap weight at 1.0
            ))
    
    def search_context(self, query: str, limit: int = 10) -> List[MemoryResult]:
        """Search context entries by keyword."""
        keywords = self._extract_keywords(query)
        if not keywords:
            return []
        
        with self._get_session() as db:
            # Find matching entries with relevance scores
            from sqlalchemy import case
            
            # Query search index
            results = (
                db.query(
                    SearchIndex.entry_id,
                    func.sum(SearchIndex.weight).label("score"),
                )
                .filter(SearchIndex.entry_type == "context")
                .filter(SearchIndex.keyword.in_(keywords))
                .group_by(SearchIndex.entry_id)
                .order_by(func.sum(SearchIndex.weight).desc())
                .limit(limit * 2)  # Get more to filter expired
                .all()
            )
            
            # Fetch actual entries
            entry_ids = [r[0] for r in results]
            scores = {r[0]: r[1] for r in results}
            
            entries = (
                db.query(ContextEntry)
                .filter(ContextEntry.id.in_(entry_ids))
                .all()
            )
            
            # Filter expired and build results
            memory_results = []
            for entry in entries:
                if entry.expires_at and entry.expires_at < datetime.utcnow():
                    continue
                
                memory_results.append(MemoryResult(
                    content=entry.value,
                    category=entry.category,
                    key=entry.key,
                    relevance=scores.get(entry.id, 0),
                    source=entry.source,
                    created_at=entry.created_at,
                    metadata=entry.extra_data or {},
                ))
            
            # Sort by relevance
            memory_results.sort(key=lambda x: x.relevance, reverse=True)
            return memory_results[:limit]
    
    def get_relevant_context(
        self,
        query: str,
        categories: Optional[List[str]] = None,
        limit: int = 5,
    ) -> str:
        """Get relevant context formatted for LLM injection."""
        results = self.search_context(query, limit=limit * 2)
        
        if categories:
            results = [r for r in results if r.category in categories]
        
        results = results[:limit]
        
        if not results:
            return ""
        
        lines = ["## Relevant Context from Memory\n"]
        for r in results:
            lines.append(f"**{r.category}/{r.key}**: {r.content}")
        
        return "\n".join(lines)
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        with self._get_session() as db:
            session_count = db.query(ConversationSession).count()
            message_count = db.query(Message).count()
            context_count = db.query(ContextEntry).count()
            
            # Get category breakdown
            categories = (
                db.query(ContextEntry.category, func.count(ContextEntry.id))
                .group_by(ContextEntry.category)
                .all()
            )
            
            return {
                "sessions": session_count,
                "messages": message_count,
                "context_entries": context_count,
                "categories": {cat: count for cat, count in categories},
                "database_path": str(MEMORY_DIR / "memory.db"),
            }
    
    def cleanup_expired(self) -> int:
        """Remove expired context entries."""
        with self._get_session() as db:
            expired = (
                db.query(ContextEntry)
                .filter(ContextEntry.expires_at < datetime.utcnow())
                .all()
            )
            
            for entry in expired:
                db.query(SearchIndex).filter_by(
                    entry_type="context", entry_id=entry.id
                ).delete()
                db.delete(entry)
            
            return len(expired)
    
    def export_context(self) -> Dict[str, Any]:
        """Export all context for backup."""
        with self._get_session() as db:
            entries = db.query(ContextEntry).all()
            return {
                "exported_at": datetime.utcnow().isoformat(),
                "entries": [
                    {
                        "category": e.category,
                        "key": e.key,
                        "value": e.value,
                        "source": e.source,
                        "confidence": e.confidence,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in entries
                ]
            }
    
    def import_context(self, data: Dict[str, Any]) -> int:
        """Import context from backup."""
        count = 0
        for entry in data.get("entries", []):
            self.add_context(
                category=entry["category"],
                key=entry["key"],
                value=entry["value"],
                source=entry.get("source", "import"),
                confidence=entry.get("confidence", 1.0),
            )
            count += 1
        return count


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

def get_memory_service() -> MemoryService:
    """Get the singleton MemoryService instance."""
    return MemoryService()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def remember(category: str, key: str, value: str, **kwargs) -> int:
    """Convenience function to store a memory."""
    return get_memory_service().add_context(category, key, value, **kwargs)


def recall(category: str, key: str) -> Optional[str]:
    """Convenience function to recall a memory."""
    return get_memory_service().get_context(category, key)


def search_memory(query: str, limit: int = 5) -> List[MemoryResult]:
    """Convenience function to search memories."""
    return get_memory_service().search_context(query, limit)
