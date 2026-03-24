"""
Unified Project Registry — single source of truth for all project identifiers.

Consolidates mappings previously scattered across:
- DevOps/config/tickets/org-mapping.yml
- DevOps/webhook-server/server.py
- agents/scaffolding/config.py
- services/session_timer.py

Every service that needs a project ID (ClickUp, Zendesk, Harvest, Hubstaff,
Slack, GitHub) should look it up here instead of hardcoding.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ProjectConfig:
    """All known identifiers and metadata for a single project."""

    name: str
    aliases: List[str]
    clickup_space_id: Optional[str] = None
    clickup_list_id: Optional[str] = None
    zendesk_tag: Optional[str] = None
    harvest_project_id: Optional[str] = None
    harvest_project_name: Optional[str] = None
    slack_channel_id: Optional[str] = None
    github_repo: Optional[str] = None
    hubstaff_project_id: Optional[str] = None
    sla_tier: str = "bronze"
    active: bool = True


# ---------------------------------------------------------------------------
# Harvest task type IDs (shared across projects)
# ---------------------------------------------------------------------------

HARVEST_TASK_TYPES: Dict[str, str] = {
    "Platform & Data Engineer": "16570077",
    "Programming": "8592654",
    "Bug Fixes": "18324059",
    "Engineering": "10280862",
    "Operations": "16661734",
    "Client meetings": "8592709",
    "Product Management": "8805392",
    "Project Management": "8592656",
    "System architecture": "8592772",
    "Graphic Design": "8592653",
    "Business Development": "8592657",
    "Marketing": "8592655",
    "Product Requirements": "8608553",
    "Project background": "23860836",
}


# ---------------------------------------------------------------------------
# ClickUp workspace constants
# ---------------------------------------------------------------------------

CLICKUP_WORKSPACE_ID = "14298923"
CLICKUP_FALLBACK_SPACE_ID = "49674081"
CLICKUP_FALLBACK_LIST_ID = "387136998"  # Customer Support catch-all


# ---------------------------------------------------------------------------
# Hubstaff constants
# ---------------------------------------------------------------------------

HUBSTAFF_ORG_ID = "588952"


# ---------------------------------------------------------------------------
# Project definitions
# ---------------------------------------------------------------------------

_PROJECTS: List[ProjectConfig] = [
    # --- Client projects ---------------------------------------------------
    ProjectConfig(
        name="AP Driving",
        aliases=["ap-driving", "apdriving", "ap driving"],
        clickup_space_id="90113645942",
        clickup_list_id="901109833325",
        zendesk_tag="ap-driving",
        sla_tier="gold",
    ),
    ProjectConfig(
        name="Office Design Group",
        aliases=["office design group", "odg"],
        clickup_space_id="90113547910",
        clickup_list_id="901112746420",
        zendesk_tag="odg",
        sla_tier="silver",
    ),
    ProjectConfig(
        name="Maine Lobster",
        aliases=["maine lobster", "mainelobster", "maine-lobster"],
        clickup_space_id="63121663",
        clickup_list_id="901103001907",
        zendesk_tag="maine-lobster",
        sla_tier="gold",
    ),
    ProjectConfig(
        name="Lake County Pipe",
        aliases=["lake county pipe", "lcp"],
        clickup_space_id="48528603",
        clickup_list_id="901106405993",
        zendesk_tag="lcp",
        sla_tier="silver",
    ),
    ProjectConfig(
        name="ForgeLab/Collegewise",
        aliases=["forgelab", "collegewise", "forgelab/collegewise"],
        clickup_space_id="48460400",
        clickup_list_id="192558687",
        zendesk_tag="forgelab",
        hubstaff_project_id="3295429",
        harvest_project_id="24591687",
        harvest_project_name="Product & Technology",
        sla_tier="gold",
    ),
    ProjectConfig(
        name="Waynes Aircraft",
        aliases=["waynes aircraft", "waynes"],
        clickup_space_id="90110040647",
        clickup_list_id="901100527218",
        zendesk_tag="waynes",
        sla_tier="silver",
    ),
    ProjectConfig(
        name="Cabinet Saver",
        aliases=["cabinet saver", "cabinetsaver", "cabinet-saver"],
        clickup_space_id="26300621",
        clickup_list_id="381226170",
        zendesk_tag="cabinet-saver",
        sla_tier="bronze",
    ),
    ProjectConfig(
        name="Phyto/PDX Aromatics",
        aliases=["phyto", "pdxaromatics", "pdx aromatics", "phyto/pdx aromatics"],
        clickup_space_id="90113590585",
        clickup_list_id="901109466310",
        zendesk_tag="phyto",
        hubstaff_project_id="3860901",
        sla_tier="gold",
    ),
    ProjectConfig(
        name="Nemesis",
        aliases=["nemesis"],
        clickup_space_id="26271289",
        clickup_list_id="192566104",
        zendesk_tag="nemesis",
        sla_tier="bronze",
    ),
    # --- Internal projects -------------------------------------------------
    ProjectConfig(
        name="Product & Technology",
        aliases=[
            "product & technology", "product and technology",
            "agent007", "orchestrator", "dashboard", "syncaudit",
            "infrastructure", "devops",
        ],
        harvest_project_id="24591687",
        harvest_project_name="Product & Technology",
        hubstaff_project_id="3295429",
        sla_tier="internal",
    ),
    ProjectConfig(
        name="Operations",
        aliases=["operations", "accounting", "invoicing", "upwork", "quickbooks"],
        harvest_project_id="28838838",
        harvest_project_name="Operations",
        sla_tier="internal",
    ),
    ProjectConfig(
        name="CYS-001",
        aliases=["cys-001", "cys", "pcos"],
        harvest_project_id="46242795",
        harvest_project_name="CYS-001",
        hubstaff_project_id="3851845",
        sla_tier="silver",
    ),
    ProjectConfig(
        name="Ongoing Support",
        aliases=["ongoing support", "support"],
        harvest_project_id="47266092",
        harvest_project_name="Ongoing support",
        sla_tier="internal",
    ),
    ProjectConfig(
        name="Proactive Error Tracking",
        aliases=[
            "proactive error tracking", "error tracking",
            "monitoring", "observability",
        ],
        harvest_project_id="47290843",
        harvest_project_name="Proactive error tracking and visibility",
        sla_tier="internal",
    ),
    ProjectConfig(
        name="Client Development",
        aliases=["client development", "client dev"],
        harvest_project_id="38402985",
        harvest_project_name="Client development",
        sla_tier="internal",
    ),
    ProjectConfig(
        name="Customer Dashboard",
        aliases=[
            "customer dashboard", "customer dashboard and document handling",
            "document handling",
        ],
        harvest_project_id="41727306",
        harvest_project_name="Customer Dashboard and Document Handling",
        sla_tier="internal",
    ),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ProjectRegistry:
    """Unified project registry — single source of truth for all project identifiers."""

    def __init__(self, projects: Optional[List[ProjectConfig]] = None):
        self._projects: List[ProjectConfig] = list(projects or _PROJECTS)
        self._alias_index: Dict[str, ProjectConfig] = {}
        self._space_index: Dict[str, ProjectConfig] = {}
        self._tag_index: Dict[str, ProjectConfig] = {}
        self._harvest_index: Dict[str, ProjectConfig] = {}
        self._rebuild_indexes()

    # -- index management ---------------------------------------------------

    def _rebuild_indexes(self) -> None:
        self._alias_index.clear()
        self._space_index.clear()
        self._tag_index.clear()
        self._harvest_index.clear()

        for proj in self._projects:
            # Alias index — includes the canonical name
            for alias in [proj.name.lower()] + [a.lower() for a in proj.aliases]:
                self._alias_index[alias] = proj
            if proj.clickup_space_id:
                self._space_index[proj.clickup_space_id] = proj
            if proj.zendesk_tag:
                self._tag_index[proj.zendesk_tag.lower()] = proj
            if proj.harvest_project_id:
                # Handle dual IDs like "47266092 / 47266090"
                for hid in proj.harvest_project_id.replace(" ", "").split("/"):
                    self._harvest_index[hid] = proj

    # -- lookups ------------------------------------------------------------

    def get_project(self, name_or_alias: str) -> Optional[ProjectConfig]:
        """Look up a project by exact name or alias (case-insensitive)."""
        return self._alias_index.get(name_or_alias.lower().strip())

    def get_all_projects(self, active_only: bool = True) -> List[ProjectConfig]:
        """Return all registered projects."""
        if active_only:
            return [p for p in self._projects if p.active]
        return list(self._projects)

    def get_by_clickup_space(self, space_id: str) -> Optional[ProjectConfig]:
        """Look up a project by its ClickUp space ID."""
        return self._space_index.get(str(space_id))

    def get_by_zendesk_tag(self, tag: str) -> Optional[ProjectConfig]:
        """Look up a project by its Zendesk organization tag."""
        return self._tag_index.get(tag.lower().strip())

    def get_by_harvest_id(self, harvest_id: str) -> Optional[ProjectConfig]:
        """Look up a project by its Harvest project ID."""
        return self._harvest_index.get(str(harvest_id).strip())

    def match_project(self, text: str) -> Optional[ProjectConfig]:
        """Fuzzy match a project from free text (e.g., a chat message).

        Performs case-insensitive substring matching against all aliases.
        Returns the best match — longest alias match wins to avoid false
        positives (e.g., "lcp" won't shadow "lake county pipe").
        """
        text_lower = text.lower()
        best: Optional[ProjectConfig] = None
        best_len = 0

        for alias, proj in self._alias_index.items():
            if alias in text_lower and len(alias) > best_len:
                if not proj.active:
                    continue
                best = proj
                best_len = len(alias)

        return best

    def get_clickup_workspace_id(self) -> str:
        """Return the ClickUp workspace (team) ID."""
        return CLICKUP_WORKSPACE_ID

    def get_fallback_list_id(self) -> str:
        """Return the fallback ClickUp list for unmatched tickets."""
        return CLICKUP_FALLBACK_LIST_ID

    # -- convenience --------------------------------------------------------

    def get_client_projects(self, active_only: bool = True) -> List[ProjectConfig]:
        """Return only client-facing projects (non-internal)."""
        return [
            p for p in self.get_all_projects(active_only=active_only)
            if p.sla_tier != "internal"
        ]

    def get_harvest_task_id(self, task_name: str) -> Optional[str]:
        """Look up a Harvest task type ID by name."""
        return HARVEST_TASK_TYPES.get(task_name)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_registry: Optional[ProjectRegistry] = None


def get_project_registry() -> ProjectRegistry:
    """Get the global project registry singleton."""
    global _registry
    if _registry is None:
        _registry = ProjectRegistry()
    return _registry
