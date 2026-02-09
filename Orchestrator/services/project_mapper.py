"""
Project Mapper — Auto-detects and caches ClickUp ↔ Hubstaff project mappings.

Used by AgentMetrics and scaffolding agents to automatically find the correct
Hubstaff project for time logging based on ClickUp space/list.

Cache refreshes every 24 hours or on demand.
"""

import json
import os
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE_FILE = Path(__file__).parent.parent / "data" / "project_mapper" / "mapping_cache.json"
CACHE_TTL = 86400  # 24 hours


def _load_cache() -> Dict[str, Any]:
    """Load cached mapping from disk."""
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text())
            # Normalise key: older cache files use "mapping" (singular)
            if "mapping" in data and "mappings" not in data:
                data["mappings"] = data.pop("mapping")
            return data
        except Exception:
            pass
    return {"mappings": {}, "updated_at": 0}


def _save_cache(data: Dict[str, Any]):
    """Save mapping cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2))


def refresh_mapping(min_score: float = 0.6) -> Dict[str, Any]:
    """
    Refresh the ClickUp ↔ Hubstaff mapping by querying both APIs.

    Returns dict keyed by clickup_space_id with:
        - clickup_name, clickup_space_id
        - hubstaff_project_id, hubstaff_name
        - match_score
        - lists (clickup list IDs in this space)
    """
    from services.tickets.clickup_client import get_clickup_client
    from services.hubstaff.client import HubstaffClient

    clickup = get_clickup_client()
    hubstaff = HubstaffClient()

    # Get ClickUp spaces + lists
    clickup_spaces = {}
    for ws in clickup.get_workspaces():
        for space in clickup.get_spaces(ws["id"]):
            lists = []
            for lst in clickup.get_folderless_lists(space["id"]):
                lists.append({"id": lst["id"], "name": lst["name"]})
            for folder in clickup.get_folders(space["id"]):
                for lst in folder.get("lists", []):
                    lists.append({"id": lst["id"], "name": lst["name"]})
            clickup_spaces[space["id"]] = {
                "name": space["name"],
                "lists": lists,
            }

    # Get Hubstaff projects
    org_id = os.getenv("HUBSTAFF_ORG_ID", "588952")
    hs_projects = {}
    projects = hubstaff._request("GET", f"/organizations/{org_id}/projects")
    for p in projects.get("projects", []):
        hs_projects[p["id"]] = p["name"]

    # Match by name similarity
    mappings = {}
    for cu_id, cu_data in clickup_spaces.items():
        cu_name = cu_data["name"]
        cu_lower = cu_name.lower().replace("-", " ").replace("/", " ").strip()

        best_score = 0
        best_hs_id = None
        best_hs_name = None

        for hs_id, hs_name in hs_projects.items():
            # Compare against the first part of Hubstaff name (before " / ")
            hs_lower = hs_name.split("/")[0].strip().lower().replace("-", " ")
            score = SequenceMatcher(None, cu_lower, hs_lower).ratio()
            if score > best_score:
                best_score = score
                best_hs_id = hs_id
                best_hs_name = hs_name

        if best_score >= min_score:
            mappings[cu_id] = {
                "clickup_space_id": cu_id,
                "clickup_name": cu_name,
                "hubstaff_project_id": best_hs_id,
                "hubstaff_name": best_hs_name,
                "match_score": round(best_score, 3),
                "lists": cu_data["lists"],
            }

    cache = {
        "mappings": mappings,
        "updated_at": time.time(),
        "hubstaff_org_id": int(org_id),
        "hubstaff_user_id": int(os.getenv("HUBSTAFF_USER_ID", "0")),
    }
    _save_cache(cache)
    return cache


def get_mapping(force_refresh: bool = False) -> Dict[str, Dict]:
    """
    Get the project mapping (cached, refreshes every 24h).

    Returns dict keyed by clickup_space_id.
    """
    cache = _load_cache()

    if force_refresh or (time.time() - cache.get("updated_at", 0) > CACHE_TTL):
        try:
            cache = refresh_mapping()
        except Exception as e:
            print(f"[ProjectMapper] Refresh failed: {e}")
            if not cache.get("mappings"):
                return {}

    return cache.get("mappings", {})


def get_hubstaff_project_id(clickup_space_id: str = None, clickup_list_id: str = None,
                             project_name: str = None) -> Optional[int]:
    """
    Look up Hubstaff project ID from a ClickUp space ID, list ID, or project name.

    Args:
        clickup_space_id: Direct space ID lookup
        clickup_list_id: Searches all mappings for a list containing this ID
        project_name: Fuzzy match by name

    Returns Hubstaff project ID or None.
    """
    mappings = get_mapping()

    # Direct space lookup
    if clickup_space_id and clickup_space_id in mappings:
        return mappings[clickup_space_id]["hubstaff_project_id"]

    # Search by list ID
    if clickup_list_id:
        for m in mappings.values():
            for lst in m.get("lists", []):
                if lst["id"] == clickup_list_id:
                    return m["hubstaff_project_id"]

    # Fuzzy match by name
    if project_name:
        name_lower = project_name.lower()
        for m in mappings.values():
            if name_lower in m["clickup_name"].lower() or name_lower in m.get("hubstaff_name", "").lower():
                return m["hubstaff_project_id"]

    return None


def get_hubstaff_ids() -> Dict[str, int]:
    """Get the cached Hubstaff org_id and user_id."""
    cache = _load_cache()
    return {
        "org_id": cache.get("hubstaff_org_id", int(os.getenv("HUBSTAFF_ORG_ID", "0"))),
        "user_id": cache.get("hubstaff_user_id", int(os.getenv("HUBSTAFF_USER_ID", "0"))),
    }


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

    import sys
    force = "--refresh" in sys.argv

    print("Refreshing project mapping..." if force else "Loading project mapping...")
    mappings = get_mapping(force_refresh=force)

    print(f"\n{'='*60}")
    print(f"Mapped {len(mappings)} ClickUp spaces → Hubstaff projects:\n")
    for m in sorted(mappings.values(), key=lambda x: x["clickup_name"]):
        icon = "✅" if m["match_score"] >= 0.8 else "⚠️"
        print(f"  {icon} {m['clickup_name']}")
        print(f"     → {m['hubstaff_name']} (hs:{m['hubstaff_project_id']}, score:{m['match_score']:.0%})")
        for lst in m.get("lists", []):
            print(f"       - {lst['name']} (cu:{lst['id']})")

    ids = get_hubstaff_ids()
    print(f"\nHubstaff: org={ids['org_id']}, user={ids['user_id']}")
    print(f"Cache: {CACHE_FILE}")
