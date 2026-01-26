"""
Claude CLI Tool for CrewAI

Wraps the Claude Code CLI for file operations and code execution.
CrewAI agents use this tool to delegate actual file/bash work to Claude CLI.

Architecture:
    CrewAI (planning/review) → ClaudeCLITool → claude --print → Results

Features:
- Non-interactive mode (--print)
- JSON output for structured parsing
- Tool restrictions (Read, Edit, Bash only)
- Budget limits
- Governance integration
"""

import os
import subprocess
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from crewai.tools import BaseTool

# Paths - relative to this file for portability
ORCHESTRATOR_ROOT = Path(__file__).parent.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent

# Add parent to path for governance imports
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from governance.policies import is_path_blocked, is_production_path
from governance.validators import validate_before_execution, validate_after_execution, ValidationStatus
from governance.audit import get_audit_logger, AuditEvent, ActionType
from governance.cost_tracker import get_cost_tracker


class PermissionMode(Enum):
    """Claude CLI permission modes."""
    DEFAULT = "default"          # Normal interactive prompts
    ACCEPT_EDITS = "acceptEdits" # Auto-accept file edits
    PLAN = "plan"                # Show plan, require approval
    DONT_ASK = "dontAsk"         # Skip permission prompts
    BYPASS = "bypassPermissions" # Bypass all (dangerous!)


@dataclass
class ClaudeCLIConfig:
    """Configuration for Claude CLI invocation."""
    model: str = "sonnet"
    allowed_tools: List[str] = None
    permission_mode: PermissionMode = PermissionMode.PLAN
    max_budget_usd: float = 1.0
    timeout_seconds: int = 300
    working_directory: str = None
    add_dirs: List[str] = None
    system_prompt_append: str = None
    
    def __post_init__(self):
        if self.allowed_tools is None:
            # Default: only allow read, edit, bash (no web, no mcp)
            self.allowed_tools = ["Read", "Edit", "Bash"]


class ClaudeCLITool(BaseTool):
    """
    CrewAI tool that delegates tasks to Claude CLI for execution.
    
    Use this for actual file operations, code writing, and bash commands.
    Claude CLI has native tool use and built-in safety controls.
    """
    
    name: str = "claude_cli"
    description: str = """Execute a task using Claude CLI (Claude Code).
    
    Use this tool when you need to:
    - Read or write files
    - Execute bash commands
    - Make code changes
    
    Claude CLI will handle the actual file operations with its native tools.
    
    Input: A clear task description for Claude CLI to execute.
    Output: The result of Claude CLI's execution (JSON or text).
    
    Example: "Read the file src/main.py and add error handling to the parse function"
    """
    
    config: ClaudeCLIConfig = None
    
    def __init__(self, config: ClaudeCLIConfig = None):
        super().__init__()
        self.config = config or ClaudeCLIConfig()
        self._claude_path = self._find_claude()
    
    def _find_claude(self) -> str:
        """Find the claude CLI executable."""
        # Check common locations
        paths = [
            os.path.expanduser("~/.local/bin/claude"),
            "/usr/local/bin/claude",
            "claude",  # In PATH
        ]
        
        for path in paths:
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return path
            except (subprocess.SubprocessError, FileNotFoundError):
                continue
        
        raise RuntimeError("Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code")
    
    def _build_command(self, task: str) -> List[str]:
        """Build the claude CLI command."""
        cmd = [
            self._claude_path,
            "--print",  # Non-interactive
            "--output-format", "json",  # Structured output
            "--model", self.config.model,
            "--permission-mode", self.config.permission_mode.value,
        ]
        
        # Add allowed tools
        if self.config.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.config.allowed_tools)])
        
        # Add budget limit
        if self.config.max_budget_usd:
            cmd.extend(["--max-budget-usd", str(self.config.max_budget_usd)])
        
        # Add additional directories
        if self.config.add_dirs:
            for d in self.config.add_dirs:
                cmd.extend(["--add-dir", d])
        
        # Add system prompt append
        if self.config.system_prompt_append:
            cmd.extend(["--append-system-prompt", self.config.system_prompt_append])
        
        # Add the task as the prompt
        cmd.append(task)
        
        return cmd
    
    def _run(self, task: str) -> str:
        """Execute a task via Claude CLI."""
        logger = get_audit_logger()
        cost_tracker = get_cost_tracker()
        
        # =======================================================================
        # PRE-VALIDATION
        # =======================================================================
        
        pre_result = validate_before_execution(task=task)
        logger.log_validation("PreValidator", pre_result.to_dict(), context="claude_cli_task")
        
        if pre_result.is_blocked:
            logger.log_policy_violation(
                agent="claude_cli",
                violation_code="TASK_BLOCKED",
                details=f"Task blocked: {[i.message for i in pre_result.issues]}",
                blocked=True,
            )
            return f"BLOCKED: Task violates security policy. Issues: {[i.message for i in pre_result.issues]}"
        
        if pre_result.requires_escalation:
            logger.log_escalation(
                agent="claude_cli",
                reason="Task requires human approval",
                context={"issues": [i.message for i in pre_result.issues]},
            )
            return f"ESCALATE: Task requires human approval before execution. Issues: {[i.message for i in pre_result.issues]}"
        
        # Track tool call
        cost_tracker.record_tool_call()
        
        # =======================================================================
        # EXECUTE CLAUDE CLI
        # =======================================================================
        
        cmd = self._build_command(task)
        working_dir = self.config.working_directory or os.getenv("WORKSPACE_ROOT", str(AGENT007_ROOT))
        
        logger.log(AuditEvent(
            action_type=ActionType.TOOL_USE,
            agent="claude_cli",
            description=f"Invoking Claude CLI: {task[:100]}...",
            input_data={"task": task, "command": " ".join(cmd[:10]) + "..."},
        ))
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=working_dir,
                env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "crewai-orchestrator"},
            )
            
            stdout = result.stdout
            stderr = result.stderr
            
            # Log execution
            logger.log(AuditEvent(
                action_type=ActionType.TOOL_USE,
                agent="claude_cli",
                description=f"Claude CLI completed with exit code {result.returncode}",
                output_data={
                    "exit_code": result.returncode,
                    "stdout_preview": stdout[:500] if stdout else None,
                    "stderr": stderr[:500] if stderr else None,
                },
            ))
            
            if result.returncode != 0:
                cost_tracker.record_failure(f"Claude CLI exit code: {result.returncode}")
                return f"ERROR: Claude CLI failed with exit code {result.returncode}.\nStderr: {stderr}"
            
        except subprocess.TimeoutExpired:
            cost_tracker.record_failure("Claude CLI timeout")
            logger.log(AuditEvent(
                action_type=ActionType.TASK_FAILED,
                agent="claude_cli",
                description=f"Claude CLI timed out after {self.config.timeout_seconds}s",
            ))
            return f"ERROR: Claude CLI timed out after {self.config.timeout_seconds} seconds."
        
        except Exception as e:
            cost_tracker.record_failure(str(e))
            logger.log(AuditEvent(
                action_type=ActionType.TASK_FAILED,
                agent="claude_cli",
                description=f"Claude CLI error: {e}",
            ))
            return f"ERROR: Failed to execute Claude CLI: {e}"
        
        # =======================================================================
        # POST-VALIDATION
        # =======================================================================
        
        post_result = validate_after_execution(response=stdout)
        logger.log_validation("PostValidator", post_result.to_dict(), context="claude_cli_output")
        
        if post_result.is_blocked:
            logger.log_policy_violation(
                agent="claude_cli",
                violation_code="OUTPUT_BLOCKED",
                details=f"Output blocked: {[i.message for i in post_result.issues]}",
                blocked=True,
            )
            return f"BLOCKED: Claude CLI output violates policy. Issues: {[i.message for i in post_result.issues]}"
        
        # =======================================================================
        # PARSE AND RETURN
        # =======================================================================
        
        # Try to parse JSON output
        try:
            output_json = json.loads(stdout)
            
            # Extract the useful parts
            if isinstance(output_json, dict):
                # Handle different output formats
                if "result" in output_json:
                    return json.dumps(output_json["result"], indent=2)
                elif "content" in output_json:
                    return output_json["content"]
                elif "message" in output_json:
                    return output_json["message"]
            
            return json.dumps(output_json, indent=2)
            
        except json.JSONDecodeError:
            # Return raw output if not JSON
            return stdout


class ClaudeCLIReadTool(BaseTool):
    """Specialized tool for reading files via Claude CLI."""
    
    name: str = "claude_read"
    description: str = """Read a file using Claude CLI.
    Input: file path
    Output: file contents"""
    
    def _run(self, file_path: str) -> str:
        # Check path policy first
        if is_path_blocked(file_path):
            return f"BLOCKED: Cannot read '{file_path}' - matches blocked pattern"
        
        cli = ClaudeCLITool(config=ClaudeCLIConfig(
            allowed_tools=["Read"],
            permission_mode=PermissionMode.DONT_ASK,
            max_budget_usd=0.10,
        ))
        
        return cli._run(f"Read the file {file_path} and return its contents")


class ClaudeCLIEditTool(BaseTool):
    """Specialized tool for editing files via Claude CLI."""
    
    name: str = "claude_edit"
    description: str = """Edit a file using Claude CLI.
    Input: file_path ||| edit_instructions
    Example: src/main.py ||| Add error handling to the parse function"""
    
    def _run(self, input_str: str) -> str:
        if "|||" not in input_str:
            return "ERROR: Input must be 'file_path ||| edit_instructions'"
        
        parts = input_str.split("|||", 1)
        file_path = parts[0].strip()
        instructions = parts[1].strip()
        
        # Check path policy
        if is_path_blocked(file_path):
            return f"BLOCKED: Cannot edit '{file_path}' - matches blocked pattern"
        
        if is_production_path(file_path):
            return f"ESCALATE: Cannot edit production path '{file_path}' without approval"
        
        cli = ClaudeCLITool(config=ClaudeCLIConfig(
            allowed_tools=["Read", "Edit"],
            permission_mode=PermissionMode.ACCEPT_EDITS,
            max_budget_usd=0.50,
        ))
        
        return cli._run(f"Edit the file {file_path}: {instructions}")


class ClaudeCLIBashTool(BaseTool):
    """Specialized tool for running bash commands via Claude CLI."""
    
    name: str = "claude_bash"
    description: str = """Run a bash command using Claude CLI.
    Input: bash command or task description
    Example: "List all Python files in the src directory"
    
    NOTE: Destructive commands (rm -rf, etc.) are blocked."""
    
    def _run(self, command: str) -> str:
        # Pre-validate for dangerous commands
        pre_result = validate_before_execution(command=command)
        
        if pre_result.is_blocked:
            return f"BLOCKED: Command violates security policy: {[i.message for i in pre_result.issues]}"
        
        cli = ClaudeCLITool(config=ClaudeCLIConfig(
            allowed_tools=["Bash"],
            permission_mode=PermissionMode.PLAN,  # Show plan before executing
            max_budget_usd=0.25,
        ))
        
        return cli._run(f"Run this bash command or task: {command}")


def get_claude_cli_tools(config: ClaudeCLIConfig = None) -> List[BaseTool]:
    """Get all Claude CLI tools for CrewAI agents."""
    return [
        ClaudeCLITool(config=config or ClaudeCLIConfig()),
        ClaudeCLIReadTool(),
        ClaudeCLIEditTool(),
        ClaudeCLIBashTool(),
    ]
