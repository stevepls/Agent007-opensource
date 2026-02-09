"""
Scaffolding Agent - Project Configuration

Maps projects to their ClickUp spaces/lists, GitHub repos, and local paths.
"""

# ClickUp space IDs and list IDs per project
PROJECT_CONFIGS = {
    "phyto": {
        "name": "Phyto-PDXAromatics",
        "clickup_space_id": "90113590585",
        "clickup_list_id": "901109466310",  # Ongoing Magento 2 Support
        "github_repo": "pdxaromatics/magento2",
        "github_ssh_url": "git@github.com:pdxaromatics/magento2.git",
        "local_path": "/home/steve/Sites/phyto/phytom2-repo",
        "default_branch": "main",
        "stack": ["php", "magento2", "mysql", "elasticsearch"],
        "status_pending": "pending ai scaffolding",
        "status_done": "to do",
        # Hubstaff time tracking
        "hubstaff_project_id": 3860901,  # Phyto-PDXAromatics / List
        "hubstaff_user_id": 2727066,     # Steve Bien-Aime
    },
}

# Branch prefix rules
BRANCH_PREFIXES = {
    "bug": "bugfix",
    "fix": "bugfix",
    "error": "bugfix",
    "broken": "bugfix",
    "crash": "bugfix",
    "not working": "bugfix",
    "issue": "bugfix",
    "feature": "feature",
    "add": "feature",
    "new": "feature",
    "implement": "feature",
    "create": "feature",
    "update": "update",
    "change": "update",
    "modify": "update",
    "adjust": "update",
    "upgrade": "upgrade",
    "version": "upgrade",
    "migrate": "upgrade",
    "hotfix": "hotfix",
    "urgent": "hotfix",
    "critical": "hotfix",
    "emergency": "hotfix",
    "project": "project",
    "setup": "project",
    "configure": "project",
    "init": "project",
}

# Default prefix if no match
DEFAULT_PREFIX = "feature"

# Lock file location (one instance per project)
LOCK_DIR = "/tmp/scaffolding-agent-locks"
