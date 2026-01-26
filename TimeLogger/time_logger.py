"""
Time Logger Module

A comprehensive time tracking system that supports both manual time entries
and active timer tracking with JSON persistence and CSV export capabilities.
"""

import atexit
import csv
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import uuid4


@dataclass
class TimeEntry:
    """Represents a completed time entry."""
    id: str
    start_time: str
    end_time: str
    duration: float
    task: str
    category: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimeEntry':
        """Create entry from dictionary."""
        return cls(**data)


@dataclass
class ActiveTimer:
    """Represents an active timer."""
    id: str
    start_time: str
    task: str
    category: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert timer to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ActiveTimer':
        """Create timer from dictionary."""
        return cls(**data)


class TimeLogger:
    """
    Time logging system with support for manual entries and active timers.

    Features:
    - Manual time entry logging
    - Active timer start/stop
    - Entry filtering and retrieval
    - Time summaries by category/task
    - CSV export
    - JSON persistence
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize TimeLogger.

        Args:
            data_dir: Directory for data files. Defaults to ./data
        """
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.entries_file = self.data_dir / "time_entries.json"
        self.timer_file = self.data_dir / "active_timer.json"

        self.entries: List[TimeEntry] = []
        self.active_timer: Optional[ActiveTimer] = None

        self._load()
        atexit.register(self.save)

    def log_time(
        self,
        start_time: datetime,
        end_time: datetime,
        task: str,
        category: str,
        notes: str = ""
    ) -> TimeEntry:
        """
        Add a manual time entry.

        Args:
            start_time: Start datetime
            end_time: End datetime
            task: Task description
            category: Category name
            notes: Optional notes

        Returns:
            Created TimeEntry

        Raises:
            ValueError: If end_time is before start_time
        """
        if end_time < start_time:
            raise ValueError("End time cannot be before start time")

        duration = (end_time - start_time).total_seconds() / 3600.0

        entry = TimeEntry(
            id=str(uuid4()),
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration=round(duration, 2),
            task=task,
            category=category,
            notes=notes
        )

        self.entries.append(entry)
        self.save()

        return entry

    def start_timer(self, task: str, category: str) -> ActiveTimer:
        """
        Start an active timer.

        Args:
            task: Task description
            category: Category name

        Returns:
            Created ActiveTimer

        Raises:
            RuntimeError: If a timer is already running
        """
        if self.active_timer is not None:
            raise RuntimeError(
                f"Timer already running for task: {self.active_timer.task}"
            )

        self.active_timer = ActiveTimer(
            id=str(uuid4()),
            start_time=datetime.now().isoformat(),
            task=task,
            category=category
        )

        self.save()
        return self.active_timer

    def stop_timer(self, notes: str = "") -> TimeEntry:
        """
        Stop the active timer and create a time entry.

        Args:
            notes: Optional notes for the entry

        Returns:
            Created TimeEntry

        Raises:
            RuntimeError: If no timer is running
        """
        if self.active_timer is None:
            raise RuntimeError("No timer is running")

        end_time = datetime.now()
        start_time = datetime.fromisoformat(self.active_timer.start_time)

        entry = self.log_time(
            start_time=start_time,
            end_time=end_time,
            task=self.active_timer.task,
            category=self.active_timer.category,
            notes=notes
        )

        self.active_timer = None
        self.save()

        return entry

    def get_entries(
        self,
        category: Optional[str] = None,
        task: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[TimeEntry]:
        """
        Retrieve filtered time entries.

        Args:
            category: Filter by category
            task: Filter by task (case-insensitive substring match)
            start_date: Filter entries after this date
            end_date: Filter entries before this date

        Returns:
            List of matching TimeEntry objects
        """
        filtered = self.entries.copy()

        if category is not None:
            filtered = [e for e in filtered if e.category == category]

        if task is not None:
            task_lower = task.lower()
            filtered = [e for e in filtered if task_lower in e.task.lower()]

        if start_date is not None:
            start_iso = start_date.isoformat()
            filtered = [e for e in filtered if e.start_time >= start_iso]

        if end_date is not None:
            end_iso = end_date.isoformat()
            filtered = [e for e in filtered if e.end_time <= end_iso]

        return filtered

    def get_summary(
        self,
        group_by: str = "category",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        Generate time summaries grouped by category or task.

        Args:
            group_by: Group by 'category' or 'task'
            start_date: Include entries after this date
            end_date: Include entries before this date

        Returns:
            Dictionary mapping group names to total hours

        Raises:
            ValueError: If group_by is not 'category' or 'task'
        """
        if group_by not in ("category", "task"):
            raise ValueError("group_by must be 'category' or 'task'")

        entries = self.get_entries(start_date=start_date, end_date=end_date)

        summary: Dict[str, float] = {}
        for entry in entries:
            key = entry.category if group_by == "category" else entry.task
            summary[key] = summary.get(key, 0.0) + entry.duration

        return dict(sorted(summary.items(), key=lambda x: x[1], reverse=True))

    def export_to_csv(self, output_path: Path) -> None:
        """
        Export all time entries to CSV file.

        Args:
            output_path: Path for the output CSV file

        Raises:
            IOError: If file cannot be written
        """
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                if not self.entries:
                    return

                fieldnames = ['id', 'start_time', 'end_time', 'duration',
                             'task', 'category', 'notes']
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                writer.writeheader()
                for entry in self.entries:
                    writer.writerow(entry.to_dict())
        except IOError as e:
            raise IOError(f"Failed to export to CSV: {e}")

    def save(self) -> None:
        """
        Save entries and active timer to JSON files.

        Raises:
            IOError: If files cannot be written
        """
        try:
            entries_data = [entry.to_dict() for entry in self.entries]
            with open(self.entries_file, 'w', encoding='utf-8') as f:
                json.dump(entries_data, f, indent=2)

            if self.active_timer is not None:
                with open(self.timer_file, 'w', encoding='utf-8') as f:
                    json.dump(self.active_timer.to_dict(), f, indent=2)
            else:
                if self.timer_file.exists():
                    self.timer_file.unlink()
        except IOError as e:
            raise IOError(f"Failed to save data: {e}")

    def _load(self) -> None:
        """
        Load entries and active timer from JSON files.

        Internal method called during initialization.
        """
        try:
            if self.entries_file.exists():
                with open(self.entries_file, 'r', encoding='utf-8') as f:
                    entries_data = json.load(f)
                    self.entries = [
                        TimeEntry.from_dict(data) for data in entries_data
                    ]
        except (IOError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load entries: {e}")
            self.entries = []

        try:
            if self.timer_file.exists():
                with open(self.timer_file, 'r', encoding='utf-8') as f:
                    timer_data = json.load(f)
                    self.active_timer = ActiveTimer.from_dict(timer_data)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Warning: Failed to load active timer: {e}")
            self.active_timer = None


if __name__ == "__main__":
    logger = TimeLogger()

    logger.start_timer("Writing documentation", "Development")
    print("Timer started...")

    import time
    time.sleep(2)

    entry = logger.stop_timer("Completed initial draft")
    print(f"Timer stopped. Duration: {entry.duration} hours")

    logger.log_time(
        start_time=datetime.now() - timedelta(hours=2),
        end_time=datetime.now() - timedelta(hours=1),
        task="Code review",
        category="Development",
        notes="Reviewed PR #123"
    )

    print("\nAll entries:")
    for e in logger.get_entries():
        print(f"  {e.task} ({e.category}): {e.duration}h")

    print("\nSummary by category:")
    for cat, hours in logger.get_summary(group_by="category").items():
        print(f"  {cat}: {hours}h")

    csv_path = Path("time_log_export.csv")
    logger.export_to_csv(csv_path)
    print(f"\nExported to {csv_path}")
