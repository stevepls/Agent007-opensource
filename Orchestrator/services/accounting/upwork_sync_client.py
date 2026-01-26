"""
Upwork Sync API Client

Wraps the upwork-sync PHP service API for Orchestrator integration.
The PHP service handles QuickBooks OAuth and invoice creation.
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

# Relative paths for portability
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent

# Default to local Docker service
UPWORK_SYNC_URL = os.getenv("UPWORK_SYNC_URL", "http://localhost:8080")


@dataclass
class Invoice:
    """Parsed invoice from upwork-sync."""
    id: str
    client: str
    project: str
    gross: float
    service_fee: float
    net: float
    date: str
    status: str
    qb_invoice_id: Optional[str] = None
    error_message: Optional[str] = None


class UpworkSyncClient:
    """Client for the upwork-sync PHP API."""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or UPWORK_SYNC_URL).rstrip("/")
        self.timeout = 30
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request to the API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        kwargs.setdefault("timeout", self.timeout)
        
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.ConnectionError:
            return {"error": f"Cannot connect to upwork-sync at {self.base_url}"}
        except requests.exceptions.Timeout:
            return {"error": "Request timed out"}
        except requests.exceptions.HTTPError as e:
            return {"error": f"HTTP error: {e.response.status_code}"}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON response", "raw": response.text[:500]}
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the service is running."""
        result = self._request("GET", "/")
        if "error" in result:
            return {"status": "offline", **result}
        return {"status": "online", "connected": True}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current sync status and stats."""
        # Try the main dashboard endpoint
        result = self._request("GET", "/")
        if "error" in result:
            return result
        
        # Parse status from response or use sync-log.json directly
        return {
            "connected": True,
            "qb_connected": result.get("qb_connected", False),
            "pending_invoices": result.get("pending", 0),
            "synced_invoices": result.get("synced", 0),
            "errors": result.get("errors", 0),
        }
    
    def list_invoices(self, status: str = None) -> List[Invoice]:
        """Get list of parsed invoices."""
        # Read directly from sync-log.json for reliability
        sync_log = AGENT007_ROOT / "Accounting" / "upwork-sync" / "upwork" / "parsed" / "sync-log.json"
        
        if not sync_log.exists():
            return []
        
        try:
            with open(sync_log) as f:
                data = json.load(f)
            
            invoices = []
            for inv in data.get("invoices", []):
                if status and inv.get("status") != status:
                    continue
                invoices.append(Invoice(
                    id=inv.get("id", ""),
                    client=inv.get("client", ""),
                    project=inv.get("project", ""),
                    gross=float(inv.get("gross", 0)),
                    service_fee=float(inv.get("service_fee", 0)),
                    net=float(inv.get("net", 0)),
                    date=inv.get("date", ""),
                    status=inv.get("status", "pending"),
                    qb_invoice_id=inv.get("qb_invoice_id"),
                    error_message=inv.get("error_message"),
                ))
            return invoices
        except Exception as e:
            return []
    
    def parse_files(self) -> Dict[str, Any]:
        """Trigger file parsing (PDF/CSV → JSON)."""
        return self._request("POST", "/parse.php")
    
    def run_sync(self, dry_run: bool = False) -> Dict[str, Any]:
        """Run QuickBooks sync."""
        params = {"dry_run": "1"} if dry_run else {}
        return self._request("GET", "/sync.php", params=params)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary for the Orchestrator dashboard."""
        invoices = self.list_invoices()
        
        pending = [i for i in invoices if i.status == "pending"]
        synced = [i for i in invoices if i.status == "synced"]
        errors = [i for i in invoices if i.status == "error"]
        
        total_pending = sum(i.gross for i in pending)
        total_synced = sum(i.gross for i in synced)
        
        return {
            "service": "upwork-sync",
            "status": self.health_check().get("status", "unknown"),
            "invoices": {
                "pending": len(pending),
                "synced": len(synced),
                "errors": len(errors),
                "total": len(invoices),
            },
            "amounts": {
                "pending_usd": total_pending,
                "synced_usd": total_synced,
            },
            "last_checked": datetime.utcnow().isoformat(),
        }


# Global client instance
_client: Optional[UpworkSyncClient] = None


def get_sync_client() -> UpworkSyncClient:
    """Get the global sync client."""
    global _client
    if _client is None:
        _client = UpworkSyncClient()
    return _client
