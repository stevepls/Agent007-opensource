#!/usr/bin/env python3
"""
Time Logger CLI

Interactive command-line interface for tracking time entries.
Provides an easy-to-use menu for starting/stopping timers, logging past time,
viewing summaries, and exporting data.
"""

import sys
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from time_logger import (
    get_time_logger,
    TimeLogger,
    TimeEntry,
    ActiveTimer,
    TimePeriod
)


# =============================================================================
# Display Helpers
# =============================================================================

def clear_screen():
    """Clear the terminal screen."""
    print("\033[2J\033[H", end="")


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_divider():
    """Print a simple divider."""
    print("-" * 70)


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def print_success(message: str):
    """Print a success message."""
    print(f"\n✓ {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"\n✗ Error: {message}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"\n⚠ Warning: {message}")


# =============================================================================
# Input Helpers
# =============================================================================

def get_input(prompt: str, default: Optional[str] = None) -> str:
    """Get user input with optional default value."""
    if default:
        full_prompt = f"{prompt} [{default}]: "
    else:
        full_prompt = f"{prompt}: "

    value = input(full_prompt).strip()
    return value if value else (default or "")


def get_datetime_input(prompt: str, allow_future: bool = False) -> Optional[datetime]:
    """
    Get a datetime from user input.
    Supports formats: YYYY-MM-DD HH:MM, HH:MM (today), or relative like "2h ago", "30m ago"
    """
    while True:
        user_input = input(f"{prompt} (YYYY-MM-DD HH:MM, HH:MM, or '2h ago', '30m ago'): ").strip()

        if not user_input:
            return None

        try:
            # Try relative time format (e.g., "2h ago", "30m ago")
            if "ago" in user_input.lower():
                parts = user_input.lower().replace("ago", "").strip().split()
                if len(parts) == 1:
                    value_str = parts[0]
                    if value_str.endswith('h'):
                        hours = float(value_str[:-1])
                        return datetime.now() - timedelta(hours=hours)
                    elif value_str.endswith('m'):
                        minutes = float(value_str[:-1])
                        return datetime.now() - timedelta(minutes=minutes)
                    elif value_str.endswith('s'):
                        seconds = float(value_str[:-1])
                        return datetime.now() - timedelta(seconds=seconds)

            # Try HH:MM format (assume today)
            if ":" in user_input and "-" not in user_input:
                time_parts = user_input.split(":")
                if len(time_parts) == 2:
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    dt = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)

                    # If time is in the future and not allowed, assume yesterday
                    if not allow_future and dt > datetime.now():
                        dt -= timedelta(days=1)

                    return dt

            # Try full datetime format
            dt = datetime.strptime(user_input, "%Y-%m-%d %H:%M")

            # Validate future dates
            if not allow_future and dt > datetime.now():
                print_error("Time cannot be in the future. Please try again.")
                continue

            return dt

        except ValueError:
            print_error("Invalid format. Please use YYYY-MM-DD HH:MM, HH:MM, or '2h ago', '30m ago'")
            continue


def get_int_input(prompt: str, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Optional[int]:
    """Get integer input with optional range validation."""
    while True:
        value = input(f"{prompt}: ").strip()

        if not value:
            return None

        try:
            num = int(value)

            if min_val is not None and num < min_val:
                print_error(f"Value must be at least {min_val}")
                continue

            if max_val is not None and num > max_val:
                print_error(f"Value must be at most {max_val}")
                continue

            return num

        except ValueError:
            print_error("Please enter a valid number")


def confirm(prompt: str, default: bool = False) -> bool:
    """Get yes/no confirmation from user."""
    default_str = "Y/n" if default else "y/N"
    response = input(f"{prompt} [{default_str}]: ").strip().lower()

    if not response:
        return default

    return response in ['y', 'yes']


# =============================================================================
# Menu Actions
# =============================================================================

def start_timer_action(logger: TimeLogger):
    """Start a new timer."""
    print_header("Start Timer")

    # Check if timer already running
    active = logger.get_active_timer()
    if active:
        print_warning(f"Timer already running for: {active.task}")
        elapsed = format_duration(active.get_elapsed_seconds())
        print(f"Elapsed time: {elapsed}")
        print()

        if not confirm("Stop current timer and start a new one?"):
            return

        # Stop the current timer
        try:
            entry = logger.stop_timer()
            print_success(f"Stopped timer: {entry.task} ({entry.get_duration_formatted()})")
        except Exception as e:
            print_error(f"Failed to stop timer: {e}")
            return

    # Get task details
    print()
    task = get_input("Task description")
    if not task:
        print_error("Task description is required")
        return

    category = get_input("Category (e.g., development, meeting, research)")
    if not category:
        print_error("Category is required")
        return

    notes = get_input("Notes (optional)")

    # Start the timer
    try:
        timer = logger.start_timer(task, category, notes if notes else None)
        print_success(f"Timer started for: {task}")
        print(f"Category: {category}")
        if notes:
            print(f"Notes: {notes}")
    except Exception as e:
        print_error(f"Failed to start timer: {e}")


def stop_timer_action(logger: TimeLogger):
    """Stop the active timer."""
    print_header("Stop Timer")

    active = logger.get_active_timer()
    if not active:
        print_error("No active timer to stop")
        return

    # Show current timer info
    print(f"\nTask: {active.task}")
    print(f"Category: {active.category}")
    if active.notes:
        print(f"Notes: {active.notes}")

    elapsed = format_duration(active.get_elapsed_seconds())
    print(f"Elapsed time: {elapsed}")
    print()

    # Option to update notes
    if confirm("Update notes before stopping?"):
        notes = get_input("Notes", default=active.notes or "")
    else:
        notes = None

    # Stop the timer
    try:
        entry = logger.stop_timer(notes if notes else None)
        print_success(f"Timer stopped: {entry.task}")
        print(f"Duration: {entry.get_duration_formatted()}")
    except Exception as e:
        print_error(f"Failed to stop timer: {e}")


def log_past_time_action(logger: TimeLogger):
    """Log a past time entry."""
    print_header("Log Past Time")

    # Get task details
    print()
    task = get_input("Task description")
    if not task:
        print_error("Task description is required")
        return

    category = get_input("Category (e.g., development, meeting, research)")
    if not category:
        print_error("Category is required")
        return

    # Get time range
    print()
    print("Enter the time range for this task:")
    start_time = get_datetime_input("Start time", allow_future=False)
    if not start_time:
        print_error("Start time is required")
        return

    end_time = get_datetime_input("End time", allow_future=False)
    if not end_time:
        print_error("End time is required")
        return

    notes = get_input("Notes (optional)")

    # Calculate and display duration
    duration = (end_time - start_time).total_seconds()
    if duration <= 0:
        print_error("End time must be after start time")
        return

    print(f"\nDuration: {format_duration(duration)}")

    if not confirm("Save this entry?", default=True):
        print("Entry cancelled")
        return

    # Log the entry
    try:
        entry = logger.log_time_entry(task, category, start_time, end_time, notes if notes else None)
        print_success(f"Time entry logged: {task}")
        print(f"Duration: {entry.get_duration_formatted()}")
    except Exception as e:
        print_error(f"Failed to log entry: {e}")


def view_today_summary_action(logger: TimeLogger):
    """View today's time summary."""
    print_header("Today's Summary")

    try:
        summary = logger.get_summary(period=TimePeriod.DAILY)

        print(f"\nDate: {summary['period_name']}")
        print(f"Total entries: {summary['total_entries']}")
        print(f"Total time: {summary['total_duration_formatted']}")

        # Show active timer if running
        active = logger.get_active_timer()
        if active:
            elapsed = format_duration(active.get_elapsed_seconds())
            print(f"\n⏱ Active timer: {active.task} ({elapsed})")

        # Show by category
        if summary['by_category']:
            print("\nBy Category:")
            print_divider()
            for category, data in sorted(summary['by_category'].items()):
                pct = data['percentage']
                print(f"  {category:20} {data['total_duration_formatted']:>10} ({pct:>5.1f}%) - {data['count']} entries")

        # Show individual entries
        if summary['entries']:
            print("\nEntries:")
            print_divider()
            for entry_dict in summary['entries']:
                entry = TimeEntry.from_dict(entry_dict)
                start = datetime.fromisoformat(entry.start_time)
                print(f"  {start.strftime('%H:%M')} - {entry.task} ({entry.get_duration_formatted()})")
                print(f"          Category: {entry.category}")
                if entry.notes:
                    print(f"          Notes: {entry.notes}")
        else:
            print("\nNo entries for today")

    except Exception as e:
        print_error(f"Failed to generate summary: {e}")


def view_all_entries_action(logger: TimeLogger):
    """View all time entries."""
    print_header("All Time Entries")

    try:
        entries = logger.get_entries()

        if not entries:
            print("\nNo entries found")
            return

        print(f"\nTotal entries: {len(entries)}")

        # Group by date
        by_date = {}
        for entry in entries:
            start = datetime.fromisoformat(entry.start_time)
            date_key = start.strftime("%Y-%m-%d")
            if date_key not in by_date:
                by_date[date_key] = []
            by_date[date_key].append(entry)

        # Display entries by date (most recent first)
        for date_key in sorted(by_date.keys(), reverse=True):
            print(f"\n{date_key}")
            print_divider()

            date_entries = by_date[date_key]
            total_duration = sum(e.duration for e in date_entries)

            for entry in sorted(date_entries, key=lambda e: e.start_time):
                start = datetime.fromisoformat(entry.start_time)
                print(f"  {start.strftime('%H:%M')} - {entry.task} ({entry.get_duration_formatted()})")
                print(f"          Category: {entry.category}")
                if entry.notes:
                    print(f"          Notes: {entry.notes}")

            print(f"\n  Day total: {format_duration(total_duration)}")

    except Exception as e:
        print_error(f"Failed to retrieve entries: {e}")


def export_data_action(logger: TimeLogger):
    """Export data to file."""
    print_header("Export Data")

    print("\nExport format:")
    print("  1. CSV")
    print("  2. JSON")

    choice = get_int_input("\nSelect format", min_val=1, max_val=2)

    if choice is None:
        print("Export cancelled")
        return

    filename = get_input("Filename (optional, leave blank for auto-generated)")

    try:
        if choice == 1:
            path = logger.export_to_csv(filename if filename else None)
            print_success(f"Data exported to CSV: {path}")
        elif choice == 2:
            path = logger.export_to_json(filename if filename else None)
            print_success(f"Data exported to JSON: {path}")
    except Exception as e:
        print_error(f"Export failed: {e}")


# =============================================================================
# Main Menu
# =============================================================================

def show_menu():
    """Display the main menu."""
    print_header("Time Logger CLI")
    print("\nOptions:")
    print("  1. Start Timer")
    print("  2. Stop Timer")
    print("  3. Log Past Time")
    print("  4. View Today's Summary")
    print("  5. View All Entries")
    print("  6. Export Data")
    print("  7. Exit")


def main():
    """Main CLI loop."""
    logger = get_time_logger()

    print("Welcome to Time Logger CLI!")

    while True:
        show_menu()

        # Show active timer status if running
        active = logger.get_active_timer()
        if active:
            elapsed = format_duration(active.get_elapsed_seconds())
            print(f"\n⏱ Active timer: {active.task} ({elapsed})")

        print()
        choice = get_int_input("Select an option", min_val=1, max_val=7)

        if choice is None:
            continue

        if choice == 1:
            start_timer_action(logger)
        elif choice == 2:
            stop_timer_action(logger)
        elif choice == 3:
            log_past_time_action(logger)
        elif choice == 4:
            view_today_summary_action(logger)
        elif choice == 5:
            view_all_entries_action(logger)
        elif choice == 6:
            export_data_action(logger)
        elif choice == 7:
            if active:
                print_warning("You have an active timer running!")
                if confirm("Do you want to stop it before exiting?"):
                    stop_timer_action(logger)

            print("\nGoodbye!")
            sys.exit(0)

        # Wait for user to continue
        input("\nPress Enter to continue...")
        clear_screen()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
