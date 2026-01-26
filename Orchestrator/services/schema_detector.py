"""
Schema Change Detector

Monitors git commits and detects database schema changes.
Automatically prompts for review when schema changes are found.
"""

import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


# Configuration
SERVICES_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
AGENT007_ROOT = ORCHESTRATOR_ROOT.parent


class SchemaChangeType(Enum):
    """Types of schema changes."""
    CREATE_TABLE = "create_table"
    ALTER_TABLE = "alter_table"
    DROP_TABLE = "drop_table"
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_CONSTRAINT = "add_constraint"
    DROP_CONSTRAINT = "drop_constraint"
    MIGRATION = "migration"
    MODEL_CHANGE = "model_change"
    UNKNOWN = "unknown"


@dataclass
class SchemaChange:
    """Represents a detected schema change."""
    id: str
    type: SchemaChangeType
    file_path: str
    commit_hash: str
    commit_message: str
    commit_date: str
    author: str
    lines_added: int = 0
    lines_removed: int = 0
    preview: str = ""
    reviewed: bool = False
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "file_path": self.file_path,
            "commit_hash": self.commit_hash,
            "commit_message": self.commit_message,
            "commit_date": self.commit_date,
            "author": self.author,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "preview": self.preview,
            "reviewed": self.reviewed,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
        }


class SchemaChangeDetector:
    """Detects schema changes in git commits."""
    
    _instance: Optional["SchemaChangeDetector"] = None
    
    # Patterns that indicate schema changes
    FILE_PATTERNS = [
        r'migrations?/',
        r'alembic/',
        r'schema',
        r'\.sql$',
        r'models\.py$',
        r'models/',
        r'database/',
        r'prisma/',
        r'drizzle/',
        r'typeorm/',
        r'sequelize/',
    ]
    
    CONTENT_PATTERNS = {
        SchemaChangeType.CREATE_TABLE: [
            r'CREATE\s+TABLE',
            r'class\s+\w+\(.*Base.*\)',  # SQLAlchemy
            r'@Entity\(',  # TypeORM
        ],
        SchemaChangeType.ALTER_TABLE: [
            r'ALTER\s+TABLE',
            r'op\.alter_column',  # Alembic
        ],
        SchemaChangeType.DROP_TABLE: [
            r'DROP\s+TABLE',
            r'op\.drop_table',
        ],
        SchemaChangeType.ADD_COLUMN: [
            r'ADD\s+COLUMN',
            r'op\.add_column',
        ],
        SchemaChangeType.DROP_COLUMN: [
            r'DROP\s+COLUMN',
            r'op\.drop_column',
        ],
        SchemaChangeType.ADD_INDEX: [
            r'CREATE\s+INDEX',
            r'op\.create_index',
        ],
        SchemaChangeType.DROP_INDEX: [
            r'DROP\s+INDEX',
            r'op\.drop_index',
        ],
        SchemaChangeType.MIGRATION: [
            r'def upgrade\(',
            r'def downgrade\(',
            r'exports\.up',
            r'exports\.down',
        ],
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._reviewed_changes: set = set()
        self._cached_changes: List[SchemaChange] = []
        self._last_check: Optional[datetime] = None
    
    def _run_git(self, *args, cwd: Path = None) -> Optional[str]:
        """Run a git command and return output."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd or AGENT007_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None
    
    def _is_schema_file(self, file_path: str) -> bool:
        """Check if a file path matches schema file patterns."""
        for pattern in self.FILE_PATTERNS:
            if re.search(pattern, file_path, re.IGNORECASE):
                return True
        return False
    
    def _classify_change(self, content: str) -> SchemaChangeType:
        """Classify the type of schema change from content."""
        for change_type, patterns in self.CONTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                    return change_type
        return SchemaChangeType.UNKNOWN
    
    def detect_changes(
        self,
        since: str = "7 days ago",
        limit: int = 20,
        include_reviewed: bool = False,
    ) -> List[SchemaChange]:
        """
        Detect schema changes in recent commits.
        
        Args:
            since: How far back to look (git date format)
            limit: Maximum commits to check
            include_reviewed: Include already-reviewed changes
            
        Returns:
            List of detected SchemaChange objects
        """
        changes = []
        
        # Get recent commits with files changed
        log_output = self._run_git(
            "log",
            f"--since={since}",
            f"-{limit}",
            "--pretty=format:%H|%s|%ai|%an",
            "--name-status",
        )
        
        if not log_output:
            return changes
        
        current_commit = None
        commit_info = {}
        
        for line in log_output.split('\n'):
            if not line.strip():
                continue
            
            # Check if this is a commit line (contains |)
            if '|' in line and line.count('|') >= 3:
                parts = line.split('|')
                current_commit = parts[0]
                commit_info = {
                    "hash": parts[0],
                    "message": parts[1],
                    "date": parts[2],
                    "author": parts[3] if len(parts) > 3 else "Unknown",
                }
            elif current_commit and '\t' in line:
                # This is a file status line
                parts = line.split('\t')
                if len(parts) >= 2:
                    status = parts[0]
                    file_path = parts[-1]
                    
                    if self._is_schema_file(file_path):
                        change_id = f"{current_commit[:8]}-{Path(file_path).name}"
                        
                        # Skip if already reviewed
                        if change_id in self._reviewed_changes and not include_reviewed:
                            continue
                        
                        # Get the diff for this file
                        diff = self._run_git(
                            "show",
                            f"{current_commit}",
                            "--",
                            file_path,
                        )
                        
                        # Count lines
                        added = len(re.findall(r'^\+[^+]', diff or "", re.MULTILINE))
                        removed = len(re.findall(r'^-[^-]', diff or "", re.MULTILINE))
                        
                        # Classify the change
                        change_type = self._classify_change(diff or "")
                        
                        # Extract preview (first few changed lines)
                        preview_lines = []
                        for diff_line in (diff or "").split('\n'):
                            if diff_line.startswith('+') or diff_line.startswith('-'):
                                if not diff_line.startswith('+++') and not diff_line.startswith('---'):
                                    preview_lines.append(diff_line)
                                    if len(preview_lines) >= 10:
                                        break
                        
                        changes.append(SchemaChange(
                            id=change_id,
                            type=change_type,
                            file_path=file_path,
                            commit_hash=commit_info["hash"],
                            commit_message=commit_info["message"],
                            commit_date=commit_info["date"],
                            author=commit_info["author"],
                            lines_added=added,
                            lines_removed=removed,
                            preview='\n'.join(preview_lines),
                            reviewed=change_id in self._reviewed_changes,
                        ))
        
        self._cached_changes = changes
        self._last_check = datetime.utcnow()
        
        return changes
    
    def mark_reviewed(self, change_id: str, reviewer: str = "human"):
        """Mark a schema change as reviewed."""
        self._reviewed_changes.add(change_id)
        
        # Update cached change
        for change in self._cached_changes:
            if change.id == change_id:
                change.reviewed = True
                change.reviewed_by = reviewer
                change.reviewed_at = datetime.utcnow().isoformat()
                break
    
    def get_unreviewd_count(self) -> int:
        """Get count of unreviewed schema changes."""
        if not self._cached_changes:
            self.detect_changes()
        return len([c for c in self._cached_changes if not c.reviewed])
    
    def needs_attention(self) -> bool:
        """Check if there are schema changes needing attention."""
        return self.get_unreviewd_count() > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of schema changes."""
        if not self._cached_changes:
            self.detect_changes()
        
        by_type = {}
        for change in self._cached_changes:
            by_type[change.type.value] = by_type.get(change.type.value, 0) + 1
        
        return {
            "total": len(self._cached_changes),
            "unreviewed": self.get_unreviewd_count(),
            "by_type": by_type,
            "last_check": self._last_check.isoformat() if self._last_check else None,
        }


# Global access
_detector: Optional[SchemaChangeDetector] = None


def get_schema_detector() -> SchemaChangeDetector:
    """Get the global schema change detector."""
    global _detector
    if _detector is None:
        _detector = SchemaChangeDetector()
    return _detector
