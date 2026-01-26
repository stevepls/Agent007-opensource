"""
SyncAudit Agent Client

Helper utilities for AI agents to query and analyze sync data.
Designed for easy integration with CrewAI, LangChain, or direct LLM use.

Example usage:
    from utils.agent_client import SyncAuditClient
    
    client = SyncAuditClient("http://localhost:8000")
    
    # Get summary for agent analysis
    summary = client.get_summary(project="apdriving")
    
    # Diagnose a specific order
    diagnosis = client.diagnose("12345", project="apdriving")
    
    # Find all mismatches needing attention
    mismatches = client.get_mismatches(project="apdriving")
"""

import httpx
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SyncAuditClient:
    """
    Client for interacting with SyncAudit API.
    Designed for AI agent consumption.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key
    
    def _request(self, method: str, path: str, **kwargs):
        """Make HTTP request to API."""
        url = f"{self.base_url}{path}"
        with httpx.Client() as client:
            response = client.request(
                method, 
                url, 
                headers=self.headers,
                timeout=30.0,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
    
    # ==========================================================================
    # Agent-Optimized Methods
    # ==========================================================================
    
    def get_summary(self, project: str = None) -> dict:
        """
        Get a concise summary of sync health.
        
        Returns:
            dict with:
            - total_events: int
            - by_status: dict of status -> count
            - critical_issues: list of issues needing attention
            - needs_attention: bool
        """
        params = {}
        if project:
            params["project"] = project
        return self._request("GET", "/api/agent/summary", params=params)
    
    def diagnose(self, source_id: str, project: str) -> dict:
        """
        Get detailed diagnosis for a specific record.
        
        Returns:
            dict with:
            - timeline: list of events for this record
            - current_status: str
            - mismatches: list of field mismatches
            - diagnosis: dict with synced/has_mismatches/failed/needs_manual_review
        """
        return self._request("GET", f"/api/agent/diagnose/{source_id}", params={"project": project})
    
    def get_mismatches(self, project: str = None, limit: int = 20) -> list:
        """
        Get all records with detected mismatches.
        
        Returns:
            list of events with mismatch_count > 0
        """
        params = {"limit": limit}
        if project:
            params["project"] = project
        return self._request("GET", "/api/mismatches", params=params)
    
    def get_stats(self, project: str, days: int = 7) -> dict:
        """
        Get summary statistics for a project.
        
        Returns:
            dict with total_events, synced, failed, success_rate, common_errors
        """
        return self._request("GET", "/api/stats", params={"project": project, "days": days})
    
    def compare(self, source_id: str, project: str) -> dict:
        """
        Compare source vs target data for a record.
        
        Returns:
            dict with match (bool), mismatch_count, mismatches list
        """
        return self._request("GET", f"/api/compare/{source_id}", params={"project": project})
    
    def list_events(
        self,
        project: str = None,
        status: str = None,
        days: int = 7,
        limit: int = 50
    ) -> list:
        """
        List sync events with filters.
        
        Returns:
            list of event dicts
        """
        params = {"days": days, "limit": limit}
        if project:
            params["project"] = project
        if status:
            params["status"] = status
        return self._request("GET", "/api/events", params=params)
    
    def log_event(
        self,
        project: str,
        source_system: str,
        target_system: str,
        source_id: str,
        event_type: str,
        status: str,
        source_data: dict = None,
        target_data: dict = None,
        error_message: str = None,
        triggered_by: str = "agent"
    ) -> dict:
        """
        Log a new sync event.
        
        Returns:
            dict with created event including id
        """
        payload = {
            "project": project,
            "source_system": source_system,
            "target_system": target_system,
            "source_id": source_id,
            "event_type": event_type,
            "status": status,
            "source_data": source_data,
            "target_data": target_data,
            "error_message": error_message,
            "triggered_by": triggered_by
        }
        return self._request("POST", "/api/events", json=payload)
    
    # ==========================================================================
    # Agent Helper Methods
    # ==========================================================================
    
    def format_for_llm(self, data: dict) -> str:
        """
        Format API response as human-readable text for LLM consumption.
        """
        if "critical_issues" in data:
            # Summary format
            lines = [
                f"## Sync Health Summary",
                f"- Total Events: {data.get('total_events', 0)}",
                f"- Status Breakdown: {data.get('by_status', {})}",
                f"- Needs Attention: {'Yes' if data.get('needs_attention') else 'No'}",
                "",
                "### Critical Issues:"
            ]
            for issue in data.get("critical_issues", [])[:5]:
                lines.append(f"- {issue.get('project')} Order #{issue.get('source_id')}: {issue.get('status')} ({issue.get('mismatch_count', 0)} mismatches)")
            return "\n".join(lines)
        
        elif "diagnosis" in data:
            # Diagnosis format
            diag = data.get("diagnosis", {})
            lines = [
                f"## Diagnosis for Order #{data.get('source_id')}",
                f"- Project: {data.get('project')}",
                f"- Current Status: {data.get('current_status')}",
                f"- Target ID (Acuity): {data.get('target_id', 'N/A')}",
                f"- Synced: {'Yes' if diag.get('synced') else 'No'}",
                f"- Has Mismatches: {'Yes' if diag.get('has_mismatches') else 'No'}",
                f"- Failed: {'Yes' if diag.get('failed') else 'No'}",
                f"- Needs Manual Review: {'Yes' if diag.get('needs_manual_review') else 'No'}",
            ]
            
            if data.get("error_message"):
                lines.append(f"- Error: {data.get('error_message')}")
            
            if data.get("mismatches"):
                lines.append("\n### Mismatches:")
                for m in data.get("mismatches", []):
                    lines.append(f"- {m.get('field')}: source='{m.get('source_value')}' vs target='{m.get('target_value')}' ({m.get('severity', 'medium')} severity)")
            
            return "\n".join(lines)
        
        else:
            # Generic format
            import json
            return json.dumps(data, indent=2, default=str)
    
    def get_actionable_issues(self, project: str = None) -> list:
        """
        Get list of issues that need action, formatted for agent decision-making.
        
        Returns:
            list of dicts with issue_type, source_id, description, suggested_action
        """
        summary = self.get_summary(project=project)
        issues = []
        
        for issue in summary.get("critical_issues", []):
            action = "unknown"
            if issue.get("status") == "failed":
                action = "retry_sync"
            elif issue.get("mismatch_count", 0) > 0:
                action = "investigate_mismatch"
            
            issues.append({
                "issue_type": issue.get("status"),
                "source_id": issue.get("source_id"),
                "project": issue.get("project"),
                "mismatch_count": issue.get("mismatch_count", 0),
                "error_preview": issue.get("error"),
                "suggested_action": action
            })
        
        return issues


# =============================================================================
# CrewAI Tool Wrapper (Optional)
# =============================================================================

def create_crewai_tools(client: SyncAuditClient):
    """
    Create CrewAI-compatible tools from the SyncAudit client.
    
    Usage:
        from utils.agent_client import SyncAuditClient, create_crewai_tools
        
        client = SyncAuditClient("http://localhost:8000")
        tools = create_crewai_tools(client)
        
        # Use in CrewAI agent
        agent = Agent(
            role="Sync Auditor",
            tools=tools,
            ...
        )
    """
    try:
        from crewai_tools import tool
    except ImportError:
        return []
    
    @tool("Get Sync Summary")
    def get_sync_summary(project: str = None) -> str:
        """Get a summary of sync health for a project. Returns status counts and critical issues."""
        result = client.get_summary(project=project)
        return client.format_for_llm(result)
    
    @tool("Diagnose Sync Issue")
    def diagnose_sync_issue(source_id: str, project: str) -> str:
        """Diagnose sync issues for a specific order/record. Returns timeline and mismatch details."""
        result = client.diagnose(source_id, project)
        return client.format_for_llm(result)
    
    @tool("Get Sync Mismatches")
    def get_sync_mismatches(project: str = None) -> str:
        """Get all records with data mismatches between source and target systems."""
        result = client.get_mismatches(project=project)
        return f"Found {len(result)} records with mismatches:\n" + "\n".join([
            f"- Order #{r.get('source_id')}: {r.get('mismatch_count')} mismatches"
            for r in result[:10]
        ])
    
    @tool("Compare Source and Target")
    def compare_sync_data(source_id: str, project: str) -> str:
        """Compare source (WooCommerce) and target (Acuity) data for a record."""
        result = client.compare(source_id, project)
        if result.get("match"):
            return f"Order #{source_id}: Data matches perfectly between source and target."
        else:
            mismatches = result.get("mismatches", [])
            return f"Order #{source_id}: Found {len(mismatches)} mismatches:\n" + "\n".join([
                f"- {m.get('field')}: '{m.get('source_value')}' vs '{m.get('target_value')}'"
                for m in mismatches
            ])
    
    return [get_sync_summary, diagnose_sync_issue, get_sync_mismatches, compare_sync_data]


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Demo usage
    client = SyncAuditClient("http://localhost:8000")
    
    print("=== SyncAudit Agent Client Demo ===\n")
    
    try:
        # Get summary
        summary = client.get_summary()
        print("Summary:")
        print(client.format_for_llm(summary))
        print()
        
        # Get actionable issues
        issues = client.get_actionable_issues()
        print(f"Actionable Issues: {len(issues)}")
        for issue in issues[:5]:
            print(f"  - {issue}")
        
    except Exception as e:
        print(f"Error connecting to API: {e}")
        print("Make sure the SyncAudit API is running at http://localhost:8000")
