"""
Allowlist - Whitelist-based Permission System

Default: DENY everything
Explicit: ALLOW only what's in the whitelist
Dynamic: Propose additions for safe operations

Permission Levels:
- read: Can read/view only
- write: Can modify
- execute: Can run commands
- admin: Full access (requires human)
"""

import os
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Any
from enum import Enum
from pathlib import Path
import fnmatch
import re

# Paths - relative to this file for portability
GOVERNANCE_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = GOVERNANCE_ROOT.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent


class Permission(Enum):
    """Permission levels from least to most privileged."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"
    
    def __lt__(self, other):
        order = [Permission.NONE, Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.ADMIN]
        return order.index(self) < order.index(other)
    
    def __le__(self, other):
        return self == other or self < other


@dataclass
class AllowlistEntry:
    """A single allowlist entry."""
    pattern: str  # Glob or regex pattern
    permission: Permission
    description: str
    added_by: str = "system"
    added_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    conditions: Optional[Dict[str, Any]] = None  # Additional constraints
    
    def to_dict(self) -> Dict:
        return {
            "pattern": self.pattern,
            "permission": self.permission.value,
            "description": self.description,
            "added_by": self.added_by,
            "added_at": self.added_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "conditions": self.conditions,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AllowlistEntry":
        return cls(
            pattern=data["pattern"],
            permission=Permission(data["permission"]),
            description=data["description"],
            added_by=data.get("added_by", "system"),
            added_at=datetime.fromisoformat(data["added_at"]) if data.get("added_at") else datetime.utcnow(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            conditions=data.get("conditions"),
        )
    
    def matches(self, value: str) -> bool:
        """Check if this entry matches a value."""
        # Expand $WORKSPACE placeholder to actual workspace path
        pattern = self.pattern
        if "$WORKSPACE" in pattern:
            workspace = os.getenv("WORKSPACE_ROOT", str(AGENT007_ROOT))
            pattern = pattern.replace("$WORKSPACE", workspace)
        
        # Try glob match first
        if fnmatch.fnmatch(value, pattern):
            return True
        # Try regex match
        try:
            if re.match(pattern, value):
                return True
        except re.error:
            pass
        # Exact match
        return value == pattern
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


@dataclass
class ProposedEntry:
    """A proposed addition to the allowlist."""
    entry: AllowlistEntry
    reason: str
    risk_assessment: str
    proposed_by: str = "agent"
    proposed_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, approved, rejected
    
    def to_dict(self) -> Dict:
        return {
            "entry": self.entry.to_dict(),
            "reason": self.reason,
            "risk_assessment": self.risk_assessment,
            "proposed_by": self.proposed_by,
            "proposed_at": self.proposed_at.isoformat(),
            "status": self.status,
        }


class Allowlist:
    """
    Whitelist-based permission system.
    
    Categories:
    - environments: Which environments agents can access
    - paths: Which file paths are allowed
    - commands: Which shell commands are allowed
    - tools: Which DevOps tools are allowed
    - apis: Which external APIs are allowed
    """
    
    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path or "./allowlist.json")
        
        # Allowlist by category
        self.environments: List[AllowlistEntry] = []
        self.paths: List[AllowlistEntry] = []
        self.commands: List[AllowlistEntry] = []
        self.tools: List[AllowlistEntry] = []
        self.apis: List[AllowlistEntry] = []
        
        # Proposed entries awaiting approval
        self.proposed: List[ProposedEntry] = []
        
        # Load or initialize
        if self.config_path.exists():
            self.load()
        else:
            self._initialize_defaults()
            self.save()
    
    def _initialize_defaults(self):
        """Initialize with sensible defaults - very restrictive."""
        
        # Environments: Only local and dev by default
        self.environments = [
            AllowlistEntry("local", Permission.ADMIN, "Local development environment"),
            AllowlistEntry("dev", Permission.WRITE, "Development environment"),
            AllowlistEntry("staging", Permission.READ, "Staging - read only by default"),
            # production is NOT in the list - blocked by default
        ]
        
        # Paths: Workspace paths only (default to relative path for portability)
        workspace = os.getenv("WORKSPACE_ROOT", str(AGENT007_ROOT))
        self.paths = [
            # Readable
            AllowlistEntry(f"{workspace}/**/*.py", Permission.READ, "Python source files"),
            AllowlistEntry(f"{workspace}/**/*.md", Permission.READ, "Documentation"),
            AllowlistEntry(f"{workspace}/**/*.json", Permission.READ, "JSON config files"),
            AllowlistEntry(f"{workspace}/**/*.yml", Permission.READ, "YAML config files"),
            AllowlistEntry(f"{workspace}/**/*.yaml", Permission.READ, "YAML config files"),
            AllowlistEntry(f"{workspace}/**/*.txt", Permission.READ, "Text files"),
            AllowlistEntry(f"{workspace}/**/*.sh", Permission.READ, "Shell scripts"),
            AllowlistEntry(f"{workspace}/**/*.php", Permission.READ, "PHP source files"),
            AllowlistEntry(f"{workspace}/**/*.js", Permission.READ, "JavaScript files"),
            AllowlistEntry(f"{workspace}/**/*.ts", Permission.READ, "TypeScript files"),
            AllowlistEntry(f"{workspace}/**/*.css", Permission.READ, "CSS files"),
            AllowlistEntry(f"{workspace}/**/*.html", Permission.READ, "HTML files"),
            
            # Writable - specific directories
            AllowlistEntry(f"{workspace}/Orchestrator/**", Permission.WRITE, "Orchestrator project"),
            AllowlistEntry(f"{workspace}/SyncAudit/**", Permission.WRITE, "SyncAudit project"),
            
            # Explicitly blocked (even though not in list, this makes it clear)
            # .env, secrets/, ssh-ca/ are NOT listed = blocked
        ]
        
        # Commands: Safe read-only commands
        self.commands = [
            # Safe inspection commands
            AllowlistEntry("ls *", Permission.EXECUTE, "List directory contents"),
            AllowlistEntry("cat *", Permission.EXECUTE, "View file contents"),
            AllowlistEntry("head *", Permission.EXECUTE, "View file start"),
            AllowlistEntry("tail *", Permission.EXECUTE, "View file end"),
            AllowlistEntry("grep *", Permission.EXECUTE, "Search in files"),
            AllowlistEntry("find *", Permission.EXECUTE, "Find files"),
            AllowlistEntry("wc *", Permission.EXECUTE, "Count lines/words"),
            AllowlistEntry("file *", Permission.EXECUTE, "Check file type"),
            AllowlistEntry("tree *", Permission.EXECUTE, "Directory tree"),
            
            # Git read operations
            AllowlistEntry("git status*", Permission.EXECUTE, "Git status"),
            AllowlistEntry("git log*", Permission.EXECUTE, "Git history"),
            AllowlistEntry("git diff*", Permission.EXECUTE, "Git diff"),
            AllowlistEntry("git branch*", Permission.EXECUTE, "Git branches"),
            AllowlistEntry("git show*", Permission.EXECUTE, "Git show"),
            
            # Python/Node inspection
            AllowlistEntry("python3 --version", Permission.EXECUTE, "Python version"),
            AllowlistEntry("node --version", Permission.EXECUTE, "Node version"),
            AllowlistEntry("pip list*", Permission.EXECUTE, "List Python packages"),
            AllowlistEntry("npm list*", Permission.EXECUTE, "List Node packages"),
            
            # Testing
            AllowlistEntry("python3 -m pytest*", Permission.EXECUTE, "Run Python tests"),
            AllowlistEntry("npm test*", Permission.EXECUTE, "Run Node tests"),
        ]
        
        # Tools: Safe DevOps tools only
        self.tools = [
            AllowlistEntry("tickets", Permission.EXECUTE, "Ticket management"),
            AllowlistEntry("focus", Permission.EXECUTE, "Focus mode"),
            AllowlistEntry("init-tests", Permission.EXECUTE, "Initialize tests"),
            # Risky tools NOT listed = blocked
        ]
        
        # APIs: No external APIs by default
        self.apis = [
            AllowlistEntry("localhost:*", Permission.READ, "Local services"),
            AllowlistEntry("127.0.0.1:*", Permission.READ, "Local services"),
        ]
    
    def check(self, category: str, value: str, required_permission: Permission = Permission.READ) -> tuple[bool, Optional[AllowlistEntry]]:
        """
        Check if an operation is allowed.
        
        Returns:
            (allowed, matching_entry) - entry is None if not allowed
        """
        entries = getattr(self, category, [])
        
        for entry in entries:
            if entry.is_expired():
                continue
            if entry.matches(value):
                if entry.permission >= required_permission:
                    return True, entry
                else:
                    # Found but insufficient permission
                    return False, entry
        
        # Not found = not allowed
        return False, None
    
    def check_path(self, path: str, permission: Permission = Permission.READ) -> tuple[bool, Optional[AllowlistEntry]]:
        """Check if a path operation is allowed."""
        return self.check("paths", path, permission)
    
    def check_command(self, command: str) -> tuple[bool, Optional[AllowlistEntry]]:
        """Check if a command is allowed."""
        return self.check("commands", command, Permission.EXECUTE)
    
    def check_environment(self, env: str, permission: Permission = Permission.READ) -> tuple[bool, Optional[AllowlistEntry]]:
        """Check if environment access is allowed."""
        return self.check("environments", env, permission)
    
    def check_tool(self, tool: str) -> tuple[bool, Optional[AllowlistEntry]]:
        """Check if a DevOps tool is allowed."""
        return self.check("tools", tool, Permission.EXECUTE)
    
    def propose_addition(
        self,
        category: str,
        pattern: str,
        permission: Permission,
        description: str,
        reason: str,
        risk_assessment: str = None,
    ) -> ProposedEntry:
        """
        Propose a new allowlist entry for human approval.
        
        Called when an operation is blocked but appears safe.
        """
        # Auto-assess risk if not provided
        if risk_assessment is None:
            risk_assessment = self._assess_risk(category, pattern, permission)
        
        entry = AllowlistEntry(
            pattern=pattern,
            permission=permission,
            description=description,
        )
        
        proposal = ProposedEntry(
            entry=entry,
            reason=reason,
            risk_assessment=risk_assessment,
        )
        
        self.proposed.append(proposal)
        self.save()
        
        return proposal
    
    def _assess_risk(self, category: str, pattern: str, permission: Permission) -> str:
        """Auto-assess risk level of a proposed entry."""
        risks = []
        
        # High-risk patterns
        high_risk_patterns = [
            "production", "prod", "live",
            "secret", "key", "password", "token",
            ".env", "credentials",
            "rm ", "delete", "drop",
            "sudo", "chmod", "chown",
        ]
        
        pattern_lower = pattern.lower()
        for hrp in high_risk_patterns:
            if hrp in pattern_lower:
                risks.append(f"Contains high-risk keyword: {hrp}")
        
        # Permission-based risk
        if permission == Permission.ADMIN:
            risks.append("Requests ADMIN permission")
        elif permission == Permission.EXECUTE:
            risks.append("Requests EXECUTE permission")
        elif permission == Permission.WRITE:
            risks.append("Requests WRITE permission")
        
        # Category-based risk
        if category == "commands":
            risks.append("Command execution is inherently risky")
        elif category == "environments" and "prod" in pattern_lower:
            risks.append("Production environment access")
        
        if risks:
            return "ELEVATED RISK: " + "; ".join(risks)
        else:
            return "LOW RISK: Standard read-only access"
    
    def approve_proposal(self, index: int, approved_by: str = "human") -> bool:
        """Approve a proposed entry."""
        if index < 0 or index >= len(self.proposed):
            return False
        
        proposal = self.proposed[index]
        proposal.status = "approved"
        proposal.entry.added_by = approved_by
        proposal.entry.added_at = datetime.utcnow()
        
        # Add to appropriate category
        # Determine category from pattern (simple heuristic)
        if "/" in proposal.entry.pattern or "." in proposal.entry.pattern:
            self.paths.append(proposal.entry)
        elif any(cmd in proposal.entry.pattern for cmd in ["git", "npm", "python", "pip"]):
            self.commands.append(proposal.entry)
        else:
            self.tools.append(proposal.entry)
        
        self.save()
        return True
    
    def reject_proposal(self, index: int) -> bool:
        """Reject a proposed entry."""
        if index < 0 or index >= len(self.proposed):
            return False
        
        self.proposed[index].status = "rejected"
        self.save()
        return True
    
    def add_entry(
        self,
        category: str,
        pattern: str,
        permission: Permission,
        description: str,
        added_by: str = "human",
    ) -> AllowlistEntry:
        """Directly add an entry (for admin use)."""
        entry = AllowlistEntry(
            pattern=pattern,
            permission=permission,
            description=description,
            added_by=added_by,
        )
        
        entries = getattr(self, category, None)
        if entries is not None:
            entries.append(entry)
            self.save()
        
        return entry
    
    def remove_entry(self, category: str, pattern: str) -> bool:
        """Remove an entry by pattern."""
        entries = getattr(self, category, None)
        if entries is None:
            return False
        
        for i, entry in enumerate(entries):
            if entry.pattern == pattern:
                entries.pop(i)
                self.save()
                return True
        
        return False
    
    def save(self):
        """Save allowlist to file."""
        data = {
            "environments": [e.to_dict() for e in self.environments],
            "paths": [e.to_dict() for e in self.paths],
            "commands": [e.to_dict() for e in self.commands],
            "tools": [e.to_dict() for e in self.tools],
            "apis": [e.to_dict() for e in self.apis],
            "proposed": [p.to_dict() for p in self.proposed if p.status == "pending"],
        }
        
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load allowlist from file."""
        with open(self.config_path) as f:
            data = json.load(f)
        
        self.environments = [AllowlistEntry.from_dict(e) for e in data.get("environments", [])]
        self.paths = [AllowlistEntry.from_dict(e) for e in data.get("paths", [])]
        self.commands = [AllowlistEntry.from_dict(e) for e in data.get("commands", [])]
        self.tools = [AllowlistEntry.from_dict(e) for e in data.get("tools", [])]
        self.apis = [AllowlistEntry.from_dict(e) for e in data.get("apis", [])]
        
        self.proposed = []
        for p in data.get("proposed", []):
            self.proposed.append(ProposedEntry(
                entry=AllowlistEntry.from_dict(p["entry"]),
                reason=p["reason"],
                risk_assessment=p["risk_assessment"],
                proposed_by=p.get("proposed_by", "agent"),
                proposed_at=datetime.fromisoformat(p["proposed_at"]) if p.get("proposed_at") else datetime.utcnow(),
                status=p.get("status", "pending"),
            ))
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of allowlist."""
        return {
            "environments": len(self.environments),
            "paths": len(self.paths),
            "commands": len(self.commands),
            "tools": len(self.tools),
            "apis": len(self.apis),
            "pending_proposals": len([p for p in self.proposed if p.status == "pending"]),
        }


# Global instance
_allowlist: Optional[Allowlist] = None


def get_allowlist() -> Allowlist:
    """Get the global allowlist instance."""
    global _allowlist
    if _allowlist is None:
        config_path = os.getenv("ALLOWLIST_PATH", "./governance/allowlist.json")
        _allowlist = Allowlist(config_path)
    return _allowlist


def check_allowed(category: str, value: str, permission: Permission = Permission.READ) -> tuple[bool, str]:
    """
    Convenience function to check if an operation is allowed.
    
    Returns:
        (allowed, message)
    """
    allowlist = get_allowlist()
    allowed, entry = allowlist.check(category, value, permission)
    
    if allowed:
        return True, f"Allowed by: {entry.description}"
    elif entry:
        return False, f"Insufficient permission. Has {entry.permission.value}, needs {permission.value}"
    else:
        return False, f"Not in allowlist. Operation blocked by default."


def propose_if_safe(
    category: str,
    value: str,
    permission: Permission,
    reason: str,
) -> Optional[ProposedEntry]:
    """
    Check if operation is allowed; if not, propose addition if it appears safe.
    
    Returns the proposal if one was created, None if operation was allowed or too risky.
    """
    allowlist = get_allowlist()
    allowed, entry = allowlist.check(category, value, permission)
    
    if allowed:
        return None  # Already allowed
    
    # Assess if this seems safe enough to propose
    risk = allowlist._assess_risk(category, value, permission)
    
    if "ELEVATED RISK" in risk and "production" in risk.lower():
        # Too risky to even propose
        return None
    
    # Propose the addition
    return allowlist.propose_addition(
        category=category,
        pattern=value,
        permission=permission,
        description=f"Auto-proposed: {value}",
        reason=reason,
        risk_assessment=risk,
    )
