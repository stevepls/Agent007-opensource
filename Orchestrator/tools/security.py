"""
Security Scanning Tools for CrewAI

Provides tools for agents to run security scans using
Checkov, Trivy, and Bandit.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Optional, List, Type, Dict, Any
from pydantic import BaseModel, Field

try:
    from crewai.tools import BaseTool
except ImportError:
    from crewai_tools import BaseTool


# Paths
DEVOPS_ROOT = Path(os.environ.get("DEVOPS_ROOT", Path.home() / "DevOps"))
SECURITY_CONFIG_DIR = DEVOPS_ROOT / "security"


# =============================================================================
# Input Schemas
# =============================================================================

class SecurityScanInput(BaseModel):
    """Input for security scanning."""
    path: str = Field(description="Path to scan (file or directory)")
    scanners: Optional[List[str]] = Field(
        None,
        description="Scanners to run: checkov, trivy, bandit. Default: all applicable"
    )
    severity: Optional[str] = Field(
        "HIGH",
        description="Minimum severity: LOW, MEDIUM, HIGH, CRITICAL"
    )


class CheckovScanInput(BaseModel):
    """Input for Checkov scan."""
    path: str = Field(description="Path to scan")
    framework: Optional[str] = Field(
        None,
        description="Framework to scan: dockerfile, kubernetes, terraform, etc."
    )
    compact: bool = Field(True, description="Compact output")


class TrivyScanInput(BaseModel):
    """Input for Trivy scan."""
    path: str = Field(description="Path to scan (directory or image)")
    scan_type: str = Field("fs", description="Scan type: fs (filesystem), image, repo")
    severity: str = Field("HIGH,CRITICAL", description="Severity filter")


class BanditScanInput(BaseModel):
    """Input for Bandit scan."""
    path: str = Field(description="Python code path to scan")
    severity: str = Field("MEDIUM", description="Minimum severity: LOW, MEDIUM, HIGH")


# =============================================================================
# Helper Functions
# =============================================================================

def _run_command(cmd: List[str], timeout: int = 300) -> Dict[str, Any]:
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
        }
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command not found. Install the tool first.",
            "returncode": -1,
        }


def _detect_project_type(path: str) -> List[str]:
    """Detect project type to determine which scanners to run."""
    p = Path(path)
    scanners = []
    
    if p.is_file():
        if p.suffix == ".py":
            scanners.append("bandit")
        elif p.name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"):
            scanners.extend(["checkov", "trivy"])
        elif p.suffix in (".tf", ".yaml", ".yml"):
            scanners.append("checkov")
    else:
        # Directory - check for various project indicators
        if (p / "requirements.txt").exists() or (p / "setup.py").exists() or (p / "pyproject.toml").exists():
            scanners.append("bandit")
        
        if (p / "Dockerfile").exists() or list(p.glob("docker-compose*.yml")):
            scanners.extend(["checkov", "trivy"])
        
        if list(p.glob("*.tf")) or (p / "terraform").exists():
            scanners.append("checkov")
        
        if (p / "k8s").exists() or list(p.glob("**/deployment.yaml")):
            scanners.extend(["checkov", "trivy"])
    
    return list(set(scanners))


# =============================================================================
# Security Scanning Tools
# =============================================================================

class RunSecurityScanTool(BaseTool):
    """Run comprehensive security scan."""
    
    name: str = "run_security_scan"
    description: str = """
Run security scans on a path. Auto-detects project type and runs appropriate scanners:
- Checkov: Infrastructure as Code (Docker, Kubernetes, Terraform)
- Trivy: Vulnerabilities in dependencies and containers
- Bandit: Python security issues

Returns summary of findings with severity levels.
"""
    args_schema: Type[BaseModel] = SecurityScanInput
    
    def _run(
        self,
        path: str,
        scanners: List[str] = None,
        severity: str = "HIGH",
    ) -> str:
        path = os.path.expanduser(path)
        
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."
        
        # Auto-detect scanners if not specified
        if not scanners:
            scanners = _detect_project_type(path)
            if not scanners:
                return "Could not determine project type. Specify scanners manually."
        
        results = []
        
        for scanner in scanners:
            if scanner == "checkov":
                result = self._run_checkov(path, severity)
            elif scanner == "trivy":
                result = self._run_trivy(path, severity)
            elif scanner == "bandit":
                result = self._run_bandit(path, severity)
            else:
                result = f"Unknown scanner: {scanner}"
            
            results.append(f"=== {scanner.upper()} ===\n{result}")
        
        return "\n\n".join(results)
    
    def _run_checkov(self, path: str, severity: str) -> str:
        config_file = SECURITY_CONFIG_DIR / ".checkov.yml"
        cmd = ["checkov", "-d", path, "--quiet", "--compact"]
        
        if config_file.exists():
            cmd.extend(["--config-file", str(config_file)])
        
        result = _run_command(cmd)
        
        if result["returncode"] == -1:
            return result["stderr"]
        
        # Parse output
        output = result["stdout"]
        if "Passed checks:" in output:
            # Extract summary
            lines = output.split("\n")
            summary_lines = [l for l in lines if any(x in l for x in ["Passed", "Failed", "Skipped"])]
            return "\n".join(summary_lines) if summary_lines else "Scan completed. No issues found."
        
        return output[:1000] if output else "No issues found."
    
    def _run_trivy(self, path: str, severity: str) -> str:
        config_file = SECURITY_CONFIG_DIR / "trivy.yaml"
        cmd = ["trivy", "fs", path, "--severity", severity]
        
        if config_file.exists():
            cmd.extend(["--config", str(config_file)])
        
        result = _run_command(cmd)
        
        if result["returncode"] == -1:
            return result["stderr"]
        
        output = result["stdout"]
        # Summarize output
        if "Total:" in output:
            lines = output.split("\n")
            summary = [l for l in lines if "Total:" in l or "CRITICAL" in l or "HIGH" in l]
            return "\n".join(summary[:10]) if summary else "No vulnerabilities found."
        
        return output[:1000] if output else "No vulnerabilities found."
    
    def _run_bandit(self, path: str, severity: str) -> str:
        config_file = SECURITY_CONFIG_DIR / "bandit.yml"
        cmd = ["bandit", "-r", path, "-ll"]  # -ll = medium and higher
        
        if config_file.exists():
            cmd.extend(["-c", str(config_file)])
        
        result = _run_command(cmd)
        
        if result["returncode"] == -1:
            return result["stderr"]
        
        output = result["stdout"]
        # Extract summary
        if "Run metrics:" in output or "Total lines" in output:
            lines = output.split("\n")
            # Find issues
            issues = [l for l in lines if "Issue:" in l or "Severity:" in l]
            if issues:
                return f"Found {len([l for l in issues if 'Issue:' in l])} issues:\n" + "\n".join(issues[:20])
        
        return "No security issues found."


class RunCheckovTool(BaseTool):
    """Run Checkov IaC security scan."""
    
    name: str = "run_checkov"
    description: str = "Run Checkov infrastructure-as-code security scan on Docker, Kubernetes, Terraform files."
    args_schema: Type[BaseModel] = CheckovScanInput
    
    def _run(
        self,
        path: str,
        framework: str = None,
        compact: bool = True,
    ) -> str:
        path = os.path.expanduser(path)
        
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."
        
        cmd = ["checkov", "-d", path]
        
        if framework:
            cmd.extend(["--framework", framework])
        if compact:
            cmd.append("--compact")
        
        cmd.append("--quiet")
        
        result = _run_command(cmd, timeout=180)
        
        if result["returncode"] == -1:
            return f"Error: {result['stderr']}"
        
        output = result["stdout"]
        return output[:2000] if output else "No issues found."


class RunTrivyTool(BaseTool):
    """Run Trivy vulnerability scan."""
    
    name: str = "run_trivy"
    description: str = "Run Trivy vulnerability scanner on filesystem, container images, or git repos."
    args_schema: Type[BaseModel] = TrivyScanInput
    
    def _run(
        self,
        path: str,
        scan_type: str = "fs",
        severity: str = "HIGH,CRITICAL",
    ) -> str:
        path = os.path.expanduser(path)
        
        if scan_type == "fs" and not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."
        
        cmd = ["trivy", scan_type, path, "--severity", severity]
        
        result = _run_command(cmd, timeout=300)
        
        if result["returncode"] == -1:
            return f"Error: {result['stderr']}"
        
        output = result["stdout"]
        
        # Summarize if too long
        if len(output) > 2000:
            lines = output.split("\n")
            # Keep header and summary
            summary = lines[:50]
            return "\n".join(summary) + f"\n\n... ({len(lines) - 50} more lines)"
        
        return output if output else "No vulnerabilities found."


class RunBanditTool(BaseTool):
    """Run Bandit Python security scan."""
    
    name: str = "run_bandit"
    description: str = "Run Bandit security linter on Python code to find common security issues."
    args_schema: Type[BaseModel] = BanditScanInput
    
    def _run(
        self,
        path: str,
        severity: str = "MEDIUM",
    ) -> str:
        path = os.path.expanduser(path)
        
        if not os.path.exists(path):
            return f"Error: Path '{path}' does not exist."
        
        severity_flag = {
            "LOW": "-l",
            "MEDIUM": "-ll",
            "HIGH": "-lll",
        }.get(severity.upper(), "-ll")
        
        cmd = ["bandit", "-r", path, severity_flag, "-f", "txt"]
        
        result = _run_command(cmd, timeout=180)
        
        if result["returncode"] == -1:
            return f"Error: {result['stderr']}"
        
        output = result["stdout"]
        return output[:2000] if output else "No security issues found."


class CheckSecurityDependenciesTool(BaseTool):
    """Check Python dependencies for known vulnerabilities."""
    
    name: str = "check_security_dependencies"
    description: str = "Check Python dependencies for known security vulnerabilities using Safety."
    args_schema: Type[BaseModel] = SecurityScanInput
    
    def _run(
        self,
        path: str,
        scanners: List[str] = None,  # ignored
        severity: str = "HIGH",  # ignored
    ) -> str:
        path = os.path.expanduser(path)
        
        # Find requirements file
        p = Path(path)
        req_files = []
        
        if p.is_file() and p.name.endswith(".txt"):
            req_files.append(str(p))
        else:
            # Search for requirements files
            req_files.extend([str(f) for f in p.glob("**/requirements*.txt")])
        
        if not req_files:
            return "No requirements.txt files found."
        
        results = []
        
        for req_file in req_files[:5]:  # Limit to 5 files
            cmd = ["safety", "check", "-r", req_file, "--output", "text"]
            result = _run_command(cmd, timeout=60)
            
            if result["returncode"] == -1:
                results.append(f"{req_file}: {result['stderr']}")
            else:
                output = result["stdout"]
                if "No known security vulnerabilities" in output:
                    results.append(f"{req_file}: ✓ No vulnerabilities found")
                else:
                    results.append(f"{req_file}:\n{output[:500]}")
        
        return "\n\n".join(results)


# =============================================================================
# Tool Collections
# =============================================================================

def get_security_tools() -> list:
    """Get all security scanning tools."""
    return [
        RunSecurityScanTool(),
        RunCheckovTool(),
        RunTrivyTool(),
        RunBanditTool(),
        CheckSecurityDependenciesTool(),
    ]
