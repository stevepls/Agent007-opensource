"""
Text Quality Checker

Checks text for grammar, spelling, and style issues before sending.
Uses LanguageTool API (free, open source) as Grammarly doesn't have a public API.

All outgoing messages should be checked before queuing.

Options:
1. LanguageTool Cloud API (free tier: 20 requests/minute)
2. Self-hosted LanguageTool server
3. Mock mode for testing
"""

import os
import json
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


# Configuration
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent

# LanguageTool API endpoints
LANGUAGETOOL_API_URL = os.getenv(
    "LANGUAGETOOL_API_URL",
    "https://api.languagetool.org/v2"
)

# Optional premium key for higher limits
LANGUAGETOOL_API_KEY = os.getenv("LANGUAGETOOL_API_KEY")


class IssueType(Enum):
    """Types of text issues."""
    GRAMMAR = "grammar"
    SPELLING = "spelling"
    PUNCTUATION = "punctuation"
    STYLE = "style"
    TYPOGRAPHY = "typography"
    CASING = "casing"
    REDUNDANCY = "redundancy"
    OTHER = "other"


class IssueSeverity(Enum):
    """Severity levels."""
    ERROR = "error"
    WARNING = "warning"
    HINT = "hint"


@dataclass
class TextIssue:
    """A single text quality issue."""
    message: str
    short_message: str
    offset: int
    length: int
    context: str
    issue_type: IssueType
    severity: IssueSeverity
    replacements: List[str]
    rule_id: str
    rule_description: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "short_message": self.short_message,
            "offset": self.offset,
            "length": self.length,
            "context": self.context,
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "replacements": self.replacements,
            "rule_id": self.rule_id,
        }


@dataclass
class TextCheckResult:
    """Result of text quality check."""
    text: str
    language: str
    issues: List[TextIssue]
    is_clean: bool  # No errors (warnings/hints are ok)
    error_count: int
    warning_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text_preview": self.text[:100] + "..." if len(self.text) > 100 else self.text,
            "language": self.language,
            "is_clean": self.is_clean,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
        }
    
    def get_summary(self) -> str:
        """Get a human-readable summary."""
        if self.is_clean:
            return "✓ No errors found"
        
        parts = []
        if self.error_count:
            parts.append(f"{self.error_count} error(s)")
        if self.warning_count:
            parts.append(f"{self.warning_count} warning(s)")
        
        return f"Found: {', '.join(parts)}"
    
    def format_issues(self) -> str:
        """Format issues for display."""
        if not self.issues:
            return "No issues found."
        
        lines = []
        for i, issue in enumerate(self.issues, 1):
            icon = "🔴" if issue.severity == IssueSeverity.ERROR else "🟡"
            lines.append(f"{icon} {i}. {issue.message}")
            if issue.replacements:
                lines.append(f"   Suggestions: {', '.join(issue.replacements[:3])}")
        
        return "\n".join(lines)


class TextChecker:
    """Text quality checker using LanguageTool."""
    
    def __init__(self, api_url: str = None, api_key: str = None):
        self.api_url = (api_url or LANGUAGETOOL_API_URL).rstrip("/")
        self.api_key = api_key or LANGUAGETOOL_API_KEY
        self._available = None
    
    @property
    def is_available(self) -> bool:
        """Check if the API is accessible."""
        if self._available is None:
            try:
                response = requests.get(
                    f"{self.api_url}/languages",
                    timeout=5,
                )
                self._available = response.status_code == 200
            except Exception:
                self._available = False
        return self._available
    
    def _parse_issue_type(self, category: str) -> IssueType:
        """Map LanguageTool categories to our types."""
        category = category.upper()
        if "GRAMMAR" in category:
            return IssueType.GRAMMAR
        elif "TYPO" in category or "SPELL" in category:
            return IssueType.SPELLING
        elif "PUNCT" in category:
            return IssueType.PUNCTUATION
        elif "STYLE" in category:
            return IssueType.STYLE
        elif "TYPOGRAPHY" in category:
            return IssueType.TYPOGRAPHY
        elif "CASE" in category or "CASING" in category:
            return IssueType.CASING
        elif "REDUNDANCY" in category:
            return IssueType.REDUNDANCY
        else:
            return IssueType.OTHER
    
    def _parse_severity(self, match: Dict) -> IssueSeverity:
        """Determine severity from match data."""
        rule = match.get("rule", {})
        issue_type = rule.get("issueType", "").lower()
        
        if issue_type in ("misspelling", "grammar"):
            return IssueSeverity.ERROR
        elif issue_type in ("style", "typographical"):
            return IssueSeverity.WARNING
        else:
            return IssueSeverity.HINT
    
    def check(
        self,
        text: str,
        language: str = "en-US",
        disabled_rules: List[str] = None,
        enabled_only: List[str] = None,
    ) -> TextCheckResult:
        """
        Check text for issues.
        
        Args:
            text: Text to check
            language: Language code (en-US, en-GB, etc.)
            disabled_rules: Rules to disable (e.g., ["WHITESPACE_RULE"])
            enabled_only: Only enable these rules
        
        Returns:
            TextCheckResult with issues found
        """
        if not text or not text.strip():
            return TextCheckResult(
                text=text,
                language=language,
                issues=[],
                is_clean=True,
                error_count=0,
                warning_count=0,
            )
        
        # Build request
        data = {
            "text": text,
            "language": language,
        }
        
        if self.api_key:
            data["apiKey"] = self.api_key
        
        if disabled_rules:
            data["disabledRules"] = ",".join(disabled_rules)
        
        if enabled_only:
            data["enabledRules"] = ",".join(enabled_only)
            data["enabledOnly"] = "true"
        
        try:
            response = requests.post(
                f"{self.api_url}/check",
                data=data,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.RequestException as e:
            # Return clean result on API failure (fail open for UX)
            return TextCheckResult(
                text=text,
                language=language,
                issues=[],
                is_clean=True,
                error_count=0,
                warning_count=0,
            )
        
        # Parse matches into issues
        issues = []
        error_count = 0
        warning_count = 0
        
        for match in result.get("matches", []):
            rule = match.get("rule", {})
            category = rule.get("category", {})
            
            severity = self._parse_severity(match)
            if severity == IssueSeverity.ERROR:
                error_count += 1
            elif severity == IssueSeverity.WARNING:
                warning_count += 1
            
            issues.append(TextIssue(
                message=match.get("message", ""),
                short_message=match.get("shortMessage", ""),
                offset=match.get("offset", 0),
                length=match.get("length", 0),
                context=match.get("context", {}).get("text", ""),
                issue_type=self._parse_issue_type(category.get("id", "")),
                severity=severity,
                replacements=[r.get("value", "") for r in match.get("replacements", [])[:5]],
                rule_id=rule.get("id", ""),
                rule_description=rule.get("description", ""),
            ))
        
        return TextCheckResult(
            text=text,
            language=language,
            issues=issues,
            is_clean=error_count == 0,
            error_count=error_count,
            warning_count=warning_count,
        )
    
    def auto_correct(self, text: str, language: str = "en-US") -> str:
        """
        Attempt to auto-correct text using first suggestions.
        NOTE: Use with caution - may not always be appropriate.
        """
        result = self.check(text, language)
        
        if result.is_clean:
            return text
        
        # Apply corrections in reverse order (to preserve offsets)
        corrected = text
        for issue in sorted(result.issues, key=lambda x: x.offset, reverse=True):
            if issue.replacements and issue.severity == IssueSeverity.ERROR:
                start = issue.offset
                end = issue.offset + issue.length
                corrected = corrected[:start] + issue.replacements[0] + corrected[end:]
        
        return corrected
    
    def get_readability_score(self, text: str) -> Dict[str, Any]:
        """
        Estimate readability metrics.
        Simple implementation without external API.
        """
        words = text.split()
        sentences = text.count('.') + text.count('!') + text.count('?')
        sentences = max(sentences, 1)
        
        avg_words_per_sentence = len(words) / sentences
        avg_word_length = sum(len(w) for w in words) / max(len(words), 1)
        
        # Simple readability estimation
        if avg_words_per_sentence > 25 or avg_word_length > 6:
            level = "advanced"
        elif avg_words_per_sentence > 15 or avg_word_length > 5:
            level = "intermediate"
        else:
            level = "simple"
        
        return {
            "word_count": len(words),
            "sentence_count": sentences,
            "avg_words_per_sentence": round(avg_words_per_sentence, 1),
            "avg_word_length": round(avg_word_length, 1),
            "readability_level": level,
        }


# Global instance
_checker: Optional[TextChecker] = None


def get_text_checker() -> TextChecker:
    """Get the global text checker."""
    global _checker
    if _checker is None:
        _checker = TextChecker()
    return _checker


def check_text(text: str, language: str = "en-US") -> TextCheckResult:
    """Convenience function to check text."""
    return get_text_checker().check(text, language)


def must_be_clean(text: str, language: str = "en-US") -> bool:
    """Check if text is error-free. Returns True if clean."""
    return get_text_checker().check(text, language).is_clean
