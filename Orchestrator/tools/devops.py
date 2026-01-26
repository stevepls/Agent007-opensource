"""
DevOps Tool Wrappers

Provides safe access to DevOps tools from the DevOps/ folder.
All tools are validated against the allowlist before execution.

Available Tools:
- tickets: Ticket management
- focus: Focus mode
- init-tests: Initialize tests
- (more can be added to allowlist)
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from crewai.tools import BaseTool

# Add parent to path for governance imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from governance.allowlist import get_allowlist, Permission, propose_if_safe
from governance.audit import get_audit_logger, AuditEvent, ActionType
from governance.cost_tracker import get_cost_tracker


# DevOps bin directory
DEVOPS_BIN = Path(os.getenv("DEVOPS_BIN", "/home/steve/Agent007/DevOps/bin"))


@dataclass
class DevOpsTool:
    """Metadata for a DevOps tool."""
    name: str
    description: str
    risk_level: str  # low, medium, high, critical
    requires_args: bool = False
    example_usage: str = ""


# Tool registry with metadata
DEVOPS_TOOLS: Dict[str, DevOpsTool] = {
    # Safe tools (low risk)
    "tickets": DevOpsTool(
        name="tickets",
        description="Manage support tickets - view, create, update tickets",
        risk_level="low",
        requires_args=True,
        example_usage="tickets list | tickets show 123",
    ),
    "focus": DevOpsTool(
        name="focus",
        description="Enable focus mode - blocks distractions",
        risk_level="low",
        requires_args=False,
        example_usage="focus",
    ),
    "init-tests": DevOpsTool(
        name="init-tests",
        description="Initialize test environment for a project",
        risk_level="low",
        requires_args=True,
        example_usage="init-tests project-name",
    ),
    
    # Medium risk tools (require approval)
    "download-artifacts": DevOpsTool(
        name="download-artifacts",
        description="Download build artifacts from CI/CD",
        risk_level="medium",
        requires_args=True,
        example_usage="download-artifacts project-name",
    ),
    "lightsail": DevOpsTool(
        name="lightsail",
        description="AWS Lightsail management commands",
        risk_level="medium",
        requires_args=True,
        example_usage="lightsail list | lightsail status instance-name",
    ),
    
    # High risk tools (blocked by default)
    "deploy-cysterhood-plugins": DevOpsTool(
        name="deploy-cysterhood-plugins",
        description="Deploy plugins to Cysterhood - MODIFIES PRODUCTION",
        risk_level="high",
        requires_args=False,
        example_usage="deploy-cysterhood-plugins",
    ),
    "sync-db": DevOpsTool(
        name="sync-db",
        description="Sync database between environments - DATA TRANSFER",
        risk_level="high",
        requires_args=True,
        example_usage="sync-db source target",
    ),
    "sync-cysterhood-db": DevOpsTool(
        name="sync-cysterhood-db",
        description="Sync Cysterhood database - DATA TRANSFER",
        risk_level="high",
        requires_args=False,
        example_usage="sync-cysterhood-db",
    ),
    "wp-add-admin": DevOpsTool(
        name="wp-add-admin",
        description="Add WordPress admin user - SECURITY SENSITIVE",
        risk_level="high",
        requires_args=True,
        example_usage="wp-add-admin site-name username email",
    ),
    
    # Critical tools (never allowed for agents)
    "manage-access": DevOpsTool(
        name="manage-access",
        description="Manage SSH access and permissions - CRITICAL SECURITY",
        risk_level="critical",
        requires_args=True,
        example_usage="BLOCKED - Human only",
    ),
    "ssh-pressable": DevOpsTool(
        name="ssh-pressable",
        description="SSH to Pressable servers - PRODUCTION ACCESS",
        risk_level="critical",
        requires_args=True,
        example_usage="BLOCKED - Human only",
    ),
    "remote-agent": DevOpsTool(
        name="remote-agent",
        description="Run remote agent commands - REMOTE EXECUTION",
        risk_level="critical",
        requires_args=True,
        example_usage="BLOCKED - Human only",
    ),
}


def list_available_tools() -> List[Dict[str, Any]]:
    """List all DevOps tools with their status."""
    allowlist = get_allowlist()
    result = []
    
    for name, tool in DEVOPS_TOOLS.items():
        allowed, entry = allowlist.check_tool(name)
        result.append({
            "name": name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "allowed": allowed,
            "permission": entry.permission.value if entry else "not_in_allowlist",
            "example": tool.example_usage,
        })
    
    return result


class DevOpsToolRunner(BaseTool):
    """
    Run DevOps tools with allowlist validation.
    
    Only tools in the allowlist can be executed.
    High-risk tools will be proposed for approval.
    Critical tools are never allowed.
    """
    
    name: str = "devops_tool"
    description: str = """Run a DevOps tool from the DevOps/bin directory.
    
    Input format: tool_name [arguments]
    Example: tickets list
    Example: focus
    Example: init-tests myproject
    
    Available tools (safe):
    - tickets: Manage support tickets
    - focus: Enable focus mode
    - init-tests: Initialize test environment
    
    Tools requiring approval:
    - download-artifacts: Download CI/CD artifacts
    - lightsail: AWS Lightsail management
    
    Blocked tools (human only):
    - deploy-*, sync-db, manage-access, ssh-*
    """
    
    def _run(self, input_str: str) -> str:
        logger = get_audit_logger()
        cost_tracker = get_cost_tracker()
        allowlist = get_allowlist()
        
        # Parse input
        parts = input_str.strip().split(maxsplit=1)
        tool_name = parts[0] if parts else ""
        args = parts[1] if len(parts) > 1 else ""
        
        # Check if tool exists
        if tool_name not in DEVOPS_TOOLS:
            # Check if it's a real binary
            tool_path = DEVOPS_BIN / tool_name
            if not tool_path.exists():
                return f"ERROR: Unknown DevOps tool: {tool_name}. Use 'devops_list' to see available tools."
        
        tool_meta = DEVOPS_TOOLS.get(tool_name)
        
        # Critical tools are NEVER allowed
        if tool_meta and tool_meta.risk_level == "critical":
            logger.log_policy_violation(
                agent="devops_tool",
                violation_code="CRITICAL_TOOL_BLOCKED",
                details=f"Critical tool '{tool_name}' is blocked for agent access",
                blocked=True,
            )
            return f"BLOCKED: Tool '{tool_name}' is critical and cannot be used by agents. Human intervention required."
        
        # Check allowlist
        allowed, entry = allowlist.check_tool(tool_name)
        
        if not allowed:
            # Propose if medium risk or lower
            if tool_meta and tool_meta.risk_level in ["low", "medium"]:
                proposal = propose_if_safe(
                    category="tools",
                    value=tool_name,
                    permission=Permission.EXECUTE,
                    reason=f"Agent requested DevOps tool: {tool_name}",
                )
                
                if proposal:
                    logger.log(AuditEvent(
                        action_type=ActionType.ESCALATION,
                        agent="devops_tool",
                        description=f"Proposed tool '{tool_name}' for approval",
                    ))
                    return f"ESCALATE: Tool '{tool_name}' not in allowlist. Proposed for approval.\nRisk: {proposal.risk_assessment}\nPlease approve in the Governance tab."
            
            logger.log_policy_violation(
                agent="devops_tool",
                violation_code="TOOL_NOT_ALLOWED",
                details=f"Tool '{tool_name}' not in allowlist",
                blocked=True,
            )
            return f"BLOCKED: Tool '{tool_name}' is not in the allowlist."
        
        # Track tool call
        cost_tracker.record_tool_call()
        
        # Execute the tool
        tool_path = DEVOPS_BIN / tool_name
        
        if not tool_path.exists():
            return f"ERROR: Tool binary not found: {tool_path}"
        
        logger.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent="devops_tool",
            description=f"Executing DevOps tool: {tool_name} {args}",
            input_data={"tool": tool_name, "args": args},
        ))
        
        try:
            cmd = [str(tool_path)]
            if args:
                cmd.extend(args.split())
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(DEVOPS_BIN.parent),
                env={**os.environ, "DEVOPS_AGENT": "true"},
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            
            logger.log(AuditEvent(
                action_type=ActionType.TOOL_USE,
                agent="devops_tool",
                description=f"DevOps tool completed: exit code {result.returncode}",
                output_data={"exit_code": result.returncode, "output_preview": output[:500]},
            ))
            
            if result.returncode != 0:
                return f"Tool exited with code {result.returncode}:\n{output}"
            
            return output or "Command completed successfully (no output)"
            
        except subprocess.TimeoutExpired:
            return f"ERROR: Tool '{tool_name}' timed out after 60 seconds"
        except Exception as e:
            logger.log(AuditEvent(
                action_type=ActionType.TASK_FAILED,
                agent="devops_tool",
                description=f"DevOps tool error: {e}",
            ))
            return f"ERROR: Failed to execute tool: {e}"


class DevOpsListTool(BaseTool):
    """List available DevOps tools and their permissions."""
    
    name: str = "devops_list"
    description: str = """List all available DevOps tools with their permission status.
    Shows which tools are allowed, which require approval, and which are blocked."""
    
    def _run(self, _: str = "") -> str:
        tools = list_available_tools()
        
        lines = ["DevOps Tools:\n"]
        
        # Group by status
        allowed = [t for t in tools if t["allowed"]]
        proposed = [t for t in tools if not t["allowed"] and t["risk_level"] in ["low", "medium"]]
        blocked = [t for t in tools if not t["allowed"] and t["risk_level"] in ["high", "critical"]]
        
        lines.append("✅ ALLOWED (can use directly):")
        for t in allowed:
            lines.append(f"  - {t['name']}: {t['description']}")
        
        lines.append("\n⚠️ REQUIRES APPROVAL (will propose):")
        for t in proposed:
            lines.append(f"  - {t['name']}: {t['description']} (risk: {t['risk_level']})")
        
        lines.append("\n🚫 BLOCKED (human only):")
        for t in blocked:
            lines.append(f"  - {t['name']}: {t['description']} (risk: {t['risk_level']})")
        
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Focus Tool - Cursor Workspace Switcher
# ─────────────────────────────────────────────────────────────────────────────

WORKSPACES_DIR = Path(os.getenv(
    "CURSOR_WORKSPACES_DIR",
    "/home/steve/Agent007/DevOps/.cursor/workspaces"
))

# Project descriptions (mirrors the focus script)
PROJECT_DESCRIPTIONS: Dict[str, str] = {
    "odg-erp": "ODG Odoo ERP application & customization",
    "odg-migration": "ODG data migration & system integration",
    "apdriving": "Driving school booking platform",
    "lcp": "Shopify to NAV ERP connector",
    "upwork-sync": "Upwork to QuickBooks sync",
    "forge-lab": "Forge Lab project",
    "cw": "CW project (Cysterhood)",
    "devops-dashboard": "DevOps dashboard application",
    "pcos-project": "PCOS project - OvaFit & WordPress",
    "phyto": "Phyto project",
}


def list_workspaces() -> List[Dict[str, Any]]:
    """List all available Cursor workspaces."""
    workspaces = []
    
    if not WORKSPACES_DIR.exists():
        return workspaces
    
    for ws_file in sorted(WORKSPACES_DIR.glob("*.code-workspace")):
        name = ws_file.stem
        workspaces.append({
            "name": name,
            "description": PROJECT_DESCRIPTIONS.get(name, "No description"),
            "path": str(ws_file),
        })
    
    return workspaces


class FocusListTool(BaseTool):
    """List available Cursor workspaces."""
    
    name: str = "focus_list"
    description: str = """List all available project workspaces that can be opened in Cursor.
    Returns a list of projects with their names and descriptions."""
    
    def _run(self, _: str = "") -> str:
        workspaces = list_workspaces()
        
        if not workspaces:
            return f"No workspaces found in {WORKSPACES_DIR}"
        
        lines = ["🎯 Available Project Workspaces:\n"]
        for ws in workspaces:
            lines.append(f"  • {ws['name']:18} - {ws['description']}")
        
        lines.append(f"\nUse 'focus_open' with the project name to open a workspace.")
        return "\n".join(lines)


class FocusOpenTool(BaseTool):
    """Open a Cursor workspace for a specific project."""
    
    name: str = "focus_open"
    description: str = """Open a project workspace in a new Cursor window.
    
    Input: Project name (e.g., 'apdriving', 'odg-erp', 'lcp')
    
    This opens a dedicated Cursor workspace with:
    - Isolated codebase indexing
    - Project-specific AI context
    - Pre-configured settings
    
    Use 'focus_list' to see available projects."""
    
    def _run(self, project_name: str) -> str:
        logger = get_audit_logger()
        project_name = project_name.strip().lower()
        
        if not project_name:
            return "ERROR: Please specify a project name. Use 'focus_list' to see available projects."
        
        workspace_file = WORKSPACES_DIR / f"{project_name}.code-workspace"
        
        if not workspace_file.exists():
            available = [ws["name"] for ws in list_workspaces()]
            return (
                f"ERROR: Workspace '{project_name}' not found.\n"
                f"Available workspaces: {', '.join(available)}"
            )
        
        # Check if cursor CLI is available
        cursor_path = subprocess.run(
            ["which", "cursor"],
            capture_output=True,
            text=True,
        )
        
        if cursor_path.returncode != 0:
            return (
                "ERROR: 'cursor' CLI not found in PATH.\n"
                "Install it from Cursor: Cmd/Ctrl+Shift+P → 'Install cursor command'"
            )
        
        # Log the action
        logger.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent="focus_open",
            description=f"Opening workspace: {project_name}",
            input_data={"project": project_name, "workspace": str(workspace_file)},
        ))
        
        try:
            # Open workspace in background
            subprocess.Popen(
                ["cursor", "--no-sandbox", str(workspace_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            
            desc = PROJECT_DESCRIPTIONS.get(project_name, "")
            return (
                f"🚀 Opening {project_name} workspace...\n"
                f"   {workspace_file}\n"
                f"   {desc}\n\n"
                f"✓ Workspace opened in new Cursor window!"
            )
            
        except Exception as e:
            logger.log(AuditEvent(
                action_type=ActionType.TASK_FAILED,
                agent="focus_open",
                description=f"Failed to open workspace: {e}",
            ))
            return f"ERROR: Failed to open workspace: {e}"


def get_devops_tools() -> List[BaseTool]:
    """Get all DevOps tools for CrewAI agents."""
    return [
        DevOpsToolRunner(),
        DevOpsListTool(),
    ]


def get_focus_tools() -> List[BaseTool]:
    """Get Focus workspace tools for CrewAI agents."""
    return [
        FocusListTool(),
        FocusOpenTool(),
    ]
