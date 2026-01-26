"""
Pre and Post Execution Validators

Validates agent inputs and outputs against policies.
Blocks dangerous operations before they happen.
Flags policy violations in outputs.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime
import re

from .policies import (
    get_policy,
    is_path_blocked,
    is_production_path,
    contains_blocked_pattern,
    contains_placeholder,
    should_escalate,
)
from .allowlist import get_allowlist, Permission, propose_if_safe


class ValidationStatus(Enum):
    """Result status of a validation check."""
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    ESCALATE = "escalate"


@dataclass
class ValidationIssue:
    """A single validation issue."""
    code: str
    message: str
    severity: ValidationStatus
    context: Optional[str] = None
    policy_category: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    status: ValidationStatus
    issues: List[ValidationIssue] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    validated_by: str = "unknown"
    
    @property
    def is_blocked(self) -> bool:
        return self.status == ValidationStatus.BLOCK
    
    @property
    def requires_escalation(self) -> bool:
        return self.status == ValidationStatus.ESCALATE
    
    @property
    def has_warnings(self) -> bool:
        return any(i.severity == ValidationStatus.WARN for i in self.issues)
    
    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        # Escalate status if needed
        if issue.severity == ValidationStatus.BLOCK:
            self.status = ValidationStatus.BLOCK
        elif issue.severity == ValidationStatus.ESCALATE and self.status != ValidationStatus.BLOCK:
            self.status = ValidationStatus.ESCALATE
        elif issue.severity == ValidationStatus.WARN and self.status == ValidationStatus.PASS:
            self.status = ValidationStatus.WARN
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": [
                {
                    "code": i.code,
                    "message": i.message,
                    "severity": i.severity.value,
                    "context": i.context,
                    "policy_category": i.policy_category,
                }
                for i in self.issues
            ],
            "timestamp": self.timestamp.isoformat(),
            "validated_by": self.validated_by,
        }


class PreValidator:
    """
    Validates inputs BEFORE agent execution.
    
    Checks:
    - Task description for escalation keywords
    - File paths for blocked patterns
    - Commands for dangerous operations
    - Production environment detection
    """
    
    def __init__(self):
        self.name = "PreValidator"
    
    def validate_task(self, task_description: str) -> ValidationResult:
        """Validate a task description before execution."""
        result = ValidationResult(status=ValidationStatus.PASS, validated_by=self.name)
        
        # Check for escalation keywords
        if should_escalate(task_description):
            result.add_issue(ValidationIssue(
                code="ESCALATE_KEYWORDS",
                message="Task contains keywords requiring human review",
                severity=ValidationStatus.ESCALATE,
                context=task_description[:200],
                policy_category="escalation",
            ))
        
        # Check for production indicators
        if is_production_path(task_description):
            result.add_issue(ValidationIssue(
                code="PRODUCTION_DETECTED",
                message="Task references production environment - requires explicit approval",
                severity=ValidationStatus.ESCALATE,
                context="Detected production indicators in task",
                policy_category="production",
            ))
        
        # Check for blocked commands in task description
        blocked_commands = get_policy("security", "blocked_commands") or []
        for cmd in blocked_commands:
            if cmd.lower() in task_description.lower():
                result.add_issue(ValidationIssue(
                    code="BLOCKED_COMMAND",
                    message=f"Task contains blocked command pattern: {cmd}",
                    severity=ValidationStatus.BLOCK,
                    context=cmd,
                    policy_category="security",
                ))
        
        return result
    
    def validate_file_path(self, path: str, operation: str = "read") -> ValidationResult:
        """Validate a file path before access using allowlist."""
        result = ValidationResult(status=ValidationStatus.PASS, validated_by=self.name)
        
        # First check blocklist (explicit denials always win)
        if is_path_blocked(path):
            result.add_issue(ValidationIssue(
                code="BLOCKED_PATH",
                message=f"Access to path '{path}' is blocked by security policy",
                severity=ValidationStatus.BLOCK,
                context=path,
                policy_category="security",
            ))
            return result
        
        # Check production paths for write operations
        if operation in ["write", "delete"] and is_production_path(path):
            result.add_issue(ValidationIssue(
                code="PRODUCTION_WRITE",
                message=f"Write/delete to production path '{path}' requires approval",
                severity=ValidationStatus.ESCALATE,
                context=path,
                policy_category="production",
            ))
            return result
        
        # Check allowlist
        permission_map = {
            "read": Permission.READ,
            "write": Permission.WRITE,
            "delete": Permission.WRITE,
            "execute": Permission.EXECUTE,
        }
        required_permission = permission_map.get(operation, Permission.READ)
        
        allowlist = get_allowlist()
        allowed, entry = allowlist.check_path(path, required_permission)
        
        if not allowed:
            if entry:
                # Path found but insufficient permission
                result.add_issue(ValidationIssue(
                    code="INSUFFICIENT_PERMISSION",
                    message=f"Path '{path}' requires {required_permission.value} but only has {entry.permission.value}",
                    severity=ValidationStatus.ESCALATE,
                    context=f"Has: {entry.permission.value}, Needs: {required_permission.value}",
                    policy_category="allowlist",
                ))
            else:
                # Path not in allowlist - propose if safe
                proposal = propose_if_safe(
                    category="paths",
                    value=path,
                    permission=required_permission,
                    reason=f"Agent requested {operation} access to {path}",
                )
                
                if proposal:
                    result.add_issue(ValidationIssue(
                        code="NOT_IN_ALLOWLIST_PROPOSED",
                        message=f"Path '{path}' not in allowlist. Proposed for approval: {proposal.risk_assessment}",
                        severity=ValidationStatus.ESCALATE,
                        context=f"Proposal created for human review",
                        policy_category="allowlist",
                    ))
                else:
                    result.add_issue(ValidationIssue(
                        code="NOT_IN_ALLOWLIST",
                        message=f"Path '{path}' not in allowlist and too risky to propose",
                        severity=ValidationStatus.BLOCK,
                        context=path,
                        policy_category="allowlist",
                    ))
        
        return result
    
    def validate_command(self, command: str) -> ValidationResult:
        """Validate a shell command before execution using allowlist."""
        result = ValidationResult(status=ValidationStatus.PASS, validated_by=self.name)
        
        # First check blocklist (explicit denials always win)
        blocked_commands = get_policy("security", "blocked_commands") or []
        
        for blocked in blocked_commands:
            if blocked.lower() in command.lower():
                result.add_issue(ValidationIssue(
                    code="BLOCKED_COMMAND",
                    message=f"Command contains blocked pattern: {blocked}",
                    severity=ValidationStatus.BLOCK,
                    context=command,
                    policy_category="security",
                ))
                return result
        
        # Check for pipe to shell patterns
        if re.search(r'\|\s*(bash|sh|zsh)', command):
            result.add_issue(ValidationIssue(
                code="PIPE_TO_SHELL",
                message="Piping to shell is blocked for security",
                severity=ValidationStatus.BLOCK,
                context=command,
                policy_category="security",
            ))
            return result
        
        # Check allowlist
        allowlist = get_allowlist()
        allowed, entry = allowlist.check_command(command)
        
        if not allowed:
            # Command not in allowlist - propose if safe
            proposal = propose_if_safe(
                category="commands",
                value=command,
                permission=Permission.EXECUTE,
                reason=f"Agent requested command execution: {command[:50]}...",
            )
            
            if proposal:
                result.add_issue(ValidationIssue(
                    code="COMMAND_NOT_IN_ALLOWLIST_PROPOSED",
                    message=f"Command not in allowlist. Proposed for approval: {proposal.risk_assessment}",
                    severity=ValidationStatus.ESCALATE,
                    context=f"Command: {command[:50]}...",
                    policy_category="allowlist",
                ))
            else:
                result.add_issue(ValidationIssue(
                    code="COMMAND_NOT_IN_ALLOWLIST",
                    message=f"Command not in allowlist and too risky to propose",
                    severity=ValidationStatus.BLOCK,
                    context=command[:50],
                    policy_category="allowlist",
                ))
        
        return result


class PostValidator:
    """
    Validates outputs AFTER agent execution.
    
    Checks:
    - Code for placeholders (TODO, FIXME, ...)
    - Output for secrets/credentials
    - Code quality standards
    - Completion of task
    """
    
    def __init__(self):
        self.name = "PostValidator"
    
    def validate_code_output(self, code: str, file_path: str = None) -> ValidationResult:
        """Validate code before writing to file."""
        result = ValidationResult(status=ValidationStatus.PASS, validated_by=self.name)
        
        # Check for placeholder patterns
        placeholder = contains_placeholder(code)
        if placeholder:
            result.add_issue(ValidationIssue(
                code="PLACEHOLDER_CODE",
                message=f"Code contains placeholder pattern: {placeholder}",
                severity=ValidationStatus.WARN,
                context=placeholder,
                policy_category="quality",
            ))
        
        # Check for blocked output patterns (secrets, keys, etc.)
        blocked_pattern = contains_blocked_pattern(code)
        if blocked_pattern:
            result.add_issue(ValidationIssue(
                code="SECRET_IN_OUTPUT",
                message="Code contains what appears to be a secret or API key",
                severity=ValidationStatus.BLOCK,
                context="Pattern matched: [REDACTED]",
                policy_category="security",
            ))
        
        # Check file size
        max_lines = get_policy("quality", "max_file_lines") or 500
        line_count = len(code.split('\n'))
        if line_count > max_lines:
            result.add_issue(ValidationIssue(
                code="FILE_TOO_LARGE",
                message=f"File has {line_count} lines, exceeds max of {max_lines}",
                severity=ValidationStatus.WARN,
                context=f"{line_count} lines",
                policy_category="quality",
            ))
        
        return result
    
    def validate_agent_response(self, response: str, expected_format: str = None) -> ValidationResult:
        """Validate an agent's response for policy compliance."""
        result = ValidationResult(status=ValidationStatus.PASS, validated_by=self.name)
        
        # Check for secrets in response
        blocked_pattern = contains_blocked_pattern(response)
        if blocked_pattern:
            result.add_issue(ValidationIssue(
                code="SECRET_IN_RESPONSE",
                message="Agent response contains what appears to be a secret",
                severity=ValidationStatus.BLOCK,
                context="Pattern matched: [REDACTED]",
                policy_category="security",
            ))
        
        # Check for escalation indicators in response
        low_confidence_patterns = [
            r"i('m| am) not sure",
            r"i('m| am) uncertain",
            r"confidence[:\s]+[0-7]\d?%",  # Less than 80%
            r"this might not be",
            r"i need more (information|context|clarification)",
        ]
        
        for pattern in low_confidence_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                result.add_issue(ValidationIssue(
                    code="LOW_CONFIDENCE",
                    message="Agent expressed uncertainty - consider escalation",
                    severity=ValidationStatus.ESCALATE,
                    context=pattern,
                    policy_category="escalation",
                ))
                break
        
        return result
    
    def validate_review_verdict(self, verdict: str) -> ValidationResult:
        """Validate a code review verdict."""
        result = ValidationResult(status=ValidationStatus.PASS, validated_by=self.name)
        
        verdict_upper = verdict.upper()
        
        if "REJECT" in verdict_upper:
            result.add_issue(ValidationIssue(
                code="REVIEW_REJECTED",
                message="Code review resulted in REJECT - requires fixes",
                severity=ValidationStatus.BLOCK,
                context=verdict,
                policy_category="quality",
            ))
        elif "NEEDS_CHANGES" in verdict_upper:
            result.add_issue(ValidationIssue(
                code="REVIEW_CHANGES_NEEDED",
                message="Code review requires changes before approval",
                severity=ValidationStatus.WARN,
                context=verdict,
                policy_category="quality",
            ))
        
        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_before_execution(
    task: str = None,
    file_path: str = None,
    command: str = None,
    operation: str = "read"
) -> ValidationResult:
    """
    Convenience function to run all relevant pre-execution validations.
    
    Returns combined result with all issues.
    """
    validator = PreValidator()
    combined = ValidationResult(status=ValidationStatus.PASS, validated_by="PreValidator")
    
    if task:
        result = validator.validate_task(task)
        for issue in result.issues:
            combined.add_issue(issue)
    
    if file_path:
        result = validator.validate_file_path(file_path, operation)
        for issue in result.issues:
            combined.add_issue(issue)
    
    if command:
        result = validator.validate_command(command)
        for issue in result.issues:
            combined.add_issue(issue)
    
    return combined


def validate_after_execution(
    code: str = None,
    response: str = None,
    verdict: str = None,
    file_path: str = None
) -> ValidationResult:
    """
    Convenience function to run all relevant post-execution validations.
    
    Returns combined result with all issues.
    """
    validator = PostValidator()
    combined = ValidationResult(status=ValidationStatus.PASS, validated_by="PostValidator")
    
    if code:
        result = validator.validate_code_output(code, file_path)
        for issue in result.issues:
            combined.add_issue(issue)
    
    if response:
        result = validator.validate_agent_response(response)
        for issue in result.issues:
            combined.add_issue(issue)
    
    if verdict:
        result = validator.validate_review_verdict(verdict)
        for issue in result.issues:
            combined.add_issue(issue)
    
    return combined
