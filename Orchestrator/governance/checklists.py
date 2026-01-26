"""
Orchestrator Checklists

Defines checklists that the Orchestrator uses to verify project state,
documentation completeness, and deployment readiness.

Checklists are automatically checked and surfaced in the UI.
"""

import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class CheckStatus(Enum):
    """Status of a checklist item."""
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"
    UNKNOWN = "unknown"


class CheckPriority(Enum):
    """Priority of a checklist item."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class CheckResult:
    """Result of a single check."""
    name: str
    status: CheckStatus
    message: str
    priority: CheckPriority = CheckPriority.MEDIUM
    details: Optional[str] = None
    fix_command: Optional[str] = None


@dataclass
class ChecklistResult:
    """Result of running a full checklist."""
    name: str
    checks: List[CheckResult] = field(default_factory=list)
    run_at: datetime = field(default_factory=datetime.now)
    
    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)
    
    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)
    
    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)
    
    @property
    def total(self) -> int:
        return len(self.checks)
    
    @property
    def is_healthy(self) -> bool:
        critical_failures = sum(
            1 for c in self.checks 
            if c.status == CheckStatus.FAIL and c.priority == CheckPriority.CRITICAL
        )
        return critical_failures == 0


# =============================================================================
# Documentation Checklist
# =============================================================================

def check_documentation(project_path: Path) -> ChecklistResult:
    """
    Check documentation completeness for a project.
    
    Checks:
    - README.md exists and has content
    - Mermaid diagrams are present and recent
    - AppMap is configured
    - API documentation exists
    - CHANGELOG exists
    """
    result = ChecklistResult(name="Documentation")
    
    # Check README
    readme = project_path / "README.md"
    if readme.exists():
        content = readme.read_text()
        if len(content) > 500:
            result.checks.append(CheckResult(
                name="README.md",
                status=CheckStatus.PASS,
                message="README exists and has content",
                priority=CheckPriority.HIGH,
            ))
        else:
            result.checks.append(CheckResult(
                name="README.md",
                status=CheckStatus.WARN,
                message="README exists but seems incomplete",
                priority=CheckPriority.HIGH,
                details=f"Only {len(content)} characters",
            ))
    else:
        result.checks.append(CheckResult(
            name="README.md",
            status=CheckStatus.FAIL,
            message="README.md not found",
            priority=CheckPriority.HIGH,
            fix_command="touch README.md",
        ))
    
    # Check for docs directory
    docs_dir = project_path / "docs"
    if docs_dir.exists():
        result.checks.append(CheckResult(
            name="docs/ directory",
            status=CheckStatus.PASS,
            message="Documentation directory exists",
            priority=CheckPriority.MEDIUM,
        ))
    else:
        result.checks.append(CheckResult(
            name="docs/ directory",
            status=CheckStatus.WARN,
            message="No docs/ directory",
            priority=CheckPriority.MEDIUM,
            fix_command="init-docs .",
        ))
    
    # Check for Mermaid diagrams
    diagrams_dir = project_path / "docs" / "diagrams"
    mermaid_files = list(diagrams_dir.glob("*.mmd")) if diagrams_dir.exists() else []
    if mermaid_files:
        result.checks.append(CheckResult(
            name="Mermaid diagrams",
            status=CheckStatus.PASS,
            message=f"{len(mermaid_files)} diagram(s) found",
            priority=CheckPriority.MEDIUM,
        ))
    else:
        result.checks.append(CheckResult(
            name="Mermaid diagrams",
            status=CheckStatus.WARN,
            message="No Mermaid diagrams found",
            priority=CheckPriority.MEDIUM,
            fix_command="python3 ~/DevOps/observability/scripts/generate-diagrams.py --project .",
        ))
    
    # Check for AppMap configuration
    appmap_config = project_path / "appmap.yml"
    if appmap_config.exists():
        result.checks.append(CheckResult(
            name="AppMap configuration",
            status=CheckStatus.PASS,
            message="appmap.yml found",
            priority=CheckPriority.MEDIUM,
        ))
    else:
        result.checks.append(CheckResult(
            name="AppMap configuration",
            status=CheckStatus.WARN,
            message="AppMap not configured",
            priority=CheckPriority.LOW,
            fix_command="~/DevOps/observability/appmap/setup.sh .",
        ))
    
    # Check for AppMap recordings
    appmap_dirs = [
        project_path / "tmp" / "appmap",
        project_path / "storage" / "appmap",
    ]
    appmap_recordings = []
    for d in appmap_dirs:
        if d.exists():
            appmap_recordings.extend(list(d.glob("*.appmap.json")))
    
    if appmap_recordings:
        result.checks.append(CheckResult(
            name="AppMap recordings",
            status=CheckStatus.PASS,
            message=f"{len(appmap_recordings)} recording(s) found",
            priority=CheckPriority.LOW,
        ))
    elif appmap_config.exists():
        result.checks.append(CheckResult(
            name="AppMap recordings",
            status=CheckStatus.WARN,
            message="AppMap configured but no recordings",
            priority=CheckPriority.LOW,
            details="Run tests to generate recordings",
        ))
    
    # Check for CHANGELOG
    changelog = project_path / "CHANGELOG.md"
    if changelog.exists():
        result.checks.append(CheckResult(
            name="CHANGELOG.md",
            status=CheckStatus.PASS,
            message="CHANGELOG exists",
            priority=CheckPriority.LOW,
        ))
    else:
        result.checks.append(CheckResult(
            name="CHANGELOG.md",
            status=CheckStatus.WARN,
            message="No CHANGELOG.md",
            priority=CheckPriority.LOW,
        ))
    
    # Check git hooks
    post_commit = project_path / ".git" / "hooks" / "post-commit"
    if post_commit.exists():
        content = post_commit.read_text()
        if "generate-diagrams" in content:
            result.checks.append(CheckResult(
                name="Auto-documentation hook",
                status=CheckStatus.PASS,
                message="Diagram generation on commit enabled",
                priority=CheckPriority.MEDIUM,
            ))
        else:
            result.checks.append(CheckResult(
                name="Auto-documentation hook",
                status=CheckStatus.WARN,
                message="Post-commit hook exists but no diagram generation",
                priority=CheckPriority.MEDIUM,
                fix_command="init-docs .",
            ))
    else:
        result.checks.append(CheckResult(
            name="Auto-documentation hook",
            status=CheckStatus.WARN,
            message="No post-commit hook for auto-documentation",
            priority=CheckPriority.MEDIUM,
            fix_command="init-docs .",
        ))
    
    return result


# =============================================================================
# Security Checklist
# =============================================================================

def check_security(project_path: Path) -> ChecklistResult:
    """
    Check security best practices for a project.
    """
    result = ChecklistResult(name="Security")
    
    # Check .gitignore exists
    gitignore = project_path / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        
        # Check for common secret patterns
        secret_patterns = [".env", "credentials", "secrets", "*.pem", "*.key"]
        missing = [p for p in secret_patterns if p not in content]
        
        if not missing:
            result.checks.append(CheckResult(
                name=".gitignore secrets",
                status=CheckStatus.PASS,
                message="Common secret patterns in .gitignore",
                priority=CheckPriority.CRITICAL,
            ))
        else:
            result.checks.append(CheckResult(
                name=".gitignore secrets",
                status=CheckStatus.WARN,
                message=f"Missing patterns: {', '.join(missing[:3])}",
                priority=CheckPriority.CRITICAL,
            ))
    else:
        result.checks.append(CheckResult(
            name=".gitignore",
            status=CheckStatus.FAIL,
            message="No .gitignore file",
            priority=CheckPriority.CRITICAL,
        ))
    
    # Check for .env.example
    env_example = project_path / ".env.example"
    env_file = project_path / ".env"
    if env_example.exists():
        result.checks.append(CheckResult(
            name=".env.example",
            status=CheckStatus.PASS,
            message="Environment template exists",
            priority=CheckPriority.HIGH,
        ))
    elif env_file.exists():
        result.checks.append(CheckResult(
            name=".env.example",
            status=CheckStatus.WARN,
            message=".env exists but no .env.example template",
            priority=CheckPriority.HIGH,
        ))
    
    # Check for hardcoded secrets in common files
    # This is a simple check - full scan done by security tools
    suspicious_patterns = ["password=", "api_key=", "secret=", "token="]
    files_to_check = list(project_path.glob("*.py")) + list(project_path.glob("*.php"))
    
    secrets_found = False
    for f in files_to_check[:20]:  # Limit check
        try:
            content = f.read_text()
            for pattern in suspicious_patterns:
                if pattern in content.lower():
                    secrets_found = True
                    break
        except Exception:
            continue
    
    if not secrets_found:
        result.checks.append(CheckResult(
            name="Hardcoded secrets",
            status=CheckStatus.PASS,
            message="No obvious hardcoded secrets in source files",
            priority=CheckPriority.CRITICAL,
        ))
    else:
        result.checks.append(CheckResult(
            name="Hardcoded secrets",
            status=CheckStatus.WARN,
            message="Possible hardcoded secrets detected",
            priority=CheckPriority.CRITICAL,
            fix_command="~/DevOps/security/scan.sh .",
        ))
    
    return result


# =============================================================================
# Deployment Checklist
# =============================================================================

def check_deployment_readiness(project_path: Path) -> ChecklistResult:
    """
    Check if project is ready for deployment.
    """
    result = ChecklistResult(name="Deployment Readiness")
    
    # Check for docker-compose
    docker_compose = project_path / "docker-compose.yml"
    docker_compose_prod = project_path / "docker-compose.prod.yml"
    
    if docker_compose.exists() or docker_compose_prod.exists():
        result.checks.append(CheckResult(
            name="Docker Compose",
            status=CheckStatus.PASS,
            message="Docker Compose configuration found",
            priority=CheckPriority.HIGH,
        ))
    else:
        result.checks.append(CheckResult(
            name="Docker Compose",
            status=CheckStatus.WARN,
            message="No Docker Compose configuration",
            priority=CheckPriority.HIGH,
        ))
    
    # Check for Dockerfile
    dockerfile = project_path / "Dockerfile"
    if dockerfile.exists():
        result.checks.append(CheckResult(
            name="Dockerfile",
            status=CheckStatus.PASS,
            message="Dockerfile found",
            priority=CheckPriority.MEDIUM,
        ))
    
    # Check for CI/CD configuration
    ci_configs = [
        project_path / ".github" / "workflows",
        project_path / "bitbucket-pipelines.yml",
        project_path / ".gitlab-ci.yml",
    ]
    
    ci_found = any(c.exists() for c in ci_configs)
    if ci_found:
        result.checks.append(CheckResult(
            name="CI/CD Configuration",
            status=CheckStatus.PASS,
            message="CI/CD configuration found",
            priority=CheckPriority.HIGH,
        ))
    else:
        result.checks.append(CheckResult(
            name="CI/CD Configuration",
            status=CheckStatus.WARN,
            message="No CI/CD configuration detected",
            priority=CheckPriority.MEDIUM,
        ))
    
    # Check for tests
    test_dirs = [
        project_path / "tests",
        project_path / "test",
        project_path / "Tests",
    ]
    
    tests_exist = any(d.exists() for d in test_dirs)
    if tests_exist:
        result.checks.append(CheckResult(
            name="Test Suite",
            status=CheckStatus.PASS,
            message="Test directory found",
            priority=CheckPriority.HIGH,
        ))
    else:
        result.checks.append(CheckResult(
            name="Test Suite",
            status=CheckStatus.WARN,
            message="No test directory found",
            priority=CheckPriority.HIGH,
        ))
    
    return result


# =============================================================================
# Run All Checklists
# =============================================================================

def run_all_checklists(project_path: str) -> Dict[str, ChecklistResult]:
    """
    Run all checklists for a project.
    
    Returns dict of checklist name -> result.
    """
    path = Path(project_path)
    
    if not path.exists():
        raise ValueError(f"Project path not found: {project_path}")
    
    return {
        "documentation": check_documentation(path),
        "security": check_security(path),
        "deployment": check_deployment_readiness(path),
    }


def format_checklist_results(results: Dict[str, ChecklistResult]) -> str:
    """Format checklist results for display."""
    output = []
    
    for name, checklist in results.items():
        status_emoji = "✅" if checklist.is_healthy else "⚠️"
        output.append(f"\n## {status_emoji} {checklist.name}")
        output.append(f"*{checklist.passed}/{checklist.total} passed*\n")
        
        for check in checklist.checks:
            if check.status == CheckStatus.PASS:
                emoji = "✅"
            elif check.status == CheckStatus.FAIL:
                emoji = "❌"
            elif check.status == CheckStatus.WARN:
                emoji = "⚠️"
            else:
                emoji = "⏭️"
            
            output.append(f"- {emoji} **{check.name}**: {check.message}")
            
            if check.fix_command:
                output.append(f"  - Fix: `{check.fix_command}`")
    
    return "\n".join(output)
