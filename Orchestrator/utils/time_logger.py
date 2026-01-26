"""
Time Tracking Logger

Provides comprehensive time tracking functionality for the Orchestrator.
Supports manual time entries and active timer tracking with data persistence.

Resource Management:
- Uses atexit to ensure file handles are closed on shutdown
- Singleton pattern for consistent time tracking across the app
"""

import os
import json
import atexit
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid


# =============================================================================
# Configuration (relative paths for portability)
# =============================================================================

UTILS_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = UTILS_ROOT.parent
LOG_DIR = Path(os.getenv("LOG_DIR", str(ORCHESTRATOR_ROOT / "logs")))
TIME_ENTRIES_FILE = LOG_DIR / "time_entries.json"


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class TimeEntry:
    """A single time tracking entry."""
    id: str
    start_time: str  # ISO format
    end_time: str  # ISO format
    duration: float  # seconds
    task: str
    category: str
    notes: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        """Validate and set defaults after initialization."""
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()

        # Validate duration matches start/end times
        if self.start_time and self.end_time:
            start = datetime.fromisoformat(self.start_time)
            end = datetime.fromisoformat(self.end_time)
            calculated_duration = (end - start).total_seconds()
            if abs(calculated_duration - self.duration) > 1:  # Allow 1 second tolerance
                self.duration = calculated_duration

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeEntry":
        """Create TimeEntry from dictionary."""
        return cls(**data)

    def get_duration_formatted(self) -> str:
        """Get human-readable duration."""
        hours = int(self.duration // 3600)
        minutes = int((self.duration % 3600) // 60)
        seconds = int(self.duration % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"


@dataclass
class ActiveTimer:
    """Represents an active timer."""
    task: str
    category: str
    start_time: str  # ISO format
    notes: Optional[str] = None

    def get_elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        start = datetime.fromisoformat(self.start_time)
        return (datetime.utcnow() - start).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class TimePeriod(Enum):
    """Time period for summaries."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ALL = "all"


# =============================================================================
# Time Logger Class
# =============================================================================

class TimeLogger:
    """Centralized time tracker for the Orchestrator."""

    _instance: Optional["TimeLogger"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.entries: List[TimeEntry] = []
        self.active_timer: Optional[ActiveTimer] = None
        self._file_handle = None

        # Create log directory
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing entries
        self._load_entries()

        # Register cleanup on exit
        atexit.register(self._cleanup)

    def _cleanup(self):
        """Close file handles and save on shutdown."""
        if self._file_handle and not self._file_handle.closed:
            self._file_handle.close()
            self._file_handle = None
        self._save_entries()

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        self._cleanup()

    def _load_entries(self):
        """Load time entries from file."""
        if not TIME_ENTRIES_FILE.exists():
            return

        try:
            with open(TIME_ENTRIES_FILE, 'r') as f:
                data = json.load(f)
                self.entries = [TimeEntry.from_dict(entry) for entry in data.get('entries', [])]

                # Load active timer if exists
                if 'active_timer' in data and data['active_timer']:
                    self.active_timer = ActiveTimer(**data['active_timer'])
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load time entries: {e}")
            self.entries = []

    def _save_entries(self):
        """Save time entries to file."""
        try:
            data = {
                'entries': [entry.to_dict() for entry in self.entries],
                'active_timer': self.active_timer.to_dict() if self.active_timer else None,
                'last_updated': datetime.utcnow().isoformat()
            }

            with open(TIME_ENTRIES_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            print(f"Error: Could not save time entries: {e}")

    def log_time_entry(
        self,
        task: str,
        category: str,
        start_time: datetime,
        end_time: datetime,
        notes: Optional[str] = None
    ) -> TimeEntry:
        """
        Log a completed time entry.

        Args:
            task: Description of the task
            category: Category for the task (e.g., "development", "meeting", "research")
            start_time: When the task started
            end_time: When the task ended
            notes: Optional additional notes

        Returns:
            The created TimeEntry

        Raises:
            ValueError: If start_time is after end_time or if inputs are invalid
        """
        # Validation
        if not task or not task.strip():
            raise ValueError("Task description cannot be empty")

        if not category or not category.strip():
            raise ValueError("Category cannot be empty")

        if start_time >= end_time:
            raise ValueError("Start time must be before end time")

        if end_time > datetime.utcnow():
            raise ValueError("End time cannot be in the future")

        # Calculate duration
        duration = (end_time - start_time).total_seconds()

        # Create entry
        entry = TimeEntry(
            id=str(uuid.uuid4()),
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration=duration,
            task=task.strip(),
            category=category.strip(),
            notes=notes.strip() if notes else None
        )

        self.entries.append(entry)
        self._save_entries()

        return entry

    def start_timer(self, task: str, category: str, notes: Optional[str] = None) -> ActiveTimer:
        """
        Start an active timer for a task.

        Args:
            task: Description of the task
            category: Category for the task
            notes: Optional additional notes

        Returns:
            The created ActiveTimer

        Raises:
            ValueError: If a timer is already running or inputs are invalid
        """
        if self.active_timer is not None:
            raise ValueError(
                f"Timer already running for task: '{self.active_timer.task}'. "
                f"Stop it first before starting a new one."
            )

        # Validation
        if not task or not task.strip():
            raise ValueError("Task description cannot be empty")

        if not category or not category.strip():
            raise ValueError("Category cannot be empty")

        # Create active timer
        self.active_timer = ActiveTimer(
            task=task.strip(),
            category=category.strip(),
            start_time=datetime.utcnow().isoformat(),
            notes=notes.strip() if notes else None
        )

        self._save_entries()
        return self.active_timer

    def stop_timer(self, notes: Optional[str] = None) -> TimeEntry:
        """
        Stop the active timer and create a time entry.

        Args:
            notes: Optional notes to add/override from the timer

        Returns:
            The created TimeEntry

        Raises:
            ValueError: If no timer is running
        """
        if self.active_timer is None:
            raise ValueError("No active timer to stop")

        # Create time entry from active timer
        start_time = datetime.fromisoformat(self.active_timer.start_time)
        end_time = datetime.utcnow()

        # Use provided notes or fall back to timer notes
        final_notes = notes if notes is not None else self.active_timer.notes

        entry = self.log_time_entry(
            task=self.active_timer.task,
            category=self.active_timer.category,
            start_time=start_time,
            end_time=end_time,
            notes=final_notes
        )

        # Clear active timer
        self.active_timer = None
        self._save_entries()

        return entry

    def get_active_timer(self) -> Optional[ActiveTimer]:
        """Get the current active timer, if any."""
        return self.active_timer

    def cancel_timer(self):
        """Cancel the active timer without creating an entry."""
        if self.active_timer is None:
            raise ValueError("No active timer to cancel")

        self.active_timer = None
        self._save_entries()

    def get_entries(
        self,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        category: Optional[str] = None,
        task: Optional[str] = None
    ) -> List[TimeEntry]:
        """
        Get time entries with optional filtering.

        Args:
            date_range: Tuple of (start_date, end_date) to filter by
            category: Filter by category (case-insensitive partial match)
            task: Filter by task description (case-insensitive partial match)

        Returns:
            List of matching TimeEntry objects
        """
        entries = self.entries

        # Filter by date range
        if date_range:
            start_date, end_date = date_range
            entries = [
                e for e in entries
                if start_date <= datetime.fromisoformat(e.start_time) <= end_date
            ]

        # Filter by category
        if category:
            category_lower = category.lower()
            entries = [e for e in entries if category_lower in e.category.lower()]

        # Filter by task
        if task:
            task_lower = task.lower()
            entries = [e for e in entries if task_lower in e.task.lower()]

        return entries

    def get_summary(
        self,
        period: TimePeriod = TimePeriod.DAILY,
        reference_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of time entries for a period.

        Args:
            period: Time period for the summary
            reference_date: Reference date for the period (defaults to now)

        Returns:
            Dictionary with summary statistics
        """
        if reference_date is None:
            reference_date = datetime.utcnow()

        # Determine date range based on period
        if period == TimePeriod.DAILY:
            start_date = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
            period_name = start_date.strftime("%Y-%m-%d")
        elif period == TimePeriod.WEEKLY:
            # Start of week (Monday)
            start_date = reference_date - timedelta(days=reference_date.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=7)
            period_name = f"Week of {start_date.strftime('%Y-%m-%d')}"
        elif period == TimePeriod.MONTHLY:
            start_date = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # Next month
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1)
            period_name = start_date.strftime("%Y-%m")
        else:  # ALL
            start_date = datetime.min
            end_date = datetime.max
            period_name = "All time"

        # Get entries for the period
        entries = self.get_entries(date_range=(start_date, end_date))

        # Calculate statistics
        total_duration = sum(e.duration for e in entries)
        total_entries = len(entries)

        # Group by category
        by_category = {}
        for entry in entries:
            if entry.category not in by_category:
                by_category[entry.category] = {
                    'count': 0,
                    'total_duration': 0,
                    'tasks': []
                }
            by_category[entry.category]['count'] += 1
            by_category[entry.category]['total_duration'] += entry.duration
            by_category[entry.category]['tasks'].append(entry.task)

        # Format durations
        def format_duration(seconds):
            hours = seconds / 3600
            return f"{hours:.2f}h"

        return {
            'period': period.value,
            'period_name': period_name,
            'date_range': {
                'start': start_date.isoformat() if start_date != datetime.min else None,
                'end': end_date.isoformat() if end_date != datetime.max else None
            },
            'total_entries': total_entries,
            'total_duration': total_duration,
            'total_duration_formatted': format_duration(total_duration),
            'by_category': {
                cat: {
                    'count': data['count'],
                    'total_duration': data['total_duration'],
                    'total_duration_formatted': format_duration(data['total_duration']),
                    'percentage': (data['total_duration'] / total_duration * 100) if total_duration > 0 else 0,
                    'unique_tasks': len(set(data['tasks']))
                }
                for cat, data in by_category.items()
            },
            'entries': [e.to_dict() for e in entries]
        }

    def export_to_csv(self, filename: Optional[str] = None) -> str:
        """
        Export time entries to CSV format.

        Args:
            filename: Optional filename for the export (defaults to timestamped file)

        Returns:
            Path to the exported CSV file
        """
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"time_entries_{timestamp}.csv"

        output_path = LOG_DIR / filename

        try:
            with open(output_path, 'w', newline='') as csvfile:
                fieldnames = ['id', 'start_time', 'end_time', 'duration', 'duration_formatted',
                             'task', 'category', 'notes', 'created_at']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for entry in self.entries:
                    row = entry.to_dict()
                    row['duration_formatted'] = entry.get_duration_formatted()
                    writer.writerow(row)

            return str(output_path)
        except IOError as e:
            raise IOError(f"Failed to export to CSV: {e}")

    def export_to_json(self, filename: Optional[str] = None) -> str:
        """
        Export time entries to JSON format.

        Args:
            filename: Optional filename for the export (defaults to timestamped file)

        Returns:
            Path to the exported JSON file
        """
        if filename is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"time_entries_{timestamp}.json"

        output_path = LOG_DIR / filename

        try:
            data = {
                'exported_at': datetime.utcnow().isoformat(),
                'total_entries': len(self.entries),
                'entries': [entry.to_dict() for entry in self.entries]
            }

            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)

            return str(output_path)
        except IOError as e:
            raise IOError(f"Failed to export to JSON: {e}")

    def delete_entry(self, entry_id: str) -> bool:
        """
        Delete a time entry by ID.

        Args:
            entry_id: The ID of the entry to delete

        Returns:
            True if entry was deleted, False if not found
        """
        original_length = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]

        if len(self.entries) < original_length:
            self._save_entries()
            return True
        return False

    def clear_all_entries(self):
        """Clear all time entries. Use with caution!"""
        self.entries = []
        self.active_timer = None
        self._save_entries()


# =============================================================================
# Global Access
# =============================================================================

_time_logger: Optional[TimeLogger] = None


def get_time_logger() -> TimeLogger:
    """Get the global time logger instance."""
    global _time_logger
    if _time_logger is None:
        _time_logger = TimeLogger()
    return _time_logger


def log_time(
    task: str,
    category: str,
    start_time: datetime,
    end_time: datetime,
    notes: Optional[str] = None
) -> TimeEntry:
    """Quick time entry logging."""
    return get_time_logger().log_time_entry(task, category, start_time, end_time, notes)


def start_timer(task: str, category: str, notes: Optional[str] = None) -> ActiveTimer:
    """Quick timer start."""
    return get_time_logger().start_timer(task, category, notes)


def stop_timer(notes: Optional[str] = None) -> TimeEntry:
    """Quick timer stop."""
    return get_time_logger().stop_timer(notes)
