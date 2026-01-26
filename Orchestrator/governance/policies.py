"""
Centralized Policy Definitions

Single source of truth for all governance rules.
Policies are injected into agent prompts and enforced by validators.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import re


class RiskLevel(Enum):
    """Risk levels for operations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Policy:
    """A single policy rule."""
    name: str
    description: str
    risk_level: RiskLevel
    enabled: bool = True


# =============================================================================
# MASTER POLICY CONFIGURATION
# =============================================================================

POLICIES: Dict[str, Any] = {
    # -------------------------------------------------------------------------
    # SECURITY POLICIES
    # -------------------------------------------------------------------------
    "security": {
        "description": "Prevent unauthorized access and data leaks",
        
        # Files that agents can NEVER read or write
        "blocked_paths": [
            ".env",
            "*.env",
            ".env.*",
            "*.pem",
            "*.key",
            "*.crt",
            "secrets/",
            ".git/",
            ".ssh/",
            "id_rsa*",
            "*.secret",
            "credentials*",
            "wp-config.php",  # WordPress config with DB creds
        ],
        
        # Patterns that should NEVER appear in agent output
        "blocked_output_patterns": [
            r"sk-[a-zA-Z0-9]{48}",  # OpenAI API keys
            r"sk-ant-[a-zA-Z0-9-]+",  # Anthropic API keys
            r"ghp_[a-zA-Z0-9]{36}",  # GitHub tokens
            r"password\s*[=:]\s*['\"][^'\"]+['\"]",  # Hardcoded passwords
            r"api_key\s*[=:]\s*['\"][^'\"]+['\"]",  # Hardcoded API keys
            r"secret\s*[=:]\s*['\"][^'\"]+['\"]",  # Hardcoded secrets
            r"Bearer\s+[a-zA-Z0-9-._~+/]+=*",  # Bearer tokens
        ],
        
        # Commands that should NEVER be executed
        "blocked_commands": [
            "rm -rf /",
            "rm -rf ~",
            "rm -rf .",
            "> /dev/sda",
            "mkfs",
            "dd if=",
            ":(){ :|:& };:",  # Fork bomb
            "chmod 777",
            "curl | bash",
            "wget | bash",
            "eval(",
            "exec(",
            "DROP DATABASE",
            "DROP TABLE",
            "TRUNCATE TABLE",
            "DELETE FROM",  # Without WHERE
        ],
        
        # Operations that require human approval
        "require_approval": [
            "file_delete",
            "file_overwrite",
            "execute_command",
            "external_api_call",
            "database_write",
        ],
    },
    
    # -------------------------------------------------------------------------
    # PRODUCTION PROTECTION POLICIES
    # -------------------------------------------------------------------------
    "production": {
        "description": "Protect live/production environments and data",
        
        # Paths that indicate production environment
        "production_indicators": [
            "/var/www/",
            "/srv/",
            "production/",
            "prod/",
            "live/",
            ".production",
        ],
        
        # Databases that should never be modified
        "protected_databases": [
            "production",
            "prod",
            "live",
            "main",
        ],
        
        # Actions blocked in production context
        "blocked_in_production": [
            "file_write",
            "file_delete",
            "database_write",
            "execute_command",
        ],
        
        # Require explicit confirmation for production access
        "require_explicit_confirmation": True,
    },
    
    # -------------------------------------------------------------------------
    # DATA PROTECTION POLICIES
    # -------------------------------------------------------------------------
    "data_protection": {
        "description": "Protect sensitive user and business data",
        
        # PII patterns to detect and mask
        "pii_patterns": [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
            r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
            r"\b\d{16}\b",  # Credit card
            r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # Phone
        ],
        
        # Fields that should be masked in logs
        "sensitive_fields": [
            "password",
            "ssn",
            "credit_card",
            "card_number",
            "cvv",
            "pin",
            "secret",
            "token",
            "api_key",
        ],
        
        # Max data size to prevent exfiltration (bytes)
        "max_data_export_size": 1_000_000,  # 1MB
    },
    
    # -------------------------------------------------------------------------
    # QUALITY POLICIES
    # -------------------------------------------------------------------------
    "quality": {
        "description": "Ensure code quality and completeness",
        
        # Patterns that indicate incomplete code
        "placeholder_patterns": [
            r"\bTODO\b",
            r"\bFIXME\b",
            r"\bHACK\b",
            r"\bXXX\b",
            r"\.\.\..*implement",
            r"pass\s*#\s*implement",
            r"raise NotImplementedError",
            r"# YOUR CODE HERE",
        ],
        
        # Required patterns in code (at least one must be present for error handling)
        "required_patterns": {
            "error_handling": [
                r"try\s*:",
                r"except\s+",
                r"catch\s*\(",
                r"\.catch\(",
                r"if\s+.*error",
                r"raise\s+",
                r"throw\s+",
            ],
        },
        
        # Max file size (lines)
        "max_file_lines": 500,
        
        # Require code review for all changes
        "require_review": True,
    },
    
    # -------------------------------------------------------------------------
    # COST POLICIES
    # -------------------------------------------------------------------------
    "cost": {
        "description": "Control API costs and prevent runaway spending",
        
        # Token limits
        "max_tokens_per_task": 100_000,
        "max_tokens_per_agent_call": 20_000,
        "warn_at_percentage": 80,
        
        # API call limits
        "max_api_calls_per_task": 50,
        "max_tool_calls_per_task": 100,
        
        # Circuit breaker
        "circuit_breaker_threshold": 5,  # Consecutive failures before halt
        "circuit_breaker_reset_time": 300,  # Seconds
        
        # Rate limiting
        "max_requests_per_minute": 30,
    },
    
    # -------------------------------------------------------------------------
    # ESCALATION POLICIES
    # -------------------------------------------------------------------------
    "escalation": {
        "description": "When to stop and ask a human",
        
        # Automatic escalation triggers
        "auto_escalate_triggers": [
            "confidence < 0.8",
            "involves money or payments",
            "involves legal or compliance",
            "involves user data deletion",
            "involves production systems",
            "involves security configuration",
            "unclear or ambiguous requirements",
            "conflicting instructions",
            "potential data loss",
        ],
        
        # Keywords that trigger escalation
        "escalation_keywords": [
            "production",
            "live",
            "customer data",
            "payment",
            "billing",
            "legal",
            "compliance",
            "gdpr",
            "hipaa",
            "delete all",
            "drop table",
        ],
        
        # Default action when uncertain
        "default_action": "STOP_AND_ASK",
    },
}


# =============================================================================
# POLICY HELPERS
# =============================================================================

def get_policy(category: str, key: str = None) -> Any:
    """
    Get a policy value by category and optional key.
    
    Examples:
        get_policy("security", "blocked_paths")
        get_policy("cost")  # Returns entire cost policy
    """
    if category not in POLICIES:
        return None
    
    if key is None:
        return POLICIES[category]
    
    return POLICIES[category].get(key)


def is_path_blocked(path: str) -> bool:
    """Check if a path matches any blocked pattern."""
    blocked = get_policy("security", "blocked_paths") or []
    
    for pattern in blocked:
        # Convert glob pattern to regex
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        if re.search(regex, path, re.IGNORECASE):
            return True
    
    return False


def is_production_path(path: str) -> bool:
    """Check if a path indicates a production environment."""
    indicators = get_policy("production", "production_indicators") or []
    
    for indicator in indicators:
        if indicator.lower() in path.lower():
            return True
    
    return False


def contains_blocked_pattern(text: str) -> Optional[str]:
    """Check if text contains any blocked output pattern. Returns the pattern if found."""
    patterns = get_policy("security", "blocked_output_patterns") or []
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    
    return None


def contains_placeholder(text: str) -> Optional[str]:
    """Check if text contains placeholder code. Returns the pattern if found."""
    patterns = get_policy("quality", "placeholder_patterns") or []
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return pattern
    
    return None


def should_escalate(text: str) -> bool:
    """Check if content contains escalation keywords."""
    keywords = get_policy("escalation", "escalation_keywords") or []
    
    text_lower = text.lower()
    for keyword in keywords:
        if keyword.lower() in text_lower:
            return True
    
    return False


def inject_policies_into_prompt(base_prompt: str, categories: List[str] = None) -> str:
    """
    Inject policy summaries into an agent's prompt.
    
    Args:
        base_prompt: The agent's base backstory/prompt
        categories: Which policy categories to include (default: all)
    
    Returns:
        Enhanced prompt with policy context
    """
    if categories is None:
        categories = ["security", "production", "quality", "escalation"]
    
    policy_text = "\n\n=== MANDATORY POLICIES ===\n"
    
    if "security" in categories:
        policy_text += """
SECURITY:
- NEVER access files matching: .env, *.pem, *.key, secrets/, .git/
- NEVER output API keys, passwords, or tokens
- NEVER execute: rm -rf, DROP TABLE, curl|bash, chmod 777
- ALWAYS require approval for: file deletion, command execution
"""
    
    if "production" in categories:
        policy_text += """
PRODUCTION PROTECTION:
- NEVER modify files in /var/www/, /srv/, or paths containing 'production', 'prod', 'live'
- NEVER write to production databases
- If you detect production context, STOP and ask for explicit confirmation
"""
    
    if "quality" in categories:
        policy_text += """
QUALITY:
- NEVER use placeholders: TODO, FIXME, ..., pass # implement
- ALWAYS include error handling in code
- ALWAYS complete the full implementation
- Keep files under 500 lines
"""
    
    if "escalation" in categories:
        policy_text += """
ESCALATION:
- If confidence < 80%, STOP and explain your uncertainty
- If task involves: money, legal, user data deletion, production systems → STOP and ask
- If requirements are unclear or conflicting → STOP and ask for clarification
- When in doubt, ALWAYS ask rather than guess
"""
    
    return base_prompt + policy_text
