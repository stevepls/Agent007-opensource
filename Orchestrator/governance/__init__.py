"""
Orchestrator Governance Layer

Provides policy enforcement, validation, audit logging, and cost tracking
for AI agent operations.

Security Model:
- Blocklist (policies.py): Explicit denials for dangerous operations
- Allowlist (allowlist.py): Explicit permissions for safe operations
- Default: DENY if not in allowlist
"""

from .policies import POLICIES, get_policy, inject_policies_into_prompt
from .validators import PreValidator, PostValidator, ValidationResult
from .audit import AuditLogger, AuditEvent
from .cost_tracker import CostTracker, BudgetExceededError
from .allowlist import (
    Allowlist,
    AllowlistEntry,
    Permission,
    ProposedEntry,
    get_allowlist,
    check_allowed,
    propose_if_safe,
)

__all__ = [
    # Policies (blocklist)
    "POLICIES",
    "get_policy",
    "inject_policies_into_prompt",
    # Validators
    "PreValidator",
    "PostValidator",
    "ValidationResult",
    # Audit
    "AuditLogger",
    "AuditEvent",
    # Cost
    "CostTracker",
    "BudgetExceededError",
    # Allowlist (whitelist)
    "Allowlist",
    "AllowlistEntry",
    "Permission",
    "ProposedEntry",
    "get_allowlist",
    "check_allowed",
    "propose_if_safe",
]
