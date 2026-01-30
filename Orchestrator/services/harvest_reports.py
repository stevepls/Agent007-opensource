"""
Harvest Time Report Generator

Generates time tracking reports from Harvest API data.
Supports multiple report formats and groupings.
"""

import os
import csv
import io
import requests
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


class ReportPeriod(Enum):
    """Predefined report periods."""
    TODAY = "today"
    YESTERDAY = "yesterday"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"
    LAST_QUARTER = "last_quarter"
    THIS_YEAR = "this_year"
    CUSTOM = "custom"


class GroupBy(Enum):
    """Report grouping options."""
    NONE = "none"
    PROJECT = "project"
    CLIENT = "client"
    USER = "user"
    TASK = "task"
    DATE = "date"
    WEEK = "week"


@dataclass
class TimeEntry:
    """Represents a single time entry."""
    id: int
    date: str
    hours: float
    notes: str
    project_id: int
    project_name: str
    client_id: Optional[int]
    client_name: Optional[str]
    task_id: int
    task_name: str
    user_id: int
    user_name: str
    billable: bool
    billable_rate: Optional[float]
    cost_rate: Optional[float]
    is_running: bool = False
    external_reference: Optional[Dict] = None
    
    @property
    def ticket_id(self) -> Optional[str]:
        """Extract ticket ID from external reference or notes."""
        # Try external reference first
        if self.external_reference:
            ref_id = self.external_reference.get("id")
            if ref_id:
                return str(ref_id)
        
        # Try to extract from notes (format: "Ticket #1234: description")
        import re
        match = re.search(r'(?:Ticket\s*#?|#)(\d+)', self.notes, re.IGNORECASE)
        if match:
            return match.group(1)
        
        return None
    
    @property
    def ticket_url(self) -> Optional[str]:
        """Get ticket URL from external reference."""
        if self.external_reference:
            return self.external_reference.get("permalink")
        return None
    
    @property
    def description(self) -> str:
        """Get clean description (notes without ticket prefix)."""
        import re
        # Remove "Ticket #1234: " prefix if present
        desc = re.sub(r'^Ticket\s*#?\d+:\s*', '', self.notes, flags=re.IGNORECASE)
        return desc.strip()


@dataclass
class ReportSummary:
    """Summary statistics for a report."""
    total_hours: float = 0.0
    billable_hours: float = 0.0
    non_billable_hours: float = 0.0
    entry_count: int = 0
    unique_projects: int = 0
    unique_clients: int = 0
    unique_users: int = 0
    date_range: str = ""
    generated_at: str = ""


@dataclass
class TimeReport:
    """Complete time report."""
    title: str
    period: str
    from_date: str
    to_date: str
    summary: ReportSummary
    entries: List[TimeEntry] = field(default_factory=list)
    grouped_data: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)


class HarvestReportClient:
    """Client for fetching Harvest data for reports."""
    
    def __init__(self, access_token: str = None, account_id: str = None):
        self.access_token = access_token or os.getenv("HARVEST_ACCESS_TOKEN")
        self.account_id = account_id or os.getenv("HARVEST_ACCOUNT_ID")
        self.base_url = "https://api.harvestapp.com/v2"
        
        if not self.access_token or not self.account_id:
            raise ValueError("Harvest credentials not configured")
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Harvest-Account-Id": str(self.account_id),
            "User-Agent": "Orchestrator-Report-Generator",
        }
    
    def get_time_entries(
        self,
        from_date: str,
        to_date: str,
        project_id: Optional[int] = None,
        client_id: Optional[int] = None,
        user_id: Optional[int] = None,
        is_billable: Optional[bool] = None,
    ) -> List[TimeEntry]:
        """Fetch time entries for a date range."""
        entries = []
        page = 1
        
        while True:
            params = {
                "from": from_date,
                "to": to_date,
                "page": page,
                "per_page": 100,
            }
            
            if project_id:
                params["project_id"] = project_id
            if client_id:
                params["client_id"] = client_id
            if user_id:
                params["user_id"] = user_id
            if is_billable is not None:
                params["is_billable"] = str(is_billable).lower()
            
            try:
                response = requests.get(
                    f"{self.base_url}/time_entries",
                    headers=self.headers,
                    params=params,
                    timeout=60
                )
                response.raise_for_status()
                data = response.json()
                
                for entry in data.get("time_entries", []):
                    entries.append(TimeEntry(
                        id=entry["id"],
                        date=entry["spent_date"],
                        hours=entry.get("hours", 0),
                        notes=entry.get("notes", "") or "",
                        project_id=entry["project"]["id"],
                        project_name=entry["project"]["name"],
                        client_id=entry.get("client", {}).get("id"),
                        client_name=entry.get("client", {}).get("name"),
                        task_id=entry["task"]["id"],
                        task_name=entry["task"]["name"],
                        user_id=entry["user"]["id"],
                        user_name=entry["user"]["name"],
                        billable=entry.get("billable", False),
                        billable_rate=entry.get("billable_rate"),
                        cost_rate=entry.get("cost_rate"),
                        is_running=entry.get("is_running", False),
                        external_reference=entry.get("external_reference"),
                    ))
                
                # Check for more pages
                if page >= data.get("total_pages", 1):
                    break
                page += 1
                
            except Exception as e:
                print(f"Error fetching entries: {e}")
                break
        
        return entries
    
    def get_projects(self) -> List[Dict]:
        """Get all projects."""
        try:
            response = requests.get(
                f"{self.base_url}/projects",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("projects", [])
        except Exception:
            return []
    
    def get_clients(self) -> List[Dict]:
        """Get all clients."""
        try:
            response = requests.get(
                f"{self.base_url}/clients",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("clients", [])
        except Exception:
            return []
    
    def get_users(self) -> List[Dict]:
        """Get all users."""
        try:
            response = requests.get(
                f"{self.base_url}/users",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("users", [])
        except Exception:
            return []


class TimeReportGenerator:
    """Generates time reports from Harvest data."""
    
    def __init__(self, client: HarvestReportClient = None):
        self.client = client or HarvestReportClient()
    
    def get_date_range(self, period: ReportPeriod, custom_from: str = None, custom_to: str = None) -> tuple:
        """Get date range for a report period."""
        today = date.today()
        
        if period == ReportPeriod.TODAY:
            return today.isoformat(), today.isoformat()
        
        elif period == ReportPeriod.YESTERDAY:
            yesterday = today - timedelta(days=1)
            return yesterday.isoformat(), yesterday.isoformat()
        
        elif period == ReportPeriod.THIS_WEEK:
            start = today - timedelta(days=today.weekday())
            return start.isoformat(), today.isoformat()
        
        elif period == ReportPeriod.LAST_WEEK:
            start = today - timedelta(days=today.weekday() + 7)
            end = start + timedelta(days=6)
            return start.isoformat(), end.isoformat()
        
        elif period == ReportPeriod.THIS_MONTH:
            start = today.replace(day=1)
            return start.isoformat(), today.isoformat()
        
        elif period == ReportPeriod.LAST_MONTH:
            first_of_month = today.replace(day=1)
            end = first_of_month - timedelta(days=1)
            start = end.replace(day=1)
            return start.isoformat(), end.isoformat()
        
        elif period == ReportPeriod.THIS_QUARTER:
            quarter = (today.month - 1) // 3
            start = today.replace(month=quarter * 3 + 1, day=1)
            return start.isoformat(), today.isoformat()
        
        elif period == ReportPeriod.LAST_QUARTER:
            quarter = (today.month - 1) // 3
            if quarter == 0:
                start = today.replace(year=today.year - 1, month=10, day=1)
                end = today.replace(year=today.year - 1, month=12, day=31)
            else:
                start = today.replace(month=(quarter - 1) * 3 + 1, day=1)
                # End of last quarter = first day of current quarter minus 1 day
                end = today.replace(month=quarter * 3 + 1, day=1) - timedelta(days=1)
            return start.isoformat(), end.isoformat()
        
        elif period == ReportPeriod.THIS_YEAR:
            start = today.replace(month=1, day=1)
            return start.isoformat(), today.isoformat()
        
        elif period == ReportPeriod.CUSTOM:
            if not custom_from or not custom_to:
                raise ValueError("Custom period requires from_date and to_date")
            return custom_from, custom_to
        
        return today.isoformat(), today.isoformat()
    
    def generate_report(
        self,
        period: ReportPeriod = ReportPeriod.THIS_WEEK,
        from_date: str = None,
        to_date: str = None,
        group_by: GroupBy = GroupBy.PROJECT,
        project_id: Optional[int] = None,
        client_id: Optional[int] = None,
        user_id: Optional[int] = None,
        billable_only: bool = False,
        title: str = None,
    ) -> TimeReport:
        """Generate a time report."""
        
        # Get date range
        start, end = self.get_date_range(period, from_date, to_date)
        
        # Fetch entries
        entries = self.client.get_time_entries(
            from_date=start,
            to_date=end,
            project_id=project_id,
            client_id=client_id,
            user_id=user_id,
            is_billable=True if billable_only else None,
        )
        
        # Calculate summary
        summary = self._calculate_summary(entries, start, end)
        
        # Group data
        grouped = self._group_entries(entries, group_by)
        
        # Build report
        report = TimeReport(
            title=title or f"Time Report - {period.value.replace('_', ' ').title()}",
            period=period.value,
            from_date=start,
            to_date=end,
            summary=summary,
            entries=entries,
            grouped_data=grouped,
            filters={
                "project_id": project_id,
                "client_id": client_id,
                "user_id": user_id,
                "billable_only": billable_only,
                "group_by": group_by.value,
            }
        )
        
        return report
    
    def _calculate_summary(self, entries: List[TimeEntry], from_date: str, to_date: str) -> ReportSummary:
        """Calculate summary statistics."""
        total = sum(e.hours for e in entries)
        billable = sum(e.hours for e in entries if e.billable)
        projects = set(e.project_id for e in entries)
        clients = set(e.client_id for e in entries if e.client_id)
        users = set(e.user_id for e in entries)
        
        return ReportSummary(
            total_hours=round(total, 2),
            billable_hours=round(billable, 2),
            non_billable_hours=round(total - billable, 2),
            entry_count=len(entries),
            unique_projects=len(projects),
            unique_clients=len(clients),
            unique_users=len(users),
            date_range=f"{from_date} to {to_date}",
            generated_at=datetime.now().isoformat(),
        )
    
    def _group_entries(self, entries: List[TimeEntry], group_by: GroupBy) -> Dict[str, Any]:
        """Group entries by specified field."""
        if group_by == GroupBy.NONE:
            return {"all": entries}
        
        grouped = {}
        
        for entry in entries:
            if group_by == GroupBy.PROJECT:
                key = entry.project_name
            elif group_by == GroupBy.CLIENT:
                key = entry.client_name or "No Client"
            elif group_by == GroupBy.USER:
                key = entry.user_name
            elif group_by == GroupBy.TASK:
                key = entry.task_name
            elif group_by == GroupBy.DATE:
                key = entry.date
            elif group_by == GroupBy.WEEK:
                entry_date = datetime.strptime(entry.date, "%Y-%m-%d")
                week_start = entry_date - timedelta(days=entry_date.weekday())
                key = f"Week of {week_start.strftime('%Y-%m-%d')}"
            else:
                key = "all"
            
            if key not in grouped:
                grouped[key] = {
                    "entries": [],
                    "total_hours": 0,
                    "billable_hours": 0,
                    "entry_count": 0,
                }
            
            grouped[key]["entries"].append(entry)
            grouped[key]["total_hours"] += entry.hours
            grouped[key]["billable_hours"] += entry.hours if entry.billable else 0
            grouped[key]["entry_count"] += 1
        
        # Round totals
        for key in grouped:
            grouped[key]["total_hours"] = round(grouped[key]["total_hours"], 2)
            grouped[key]["billable_hours"] = round(grouped[key]["billable_hours"], 2)
        
        return grouped


# =============================================================================
# Report Formatters
# =============================================================================

def format_report_markdown(report: TimeReport, include_details: bool = True) -> str:
    """Format report as Markdown."""
    lines = []
    
    # Header
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"**Period:** {report.from_date} to {report.to_date}")
    lines.append(f"**Generated:** {report.summary.generated_at[:19]}")
    lines.append("")
    
    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Hours | **{report.summary.total_hours:.2f}** |")
    lines.append(f"| Billable Hours | {report.summary.billable_hours:.2f} |")
    lines.append(f"| Non-Billable Hours | {report.summary.non_billable_hours:.2f} |")
    lines.append(f"| Time Entries | {report.summary.entry_count} |")
    lines.append(f"| Projects | {report.summary.unique_projects} |")
    lines.append(f"| Clients | {report.summary.unique_clients} |")
    lines.append("")
    
    # Grouped breakdown
    if report.grouped_data:
        group_by = report.filters.get("group_by", "project")
        lines.append(f"## By {group_by.title()}")
        lines.append("")
        lines.append(f"| {group_by.title()} | Hours | Billable | Entries |")
        lines.append(f"|{'---' * 10}|------:|--------:|--------:|")
        
        # Sort by hours descending
        sorted_groups = sorted(
            report.grouped_data.items(),
            key=lambda x: x[1]["total_hours"],
            reverse=True
        )
        
        for name, data in sorted_groups:
            lines.append(
                f"| {name[:40]} | {data['total_hours']:.2f} | "
                f"{data['billable_hours']:.2f} | {data['entry_count']} |"
            )
        lines.append("")
    
    # Details
    if include_details and report.entries:
        lines.append("## Time Entries")
        lines.append("")
        lines.append("| Date | Ticket | Hours | Project | Description |")
        lines.append("|------|--------|------:|---------|-------------|")
        
        for entry in sorted(report.entries, key=lambda x: x.date, reverse=True)[:50]:
            # Format ticket ID with link if available
            ticket_id = entry.ticket_id
            if ticket_id:
                if entry.ticket_url:
                    ticket = f"[#{ticket_id}]({entry.ticket_url})"
                else:
                    ticket = f"#{ticket_id}"
            else:
                ticket = "-"
            
            # Get clean description
            desc = entry.description[:45]
            if len(entry.description) > 45:
                desc += "..."
            desc = desc.replace("|", "\\|").replace("\n", " ")
            
            lines.append(
                f"| {entry.date} | {ticket} | {entry.hours:.2f} | "
                f"{entry.project_name[:18]} | {desc} |"
            )
        
        if len(report.entries) > 50:
            lines.append(f"\n*... and {len(report.entries) - 50} more entries*")
    
    return "\n".join(lines)


def format_report_csv(report: TimeReport) -> str:
    """Format report as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Date", "Ticket ID", "Ticket URL", "Project", "Client", "Task", "User", 
        "Hours", "Billable", "Billable Rate", "Description"
    ])
    
    for entry in sorted(report.entries, key=lambda x: x.date):
        writer.writerow([
            entry.date,
            entry.ticket_id or "",
            entry.ticket_url or "",
            entry.project_name,
            entry.client_name or "",
            entry.task_name,
            entry.user_name,
            entry.hours,
            "Yes" if entry.billable else "No",
            entry.billable_rate or "",
            entry.description.replace("\n", " "),
        ])
    
    return output.getvalue()


def format_report_json(report: TimeReport) -> Dict[str, Any]:
    """Format report as JSON-serializable dict."""
    return {
        "title": report.title,
        "period": report.period,
        "from_date": report.from_date,
        "to_date": report.to_date,
        "summary": {
            "total_hours": report.summary.total_hours,
            "billable_hours": report.summary.billable_hours,
            "non_billable_hours": report.summary.non_billable_hours,
            "entry_count": report.summary.entry_count,
            "unique_projects": report.summary.unique_projects,
            "unique_clients": report.summary.unique_clients,
            "unique_users": report.summary.unique_users,
            "date_range": report.summary.date_range,
            "generated_at": report.summary.generated_at,
        },
        "grouped_data": {
            k: {
                "total_hours": v["total_hours"],
                "billable_hours": v["billable_hours"],
                "entry_count": v["entry_count"],
            }
            for k, v in report.grouped_data.items()
        },
        "entries": [
            {
                "id": e.id,
                "date": e.date,
                "ticket_id": e.ticket_id,
                "ticket_url": e.ticket_url,
                "project": e.project_name,
                "client": e.client_name,
                "task": e.task_name,
                "user": e.user_name,
                "hours": e.hours,
                "billable": e.billable,
                "description": e.description,
            }
            for e in report.entries
        ],
        "filters": report.filters,
    }


def format_report_text(report: TimeReport) -> str:
    """Format report as plain text."""
    lines = []
    
    # Header
    lines.append("=" * 60)
    lines.append(report.title.center(60))
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"Period: {report.from_date} to {report.to_date}")
    lines.append("")
    
    # Summary box
    lines.append("┌" + "─" * 40 + "┐")
    lines.append(f"│ {'SUMMARY':^38} │")
    lines.append("├" + "─" * 40 + "┤")
    lines.append(f"│ Total Hours:      {report.summary.total_hours:>18.2f} │")
    lines.append(f"│ Billable Hours:   {report.summary.billable_hours:>18.2f} │")
    lines.append(f"│ Non-Billable:     {report.summary.non_billable_hours:>18.2f} │")
    lines.append(f"│ Time Entries:     {report.summary.entry_count:>18} │")
    lines.append(f"│ Projects:         {report.summary.unique_projects:>18} │")
    lines.append("└" + "─" * 40 + "┘")
    lines.append("")
    
    # Grouped breakdown
    if report.grouped_data:
        group_by = report.filters.get("group_by", "project")
        lines.append(f"BY {group_by.upper()}")
        lines.append("-" * 60)
        
        sorted_groups = sorted(
            report.grouped_data.items(),
            key=lambda x: x[1]["total_hours"],
            reverse=True
        )
        
        for name, data in sorted_groups:
            hours_bar = "█" * int(data["total_hours"])
            lines.append(f"{name[:30]:<30} {data['total_hours']:>6.2f}h {hours_bar}")
        
        lines.append("")
    
    # Entry details with ticket info
    if report.entries:
        lines.append("TIME ENTRIES")
        lines.append("-" * 60)
        
        for entry in sorted(report.entries, key=lambda x: x.date, reverse=True)[:30]:
            ticket = f"#{entry.ticket_id}" if entry.ticket_id else ""
            desc = entry.description[:40]
            if len(entry.description) > 40:
                desc += "..."
            
            lines.append(f"{entry.date} | {entry.hours:>5.2f}h | {ticket:<8} | {desc}")
        
        if len(report.entries) > 30:
            lines.append(f"... and {len(report.entries) - 30} more entries")
        
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# Quick Report Functions
# =============================================================================

def generate_weekly_report(
    project_id: Optional[int] = None,
    include_last_week: bool = False,
) -> TimeReport:
    """Generate a weekly time report."""
    generator = TimeReportGenerator()
    period = ReportPeriod.LAST_WEEK if include_last_week else ReportPeriod.THIS_WEEK
    
    return generator.generate_report(
        period=period,
        group_by=GroupBy.DATE,
        project_id=project_id,
        title="Weekly Time Report",
    )


def generate_project_report(
    project_id: int,
    period: ReportPeriod = ReportPeriod.THIS_MONTH,
) -> TimeReport:
    """Generate a project-specific time report."""
    generator = TimeReportGenerator()
    
    return generator.generate_report(
        period=period,
        project_id=project_id,
        group_by=GroupBy.TASK,
        title=f"Project Time Report",
    )


def generate_client_report(
    client_id: int,
    period: ReportPeriod = ReportPeriod.THIS_MONTH,
) -> TimeReport:
    """Generate a client-specific time report."""
    generator = TimeReportGenerator()
    
    return generator.generate_report(
        period=period,
        client_id=client_id,
        group_by=GroupBy.PROJECT,
        title=f"Client Time Report",
    )


def generate_user_report(
    user_id: int = None,
    period: ReportPeriod = ReportPeriod.THIS_WEEK,
) -> TimeReport:
    """Generate a user-specific time report."""
    generator = TimeReportGenerator()
    
    return generator.generate_report(
        period=period,
        user_id=user_id,
        group_by=GroupBy.PROJECT,
        title=f"Personal Time Report",
    )


# =============================================================================
# Report Templates
# =============================================================================

REPORT_TEMPLATES = {
    "weekly_summary": {
        "name": "Weekly Summary",
        "description": "Week-over-week time summary grouped by project",
        "period": ReportPeriod.THIS_WEEK,
        "group_by": GroupBy.PROJECT,
        "include_details": False,
    },
    "daily_breakdown": {
        "name": "Daily Breakdown",
        "description": "Detailed daily time entries",
        "period": ReportPeriod.THIS_WEEK,
        "group_by": GroupBy.DATE,
        "include_details": True,
    },
    "client_billing": {
        "name": "Client Billing Report",
        "description": "Billable hours by client and project",
        "period": ReportPeriod.THIS_MONTH,
        "group_by": GroupBy.CLIENT,
        "billable_only": True,
        "include_details": False,
    },
    "project_status": {
        "name": "Project Status",
        "description": "Time by project and task",
        "period": ReportPeriod.THIS_MONTH,
        "group_by": GroupBy.TASK,
        "include_details": True,
    },
    "team_overview": {
        "name": "Team Overview",
        "description": "Team member time distribution",
        "period": ReportPeriod.THIS_WEEK,
        "group_by": GroupBy.USER,
        "include_details": False,
    },
    "monthly_invoice": {
        "name": "Monthly Invoice Report",
        "description": "Detailed billable time for invoicing",
        "period": ReportPeriod.LAST_MONTH,
        "group_by": GroupBy.PROJECT,
        "billable_only": True,
        "include_details": True,
    },
}


def generate_from_template(
    template_name: str,
    project_id: Optional[int] = None,
    client_id: Optional[int] = None,
    user_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> TimeReport:
    """Generate a report from a template."""
    if template_name not in REPORT_TEMPLATES:
        raise ValueError(f"Unknown template: {template_name}. Available: {list(REPORT_TEMPLATES.keys())}")
    
    template = REPORT_TEMPLATES[template_name]
    generator = TimeReportGenerator()
    
    period = template["period"]
    if from_date and to_date:
        period = ReportPeriod.CUSTOM
    
    return generator.generate_report(
        period=period,
        from_date=from_date,
        to_date=to_date,
        group_by=template["group_by"],
        project_id=project_id,
        client_id=client_id,
        user_id=user_id,
        billable_only=template.get("billable_only", False),
        title=template["name"],
    )


def list_templates() -> Dict[str, Dict]:
    """List available report templates."""
    return {
        name: {
            "name": t["name"],
            "description": t["description"],
            "period": t["period"].value,
            "group_by": t["group_by"].value,
        }
        for name, t in REPORT_TEMPLATES.items()
    }


# =============================================================================
# CLI Interface
# =============================================================================

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Generate Harvest time reports")
    parser.add_argument("--template", choices=list(REPORT_TEMPLATES.keys()),
                       help="Report template to use")
    parser.add_argument("--period", choices=[p.value for p in ReportPeriod],
                       default="this_week", help="Report period")
    parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--group-by", choices=[g.value for g in GroupBy],
                       default="project", help="Group entries by")
    parser.add_argument("--project-id", type=int, help="Filter by project ID")
    parser.add_argument("--client-id", type=int, help="Filter by client ID")
    parser.add_argument("--user-id", type=int, help="Filter by user ID")
    parser.add_argument("--billable", action="store_true", help="Only billable entries")
    parser.add_argument("--format", choices=["markdown", "csv", "json", "text"],
                       default="markdown", help="Output format")
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--list-templates", action="store_true", 
                       help="List available templates")
    
    args = parser.parse_args()
    
    if args.list_templates:
        print("Available Report Templates:")
        print("-" * 50)
        for name, info in list_templates().items():
            print(f"\n{name}:")
            print(f"  {info['description']}")
            print(f"  Period: {info['period']}, Group by: {info['group_by']}")
        exit(0)
    
    try:
        if args.template:
            report = generate_from_template(
                args.template,
                project_id=args.project_id,
                client_id=args.client_id,
                user_id=args.user_id,
                from_date=args.from_date,
                to_date=args.to_date,
            )
        else:
            generator = TimeReportGenerator()
            
            period = ReportPeriod(args.period)
            if args.from_date and args.to_date:
                period = ReportPeriod.CUSTOM
            
            report = generator.generate_report(
                period=period,
                from_date=args.from_date,
                to_date=args.to_date,
                group_by=GroupBy(args.group_by),
                project_id=args.project_id,
                client_id=args.client_id,
                user_id=args.user_id,
                billable_only=args.billable,
            )
        
        # Format output
        if args.format == "markdown":
            output = format_report_markdown(report)
        elif args.format == "csv":
            output = format_report_csv(report)
        elif args.format == "json":
            output = json.dumps(format_report_json(report), indent=2)
        else:
            output = format_report_text(report)
        
        # Write or print
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Report saved to {args.output}")
        else:
            print(output)
            
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)
    except Exception as e:
        print(f"Error generating report: {e}")
        exit(1)
