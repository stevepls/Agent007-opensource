"""
Accounting Tools for CrewAI Agents

Provides tools for managing Upwork → QuickBooks invoice sync.
Wraps the upwork-sync PHP service API.
"""

import sys
from pathlib import Path
from typing import List
from crewai.tools import BaseTool

# Add parent paths
TOOLS_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = TOOLS_ROOT.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from services.accounting import get_sync_client
from governance.audit import get_audit_logger, ActionType


class UpworkSyncStatusTool(BaseTool):
    """Check Upwork sync service status."""
    
    name: str = "upwork_sync_status"
    description: str = """Check the status of the Upwork → QuickBooks sync service.
    Returns: pending invoices, synced count, connection status.
    Input: none required (just pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        client = get_sync_client()
        summary = client.get_summary()
        
        get_audit_logger().log_tool_use(
            agent="accounting",
            tool="upwork_sync_status",
            input_data={},
            output_data=summary,
        )
        
        status = summary.get("status", "unknown")
        inv = summary.get("invoices", {})
        amt = summary.get("amounts", {})
        
        return f"""Upwork Sync Status: {status.upper()}
Invoices:
  - Pending: {inv.get('pending', 0)} (${amt.get('pending_usd', 0):,.2f})
  - Synced: {inv.get('synced', 0)} (${amt.get('synced_usd', 0):,.2f})
  - Errors: {inv.get('errors', 0)}
  - Total: {inv.get('total', 0)}"""


class UpworkListInvoicesTool(BaseTool):
    """List Upwork invoices."""
    
    name: str = "upwork_list_invoices"
    description: str = """List Upwork invoices with their sync status.
    Input: status filter (optional) - 'pending', 'synced', 'error', or empty for all"""
    
    def _run(self, status: str = "") -> str:
        client = get_sync_client()
        status = status.strip() if status else None
        invoices = client.list_invoices(status=status)
        
        get_audit_logger().log_tool_use(
            agent="accounting",
            tool="upwork_list_invoices",
            input_data={"status": status},
            output_data={"count": len(invoices)},
        )
        
        if not invoices:
            return f"No invoices found{f' with status {status}' if status else ''}."
        
        lines = [f"Found {len(invoices)} invoice(s):\n"]
        for inv in invoices[:20]:  # Limit to 20
            lines.append(
                f"  [{inv.status.upper():7}] {inv.id}: {inv.client} - {inv.project} "
                f"${inv.gross:,.2f} ({inv.date})"
            )
        
        if len(invoices) > 20:
            lines.append(f"  ... and {len(invoices) - 20} more")
        
        return "\n".join(lines)


class UpworkParseFilesTool(BaseTool):
    """Parse Upwork invoice files."""
    
    name: str = "upwork_parse_files"
    description: str = """Parse new Upwork invoice files (PDF/CSV) into the sync queue.
    Looks for files in upwork/invoices/ directory.
    Input: none required (just pass empty string)"""
    
    def _run(self, _: str = "") -> str:
        client = get_sync_client()
        result = client.parse_files()
        
        get_audit_logger().log_tool_use(
            agent="accounting",
            tool="upwork_parse_files",
            input_data={},
            output_data=result,
        )
        
        if "error" in result:
            return f"Parse failed: {result['error']}"
        
        parsed = result.get("parsed", 0)
        return f"Parsed {parsed} invoice file(s). Run 'upwork_list_invoices' to see results."


class UpworkRunSyncTool(BaseTool):
    """Sync invoices to QuickBooks."""
    
    name: str = "upwork_run_sync"
    description: str = """Sync pending Upwork invoices to QuickBooks Online.
    Creates draft invoices in QB (no auto-send to clients).
    Input: 'dry_run' for test mode, or empty for actual sync"""
    
    def _run(self, mode: str = "") -> str:
        dry_run = "dry" in mode.lower() if mode else False
        client = get_sync_client()
        result = client.run_sync(dry_run=dry_run)
        
        get_audit_logger().log_tool_use(
            agent="accounting",
            tool="upwork_run_sync",
            input_data={"dry_run": dry_run},
            output_data=result,
        )
        
        if "error" in result:
            return f"Sync failed: {result['error']}"
        
        synced = result.get("synced", 0)
        errors = result.get("errors", 0)
        mode_str = " (DRY RUN)" if dry_run else ""
        
        return f"Sync complete{mode_str}: {synced} synced, {errors} errors."


def get_accounting_tools() -> List[BaseTool]:
    """Get all accounting tools for CrewAI agents."""
    return [
        UpworkSyncStatusTool(),
        UpworkListInvoicesTool(),
        UpworkParseFilesTool(),
        UpworkRunSyncTool(),
    ]
