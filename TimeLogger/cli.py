"""
Command-line interface for the Time Logger.

Provides an interactive menu-driven interface for tracking time with
manual entries, active timers, summaries, and export capabilities.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import re

from time_logger import TimeLogger


# ============================================================================
# Display Helper Functions
# ============================================================================

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_separator():
    """Print a visual separator."""
    print("-" * 60)


def format_duration(hours: float) -> str:
    """Format duration in hours to human-readable format."""
    if hours < 1:
        minutes = int(hours * 60)
        return f"{minutes}m"
    elif hours < 10:
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h}h {m}m" if m > 0 else f"{h}h"
    else:
        return f"{hours:.1f}h"


def format_datetime(dt_str: str) -> str:
    """Format ISO datetime string to readable format."""
    dt = datetime.fromisoformat(dt_str)
    return dt.strftime("%Y-%m-%d %I:%M %p")


def print_time_entry(entry, show_notes: bool = True):
    """Print a formatted time entry."""
    print(f"  Task: {entry.task}")
    print(f"  Category: {entry.category}")
    print(f"  Start: {format_datetime(entry.start_time)}")
    print(f"  End: {format_datetime(entry.end_time)}")
    print(f"  Duration: {format_duration(entry.duration)}")
    if show_notes and entry.notes:
        print(f"  Notes: {entry.notes}")
    print_separator()


def print_summary(summary: dict, title: str):
    """Print a formatted summary."""
    print_header(title)

    if not summary:
        print("  No entries found for this period.")
        return

    total_hours = sum(summary.values())

    for name, hours in summary.items():
        percentage = (hours / total_hours * 100) if total_hours > 0 else 0
        bar_length = int(percentage / 2)
        bar = "█" * bar_length + "░" * (50 - bar_length)
        print(f"  {name:<30} {format_duration(hours):>8} [{bar}] {percentage:>5.1f}%")

    print_separator()
    print(f"  {'TOTAL':<30} {format_duration(total_hours):>8}")


def print_active_timer(timer):
    """Print information about the active timer."""
    start_time = datetime.fromisoformat(timer.start_time)
    elapsed = datetime.now() - start_time
    hours = elapsed.total_seconds() / 3600.0

    print_header("ACTIVE TIMER")
    print(f"  Task: {timer.task}")
    print(f"  Category: {timer.category}")
    print(f"  Started: {format_datetime(timer.start_time)}")
    print(f"  Elapsed: {format_duration(hours)}")
    print_separator()


# ============================================================================
# Input Helper Functions
# ============================================================================

def get_input(prompt: str, default: str = "") -> str:
    """Get text input from user."""
    if default:
        user_input = input(f"{prompt} [{default}]: ").strip()
        return user_input if user_input else default
    else:
        while True:
            user_input = input(f"{prompt}: ").strip()
            if user_input:
                return user_input
            print("  Error: Input cannot be empty. Please try again.")


def get_optional_input(prompt: str) -> str:
    """Get optional text input from user."""
    return input(f"{prompt} (optional): ").strip()


def get_choice(prompt: str, options: list) -> str:
    """Get a choice from a list of options."""
    print(f"\n{prompt}")
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")

    while True:
        try:
            choice = input(f"\nSelect (1-{len(options)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
            print(f"  Error: Please enter a number between 1 and {len(options)}.")
        except ValueError:
            print("  Error: Please enter a valid number.")


def parse_relative_time(time_str: str) -> Optional[datetime]:
    """
    Parse relative time expressions into datetime objects.

    Supports:
    - 'now'
    - '2h ago', '30m ago'
    - 'yesterday', 'yesterday 3pm'
    - 'today 9am'
    - Absolute times: '2026-01-25 14:30', '14:30', '2:30pm'
    """
    time_str = time_str.lower().strip()
    now = datetime.now()

    # Handle 'now'
    if time_str == 'now':
        return now

    # Handle relative time (e.g., '2h ago', '30m ago')
    ago_match = re.match(r'^(\d+)\s*(h|hour|hours|m|min|mins|minute|minutes)\s+ago$', time_str)
    if ago_match:
        amount = int(ago_match.group(1))
        unit = ago_match.group(2)
        if unit in ('h', 'hour', 'hours'):
            return now - timedelta(hours=amount)
        else:
            return now - timedelta(minutes=amount)

    # Handle 'yesterday' with optional time
    if time_str.startswith('yesterday'):
        base_date = now - timedelta(days=1)
        time_part = time_str.replace('yesterday', '').strip()
        if time_part:
            parsed_time = parse_time_of_day(time_part)
            if parsed_time:
                return base_date.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
        return base_date.replace(hour=9, minute=0, second=0, microsecond=0)

    # Handle 'today' with time
    if time_str.startswith('today'):
        time_part = time_str.replace('today', '').strip()
        if time_part:
            parsed_time = parse_time_of_day(time_part)
            if parsed_time:
                return now.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
        return now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Handle time of day for today (e.g., '2pm', '14:30')
    parsed_time = parse_time_of_day(time_str)
    if parsed_time:
        return now.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)

    # Handle full datetime string
    for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d %I:%M%p', '%Y-%m-%d %I:%M %p']:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue

    return None


def parse_time_of_day(time_str: str) -> Optional[datetime]:
    """Parse time of day expressions like '2pm', '14:30', '9:30am'."""
    time_str = time_str.strip()

    # Try various time formats
    formats = [
        '%I%p',           # 2pm
        '%I:%M%p',        # 2:30pm
        '%I:%M %p',       # 2:30 pm
        '%H:%M',          # 14:30
    ]

    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue

    return None


def get_datetime(prompt: str, allow_relative: bool = True) -> Optional[datetime]:
    """Get a datetime from user with support for relative expressions."""
    examples = []
    if allow_relative:
        examples = ["now", "2h ago", "yesterday 3pm", "today 9am", "14:30"]
    else:
        examples = ["2026-01-25 14:30", "14:30", "2pm"]

    print(f"\n{prompt}")
    print(f"  Examples: {', '.join(examples)}")

    while True:
        time_str = input("  Enter time: ").strip()
        if not time_str:
            return None

        dt = parse_relative_time(time_str)
        if dt:
            confirm = input(f"  Confirm: {dt.strftime('%Y-%m-%d %I:%M %p')} (y/n)? ").strip().lower()
            if confirm in ('y', 'yes', ''):
                return dt
            print("  Let's try again.")
        else:
            print("  Error: Could not parse time. Please try again.")


def get_date_range(prompt: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Get a date range from user."""
    print(f"\n{prompt}")
    start = get_datetime("  Start date/time", allow_relative=True)
    end = get_datetime("  End date/time", allow_relative=True)
    return start, end


# ============================================================================
# Action Functions
# ============================================================================

def action_start_timer(logger: TimeLogger):
    """Start a new timer."""
    clear_screen()
    print_header("START TIMER")

    if logger.active_timer:
        print("\nError: A timer is already running!")
        print_active_timer(logger.active_timer)
        input("\nPress Enter to continue...")
        return

    task = get_input("Task name")
    category = get_input("Category", default="General")

    try:
        timer = logger.start_timer(task, category)
        print(f"\nTimer started for '{task}' at {format_datetime(timer.start_time)}")
    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to continue...")


def action_stop_timer(logger: TimeLogger):
    """Stop the active timer."""
    clear_screen()
    print_header("STOP TIMER")

    if not logger.active_timer:
        print("\nNo timer is currently running.")
        input("\nPress Enter to continue...")
        return

    print_active_timer(logger.active_timer)

    notes = get_optional_input("\nAdd notes")

    try:
        entry = logger.stop_timer(notes)
        print(f"\nTimer stopped! Duration: {format_duration(entry.duration)}")
        print(f"Entry saved: {entry.task}")
    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to continue...")


def action_log_past_entry(logger: TimeLogger):
    """Log a past time entry manually."""
    clear_screen()
    print_header("LOG PAST TIME ENTRY")

    task = get_input("\nTask name")
    category = get_input("Category", default="General")

    start_time = get_datetime("Start time")
    if not start_time:
        print("\nError: Start time is required.")
        input("\nPress Enter to continue...")
        return

    end_time = get_datetime("End time")
    if not end_time:
        print("\nError: End time is required.")
        input("\nPress Enter to continue...")
        return

    notes = get_optional_input("\nAdd notes")

    try:
        entry = logger.log_time(start_time, end_time, task, category, notes)
        print(f"\nEntry logged successfully!")
        print(f"Duration: {format_duration(entry.duration)}")
    except ValueError as e:
        print(f"\nError: {e}")
    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to continue...")


def action_view_today(logger: TimeLogger):
    """View today's time entries."""
    clear_screen()
    print_header("TODAY'S ENTRIES")

    if logger.active_timer:
        print_active_timer(logger.active_timer)

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    entries = logger.get_entries(start_date=today_start, end_date=today_end)

    if not entries:
        print("\nNo entries recorded today.")
    else:
        print(f"\nFound {len(entries)} entries:\n")
        print_separator()
        for entry in entries:
            print_time_entry(entry)

        # Show today's summary
        summary = {}
        for entry in entries:
            summary[entry.category] = summary.get(entry.category, 0.0) + entry.duration

        print_summary(summary, "Today's Summary by Category")

    input("\nPress Enter to continue...")


def action_view_summary(logger: TimeLogger):
    """View time summaries for different periods."""
    clear_screen()
    print_header("VIEW SUMMARY")

    period = get_choice(
        "Select time period:",
        ["Today", "This Week", "This Month", "Custom Range", "All Time"]
    )

    now = datetime.now()
    start_date = None
    end_date = None

    if period == "Today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == "This Week":
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == "This Month":
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == "Custom Range":
        start_date, end_date = get_date_range("Enter date range")

    group_by = get_choice(
        "\nGroup by:",
        ["Category", "Task"]
    ).lower()

    try:
        summary = logger.get_summary(group_by=group_by, start_date=start_date, end_date=end_date)

        clear_screen()
        title = f"{period} Summary by {group_by.capitalize()}"
        if start_date:
            title += f"\n  From: {start_date.strftime('%Y-%m-%d')}"
        if end_date:
            title += f" To: {end_date.strftime('%Y-%m-%d')}"

        print_summary(summary, title)

    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to continue...")


def action_export_data(logger: TimeLogger):
    """Export time entries to CSV."""
    clear_screen()
    print_header("EXPORT DATA")

    default_filename = f"time_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    filename = get_input("\nExport filename", default=default_filename)

    if not filename.endswith('.csv'):
        filename += '.csv'

    output_path = Path(filename)

    try:
        logger.export_to_csv(output_path)
        print(f"\nSuccessfully exported {len(logger.entries)} entries to:")
        print(f"  {output_path.absolute()}")
    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to continue...")


def action_view_all_entries(logger: TimeLogger):
    """View all time entries with optional filtering."""
    clear_screen()
    print_header("VIEW ALL ENTRIES")

    print("\nFilter options (press Enter to skip):")
    category = get_optional_input("Filter by category")
    task = get_optional_input("Filter by task")

    use_date_filter = input("Filter by date range? (y/n): ").strip().lower()
    start_date = None
    end_date = None
    if use_date_filter in ('y', 'yes'):
        start_date, end_date = get_date_range("Date range filter")

    try:
        entries = logger.get_entries(
            category=category if category else None,
            task=task if task else None,
            start_date=start_date,
            end_date=end_date
        )

        clear_screen()
        print_header("FILTERED ENTRIES")

        if not entries:
            print("\nNo entries found matching filters.")
        else:
            print(f"\nFound {len(entries)} entries:\n")
            print_separator()

            # Limit display to avoid overwhelming output
            display_limit = 20
            for i, entry in enumerate(entries[:display_limit]):
                print_time_entry(entry)

            if len(entries) > display_limit:
                print(f"\n... and {len(entries) - display_limit} more entries.")
                print("Consider exporting to CSV for full data.")

    except Exception as e:
        print(f"\nError: {e}")

    input("\nPress Enter to continue...")


# ============================================================================
# Main Menu
# ============================================================================

def show_main_menu(logger: TimeLogger):
    """Display the main menu."""
    clear_screen()
    print_header("TIME LOGGER")

    if logger.active_timer:
        print_active_timer(logger.active_timer)

    print("\nMAIN MENU:")
    print("  1. Start Timer")
    print("  2. Stop Timer")
    print("  3. Log Past Entry")
    print("  4. View Today's Entries")
    print("  5. View All Entries")
    print("  6. View Summary")
    print("  7. Export to CSV")
    print("  8. Quit")

    return input("\nSelect option (1-8): ").strip()


def main():
    """Main CLI loop."""
    logger = TimeLogger()

    actions = {
        '1': action_start_timer,
        '2': action_stop_timer,
        '3': action_log_past_entry,
        '4': action_view_today,
        '5': action_view_all_entries,
        '6': action_view_summary,
        '7': action_export_data,
    }

    while True:
        try:
            choice = show_main_menu(logger)

            if choice == '8':
                clear_screen()
                print("Saving data and exiting...")
                logger.save()
                print("Goodbye!")
                sys.exit(0)

            action = actions.get(choice)
            if action:
                action(logger)
            else:
                print("\nInvalid option. Please try again.")
                input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Saving data...")
            logger.save()
            print("Goodbye!")
            sys.exit(0)
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            input("\nPress Enter to continue...")


if __name__ == '__main__':
    main()
