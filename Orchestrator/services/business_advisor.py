"""
Business Advisor — Proactive Intelligence Engine

Continuously monitors all business data sources, tracks historical trends,
and generates proactive advisories. Works from both snapshots (past data)
and live queries (real-time data).

Architecture:
    DataCollectors → Snapshots (stored JSON) → TrendAnalyzer → AdvisoryRules → Advisories
                  ↘ LiveChecks ↗

Usage:
    from services.business_advisor import get_advisor

    advisor = get_advisor()

    # Take a snapshot of current state (run periodically / on demand)
    advisor.take_snapshot()

    # Get proactive advisories
    advisories = advisor.get_advisories()

    # Get full business health report with SWOT
    report = advisor.get_health_report()

    # Get trend analysis
    trends = advisor.get_trends(days=30)
"""

import os
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

from dotenv import load_dotenv

# Paths
SERVICES_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
DATA_ROOT = ORCHESTRATOR_ROOT / "data" / "advisor"
SNAPSHOTS_DIR = DATA_ROOT / "snapshots"
ADVISORIES_DIR = DATA_ROOT / "advisories"

# Ensure .env is loaded
load_dotenv(ORCHESTRATOR_ROOT / ".env")


# =============================================================================
# Data Models
# =============================================================================

class Severity(Enum):
    """Advisory severity levels."""
    CRITICAL = "critical"   # Needs immediate action (payment failed, client churning)
    WARNING = "warning"     # Needs attention soon (deadlines approaching, trends declining)
    INFO = "info"           # Good to know (new patterns, opportunities)
    POSITIVE = "positive"   # Good news (task completed, payment received, trend improving)


class Category(Enum):
    """Advisory categories."""
    REVENUE = "revenue"
    CLIENT_HEALTH = "client_health"
    TEAM_PERFORMANCE = "team_performance"
    TASK_MANAGEMENT = "task_management"
    COMMUNICATION = "communication"
    OPERATIONS = "operations"
    OPPORTUNITY = "opportunity"
    RISK = "risk"


@dataclass
class Advisory:
    """A single proactive advisory."""
    id: str
    severity: Severity
    category: Category
    title: str
    detail: str
    recommendation: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""           # Which data source triggered it
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "detail": self.detail,
            "recommendation": self.recommendation,
            "data": self.data,
            "source": self.source,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged,
        }


@dataclass
class BusinessSnapshot:
    """Point-in-time snapshot of all business metrics."""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # ClickUp Metrics
    total_open_tasks: int = 0
    overdue_tasks: int = 0
    stale_tasks_30d: int = 0
    unassigned_tasks: int = 0
    tasks_by_status: Dict[str, int] = field(default_factory=dict)
    tasks_by_space: Dict[str, int] = field(default_factory=dict)
    tasks_created_7d: int = 0
    tasks_completed_7d: int = 0
    blocked_tasks: int = 0
    
    # Harvest Metrics
    hours_logged_7d: float = 0.0
    hours_logged_30d: float = 0.0
    hours_by_project: Dict[str, float] = field(default_factory=dict)
    hours_by_person: Dict[str, float] = field(default_factory=dict)
    days_with_time_logged_30d: int = 0
    avg_hours_per_day: float = 0.0
    
    # Gmail Metrics
    unread_emails: int = 0
    emails_received_7d: int = 0
    payment_emails_7d: int = 0
    
    # Slack Metrics
    active_channels: int = 0
    messages_7d: int = 0
    
    # Client Metrics (per client)
    client_metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Team Metrics
    team_members: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrendPoint:
    """A single metric value over time."""
    date: str
    value: float
    
    
@dataclass
class Trend:
    """Trend analysis for a metric."""
    metric_name: str
    current_value: float
    previous_value: float
    change_pct: float          # % change
    direction: str             # "up", "down", "flat"
    is_healthy: bool           # Whether direction is good
    points: List[TrendPoint] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric_name,
            "current": self.current_value,
            "previous": self.previous_value,
            "change_pct": round(self.change_pct, 1),
            "direction": self.direction,
            "is_healthy": self.is_healthy,
            "points": [{"date": p.date, "value": p.value} for p in self.points],
        }


@dataclass
class HealthReport:
    """Complete business health report."""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Overall score (0-100)
    health_score: int = 0
    
    # SWOT
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    opportunities: List[str] = field(default_factory=list)
    threats: List[str] = field(default_factory=list)
    
    # KPIs
    kpis: Dict[str, Any] = field(default_factory=dict)
    
    # Trends
    trends: List[Dict[str, Any]] = field(default_factory=list)
    
    # Advisories
    advisories: List[Dict[str, Any]] = field(default_factory=list)
    
    # Snapshot
    snapshot: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# Cache Layer
# =============================================================================

@dataclass
class CacheEntry:
    """A cached data result with TTL."""
    data: Any
    fetched_at: float  # time.time()
    ttl: int           # seconds
    
    @property
    def is_valid(self) -> bool:
        return (time.time() - self.fetched_at) < self.ttl


class DataCache:
    """
    TTL-based cache for API responses.
    
    Each data source has its own TTL based on how frequently it changes:
    - ClickUp: 15 min (tasks change moderately)
    - Harvest:  30 min (time entries are periodic)
    - Gmail:    10 min (emails arrive frequently)
    - Slack:    15 min (messages are infrequent for this workspace)
    - Team:     60 min (team members rarely change)
    
    Cache is stored in-memory and optionally persisted to disk.
    """
    
    # Default TTLs per source (seconds)
    DEFAULT_TTLS = {
        "clickup":  15 * 60,   # 15 minutes
        "harvest":  30 * 60,   # 30 minutes
        "gmail":    10 * 60,   # 10 minutes
        "slack":    15 * 60,   # 15 minutes
        "team":     60 * 60,   # 1 hour
    }
    
    def __init__(self, cache_dir: Path = None):
        self._memory: Dict[str, CacheEntry] = {}
        self._cache_dir = cache_dir or DATA_ROOT / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data if still valid, else None."""
        # Check memory first
        entry = self._memory.get(key)
        if entry and entry.is_valid:
            self._hits += 1
            return entry.data
        
        # Check disk cache
        disk_file = self._cache_dir / f"{key}.json"
        if disk_file.exists():
            try:
                with open(disk_file) as f:
                    stored = json.load(f)
                ttl = self.DEFAULT_TTLS.get(key, 15 * 60)
                fetched_at = stored.get("_fetched_at", 0)
                if (time.time() - fetched_at) < ttl:
                    data = stored.get("_data", stored)
                    self._memory[key] = CacheEntry(data=data, fetched_at=fetched_at, ttl=ttl)
                    self._hits += 1
                    return data
            except (json.JSONDecodeError, KeyError):
                pass
        
        self._misses += 1
        return None
    
    def set(self, key: str, data: Any, ttl: int = None):
        """Store data in cache with TTL."""
        ttl = ttl or self.DEFAULT_TTLS.get(key, 15 * 60)
        now = time.time()
        
        # Memory cache
        self._memory[key] = CacheEntry(data=data, fetched_at=now, ttl=ttl)
        
        # Disk cache (for persistence across restarts)
        disk_file = self._cache_dir / f"{key}.json"
        try:
            with open(disk_file, "w") as f:
                json.dump({"_data": data, "_fetched_at": now}, f, default=str)
        except Exception:
            pass  # Disk cache is best-effort
    
    def invalidate(self, key: str = None):
        """Invalidate a specific key or all keys."""
        if key:
            self._memory.pop(key, None)
            disk_file = self._cache_dir / f"{key}.json"
            if disk_file.exists():
                disk_file.unlink()
        else:
            self._memory.clear()
            for f in self._cache_dir.glob("*.json"):
                f.unlink()
    
    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{self._hits * 100 / max(total, 1):.0f}%",
            "cached_keys": list(self._memory.keys()),
            "valid_keys": [k for k, v in self._memory.items() if v.is_valid],
        }


# =============================================================================
# Data Collectors
# =============================================================================

class DataCollectors:
    """
    Collects data from all business sources with caching.
    
    Each collector checks the cache first (by source key).
    API calls only happen on cache miss or expiry.
    """
    
    def __init__(self, cache: DataCache = None):
        self._cache = cache or DataCache()
    
    @property
    def cache(self) -> DataCache:
        return self._cache
    
    def collect_clickup(self, force: bool = False) -> Dict[str, Any]:
        """Collect ClickUp workspace metrics (cached 15 min)."""
        if not force:
            cached = self._cache.get("clickup")
            if cached is not None:
                print("[CACHE] ClickUp: hit")
                return cached
        
        print("[CACHE] ClickUp: miss — fetching from API...")
        try:
            from services.tickets.clickup_tools import clickup_api_request
            
            now_ms = int(time.time() * 1000)
            thirty_days_ms = 30 * 86400 * 1000
            seven_days_ms = 7 * 86400 * 1000
            
            metrics = {
                "total_open": 0,
                "overdue": 0,
                "stale_30d": 0,
                "unassigned": 0,
                "blocked": 0,
                "created_7d": 0,
                "completed_7d": 0,
                "by_status": defaultdict(int),
                "by_space": defaultdict(int),
                "client_metrics": {},
            }
            
            teams = clickup_api_request("GET", "team")
            for team in teams.get("teams", []):
                spaces_resp = clickup_api_request("GET", f"team/{team['id']}/space")
                for space in spaces_resp.get("spaces", []):
                    space_name = space["name"]
                    space_open = 0
                    space_overdue = 0
                    space_stale = 0
                    space_in_progress = 0
                    
                    lists_resp = clickup_api_request("GET", f"space/{space['id']}/list")
                    for lst in lists_resp.get("lists", []):
                        # Open tasks
                        tasks_resp = clickup_api_request("GET", f"list/{lst['id']}/task?include_closed=false")
                        for task in tasks_resp.get("tasks", []):
                            status = task.get("status", {}).get("status", "unknown")
                            assignees = task.get("assignees", [])
                            due = task.get("due_date")
                            created = task.get("date_created")
                            updated = task.get("date_updated")
                            
                            metrics["total_open"] += 1
                            space_open += 1
                            metrics["by_status"][status] += 1
                            
                            if not assignees:
                                metrics["unassigned"] += 1
                            
                            if due and int(due) < now_ms:
                                metrics["overdue"] += 1
                                space_overdue += 1
                            
                            if updated and (now_ms - int(updated)) > thirty_days_ms:
                                metrics["stale_30d"] += 1
                                space_stale += 1
                            
                            if "block" in status.lower():
                                metrics["blocked"] += 1
                            
                            if "progress" in status.lower():
                                space_in_progress += 1
                            
                            if created and (now_ms - int(created)) < seven_days_ms:
                                metrics["created_7d"] += 1
                        
                        # Closed tasks (last 7 days)
                        closed_resp = clickup_api_request("GET", f"list/{lst['id']}/task?include_closed=true&status[]=closed&status[]=complete&status[]=done")
                        for task in closed_resp.get("tasks", []):
                            updated = task.get("date_updated")
                            if updated and (now_ms - int(updated)) < seven_days_ms:
                                metrics["completed_7d"] += 1
                    
                    metrics["by_space"][space_name] = space_open
                    metrics["client_metrics"][space_name] = {
                        "open_tasks": space_open,
                        "overdue": space_overdue,
                        "stale": space_stale,
                        "in_progress": space_in_progress,
                    }
            
            # Serialize defaultdicts for caching
            metrics["by_status"] = dict(metrics["by_status"])
            metrics["by_space"] = dict(metrics["by_space"])
            
            self._cache.set("clickup", metrics)
            return metrics
        except Exception as e:
            print(f"[WARN] ClickUp collection failed: {e}")
            return {}
    
    def collect_harvest(self, force: bool = False) -> Dict[str, Any]:
        """Collect Harvest time tracking metrics (cached 30 min)."""
        if not force:
            cached = self._cache.get("harvest")
            if cached is not None:
                print("[CACHE] Harvest: hit")
                return cached
        
        print("[CACHE] Harvest: miss — fetching from API...")
        try:
            from services.harvest_reports import HarvestReportClient
            
            client = HarvestReportClient()
            today = date.today()
            
            # Last 7 days
            entries_7d = client.get_time_entries(
                from_date=(today - timedelta(days=7)).isoformat(),
                to_date=today.isoformat()
            )
            
            # Last 30 days
            entries_30d = client.get_time_entries(
                from_date=(today - timedelta(days=30)).isoformat(),
                to_date=today.isoformat()
            )
            
            hours_7d = sum(e.hours for e in entries_7d)
            hours_30d = sum(e.hours for e in entries_30d)
            
            hours_by_project = defaultdict(float)
            hours_by_person = defaultdict(float)
            days_worked = set()
            
            for e in entries_30d:
                hours_by_project[e.project_name] += e.hours
                hours_by_person[e.user_name] += e.hours
                days_worked.add(e.date)
            
            result = {
                "hours_7d": round(hours_7d, 1),
                "hours_30d": round(hours_30d, 1),
                "by_project": dict(hours_by_project),
                "by_person": dict(hours_by_person),
                "days_worked_30d": len(days_worked),
                "avg_hours_per_day": round(hours_30d / max(len(days_worked), 1), 1),
            }
            
            self._cache.set("harvest", result)
            return result
        except Exception as e:
            print(f"[WARN] Harvest collection failed: {e}")
            return {}
    
    def collect_gmail(self, force: bool = False) -> Dict[str, Any]:
        """Collect Gmail metrics (cached 10 min)."""
        if not force:
            cached = self._cache.get("gmail")
            if cached is not None:
                print("[CACHE] Gmail: hit")
                return cached
        
        print("[CACHE] Gmail: miss — fetching from API...")
        try:
            from services.gmail.client import GmailClient
            gmail = GmailClient()
            
            if not gmail.is_authenticated:
                return {}
            
            unread = gmail.get_unread_count()
            
            # Payment emails last 7 days
            payment_msgs = gmail.list_messages(
                query="subject:(invoice OR payment OR overdue) newer_than:7d",
                max_results=50
            )
            
            result = {
                "unread": unread,
                "payment_emails_7d": len(payment_msgs),
            }
            
            self._cache.set("gmail", result)
            return result
        except Exception as e:
            print(f"[WARN] Gmail collection failed: {e}")
            return {}
    
    def collect_slack(self, force: bool = False) -> Dict[str, Any]:
        """Collect Slack metrics (cached 15 min)."""
        if not force:
            cached = self._cache.get("slack")
            if cached is not None:
                print("[CACHE] Slack: hit")
                return cached
        
        print("[CACHE] Slack: miss — fetching from API...")
        try:
            from services.slack.client import SlackClient
            slack = SlackClient()
            
            channels = slack.list_channels()
            active = 0
            total_msgs = 0
            
            seven_days_ago = time.time() - (7 * 86400)
            
            for ch in channels:
                try:
                    msgs = slack.get_messages(ch.id, limit=10)
                    recent = [m for m in msgs if hasattr(m, 'ts') and float(m.ts) > seven_days_ago]
                    if recent:
                        active += 1
                        total_msgs += len(recent)
                except:
                    pass
            
            result = {
                "total_channels": len(channels),
                "active_channels": active,
                "messages_7d": total_msgs,
            }
            
            self._cache.set("slack", result)
            return result
        except Exception as e:
            print(f"[WARN] Slack collection failed: {e}")
            return {}
    
    def collect_team(self, force: bool = False) -> List[str]:
        """Collect team members (cached 1 hour)."""
        if not force:
            cached = self._cache.get("team")
            if cached is not None:
                print("[CACHE] Team: hit")
                return cached
        
        print("[CACHE] Team: miss — fetching from API...")
        try:
            from services.tickets.clickup_tools import clickup_api_request
            members = []
            teams = clickup_api_request("GET", "team")
            for team in teams.get("teams", []):
                for member in team.get("members", []):
                    username = member.get("user", {}).get("username", "")
                    if username:
                        members.append(username)
            
            self._cache.set("team", members)
            return members
        except:
            return []


# =============================================================================
# Advisory Rules Engine
# =============================================================================

class AdvisoryRules:
    """
    Rules engine that generates advisories from snapshot data.
    
    Each rule is a method that takes the current snapshot (and optionally
    historical snapshots) and returns zero or more advisories.
    """
    
    @staticmethod
    def check_overdue_crisis(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag if overdue tasks exceed threshold."""
        advisories = []
        
        if snap.overdue_tasks > 20:
            advisories.append(Advisory(
                id="overdue-crisis",
                severity=Severity.CRITICAL,
                category=Category.TASK_MANAGEMENT,
                title=f"🚨 {snap.overdue_tasks} overdue tasks across workspace",
                detail=f"You have {snap.overdue_tasks} tasks past their due dates. "
                       f"This represents {snap.overdue_tasks}/{snap.total_open_tasks} "
                       f"({snap.overdue_tasks * 100 // max(snap.total_open_tasks, 1)}%) of open tasks.",
                recommendation="Run a backlog bankruptcy: close or re-date stale tasks. "
                              "Focus on the top 5 most critical overdue items first.",
                data={"overdue": snap.overdue_tasks, "total": snap.total_open_tasks},
                source="clickup",
            ))
        elif snap.overdue_tasks > 5:
            advisories.append(Advisory(
                id="overdue-warning",
                severity=Severity.WARNING,
                category=Category.TASK_MANAGEMENT,
                title=f"⏰ {snap.overdue_tasks} tasks are overdue",
                detail=f"{snap.overdue_tasks} tasks need attention.",
                recommendation="Review and update due dates or close completed tasks.",
                data={"overdue": snap.overdue_tasks},
                source="clickup",
            ))
        
        return advisories
    
    @staticmethod
    def check_stale_backlog(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag stale task ratio."""
        advisories = []
        
        if snap.total_open_tasks > 0:
            stale_pct = snap.stale_tasks_30d * 100 / snap.total_open_tasks
            
            if stale_pct > 60:
                advisories.append(Advisory(
                    id="stale-backlog",
                    severity=Severity.CRITICAL,
                    category=Category.TASK_MANAGEMENT,
                    title=f"🧟 {stale_pct:.0f}% of backlog is stale ({snap.stale_tasks_30d} tasks)",
                    detail=f"{snap.stale_tasks_30d} of {snap.total_open_tasks} open tasks "
                           f"haven't been updated in 30+ days. This creates noise and "
                           f"makes it impossible to see what actually matters.",
                    recommendation="Declare backlog bankruptcy: archive tasks untouched for 60+ days. "
                                  "If they were important, they'll come back.",
                    data={"stale": snap.stale_tasks_30d, "total": snap.total_open_tasks, "pct": stale_pct},
                    source="clickup",
                ))
            elif stale_pct > 30:
                advisories.append(Advisory(
                    id="stale-backlog-warning",
                    severity=Severity.WARNING,
                    category=Category.TASK_MANAGEMENT,
                    title=f"📋 {stale_pct:.0f}% of backlog is stale",
                    detail=f"{snap.stale_tasks_30d} tasks haven't been touched in 30+ days.",
                    recommendation="Review and triage stale tasks weekly.",
                    data={"stale": snap.stale_tasks_30d, "pct": stale_pct},
                    source="clickup",
                ))
        
        return advisories
    
    @staticmethod
    def check_unassigned_tasks(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag unassigned tasks."""
        advisories = []
        
        if snap.unassigned_tasks > 20:
            advisories.append(Advisory(
                id="unassigned-tasks",
                severity=Severity.WARNING,
                category=Category.TASK_MANAGEMENT,
                title=f"👻 {snap.unassigned_tasks} tasks have no owner",
                detail=f"Unassigned tasks are nobody's responsibility and will never get done.",
                recommendation="Assign owners during weekly triage. If nobody owns it, close it.",
                data={"unassigned": snap.unassigned_tasks},
                source="clickup",
            ))
        
        return advisories
    
    @staticmethod
    def check_time_tracking(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag low time tracking utilization."""
        advisories = []
        
        # Low weekly hours
        if snap.hours_logged_7d < 20:
            advisories.append(Advisory(
                id="low-time-tracking",
                severity=Severity.WARNING,
                category=Category.REVENUE,
                title=f"⏱️ Only {snap.hours_logged_7d:.1f}h logged this week",
                detail=f"Team logged {snap.hours_logged_7d:.1f} hours in the last 7 days. "
                       f"For a team of {len(snap.team_members) or '?'}, this suggests "
                       f"significant untracked work or low utilization.",
                recommendation="Ensure all team members log time daily. "
                              "Untracked hours = lost revenue.",
                data={"hours_7d": snap.hours_logged_7d, "team_size": len(snap.team_members)},
                source="harvest",
            ))
        
        # Few projects tracked vs active spaces
        tracked_projects = len(snap.hours_by_project)
        active_spaces = len([s for s, c in snap.tasks_by_space.items() if c > 0])
        
        if tracked_projects > 0 and active_spaces > 0 and tracked_projects < active_spaces * 0.3:
            advisories.append(Advisory(
                id="tracking-gap",
                severity=Severity.WARNING,
                category=Category.REVENUE,
                title=f"📊 Time logged for {tracked_projects} projects but {active_spaces} are active",
                detail=f"Only {tracked_projects} Harvest projects have time logged, "
                       f"but {active_spaces} ClickUp spaces have open tasks. "
                       f"Work is happening but not being captured.",
                recommendation="Map each ClickUp space to a Harvest project. "
                              "Set up automatic time tracking reminders.",
                data={"tracked": tracked_projects, "active_spaces": active_spaces},
                source="harvest+clickup",
            ))
        
        return advisories
    
    @staticmethod
    def check_email_overload(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag email inbox health."""
        advisories = []
        
        if snap.unread_emails > 100:
            advisories.append(Advisory(
                id="email-overload",
                severity=Severity.WARNING,
                category=Category.COMMUNICATION,
                title=f"📧 {snap.unread_emails} unread emails",
                detail=f"High unread count means messages are being missed. "
                       f"Client requests, payment notifications, and issues may be buried.",
                recommendation="Block 30 min daily for email triage. "
                              "Set up filters for payment/invoice emails to a priority label.",
                data={"unread": snap.unread_emails},
                source="gmail",
            ))
        
        return advisories
    
    @staticmethod
    def check_communication_health(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag dead team communication."""
        advisories = []
        
        if snap.active_channels == 0 and snap.messages_7d == 0:
            advisories.append(Advisory(
                id="dead-comms",
                severity=Severity.WARNING,
                category=Category.COMMUNICATION,
                title="📵 No team Slack activity in the last 7 days",
                detail="Zero messages across all channels. Team has no shared "
                       "communication channel, meaning no visibility or accountability.",
                recommendation="Revive #general with a daily standup bot. "
                              "Set up ClickUp → Slack notifications for task updates.",
                data={"channels": snap.active_channels, "messages": snap.messages_7d},
                source="slack",
            ))
        
        return advisories
    
    @staticmethod
    def check_task_velocity(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag task creation vs completion imbalance."""
        advisories = []
        
        created = snap.tasks_created_7d
        completed = snap.tasks_completed_7d
        
        if created > 0 and completed == 0:
            advisories.append(Advisory(
                id="velocity-zero-completion",
                severity=Severity.WARNING,
                category=Category.TASK_MANAGEMENT,
                title=f"📈 {created} tasks created but 0 completed this week",
                detail=f"Backlog is growing with no throughput. "
                       f"This means tasks are being added faster than they're being resolved.",
                recommendation="Focus on completing existing tasks before creating new ones. "
                              "Implement WIP limits.",
                data={"created": created, "completed": completed},
                source="clickup",
            ))
        elif created > 0 and completed > 0 and created > completed * 2:
            advisories.append(Advisory(
                id="velocity-imbalance",
                severity=Severity.INFO,
                category=Category.TASK_MANAGEMENT,
                title=f"📊 Creating tasks 2x faster than completing ({created} vs {completed})",
                detail=f"Backlog is growing. {created} created vs {completed} completed this week.",
                recommendation="Review if new tasks are truly necessary or just wishlists.",
                data={"created": created, "completed": completed},
                source="clickup",
            ))
        elif completed > created and completed > 5:
            advisories.append(Advisory(
                id="velocity-positive",
                severity=Severity.POSITIVE,
                category=Category.TASK_MANAGEMENT,
                title=f"✅ Completing more tasks than creating ({completed} vs {created})",
                detail=f"Good momentum! Backlog is shrinking.",
                recommendation="Keep this pace. Consider celebrating the wins with the team.",
                data={"created": created, "completed": completed},
                source="clickup",
            ))
        
        return advisories
    
    @staticmethod
    def check_client_health(snap: BusinessSnapshot) -> List[Advisory]:
        """Flag at-risk clients based on task/communication metrics."""
        advisories = []
        
        for client, metrics in snap.client_metrics.items():
            open_tasks = metrics.get("open_tasks", 0)
            overdue = metrics.get("overdue", 0)
            stale = metrics.get("stale", 0)
            in_progress = metrics.get("in_progress", 0)
            
            # Too many tasks in progress (WIP overload)
            if in_progress > 10:
                advisories.append(Advisory(
                    id=f"client-wip-{client[:20]}",
                    severity=Severity.WARNING,
                    category=Category.CLIENT_HEALTH,
                    title=f"🔥 {client}: {in_progress} tasks in progress simultaneously",
                    detail=f"Too much work in progress means nothing gets finished. "
                           f"Context-switching kills productivity.",
                    recommendation=f"Limit {client} to 3-5 tasks in progress. "
                                  f"Move the rest back to 'to do'.",
                    data={"client": client, "in_progress": in_progress},
                    source="clickup",
                ))
            
            # High overdue ratio
            if open_tasks > 3 and overdue > open_tasks * 0.5:
                advisories.append(Advisory(
                    id=f"client-overdue-{client[:20]}",
                    severity=Severity.WARNING,
                    category=Category.CLIENT_HEALTH,
                    title=f"⚠️ {client}: {overdue}/{open_tasks} tasks overdue",
                    detail=f"More than half of {client}'s tasks are past due.",
                    recommendation=f"Schedule a call with {client} to reset expectations. "
                                  f"Re-scope deadlines.",
                    data={"client": client, "overdue": overdue, "total": open_tasks},
                    source="clickup",
                ))
            
            # Mostly stale (client possibly abandoned)
            if open_tasks > 5 and stale > open_tasks * 0.8:
                advisories.append(Advisory(
                    id=f"client-stale-{client[:20]}",
                    severity=Severity.INFO,
                    category=Category.CLIENT_HEALTH,
                    title=f"💤 {client}: {stale}/{open_tasks} tasks stale (30+ days)",
                    detail=f"Almost all tasks for {client} are untouched. "
                           f"Either the project is paused or it's been forgotten.",
                    recommendation=f"Check in with {client}. If the project is done, "
                                  f"close the tasks. If paused, archive them.",
                    data={"client": client, "stale": stale, "total": open_tasks},
                    source="clickup",
                ))
        
        return advisories
    
    @staticmethod
    def check_wip_overload(snap: BusinessSnapshot) -> List[Advisory]:
        """Check total work-in-progress across the business."""
        advisories = []
        
        in_progress = snap.tasks_by_status.get("in progress", 0)
        team_size = len(snap.team_members) or 4  # default estimate
        
        per_person = in_progress / max(team_size, 1)
        
        if per_person > 10:
            advisories.append(Advisory(
                id="wip-overload",
                severity=Severity.CRITICAL,
                category=Category.TEAM_PERFORMANCE,
                title=f"🏋️ {in_progress} tasks in progress ({per_person:.0f} per person)",
                detail=f"With {team_size} team members and {in_progress} tasks in progress, "
                       f"each person has ~{per_person:.0f} concurrent tasks. "
                       f"Research shows >3 concurrent tasks kills productivity.",
                recommendation="Implement strict WIP limits: max 3 tasks per person. "
                              "Finish before starting new work.",
                data={"in_progress": in_progress, "team_size": team_size, "per_person": per_person},
                source="clickup",
            ))
        
        return advisories


# =============================================================================
# Trend Analyzer
# =============================================================================

class TrendAnalyzer:
    """Analyzes trends by comparing snapshots over time."""
    
    def __init__(self, snapshots_dir: Path = SNAPSHOTS_DIR):
        self.snapshots_dir = snapshots_dir
    
    def load_snapshots(self, days: int = 30) -> List[BusinessSnapshot]:
        """Load historical snapshots."""
        snapshots = []
        cutoff = datetime.now() - timedelta(days=days)
        
        if not self.snapshots_dir.exists():
            return []
        
        for f in sorted(self.snapshots_dir.glob("*.json")):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                
                ts = data.get("timestamp", "")
                if ts and datetime.fromisoformat(ts) >= cutoff:
                    snap = BusinessSnapshot(**{
                        k: v for k, v in data.items()
                        if k in BusinessSnapshot.__dataclass_fields__
                    })
                    snapshots.append(snap)
            except Exception:
                continue
        
        return snapshots
    
    def compute_trends(self, days: int = 30) -> List[Trend]:
        """Compute trends from historical snapshots."""
        snapshots = self.load_snapshots(days=days)
        
        if len(snapshots) < 2:
            return []
        
        trends = []
        latest = snapshots[-1]
        
        # Split into two halves for comparison
        mid = len(snapshots) // 2
        first_half = snapshots[:mid]
        second_half = snapshots[mid:]
        
        def avg(snaps, attr):
            vals = [getattr(s, attr, 0) for s in snaps]
            return sum(vals) / max(len(vals), 1)
        
        # Define metrics to track
        metric_configs = [
            ("total_open_tasks", "Open Tasks", False),     # Lower is better
            ("overdue_tasks", "Overdue Tasks", False),
            ("stale_tasks_30d", "Stale Tasks", False),
            ("hours_logged_7d", "Weekly Hours", True),      # Higher is better
            ("unread_emails", "Unread Emails", False),
            ("tasks_created_7d", "Tasks Created/Week", None),  # Neutral
            ("tasks_completed_7d", "Tasks Completed/Week", True),
        ]
        
        for attr, name, higher_is_better in metric_configs:
            prev = avg(first_half, attr)
            curr = avg(second_half, attr)
            
            if prev == 0 and curr == 0:
                continue
            
            change_pct = ((curr - prev) / max(abs(prev), 0.1)) * 100
            
            if abs(change_pct) < 5:
                direction = "flat"
            elif curr > prev:
                direction = "up"
            else:
                direction = "down"
            
            if higher_is_better is None:
                is_healthy = True  # Neutral metric
            elif higher_is_better:
                is_healthy = direction in ("up", "flat")
            else:
                is_healthy = direction in ("down", "flat")
            
            points = [
                TrendPoint(date=s.timestamp[:10], value=getattr(s, attr, 0))
                for s in snapshots
            ]
            
            trends.append(Trend(
                metric_name=name,
                current_value=round(curr, 1),
                previous_value=round(prev, 1),
                change_pct=round(change_pct, 1),
                direction=direction,
                is_healthy=is_healthy,
                points=points,
            ))
        
        return trends


# =============================================================================
# SWOT Generator
# =============================================================================

class SWOTGenerator:
    """Generates SWOT analysis from business metrics."""
    
    @staticmethod
    def generate(snap: BusinessSnapshot, trends: List[Trend]) -> Dict[str, List[str]]:
        """Generate SWOT from current snapshot and trends."""
        strengths = []
        weaknesses = []
        opportunities = []
        threats = []
        
        # --- STRENGTHS ---
        if snap.tasks_completed_7d > snap.tasks_created_7d and snap.tasks_completed_7d > 0:
            strengths.append(f"Task velocity is positive: {snap.tasks_completed_7d} completed vs {snap.tasks_created_7d} created this week")
        
        if snap.hours_logged_7d > 30:
            strengths.append(f"Good time tracking discipline: {snap.hours_logged_7d:.0f}h logged this week")
        
        active_clients = len([s for s, c in snap.tasks_by_space.items() if c > 0])
        if active_clients >= 5:
            strengths.append(f"Diversified client base: {active_clients} active clients")
        
        if snap.payment_emails_7d > 0:
            strengths.append(f"Revenue flowing: {snap.payment_emails_7d} payment-related emails this week")
        
        for trend in trends:
            if trend.is_healthy and trend.direction == "up" and trend.metric_name == "Tasks Completed/Week":
                strengths.append(f"Completion rate trending up ({trend.change_pct:+.0f}%)")
            if trend.is_healthy and trend.direction == "down" and trend.metric_name == "Overdue Tasks":
                strengths.append(f"Overdue tasks decreasing ({trend.change_pct:+.0f}%)")
        
        # --- WEAKNESSES ---
        if snap.stale_tasks_30d > snap.total_open_tasks * 0.5:
            pct = snap.stale_tasks_30d * 100 // max(snap.total_open_tasks, 1)
            weaknesses.append(f"Zombie backlog: {pct}% of tasks are stale (30+ days untouched)")
        
        if snap.hours_logged_7d < 20:
            weaknesses.append(f"Low time tracking: only {snap.hours_logged_7d:.0f}h logged this week")
        
        tracked = len(snap.hours_by_project)
        if tracked < active_clients * 0.3 and active_clients > 0:
            weaknesses.append(f"Time tracking gap: {tracked} projects tracked vs {active_clients} active clients")
        
        if snap.unassigned_tasks > 20:
            weaknesses.append(f"{snap.unassigned_tasks} tasks have no owner")
        
        if snap.unread_emails > 100:
            weaknesses.append(f"Email backlog: {snap.unread_emails} unread messages")
        
        if snap.messages_7d == 0:
            weaknesses.append("Team communication is dead (0 Slack messages this week)")
        
        for trend in trends:
            if not trend.is_healthy and abs(trend.change_pct) > 10:
                weaknesses.append(f"{trend.metric_name} trending wrong: {trend.change_pct:+.0f}%")
        
        # --- OPPORTUNITIES ---
        if snap.hours_logged_7d < 20 and active_clients > 5:
            estimated_lost = (40 - snap.hours_logged_7d) * 50  # $50/hr assumption
            opportunities.append(f"Capture untracked work: ~${estimated_lost:.0f}/week in potentially billable hours")
        
        if snap.stale_tasks_30d > 50:
            opportunities.append(f"Backlog cleanup: closing {snap.stale_tasks_30d} stale tasks would dramatically improve visibility")
        
        if snap.messages_7d == 0:
            opportunities.append("Revive team standups to improve coordination and reduce duplicate work")
        
        # Check for clients with lots of open tasks (upsell potential)
        for client, count in snap.tasks_by_space.items():
            if count > 15:
                opportunities.append(f"{client}: {count} open tasks may justify a dedicated sprint or retainer increase")
                break  # Only one
        
        # --- THREATS ---
        if snap.overdue_tasks > 10:
            threats.append(f"{snap.overdue_tasks} overdue tasks risk client dissatisfaction")
        
        if snap.blocked_tasks > 3:
            threats.append(f"{snap.blocked_tasks} blocked tasks may be stalling progress")
        
        # Client concentration risk
        if snap.tasks_by_space:
            top_client = max(snap.tasks_by_space.items(), key=lambda x: x[1])
            total = snap.total_open_tasks or 1
            pct = top_client[1] * 100 / total
            if pct > 30:
                threats.append(f"Client concentration: {top_client[0]} has {pct:.0f}% of all tasks")
        
        team_size = len(snap.team_members) or 4
        if active_clients > team_size * 4:
            threats.append(f"Spread too thin: {active_clients} clients for {team_size} team members")
        
        for trend in trends:
            if not trend.is_healthy and trend.metric_name == "Weekly Hours" and trend.change_pct < -20:
                threats.append(f"Time logged dropping significantly ({trend.change_pct:+.0f}%)")
        
        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "opportunities": opportunities,
            "threats": threats,
        }


# =============================================================================
# Business Advisor (Main Service)
# =============================================================================

class BusinessAdvisor:
    """
    Proactive business intelligence engine.
    
    Monitors all data sources, tracks historical trends, and generates
    actionable advisories.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._cache = DataCache()
        self._collectors = DataCollectors(cache=self._cache)
        self._trend_analyzer = TrendAnalyzer()
        self._swot_generator = SWOTGenerator()
        self._last_snapshot: Optional[BusinessSnapshot] = None
        self._last_snapshot_time: Optional[datetime] = None
        
        # Ensure data directories exist
        SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ADVISORIES_DIR.mkdir(parents=True, exist_ok=True)
    
    def take_snapshot(self, force: bool = False) -> BusinessSnapshot:
        """
        Collect data from all sources and save a snapshot.
        
        Snapshots are rate-limited to once per hour unless force=True.
        """
        # Rate limit
        if not force and self._last_snapshot_time:
            elapsed = (datetime.now() - self._last_snapshot_time).total_seconds()
            if elapsed < 3600:  # 1 hour
                return self._last_snapshot
        
        print("[INFO] Taking business snapshot...")
        snap = BusinessSnapshot()
        
        # Collect ClickUp data
        clickup = self._collectors.collect_clickup(force=force)
        if clickup:
            snap.total_open_tasks = clickup.get("total_open", 0)
            snap.overdue_tasks = clickup.get("overdue", 0)
            snap.stale_tasks_30d = clickup.get("stale_30d", 0)
            snap.unassigned_tasks = clickup.get("unassigned", 0)
            snap.blocked_tasks = clickup.get("blocked", 0)
            snap.tasks_created_7d = clickup.get("created_7d", 0)
            snap.tasks_completed_7d = clickup.get("completed_7d", 0)
            snap.tasks_by_status = dict(clickup.get("by_status", {}))
            snap.tasks_by_space = dict(clickup.get("by_space", {}))
            snap.client_metrics = clickup.get("client_metrics", {})
        
        # Collect Harvest data
        harvest = self._collectors.collect_harvest(force=force)
        if harvest:
            snap.hours_logged_7d = harvest.get("hours_7d", 0)
            snap.hours_logged_30d = harvest.get("hours_30d", 0)
            snap.hours_by_project = harvest.get("by_project", {})
            snap.hours_by_person = harvest.get("by_person", {})
            snap.days_with_time_logged_30d = harvest.get("days_worked_30d", 0)
            snap.avg_hours_per_day = harvest.get("avg_hours_per_day", 0)
        
        # Collect Gmail data
        gmail = self._collectors.collect_gmail(force=force)
        if gmail:
            snap.unread_emails = gmail.get("unread", 0)
            snap.payment_emails_7d = gmail.get("payment_emails_7d", 0)
        
        # Collect Slack data
        slack = self._collectors.collect_slack(force=force)
        if slack:
            snap.active_channels = slack.get("active_channels", 0)
            snap.messages_7d = slack.get("messages_7d", 0)
        
        # Get team members (cached 1 hour)
        snap.team_members = self._collectors.collect_team(force=force)
        
        # Save snapshot
        filename = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".json"
        filepath = SNAPSHOTS_DIR / filename
        with open(filepath, "w") as f:
            json.dump(snap.to_dict(), f, indent=2, default=str)
        
        print(f"[INFO] Snapshot saved: {filepath}")
        
        self._last_snapshot = snap
        self._last_snapshot_time = datetime.now()
        
        return snap
    
    def get_latest_snapshot(self) -> Optional[BusinessSnapshot]:
        """Get the most recent snapshot (from memory or disk)."""
        if self._last_snapshot:
            return self._last_snapshot
        
        # Load from disk
        if SNAPSHOTS_DIR.exists():
            files = sorted(SNAPSHOTS_DIR.glob("*.json"))
            if files:
                with open(files[-1]) as f:
                    data = json.load(f)
                self._last_snapshot = BusinessSnapshot(**{
                    k: v for k, v in data.items()
                    if k in BusinessSnapshot.__dataclass_fields__
                })
                return self._last_snapshot
        
        return None
    
    def get_advisories(self, refresh: bool = False) -> List[Advisory]:
        """
        Get all current advisories.
        
        If refresh=True or no recent snapshot, takes a new snapshot first.
        """
        snap = self.get_latest_snapshot()
        
        if refresh or snap is None:
            snap = self.take_snapshot(force=refresh)
        
        advisories = []
        
        # Run all advisory rules
        rules = [
            AdvisoryRules.check_overdue_crisis,
            AdvisoryRules.check_stale_backlog,
            AdvisoryRules.check_unassigned_tasks,
            AdvisoryRules.check_time_tracking,
            AdvisoryRules.check_email_overload,
            AdvisoryRules.check_communication_health,
            AdvisoryRules.check_task_velocity,
            AdvisoryRules.check_client_health,
            AdvisoryRules.check_wip_overload,
        ]
        
        for rule in rules:
            try:
                advisories.extend(rule(snap))
            except Exception as e:
                print(f"[WARN] Advisory rule {rule.__name__} failed: {e}")
        
        # Sort by severity
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.WARNING: 1,
            Severity.INFO: 2,
            Severity.POSITIVE: 3,
        }
        advisories.sort(key=lambda a: severity_order.get(a.severity, 99))
        
        return advisories
    
    def get_trends(self, days: int = 30) -> List[Trend]:
        """Get trend analysis over the specified period."""
        return self._trend_analyzer.compute_trends(days=days)
    
    def get_health_report(self, refresh: bool = False) -> HealthReport:
        """
        Generate a complete business health report.
        
        Includes: health score, SWOT, KPIs, trends, and advisories.
        """
        snap = self.get_latest_snapshot()
        if refresh or snap is None:
            snap = self.take_snapshot(force=refresh)
        
        advisories = self.get_advisories()
        trends = self.get_trends()
        swot = self._swot_generator.generate(snap, trends)
        
        # Calculate health score (0-100)
        score = 100
        for a in advisories:
            if a.severity == Severity.CRITICAL:
                score -= 15
            elif a.severity == Severity.WARNING:
                score -= 8
        
        # Boost for positive signals
        for a in advisories:
            if a.severity == Severity.POSITIVE:
                score += 5
        
        score = max(0, min(100, score))
        
        # KPIs
        active_clients = len([s for s, c in snap.tasks_by_space.items() if c > 0])
        team_size = len(snap.team_members) or 4
        
        kpis = {
            "health_score": score,
            "open_tasks": snap.total_open_tasks,
            "overdue_tasks": snap.overdue_tasks,
            "stale_pct": round(snap.stale_tasks_30d * 100 / max(snap.total_open_tasks, 1)),
            "hours_this_week": snap.hours_logged_7d,
            "hours_this_month": snap.hours_logged_30d,
            "avg_hours_per_day": snap.avg_hours_per_day,
            "active_clients": active_clients,
            "team_size": team_size,
            "tasks_per_person": round(snap.total_open_tasks / max(team_size, 1)),
            "unread_emails": snap.unread_emails,
            "task_velocity": {
                "created_7d": snap.tasks_created_7d,
                "completed_7d": snap.tasks_completed_7d,
                "net": snap.tasks_completed_7d - snap.tasks_created_7d,
            },
            "unassigned_tasks": snap.unassigned_tasks,
            "blocked_tasks": snap.blocked_tasks,
        }
        
        return HealthReport(
            health_score=score,
            strengths=swot["strengths"],
            weaknesses=swot["weaknesses"],
            opportunities=swot["opportunities"],
            threats=swot["threats"],
            kpis=kpis,
            trends=[t.to_dict() for t in trends],
            advisories=[a.to_dict() for a in advisories],
            snapshot=snap.to_dict(),
        )
    
    @property
    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.stats
    
    def invalidate_cache(self, source: str = None):
        """
        Invalidate cached data.
        
        Args:
            source: Specific source to invalidate (clickup, harvest, gmail, slack, team)
                    or None to invalidate everything.
        """
        self._cache.invalidate(source)
        print(f"[INFO] Cache invalidated: {source or 'all'}")
    
    def format_report_markdown(self, report: HealthReport = None) -> str:
        """Format health report as readable Markdown."""
        if report is None:
            report = self.get_health_report()
        
        score_emoji = "🟢" if report.health_score >= 70 else "🟡" if report.health_score >= 40 else "🔴"
        
        lines = [
            f"# Business Health Report",
            f"**Generated:** {report.generated_at[:19]}",
            f"",
            f"## Overall Health: {score_emoji} {report.health_score}/100",
            f"",
        ]
        
        # KPIs
        kpis = report.kpis
        lines.extend([
            "## Key Performance Indicators",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Open Tasks | {kpis.get('open_tasks', 0)} |",
            f"| Overdue Tasks | {kpis.get('overdue_tasks', 0)} |",
            f"| Stale Backlog | {kpis.get('stale_pct', 0)}% |",
            f"| Hours This Week | {kpis.get('hours_this_week', 0):.1f}h |",
            f"| Hours This Month | {kpis.get('hours_this_month', 0):.1f}h |",
            f"| Active Clients | {kpis.get('active_clients', 0)} |",
            f"| Team Size | {kpis.get('team_size', 0)} |",
            f"| Tasks/Person | {kpis.get('tasks_per_person', 0)} |",
            f"| Unread Emails | {kpis.get('unread_emails', 0)} |",
            f"| Task Velocity | {kpis.get('task_velocity', {}).get('net', 0):+d}/week |",
            "",
        ])
        
        # SWOT
        lines.extend([
            "## SWOT Analysis",
            "",
            "### 💪 Strengths",
        ])
        for s in report.strengths or ["(No strengths identified — more data needed)"]:
            lines.append(f"- {s}")
        
        lines.extend(["", "### 😓 Weaknesses"])
        for w in report.weaknesses or ["(No weaknesses identified)"]:
            lines.append(f"- {w}")
        
        lines.extend(["", "### 🚀 Opportunities"])
        for o in report.opportunities or ["(No opportunities identified)"]:
            lines.append(f"- {o}")
        
        lines.extend(["", "### ⚡ Threats"])
        for t in report.threats or ["(No threats identified)"]:
            lines.append(f"- {t}")
        
        # Advisories
        lines.extend(["", "## Proactive Advisories", ""])
        for a in report.advisories:
            sev = a.get("severity", "info").upper()
            lines.append(f"### [{sev}] {a.get('title', '')}")
            lines.append(f"{a.get('detail', '')}")
            lines.append(f"**Recommendation:** {a.get('recommendation', '')}")
            lines.append("")
        
        # Trends
        if report.trends:
            lines.extend(["## Trends", ""])
            for t in report.trends:
                arrow = "📈" if t["direction"] == "up" else "📉" if t["direction"] == "down" else "➡️"
                health = "✅" if t["is_healthy"] else "⚠️"
                lines.append(f"- {arrow} {health} **{t['metric']}**: {t['current']:.1f} ({t['change_pct']:+.1f}%)")
        
        return "\n".join(lines)


# =============================================================================
# Tool Registration
# =============================================================================

def advisor_take_snapshot() -> Dict[str, Any]:
    """Take a business data snapshot from all sources."""
    advisor = get_advisor()
    snap = advisor.take_snapshot(force=True)
    return {
        "status": "success",
        "timestamp": snap.timestamp,
        "summary": {
            "open_tasks": snap.total_open_tasks,
            "overdue": snap.overdue_tasks,
            "stale": snap.stale_tasks_30d,
            "hours_7d": snap.hours_logged_7d,
            "unread_emails": snap.unread_emails,
        }
    }


def advisor_get_advisories(refresh: bool = False) -> Dict[str, Any]:
    """Get proactive business advisories based on current and historical data."""
    advisor = get_advisor()
    advisories = advisor.get_advisories(refresh=refresh)
    
    by_severity = defaultdict(int)
    for a in advisories:
        by_severity[a.severity.value] += 1
    
    return {
        "total": len(advisories),
        "by_severity": dict(by_severity),
        "advisories": [a.to_dict() for a in advisories],
    }


def advisor_get_health_report(refresh: bool = False) -> Dict[str, Any]:
    """Get complete business health report with SWOT analysis, KPIs, trends, and advisories."""
    advisor = get_advisor()
    report = advisor.get_health_report(refresh=refresh)
    return report.to_dict()


def advisor_get_health_markdown(refresh: bool = False) -> str:
    """Get business health report formatted as Markdown."""
    advisor = get_advisor()
    return advisor.format_report_markdown()


def advisor_get_trends(days: int = 30) -> Dict[str, Any]:
    """Get business metric trends over the specified number of days."""
    advisor = get_advisor()
    trends = advisor.get_trends(days=days)
    
    return {
        "period_days": days,
        "trends_count": len(trends),
        "healthy": sum(1 for t in trends if t.is_healthy),
        "unhealthy": sum(1 for t in trends if not t.is_healthy),
        "trends": [t.to_dict() for t in trends],
    }


# Tools list for registration in tool_registry
ADVISOR_TOOLS = [
    {
        "name": "advisor_take_snapshot",
        "description": "Take a business data snapshot from all sources (ClickUp, Harvest, Gmail, Slack). "
                      "Snapshots are stored for historical trend analysis. Run periodically or on demand.",
        "function": advisor_take_snapshot,
        "parameters": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "advisor_get_advisories",
        "description": "Get proactive business advisories. Analyzes current data and historical trends "
                      "to surface issues before they become problems. Covers: overdue tasks, stale backlog, "
                      "time tracking gaps, client health, communication, and more.",
        "function": advisor_get_advisories,
        "parameters": {
            "type": "object",
            "properties": {
                "refresh": {
                    "type": "boolean",
                    "description": "Force a fresh data collection (default: false, uses last snapshot)"
                }
            },
        }
    },
    {
        "name": "advisor_get_health_report",
        "description": "Get complete business health report including: health score (0-100), SWOT analysis, "
                      "KPIs, metric trends, and proactive advisories. The most comprehensive view of business state.",
        "function": advisor_get_health_report,
        "parameters": {
            "type": "object",
            "properties": {
                "refresh": {
                    "type": "boolean",
                    "description": "Force fresh data collection (default: false)"
                }
            },
        }
    },
    {
        "name": "advisor_get_trends",
        "description": "Get business metric trends over time. Shows whether key metrics (tasks, hours, etc.) "
                      "are improving or declining. Requires at least 2 snapshots for comparison.",
        "function": advisor_get_trends,
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to analyze (default: 30)"
                }
            },
        }
    },
]


# =============================================================================
# Singleton
# =============================================================================

_advisor: Optional[BusinessAdvisor] = None


def get_advisor() -> BusinessAdvisor:
    """Get the global business advisor instance."""
    global _advisor
    if _advisor is None:
        _advisor = BusinessAdvisor()
    return _advisor
