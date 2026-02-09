"""
Sandbox execution layer — re-exports from DevOps/sandbox/.

The actual implementation lives in DevOps/sandbox/ since it's
shared infrastructure, not agent-specific logic.
"""

import sys
from pathlib import Path

# Add DevOps to path so we can import from there
_devops_root = Path(__file__).resolve().parents[4] / "DevOps"
if str(_devops_root) not in sys.path:
    sys.path.insert(0, str(_devops_root))

from sandbox import (
    SandboxRunner,
    SandboxResult,
    SandboxCommand,
    LocalDockerRunner,
    GitHubActionsRunner,
)

__all__ = [
    "SandboxRunner",
    "SandboxResult",
    "SandboxCommand",
    "LocalDockerRunner",
    "GitHubActionsRunner",
]
