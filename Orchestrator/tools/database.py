"""
Database Tools for CrewAI Agents

Provides safe, controlled access to project databases.
All modifying queries require approval.
Strong protections against dangerous operations.
"""

import sys
from pathlib import Path
from typing import List
from crewai.tools import BaseTool

TOOLS_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = TOOLS_ROOT.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from governance.audit import get_audit_logger


class ListDatabasesTool(BaseTool):
    """List configured database connections."""
    
    name: str = "list_databases"
    description: str = """List all configured database connections.
    Input: none required (pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        from services.database.client import get_database_manager
        
        try:
            manager = get_database_manager()
            connections = manager.list_connections()
            
            if not connections:
                return "No database connections configured. Add connections in the UI."
            
            lines = ["Configured Databases:\n"]
            for conn in connections:
                prod_tag = "🔴 PRODUCTION" if conn.is_production else ""
                ro_tag = "🔒 Read-Only" if conn.read_only else "✏️ Read-Write"
                
                lines.append(
                    f"**{conn.name}** ({conn.id})\n"
                    f"  Type: {conn.type} | {ro_tag} {prod_tag}\n"
                    f"  Host: {conn.host}:{conn.port}\n"
                    f"  Database: {conn.database}\n"
                    f"  Project: {conn.project or 'N/A'}"
                )
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class ListTablesTool(BaseTool):
    """List tables in a database."""
    
    name: str = "list_tables"
    description: str = """List all tables in a database.
    Input: database connection ID"""
    
    def _run(self, conn_id: str) -> str:
        from services.database.client import get_database_manager
        
        if not conn_id:
            return "Please provide a connection ID. Use list_databases to see available connections."
        
        try:
            manager = get_database_manager()
            tables = manager.get_tables(conn_id.strip())
            
            if not tables:
                return f"No tables found in {conn_id} (or connection failed)."
            
            lines = [f"Tables in {conn_id}:\n"]
            for table in tables:
                row_count = manager.get_row_count(conn_id, table)
                lines.append(f"  • {table} ({row_count:,} rows)")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class DescribeTableTool(BaseTool):
    """Describe a table's schema."""
    
    name: str = "describe_table"
    description: str = """Get the schema of a database table.
    Input format: "connection_id.table_name"
    Example: "mydb.users" """
    
    def _run(self, table_ref: str) -> str:
        from services.database.client import get_database_manager
        
        if not table_ref or "." not in table_ref:
            return "Invalid format. Use: connection_id.table_name"
        
        parts = table_ref.strip().split(".", 1)
        conn_id, table_name = parts[0], parts[1]
        
        try:
            manager = get_database_manager()
            schema = manager.get_table_schema(conn_id, table_name)
            
            if not schema:
                return f"Table {table_name} not found in {conn_id}."
            
            row_count = manager.get_row_count(conn_id, table_name)
            
            lines = [f"Schema: {table_name} ({row_count:,} rows)\n"]
            lines.append("| Column | Type | Nullable | Default |")
            lines.append("|--------|------|----------|---------|")
            
            for col in schema:
                # Handle different DB formats
                col_name = col.get("column_name") or col.get("Field") or col.get("name", "")
                col_type = col.get("data_type") or col.get("Type") or col.get("type", "")
                nullable = col.get("is_nullable") or col.get("Null") or ("YES" if col.get("notnull") == 0 else "NO")
                default = col.get("column_default") or col.get("Default") or col.get("dflt_value") or "-"
                
                lines.append(f"| {col_name} | {col_type} | {nullable} | {default} |")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class QueryDatabaseTool(BaseTool):
    """Execute a SELECT query."""
    
    name: str = "query_database"
    description: str = """Execute a SELECT query on a database.
    Only SELECT queries are allowed. Modifying queries require approval.
    
    Input format: JSON with fields:
    - connection: connection ID (REQUIRED)
    - query: SQL SELECT query (REQUIRED)
    - limit: max rows to return (default: 100)
    
    Example: {"connection": "mydb", "query": "SELECT * FROM users WHERE active = true", "limit": 50}"""
    
    def _run(self, input_json: str) -> str:
        import json
        from services.database.client import get_database_manager, QueryType
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        conn_id = data.get("connection")
        query = data.get("query")
        limit = data.get("limit", 100)
        
        if not conn_id:
            return "Missing required field: connection"
        if not query:
            return "Missing required field: query"
        
        try:
            manager = get_database_manager()
            
            # Analyze first
            query_type, risk_level, risk_reasons = manager.analyze_query(query)
            
            if query_type != QueryType.SELECT:
                return (
                    f"❌ Only SELECT queries allowed via this tool.\n"
                    f"Detected query type: {query_type.value}\n\n"
                    "For INSERT/UPDATE/DELETE, use 'request_db_query' to request approval."
                )
            
            result = manager.execute_query(conn_id, query, limit=limit)
            
            get_audit_logger().log_tool_use(
                agent="database",
                tool="query_database",
                input_data={"connection": conn_id, "query": query[:100]},
                output_data={"success": result.success, "rows": len(result.data)},
            )
            
            if not result.success:
                return f"❌ Query failed: {result.error}"
            
            # Format results
            if not result.data:
                return f"✓ Query returned 0 rows.\n\nExecution time: {result.execution_time_ms:.1f}ms"
            
            # Build table
            lines = [f"✓ Query returned {len(result.data)} row(s) in {result.execution_time_ms:.1f}ms\n"]
            
            if result.warnings:
                lines.append(f"⚠️ Warnings: {', '.join(result.warnings)}\n")
            
            # Header
            cols = result.columns[:10]  # Limit columns
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "|".join(["---"] * len(cols)) + "|")
            
            # Rows (limit to 20)
            for row in result.data[:20]:
                values = [str(row.get(c, ""))[:30] for c in cols]
                lines.append("| " + " | ".join(values) + " |")
            
            if len(result.data) > 20:
                lines.append(f"\n... and {len(result.data) - 20} more rows")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class RequestDBQueryTool(BaseTool):
    """Request approval for a modifying query."""
    
    name: str = "request_db_query"
    description: str = """Request approval to execute a modifying query (INSERT/UPDATE/DELETE).
    The query will be analyzed for risk and queued for human approval.
    
    Input format: JSON with fields:
    - connection: connection ID (REQUIRED)
    - query: SQL query (REQUIRED)
    
    Example: {"connection": "mydb", "query": "UPDATE users SET active = false WHERE last_login < '2024-01-01'"}"""
    
    def _run(self, input_json: str) -> str:
        import json
        from services.database.client import get_database_manager
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        conn_id = data.get("connection")
        query = data.get("query")
        
        if not conn_id:
            return "Missing required field: connection"
        if not query:
            return "Missing required field: query"
        
        try:
            manager = get_database_manager()
            
            # Check connection exists
            conn = manager.get_connection(conn_id)
            if not conn:
                return f"Connection '{conn_id}' not found."
            
            # Analyze query
            query_type, risk_level, risk_reasons = manager.analyze_query(query)
            
            # Create approval request
            req = manager.request_query_approval(conn_id, query, "agent")
            
            get_audit_logger().log_tool_use(
                agent="database",
                tool="request_db_query",
                input_data={"connection": conn_id, "query_type": query_type.value},
                output_data={"request_id": req.id, "risk_level": risk_level.value},
            )
            
            # Build response
            risk_icon = {
                "safe": "✅",
                "low": "🟢",
                "medium": "🟡",
                "high": "🟠",
                "critical": "🔴",
            }.get(risk_level.value, "⚪")
            
            lines = [
                f"⚠️ Query queued for approval\n",
                f"**Request ID:** {req.id}",
                f"**Connection:** {conn.name} ({conn_id})",
                f"**Query Type:** {query_type.value.upper()}",
                f"**Risk Level:** {risk_icon} {risk_level.value.upper()}",
            ]
            
            if conn.is_production:
                lines.append("\n🔴 **WARNING: This is a PRODUCTION database!**")
            
            if risk_reasons:
                lines.append(f"\n**Risk Factors:**")
                for reason in risk_reasons:
                    lines.append(f"  • {reason}")
            
            lines.append(f"\n**Query:**\n```sql\n{query}\n```")
            lines.append("\nA human must approve this query in the UI before it executes.")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class ViewPendingQueriesl(BaseTool):
    """View pending query approvals."""
    
    name: str = "list_pending_queries"
    description: str = """List all database queries waiting for approval.
    Input: none required (pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        from services.database.client import get_database_manager
        
        try:
            manager = get_database_manager()
            pending = manager.get_pending_approvals()
            
            if not pending:
                return "No pending query approvals."
            
            lines = [f"Pending Query Approvals ({len(pending)}):\n"]
            
            for req in pending:
                risk_icon = {
                    "safe": "✅",
                    "low": "🟢",
                    "medium": "🟡",
                    "high": "🟠",
                    "critical": "🔴",
                }.get(req.risk_level.value, "⚪")
                
                lines.append(
                    f"**{req.id}** | {risk_icon} {req.risk_level.value}\n"
                    f"  Connection: {req.connection_name}\n"
                    f"  Type: {req.query_type.value}\n"
                    f"  Query: {req.query[:50]}...\n"
                    f"  Requested: {req.created_at[:16]}"
                )
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class AnalyzeQueryTool(BaseTool):
    """Analyze a query for safety before execution."""
    
    name: str = "analyze_query"
    description: str = """Analyze a SQL query for safety and risk factors.
    Does NOT execute the query - just analyzes it.
    Input: SQL query to analyze"""
    
    def _run(self, query: str) -> str:
        from services.database.client import get_database_manager
        
        if not query:
            return "Please provide a SQL query to analyze."
        
        try:
            manager = get_database_manager()
            query_type, risk_level, risk_reasons = manager.analyze_query(query)
            
            risk_icon = {
                "safe": "✅",
                "low": "🟢",
                "medium": "🟡",
                "high": "🟠",
                "critical": "🔴",
            }.get(risk_level.value, "⚪")
            
            lines = [
                "## Query Analysis\n",
                f"**Query Type:** {query_type.value.upper()}",
                f"**Risk Level:** {risk_icon} {risk_level.value.upper()}",
            ]
            
            if risk_reasons:
                lines.append("\n**Risk Factors:**")
                for reason in risk_reasons:
                    lines.append(f"  • ⚠️ {reason}")
            else:
                lines.append("\n**Risk Factors:** None detected")
            
            # Recommendations
            lines.append("\n**Recommendations:**")
            if query_type.value == "select":
                lines.append("  • Safe to execute with query_database tool")
            elif risk_level.value in ("safe", "low"):
                lines.append("  • Low risk - request approval with request_db_query")
            elif risk_level.value == "medium":
                lines.append("  • Review carefully before requesting approval")
                lines.append("  • Consider adding WHERE clause if missing")
            else:
                lines.append("  • 🚨 HIGH RISK - Requires careful review")
                lines.append("  • Recommend testing on non-production first")
                lines.append("  • Consider breaking into smaller queries")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


def get_database_tools() -> List[BaseTool]:
    """Get all database tools for CrewAI agents."""
    return [
        ListDatabasesTool(),
        ListTablesTool(),
        DescribeTableTool(),
        QueryDatabaseTool(),
        RequestDBQueryTool(),
        ViewPendingQueriesl(),
        AnalyzeQueryTool(),
    ]
