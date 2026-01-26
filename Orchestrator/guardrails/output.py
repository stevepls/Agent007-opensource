"""
Structured Output Models

Pydantic models that enforce structured, parseable output from agents.
Use with CrewAI's output_pydantic parameter to ensure consistent responses.

Example:
    task = Task(
        description="Review this code...",
        output_pydantic=CodeReviewOutput,
        agent=reviewer
    )
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Verdict(str, Enum):
    """Code review verdicts."""
    APPROVE = "APPROVE"
    NEEDS_CHANGES = "NEEDS_CHANGES"
    REJECT = "REJECT"


class PolicyViolationType(str, Enum):
    """Types of policy violations."""
    SECURITY = "security"
    QUALITY = "quality"
    PRODUCTION = "production"
    PLACEHOLDER = "placeholder"
    SECRET_DETECTED = "secret_detected"
    BLOCKED_OPERATION = "blocked_operation"


# =============================================================================
# SHARED MODELS
# =============================================================================

class Issue(BaseModel):
    """A single issue found during review or critique."""
    
    severity: Severity = Field(description="How severe is this issue")
    category: str = Field(description="Category: security, quality, performance, style")
    file_path: Optional[str] = Field(default=None, description="File where issue was found")
    line_number: Optional[int] = Field(default=None, description="Line number if applicable")
    description: str = Field(description="Clear description of the issue")
    recommendation: str = Field(description="How to fix this issue")
    
    class Config:
        use_enum_values = True


class SeveritySummary(BaseModel):
    """Summary of issues by severity."""
    
    critical: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    low: int = Field(default=0, ge=0)
    info: int = Field(default=0, ge=0)
    
    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.low + self.info
    
    @property
    def has_blockers(self) -> bool:
        return self.critical > 0


class FileChange(BaseModel):
    """A file that was created or modified."""
    
    file_path: str = Field(description="Path to the file")
    operation: Literal["create", "modify", "delete"] = Field(description="What operation was performed")
    lines_changed: Optional[int] = Field(default=None, description="Number of lines changed")
    description: str = Field(description="Brief description of changes")


class SecurityChecklist(BaseModel):
    """Security checklist for code review."""
    
    no_hardcoded_secrets: bool = Field(description="No hardcoded API keys, passwords, or tokens")
    no_sql_injection: bool = Field(description="No SQL injection vulnerabilities")
    no_xss_vulnerabilities: bool = Field(description="No XSS vulnerabilities")
    no_path_traversal: bool = Field(description="No path traversal risks")
    no_sensitive_file_access: bool = Field(description="No writes to .env, secrets/, etc.")
    proper_input_validation: bool = Field(description="User inputs are validated")
    
    @property
    def all_passed(self) -> bool:
        return all([
            self.no_hardcoded_secrets,
            self.no_sql_injection,
            self.no_xss_vulnerabilities,
            self.no_path_traversal,
            self.no_sensitive_file_access,
            self.proper_input_validation,
        ])


# =============================================================================
# AGENT OUTPUT MODELS
# =============================================================================

class PlanningOutput(BaseModel):
    """Structured output for the Manager/Planning agent."""
    
    task_understanding: str = Field(description="Restate the task in your own words")
    files_to_modify: List[str] = Field(description="List of files to create or modify")
    files_to_read: List[str] = Field(description="List of files to read for context")
    implementation_steps: List[str] = Field(description="Step-by-step implementation plan")
    questions_or_concerns: List[str] = Field(default_factory=list, description="Any clarifying questions")
    estimated_complexity: Literal["low", "medium", "high"] = Field(description="Complexity estimate")
    requires_human_approval: bool = Field(description="Does this need human approval?")
    approval_reason: Optional[str] = Field(default=None, description="Why approval is needed")
    confidence_percentage: int = Field(ge=0, le=100, description="Confidence level 0-100")
    
    @field_validator("confidence_percentage")
    @classmethod
    def check_confidence(cls, v: int) -> int:
        if v < 80:
            # Low confidence should trigger escalation
            pass
        return v
    
    @property
    def should_escalate(self) -> bool:
        return self.confidence_percentage < 80 or self.requires_human_approval or len(self.questions_or_concerns) > 0


class CodingOutput(BaseModel):
    """Structured output for the Coder agent."""
    
    files_modified: List[FileChange] = Field(description="List of files created/modified")
    implementation_summary: str = Field(description="Summary of what was implemented")
    dependencies_added: List[str] = Field(default_factory=list, description="New dependencies if any")
    tests_added: bool = Field(default=False, description="Were tests added?")
    test_files: List[str] = Field(default_factory=list, description="List of test files")
    error_handling_added: bool = Field(description="Was error handling implemented?")
    confidence_percentage: int = Field(ge=0, le=100, description="Confidence level 0-100")
    notes: Optional[str] = Field(default=None, description="Any notes for the reviewer")
    
    @property
    def should_escalate(self) -> bool:
        return self.confidence_percentage < 80


class CodeReviewOutput(BaseModel):
    """
    Structured output for the Reviewer agent.
    
    Forces consistent, parseable code review output.
    """
    
    severity_summary: SeveritySummary = Field(description="Count of issues by severity")
    critical_issues: List[Issue] = Field(default_factory=list, description="Critical issues")
    high_issues: List[Issue] = Field(default_factory=list, description="High severity issues")
    medium_issues: List[Issue] = Field(default_factory=list, description="Medium severity issues")
    low_issues: List[Issue] = Field(default_factory=list, description="Low severity issues")
    security_checklist: SecurityChecklist = Field(description="Security checks")
    verdict: Verdict = Field(description="APPROVE, NEEDS_CHANGES, or REJECT")
    verdict_reasoning: str = Field(description="Why this verdict was given")
    confidence_percentage: int = Field(ge=0, le=100, description="Confidence level 0-100")
    
    @property
    def should_escalate(self) -> bool:
        return (
            self.confidence_percentage < 80 or
            self.severity_summary.has_blockers or
            not self.security_checklist.all_passed
        )
    
    @property
    def all_issues(self) -> List[Issue]:
        return self.critical_issues + self.high_issues + self.medium_issues + self.low_issues


class CritiqueOutput(BaseModel):
    """
    Structured output for the Self-Critique agent.
    
    Reviews agent output against policies.
    """
    
    policy_checks: List[str] = Field(description="Which policies were checked")
    violations_found: List[str] = Field(default_factory=list, description="Policy violations found")
    violation_details: List[Issue] = Field(default_factory=list, description="Detailed violations")
    
    # Quality checks
    is_complete: bool = Field(description="Is the output complete (no TODOs, placeholders)?")
    is_secure: bool = Field(description="Does output follow security policies?")
    is_production_safe: bool = Field(description="Is output safe for production paths?")
    follows_guidelines: bool = Field(description="Does output follow project guidelines?")
    
    # Overall assessment
    verdict: Literal["PASS", "FAIL", "ESCALATE"] = Field(description="PASS, FAIL, or ESCALATE")
    confidence_percentage: int = Field(ge=0, le=100, description="Confidence level 0-100")
    escalation_reason: Optional[str] = Field(default=None, description="Why escalation is needed")
    recommendations: List[str] = Field(default_factory=list, description="Suggested improvements")
    
    @property
    def should_block(self) -> bool:
        return self.verdict == "FAIL"
    
    @property
    def should_escalate(self) -> bool:
        return self.verdict == "ESCALATE" or self.confidence_percentage < 80


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_empty_review() -> CodeReviewOutput:
    """Create an empty code review output for when there's nothing to review."""
    return CodeReviewOutput(
        severity_summary=SeveritySummary(),
        security_checklist=SecurityChecklist(
            no_hardcoded_secrets=True,
            no_sql_injection=True,
            no_xss_vulnerabilities=True,
            no_path_traversal=True,
            no_sensitive_file_access=True,
            proper_input_validation=True,
        ),
        verdict=Verdict.APPROVE,
        verdict_reasoning="No code changes to review",
        confidence_percentage=100,
    )


def count_issues_by_severity(issues: List[Issue]) -> SeveritySummary:
    """Count issues by severity level."""
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    
    for issue in issues:
        severity_key = issue.severity.lower() if isinstance(issue.severity, str) else issue.severity.value
        if severity_key in counts:
            counts[severity_key] += 1
    
    return SeveritySummary(**counts)
