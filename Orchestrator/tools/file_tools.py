"""
File Tools for Agents

Provides safe file operations within the workspace.
All paths are validated to prevent escaping the workspace.

GOVERNANCE INTEGRATION:
- Pre-validation: Check paths against blocked patterns before access
- Post-validation: Check content for secrets/placeholders before write
- Audit logging: Log all file operations for traceability
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from crewai.tools import BaseTool
from pydantic import Field

# Paths - relative to this file for portability
ORCHESTRATOR_ROOT = Path(__file__).parent.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent

# Import governance modules
import sys
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from governance.policies import is_path_blocked, is_production_path, contains_blocked_pattern
from governance.validators import PreValidator, PostValidator, ValidationStatus
from governance.audit import get_audit_logger, ActionType, AuditEvent
from governance.cost_tracker import get_cost_tracker

# Get workspace root from environment (default to relative path for portability)
WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", str(AGENT007_ROOT)))

# Validators
_pre_validator = PreValidator()
_post_validator = PostValidator()


def validate_path(path: str) -> Path:
    """
    Validate that a path is within the workspace.
    Raises ValueError if path escapes workspace.
    """
    # Resolve to absolute path
    if not os.path.isabs(path):
        full_path = WORKSPACE_ROOT / path
    else:
        full_path = Path(path)
    
    # Resolve symlinks and normalize
    try:
        resolved = full_path.resolve()
    except Exception:
        resolved = full_path
    
    # Check if within workspace
    try:
        resolved.relative_to(WORKSPACE_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Path '{path}' is outside workspace. Access denied.")
    
    return resolved


def check_path_policy(path: str, operation: str = "read") -> Tuple[bool, str]:
    """
    Check if a path operation is allowed by policy.
    
    Returns:
        (allowed, message) - message explains why if not allowed
    """
    # Check blocked paths
    if is_path_blocked(path):
        return False, f"BLOCKED: Path '{path}' matches a blocked pattern (security policy)"
    
    # Check production paths for write/delete
    if operation in ["write", "delete"] and is_production_path(path):
        return False, f"BLOCKED: Cannot {operation} to production path '{path}' without approval"
    
    return True, "OK"


def check_content_policy(content: str, file_path: str = None) -> Tuple[bool, str]:
    """
    Check if content is safe to write.
    
    Returns:
        (allowed, message) - message explains why if not allowed
    """
    result = _post_validator.validate_code_output(content, file_path)
    
    if result.is_blocked:
        issues = [i.message for i in result.issues if i.severity == ValidationStatus.BLOCK]
        return False, f"BLOCKED: {'; '.join(issues)}"
    
    if result.has_warnings:
        issues = [i.message for i in result.issues if i.severity == ValidationStatus.WARN]
        return True, f"WARNING: {'; '.join(issues)}"
    
    return True, "OK"


class ReadFileTool(BaseTool):
    """Read a file from the workspace with policy enforcement."""
    
    name: str = "read_file"
    description: str = """Read the contents of a file.
    Use this to understand existing code before making changes.
    Input: file path (relative to workspace or absolute)
    Output: file contents with line numbers
    
    NOTE: Access to .env, secrets/, *.key, *.pem files is BLOCKED."""
    
    def _run(self, file_path: str) -> str:
        logger = get_audit_logger()
        cost_tracker = get_cost_tracker()
        
        try:
            # Track tool call
            cost_tracker.record_tool_call()
            
            # Validate path is within workspace
            path = validate_path(file_path)
            
            # Check policy
            allowed, message = check_path_policy(file_path, "read")
            if not allowed:
                logger.log_policy_violation(
                    agent="tool:read_file",
                    violation_code="BLOCKED_PATH_READ",
                    details=message,
                    blocked=True,
                )
                return f"Error: {message}"
            
            if not path.exists():
                return f"Error: File not found: {file_path}"
            
            if not path.is_file():
                return f"Error: Not a file: {file_path}"
            
            # Read with line numbers
            content = path.read_text()
            lines = content.split('\n')
            numbered = [f"{i+1:4}| {line}" for i, line in enumerate(lines)]
            
            # Log successful read
            logger.log_file_operation(
                agent="tool:read_file",
                operation="read",
                file_path=file_path,
                success=True,
                details=f"Read {len(content)} bytes, {len(lines)} lines",
            )
            
            return f"=== {file_path} ===\n" + '\n'.join(numbered)
            
        except ValueError as e:
            logger.log_file_operation(
                agent="tool:read_file",
                operation="read",
                file_path=file_path,
                success=False,
                details=str(e),
            )
            return f"Error: {e}"
        except Exception as e:
            logger.log_file_operation(
                agent="tool:read_file",
                operation="read",
                file_path=file_path,
                success=False,
                details=str(e),
            )
            return f"Error reading file: {e}"


class WriteFileTool(BaseTool):
    """Write content to a file with policy enforcement and content scanning."""
    
    name: str = "write_file"
    description: str = """Write content to a file.
    Creates parent directories if they don't exist.
    Input: file_path and content (separated by |||)
    Format: file_path ||| content
    Example: src/utils.py ||| def helper():\n    return True
    
    POLICIES ENFORCED:
    - Cannot write to .env, secrets/, production paths
    - Content is scanned for hardcoded secrets (BLOCKED)
    - Content is checked for placeholders like TODO (WARNING)"""
    
    def _run(self, input_str: str) -> str:
        logger = get_audit_logger()
        cost_tracker = get_cost_tracker()
        
        try:
            # Track tool call
            cost_tracker.record_tool_call()
            
            # Parse input
            if "|||" not in input_str:
                return "Error: Input must be 'file_path ||| content'"
            
            parts = input_str.split("|||", 1)
            file_path = parts[0].strip()
            content = parts[1].strip()
            
            # Validate path is within workspace
            path = validate_path(file_path)
            
            # Check path policy
            path_allowed, path_message = check_path_policy(file_path, "write")
            if not path_allowed:
                logger.log_policy_violation(
                    agent="tool:write_file",
                    violation_code="BLOCKED_PATH_WRITE",
                    details=path_message,
                    blocked=True,
                )
                return f"Error: {path_message}"
            
            # Check content policy
            content_allowed, content_message = check_content_policy(content, file_path)
            if not content_allowed:
                logger.log_policy_violation(
                    agent="tool:write_file",
                    violation_code="BLOCKED_CONTENT",
                    details=content_message,
                    blocked=True,
                )
                return f"Error: {content_message}"
            
            # Log warning if present
            if content_message.startswith("WARNING"):
                logger.log(AuditEvent(
                    action_type=ActionType.VALIDATION_CHECK,
                    description=f"Content warning for {file_path}: {content_message}",
                ))
            
            # Create parent directories
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            path.write_text(content)
            
            # Log successful write
            logger.log_file_operation(
                agent="tool:write_file",
                operation="write",
                file_path=file_path,
                success=True,
                details=f"Wrote {len(content)} bytes",
            )
            
            result = f"Successfully wrote {len(content)} bytes to {file_path}"
            if content_message.startswith("WARNING"):
                result += f"\n{content_message}"
            
            return result
            
        except ValueError as e:
            logger.log_file_operation(
                agent="tool:write_file",
                operation="write",
                file_path=file_path if 'file_path' in dir() else "unknown",
                success=False,
                details=str(e),
            )
            return f"Error: {e}"
        except Exception as e:
            logger.log_file_operation(
                agent="tool:write_file",
                operation="write",
                file_path=file_path if 'file_path' in dir() else "unknown",
                success=False,
                details=str(e),
            )
            return f"Error writing file: {e}"


class ListDirectoryTool(BaseTool):
    """List contents of a directory with policy enforcement."""
    
    name: str = "list_directory"
    description: str = """List files and folders in a directory.
    Use this to explore the codebase structure.
    Input: directory path (relative or absolute)
    Output: list of files and folders
    
    NOTE: Hidden files (.env, .git) are not shown."""
    
    def _run(self, dir_path: str) -> str:
        logger = get_audit_logger()
        cost_tracker = get_cost_tracker()
        
        try:
            # Track tool call
            cost_tracker.record_tool_call()
            
            path = validate_path(dir_path or ".")
            
            if not path.exists():
                return f"Error: Directory not found: {dir_path}"
            
            if not path.is_dir():
                return f"Error: Not a directory: {dir_path}"
            
            # List contents
            items = []
            for item in sorted(path.iterdir()):
                # Skip hidden files and common noise
                if item.name.startswith('.') or item.name in ['__pycache__', 'node_modules', '.git']:
                    continue
                
                # Skip blocked paths
                if is_path_blocked(str(item)):
                    continue
                
                if item.is_dir():
                    items.append(f"📁 {item.name}/")
                else:
                    size = item.stat().st_size
                    items.append(f"📄 {item.name} ({size} bytes)")
            
            if not items:
                return f"Directory is empty: {dir_path}"
            
            logger.log_file_operation(
                agent="tool:list_directory",
                operation="read",
                file_path=dir_path,
                success=True,
                details=f"Listed {len(items)} items",
            )
            
            return f"=== {dir_path} ===\n" + '\n'.join(items)
            
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {e}"


class SearchCodeTool(BaseTool):
    """Search for patterns in the codebase using ripgrep."""
    
    name: str = "search_code"
    description: str = """Search for a pattern in the codebase.
    Uses ripgrep for fast, accurate code search.
    Input: search pattern (regex supported)
    Output: matching lines with file paths and line numbers
    
    NOTE: Results from .env, secrets/, and other blocked paths are filtered out."""
    
    def _run(self, pattern: str) -> str:
        logger = get_audit_logger()
        cost_tracker = get_cost_tracker()
        
        try:
            # Track tool call
            cost_tracker.record_tool_call()
            
            # Use ripgrep if available, fallback to grep
            rg_path = subprocess.run(["which", "rg"], capture_output=True, text=True)
            
            if rg_path.returncode == 0:
                cmd = ["rg", "--line-number", "--max-count", "50", pattern, str(WORKSPACE_ROOT)]
            else:
                cmd = ["grep", "-rn", "--max-count=50", pattern, str(WORKSPACE_ROOT)]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout:
                # Filter out blocked paths from results
                lines = result.stdout.strip().split('\n')
                filtered_lines = []
                for line in lines:
                    # Extract file path from result (format: path:line:content)
                    if ':' in line:
                        file_path = line.split(':')[0]
                        if not is_path_blocked(file_path):
                            filtered_lines.append(line)
                
                if len(filtered_lines) > 50:
                    filtered_lines = filtered_lines[:50] + [f"... and {len(filtered_lines) - 50} more matches"]
                
                logger.log_tool_use(
                    agent="tool:search_code",
                    tool="search_code",
                    input_data={"pattern": pattern},
                    output_data={"matches": len(filtered_lines)},
                )
                
                return '\n'.join(filtered_lines) if filtered_lines else f"No matches found for: {pattern}"
            elif result.returncode == 1:
                return f"No matches found for: {pattern}"
            else:
                return f"Search error: {result.stderr}"
                
        except subprocess.TimeoutExpired:
            return "Error: Search timed out"
        except Exception as e:
            return f"Error searching: {e}"


def get_file_tools() -> list:
    """Get all file operation tools with governance integration."""
    return [
        ReadFileTool(),
        WriteFileTool(),
        ListDirectoryTool(),
        SearchCodeTool(),
    ]
