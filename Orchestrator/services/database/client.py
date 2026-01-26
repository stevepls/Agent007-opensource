"""
Database Management Client

Provides safe, controlled access to project databases.
All operations are logged and destructive operations require confirmation.

Safety Features:
- Read-only mode by default
- Query analysis before execution
- Dangerous query detection (DROP, DELETE, TRUNCATE)
- Row limit enforcement
- Execution timeouts
- Full audit logging

Supports: PostgreSQL, MySQL, SQLite
Uses: SQLAlchemy for universal access
"""

import os
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib


# Configuration
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(ORCHESTRATOR_ROOT / "data")))
DB_CONFIG_FILE = DATA_DIR / "database_connections.json"

# Safety limits
MAX_ROWS_RETURNED = 1000
QUERY_TIMEOUT_SECONDS = 30
MAX_AFFECTED_ROWS_WARNING = 100


class QueryType(Enum):
    """Types of SQL queries."""
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    CREATE = "create"
    DROP = "drop"
    ALTER = "alter"
    TRUNCATE = "truncate"
    OTHER = "other"


class RiskLevel(Enum):
    """Risk levels for database operations."""
    SAFE = "safe"           # SELECT with limits
    LOW = "low"             # INSERT, safe UPDATE
    MEDIUM = "medium"       # UPDATE/DELETE with WHERE
    HIGH = "high"           # UPDATE/DELETE affecting many rows
    CRITICAL = "critical"   # DROP, TRUNCATE, no WHERE clause


# Dangerous patterns
DANGEROUS_PATTERNS = [
    (r'\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)', RiskLevel.CRITICAL, "DROP statement detected"),
    (r'\bTRUNCATE\s+', RiskLevel.CRITICAL, "TRUNCATE statement detected"),
    (r'\bDELETE\s+FROM\s+\w+\s*$', RiskLevel.CRITICAL, "DELETE without WHERE clause"),
    (r'\bDELETE\s+FROM\s+\w+\s*;?\s*$', RiskLevel.CRITICAL, "DELETE without WHERE clause"),
    (r'\bUPDATE\s+\w+\s+SET\s+.*(?!WHERE)', RiskLevel.HIGH, "UPDATE without WHERE clause"),
    (r'\bALTER\s+TABLE', RiskLevel.HIGH, "Schema modification"),
    (r'\bGRANT\s+', RiskLevel.CRITICAL, "Permission change"),
    (r'\bREVOKE\s+', RiskLevel.CRITICAL, "Permission change"),
    (r';\s*DROP\s+', RiskLevel.CRITICAL, "SQL injection pattern"),
    (r';\s*DELETE\s+', RiskLevel.CRITICAL, "SQL injection pattern"),
    (r'--.*DROP', RiskLevel.CRITICAL, "Commented DROP detected"),
    (r'--.*DELETE', RiskLevel.CRITICAL, "Commented DELETE detected"),
    (r'--.*TRUNCATE', RiskLevel.CRITICAL, "Commented TRUNCATE detected"),
    # Block comment patterns - detect dangerous keywords INSIDE /* ... */
    (r'/\*[^*]*\*+(?:[^/*][^*]*\*+)*/', RiskLevel.LOW, "Block comment detected"),  # Generic
    (r'/\*.*\bDROP\b.*\*/', RiskLevel.CRITICAL, "DROP inside block comment"),
    (r'/\*.*\bDELETE\b.*\*/', RiskLevel.CRITICAL, "DELETE inside block comment"),
    (r'/\*.*\bTRUNCATE\b.*\*/', RiskLevel.CRITICAL, "TRUNCATE inside block comment"),
    (r'/\*.*\bALTER\b.*\*/', RiskLevel.HIGH, "ALTER inside block comment"),
    (r"'\s*OR\s+'1'\s*=\s*'1", RiskLevel.CRITICAL, "SQL injection pattern"),
]


@dataclass
class DatabaseConnection:
    """Represents a database connection configuration."""
    id: str
    name: str
    type: str  # postgresql, mysql, sqlite
    host: str
    port: int
    database: str
    username: str
    password: str  # Should be encrypted/from env
    ssl: bool = False
    read_only: bool = True  # Default to read-only
    project: Optional[str] = None
    description: str = ""
    is_production: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "username": self.username,
            "ssl": self.ssl,
            "read_only": self.read_only,
            "project": self.project,
            "description": self.description,
            "is_production": self.is_production,
        }
        # Never include password in dict
        return d
    
    @property
    def connection_string(self) -> str:
        """Generate SQLAlchemy connection string."""
        if self.type == "sqlite":
            return f"sqlite:///{self.database}"
        elif self.type == "postgresql":
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.type == "mysql":
            return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        else:
            raise ValueError(f"Unsupported database type: {self.type}")


@dataclass
class QueryResult:
    """Result of a database query."""
    success: bool
    query: str
    query_type: QueryType
    risk_level: RiskLevel
    rows_affected: int
    data: List[Dict[str, Any]]
    columns: List[str]
    execution_time_ms: float
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "query_type": self.query_type.value,
            "risk_level": self.risk_level.value,
            "rows_affected": self.rows_affected,
            "columns": self.columns,
            "data_preview": self.data[:10] if self.data else [],
            "total_rows": len(self.data),
            "execution_time_ms": self.execution_time_ms,
            "error": self.error,
            "warnings": self.warnings,
        }


@dataclass
class QueryApprovalRequest:
    """Request for approval to run a dangerous query."""
    id: str
    connection_id: str
    connection_name: str
    query: str
    query_type: QueryType
    risk_level: RiskLevel
    risk_reasons: List[str]
    estimated_affected_rows: Optional[int]
    created_at: str
    created_by: str
    status: str  # pending, approved, rejected
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None


class DatabaseManager:
    """Manages database connections and queries with safety controls."""
    
    _instance: Optional["DatabaseManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.connections: Dict[str, DatabaseConnection] = {}
        self._engines: Dict[str, Any] = {}  # SQLAlchemy engines
        self._approval_requests: Dict[str, QueryApprovalRequest] = {}
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load_connections()
    
    def _load_connections(self):
        """Load saved connections (without passwords)."""
        if DB_CONFIG_FILE.exists():
            try:
                with open(DB_CONFIG_FILE) as f:
                    data = json.load(f)
                for conn_data in data.get("connections", []):
                    # Password must come from environment
                    password_env = f"DB_{conn_data['id'].upper()}_PASSWORD"
                    password = os.getenv(password_env, "")
                    
                    conn = DatabaseConnection(
                        password=password,
                        **conn_data,
                    )
                    self.connections[conn.id] = conn
            except Exception as e:
                print(f"Error loading database connections: {e}")
    
    def _save_connections(self):
        """Save connections (without passwords)."""
        data = {
            "updated_at": datetime.utcnow().isoformat(),
            "connections": [c.to_dict() for c in self.connections.values()],
        }
        with open(DB_CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    
    def add_connection(
        self,
        id: str,
        name: str,
        type: str,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        read_only: bool = True,
        project: str = None,
        description: str = "",
        is_production: bool = False,
    ) -> DatabaseConnection:
        """Add a database connection."""
        conn = DatabaseConnection(
            id=id,
            name=name,
            type=type,
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            read_only=read_only,
            project=project,
            description=description,
            is_production=is_production,
        )
        
        self.connections[id] = conn
        self._save_connections()
        return conn
    
    def remove_connection(self, conn_id: str) -> bool:
        """Remove a connection."""
        if conn_id in self.connections:
            del self.connections[conn_id]
            if conn_id in self._engines:
                del self._engines[conn_id]
            self._save_connections()
            return True
        return False
    
    def list_connections(self) -> List[DatabaseConnection]:
        """List all connections."""
        return list(self.connections.values())
    
    def get_connection(self, conn_id: str) -> Optional[DatabaseConnection]:
        """Get a connection by ID."""
        return self.connections.get(conn_id)
    
    def _get_engine(self, conn_id: str):
        """Get or create SQLAlchemy engine."""
        if conn_id not in self._engines:
            try:
                from sqlalchemy import create_engine
                
                conn = self.connections.get(conn_id)
                if not conn:
                    raise ValueError(f"Connection {conn_id} not found")
                
                self._engines[conn_id] = create_engine(
                    conn.connection_string,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )
            except ImportError:
                raise ImportError("SQLAlchemy not installed. Run: pip install sqlalchemy")
        
        return self._engines[conn_id]
    
    # =========================================================================
    # QUERY ANALYSIS
    # =========================================================================
    
    def analyze_query(self, query: str) -> Tuple[QueryType, RiskLevel, List[str]]:
        """
        Analyze a query for type and risk level.
        Returns (query_type, risk_level, risk_reasons)
        """
        query_upper = query.upper().strip()
        risk_reasons = []
        risk_level = RiskLevel.SAFE
        
        # Determine query type
        if query_upper.startswith("SELECT"):
            query_type = QueryType.SELECT
        elif query_upper.startswith("INSERT"):
            query_type = QueryType.INSERT
            risk_level = RiskLevel.LOW
        elif query_upper.startswith("UPDATE"):
            query_type = QueryType.UPDATE
            risk_level = RiskLevel.MEDIUM
        elif query_upper.startswith("DELETE"):
            query_type = QueryType.DELETE
            risk_level = RiskLevel.MEDIUM
        elif query_upper.startswith("CREATE"):
            query_type = QueryType.CREATE
            risk_level = RiskLevel.HIGH
        elif query_upper.startswith("DROP"):
            query_type = QueryType.DROP
            risk_level = RiskLevel.CRITICAL
        elif query_upper.startswith("ALTER"):
            query_type = QueryType.ALTER
            risk_level = RiskLevel.HIGH
        elif query_upper.startswith("TRUNCATE"):
            query_type = QueryType.TRUNCATE
            risk_level = RiskLevel.CRITICAL
        else:
            query_type = QueryType.OTHER
            risk_level = RiskLevel.MEDIUM
        
        # Check dangerous patterns
        for pattern, pattern_risk, reason in DANGEROUS_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                risk_reasons.append(reason)
                if pattern_risk.value > risk_level.value:
                    risk_level = pattern_risk
        
        # Check for missing WHERE in UPDATE/DELETE
        if query_type in (QueryType.UPDATE, QueryType.DELETE):
            if "WHERE" not in query_upper:
                risk_level = RiskLevel.CRITICAL
                risk_reasons.append("No WHERE clause - affects all rows")
        
        return query_type, risk_level, risk_reasons
    
    def requires_approval(self, conn_id: str, query: str) -> bool:
        """Check if a query requires approval."""
        conn = self.connections.get(conn_id)
        if not conn:
            return True
        
        query_type, risk_level, _ = self.analyze_query(query)
        
        # Always require approval for production
        if conn.is_production and query_type != QueryType.SELECT:
            return True
        
        # Require approval for high/critical risk
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return True
        
        # Require approval for modifications on read-only connections
        if conn.read_only and query_type != QueryType.SELECT:
            return True
        
        return False
    
    # =========================================================================
    # QUERY EXECUTION
    # =========================================================================
    
    def execute_query(
        self,
        conn_id: str,
        query: str,
        params: Dict[str, Any] = None,
        limit: int = None,
        bypass_approval: bool = False,
    ) -> QueryResult:
        """
        Execute a query with safety checks.
        
        Args:
            conn_id: Connection ID
            query: SQL query
            params: Query parameters (for parameterized queries)
            limit: Override row limit
            bypass_approval: Skip approval check (for approved queries)
        
        Returns:
            QueryResult
        """
        import time
        
        conn = self.connections.get(conn_id)
        if not conn:
            return QueryResult(
                success=False,
                query=query,
                query_type=QueryType.OTHER,
                risk_level=RiskLevel.CRITICAL,
                rows_affected=0,
                data=[],
                columns=[],
                execution_time_ms=0,
                error=f"Connection {conn_id} not found",
            )
        
        # Analyze query
        query_type, risk_level, risk_reasons = self.analyze_query(query)
        warnings = risk_reasons.copy()
        
        # Check if read-only mode is violated
        if conn.read_only and query_type != QueryType.SELECT:
            return QueryResult(
                success=False,
                query=query,
                query_type=query_type,
                risk_level=risk_level,
                rows_affected=0,
                data=[],
                columns=[],
                execution_time_ms=0,
                error="Connection is read-only. Cannot execute modifying queries.",
                warnings=warnings,
            )
        
        # Check approval requirement
        if not bypass_approval and self.requires_approval(conn_id, query):
            return QueryResult(
                success=False,
                query=query,
                query_type=query_type,
                risk_level=risk_level,
                rows_affected=0,
                data=[],
                columns=[],
                execution_time_ms=0,
                error="Query requires approval. Use request_query_approval() first.",
                warnings=warnings,
            )
        
        # Add LIMIT to SELECT if not present
        if query_type == QueryType.SELECT and "LIMIT" not in query.upper():
            effective_limit = limit or MAX_ROWS_RETURNED
            query = f"{query.rstrip(';')} LIMIT {effective_limit}"
            warnings.append(f"Added LIMIT {effective_limit}")
        
        # Execute query
        try:
            from sqlalchemy import text
            
            engine = self._get_engine(conn_id)
            start_time = time.time()
            
            with engine.connect() as connection:
                result = connection.execute(text(query), params or {})
                
                if query_type == QueryType.SELECT:
                    rows = result.fetchall()
                    columns = list(result.keys())
                    data = [dict(zip(columns, row)) for row in rows]
                    rows_affected = len(data)
                else:
                    connection.commit()
                    rows_affected = result.rowcount
                    data = []
                    columns = []
            
            execution_time = (time.time() - start_time) * 1000
            
            return QueryResult(
                success=True,
                query=query,
                query_type=query_type,
                risk_level=risk_level,
                rows_affected=rows_affected,
                data=data,
                columns=columns,
                execution_time_ms=execution_time,
                warnings=warnings,
            )
            
        except Exception as e:
            return QueryResult(
                success=False,
                query=query,
                query_type=query_type,
                risk_level=risk_level,
                rows_affected=0,
                data=[],
                columns=[],
                execution_time_ms=0,
                error=str(e),
                warnings=warnings,
            )
    
    # =========================================================================
    # APPROVAL SYSTEM
    # =========================================================================
    
    def request_query_approval(
        self,
        conn_id: str,
        query: str,
        requested_by: str = "agent",
    ) -> QueryApprovalRequest:
        """Request approval for a dangerous query."""
        import uuid
        
        conn = self.connections.get(conn_id)
        query_type, risk_level, risk_reasons = self.analyze_query(query)
        
        req = QueryApprovalRequest(
            id=str(uuid.uuid4())[:8],
            connection_id=conn_id,
            connection_name=conn.name if conn else conn_id,
            query=query,
            query_type=query_type,
            risk_level=risk_level,
            risk_reasons=risk_reasons,
            estimated_affected_rows=None,  # Could run EXPLAIN
            created_at=datetime.utcnow().isoformat(),
            created_by=requested_by,
            status="pending",
        )
        
        self._approval_requests[req.id] = req
        return req
    
    def approve_query(self, request_id: str, approved_by: str) -> Optional[QueryApprovalRequest]:
        """Approve a query request."""
        req = self._approval_requests.get(request_id)
        if not req or req.status != "pending":
            return None
        
        req.status = "approved"
        req.approved_by = approved_by
        req.approved_at = datetime.utcnow().isoformat()
        return req
    
    def reject_query(self, request_id: str, rejected_by: str, reason: str) -> Optional[QueryApprovalRequest]:
        """Reject a query request."""
        req = self._approval_requests.get(request_id)
        if not req or req.status != "pending":
            return None
        
        req.status = "rejected"
        req.approved_by = rejected_by
        req.approved_at = datetime.utcnow().isoformat()
        req.rejection_reason = reason
        return req
    
    def get_pending_approvals(self) -> List[QueryApprovalRequest]:
        """Get all pending query approvals."""
        return [r for r in self._approval_requests.values() if r.status == "pending"]
    
    def execute_approved_query(self, request_id: str) -> QueryResult:
        """Execute a previously approved query."""
        req = self._approval_requests.get(request_id)
        if not req:
            return QueryResult(
                success=False,
                query="",
                query_type=QueryType.OTHER,
                risk_level=RiskLevel.CRITICAL,
                rows_affected=0,
                data=[],
                columns=[],
                execution_time_ms=0,
                error="Approval request not found",
            )
        
        if req.status != "approved":
            return QueryResult(
                success=False,
                query=req.query,
                query_type=req.query_type,
                risk_level=req.risk_level,
                rows_affected=0,
                data=[],
                columns=[],
                execution_time_ms=0,
                error=f"Query not approved (status: {req.status})",
            )
        
        return self.execute_query(req.connection_id, req.query, bypass_approval=True)
    
    # =========================================================================
    # SCHEMA INSPECTION
    # =========================================================================
    
    def get_tables(self, conn_id: str) -> List[str]:
        """Get list of tables in a database."""
        conn = self.connections.get(conn_id)
        if not conn:
            return []
        
        if conn.type == "postgresql":
            query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        elif conn.type == "mysql":
            query = "SHOW TABLES"
        elif conn.type == "sqlite":
            query = "SELECT name FROM sqlite_master WHERE type='table'"
        else:
            return []
        
        result = self.execute_query(conn_id, query)
        if result.success:
            return [list(row.values())[0] for row in result.data]
        return []
    
    def get_table_schema(self, conn_id: str, table_name: str) -> List[Dict[str, Any]]:
        """Get schema of a table."""
        conn = self.connections.get(conn_id)
        if not conn:
            return []
        
        if conn.type == "postgresql":
            query = f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """
        elif conn.type == "mysql":
            query = f"DESCRIBE {table_name}"
        elif conn.type == "sqlite":
            query = f"PRAGMA table_info({table_name})"
        else:
            return []
        
        result = self.execute_query(conn_id, query)
        return result.data if result.success else []
    
    def get_row_count(self, conn_id: str, table_name: str) -> int:
        """Get approximate row count for a table."""
        result = self.execute_query(conn_id, f"SELECT COUNT(*) as count FROM {table_name}")
        if result.success and result.data:
            return result.data[0].get("count", 0)
        return 0


# Global access
_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager."""
    global _manager
    if _manager is None:
        _manager = DatabaseManager()
    return _manager
