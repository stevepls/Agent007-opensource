"""
Universal Agent Metrics — Token, Time, and Cost Tracking

Used by ALL agents in the Orchestrator. Tracks:
- LLM token usage per call, task, and run
- Wall-clock time per task
- API cost at provider rates
- Billable cost at client rates
- Local persistent time log
- Hubstaff sync when API is available

Usage:
    from services.agent_metrics import AgentMetrics

    metrics = AgentMetrics(agent_name="scaffolding", project_key="phyto")

    with metrics.track_task("PHY-4", "FishPig WordPress integration"):
        response = metrics.llm_call(client, messages=[...], max_tokens=4096)
        # ... do work ...

    metrics.finalize_run()
    # Saves to local log, syncs to Hubstaff, reports to queue
"""

import json
import os
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# Model Pricing (per million tokens)
# ============================================================================

MODEL_PRICING = {
    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-opus": {"input": 15.0, "output": 75.0},
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    # Defaults
    "default": {"input": 3.0, "output": 15.0},
}

# Client billing multiplier (e.g., 2.5x = $1 cost → $2.50 billed)
DEFAULT_BILLING_MULTIPLIER = 2.5

# Billing rates per project (override defaults)
PROJECT_BILLING = {
    # project_key: {"multiplier": 2.5, "hourly_rate": 150.0}
    "phyto": {"multiplier": 2.5, "hourly_rate": 150.0},
    "apdriving": {"multiplier": 2.0, "hourly_rate": 125.0},
    "cysterhood": {"multiplier": 2.0, "hourly_rate": 125.0},
}


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class LLMCall:
    """A single LLM API call."""
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float = field(default_factory=time.time)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        pricing = MODEL_PRICING.get(self.model, MODEL_PRICING["default"])
        return (
            (self.input_tokens / 1_000_000 * pricing["input"])
            + (self.output_tokens / 1_000_000 * pricing["output"])
        )


@dataclass
class TaskEntry:
    """Metrics for a single task."""
    task_id: str
    task_name: str = ""
    agent_name: str = ""
    project_key: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    llm_calls: List[LLMCall] = field(default_factory=list)
    status: str = "running"  # running, completed, blocked, error

    @property
    def wall_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.llm_calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.llm_calls)

    @property
    def total_tokens(self) -> int:
        return sum(c.total_tokens for c in self.llm_calls)

    @property
    def cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.llm_calls)

    @property
    def billable_usd(self) -> float:
        billing = PROJECT_BILLING.get(self.project_key, {})
        multiplier = billing.get("multiplier", DEFAULT_BILLING_MULTIPLIER)
        return self.cost_usd * multiplier

    @property
    def billable_hours(self) -> float:
        """Convert wall time to billable hours (rounded up to nearest 0.25)."""
        hours = self.wall_seconds / 3600
        # Round up to nearest 15 minutes
        import math
        return math.ceil(hours * 4) / 4

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "agent_name": self.agent_name,
            "project_key": self.project_key,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "wall_seconds": round(self.wall_seconds, 1),
            "status": self.status,
            "llm_calls": len(self.llm_calls),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "billable_usd": round(self.billable_usd, 4),
            "billable_hours": self.billable_hours,
        }


@dataclass
class RunSummary:
    """Summary of a complete agent run."""
    agent_name: str
    project_key: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tasks: List[TaskEntry] = field(default_factory=list)
    skipped: int = 0

    @property
    def wall_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def total_tokens(self) -> int:
        return sum(t.total_tokens for t in self.tasks)

    @property
    def total_cost_usd(self) -> float:
        return sum(t.cost_usd for t in self.tasks)

    @property
    def total_billable_usd(self) -> float:
        return sum(t.billable_usd for t in self.tasks)

    @property
    def total_llm_calls(self) -> int:
        return sum(len(t.llm_calls) for t in self.tasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "project_key": self.project_key,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "wall_seconds": round(self.wall_seconds, 1),
            "tasks_processed": len(self.tasks),
            "tasks_skipped": self.skipped,
            "total_llm_calls": self.total_llm_calls,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.total_cost_usd, 6),
            "billable_usd": round(self.total_billable_usd, 4),
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def summary_text(self) -> str:
        lines = [
            f"📊 **{self.agent_name}/{self.project_key}** run complete",
            f"⏱️ {self.wall_seconds:.0f}s | {len(self.tasks)} tasks | {self.skipped} skipped",
            f"🤖 {self.total_llm_calls} LLM calls | {self.total_tokens:,} tokens",
            f"💰 Cost: ${self.total_cost_usd:.4f} | Billable: ${self.total_billable_usd:.4f}",
        ]
        for t in self.tasks:
            lines.append(f"  • [{t.task_id}] {t.task_name[:40]} — {t.wall_seconds:.0f}s, ${t.cost_usd:.4f}")
        return "\n".join(lines)


# ============================================================================
# Universal Agent Metrics
# ============================================================================

LOG_DIR = Path(__file__).parent.parent / "data" / "agent_metrics"


class AgentMetrics:
    """
    Universal metrics tracker for all agents.

    Usage:
        metrics = AgentMetrics("scaffolding", "phyto")

        with metrics.track_task("PHY-4", "FishPig Integration"):
            response = metrics.llm_call(client, messages=[...])

        metrics.finalize_run()
    """

    def __init__(self, agent_name: str, project_key: str):
        self.agent_name = agent_name
        self.project_key = project_key
        self.run = RunSummary(agent_name=agent_name, project_key=project_key)
        self._current_task: Optional[TaskEntry] = None
        self._lock = threading.Lock()

        # Ensure log directory exists
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # Task Context Manager
    # =========================================================================

    @contextmanager
    def track_task(self, task_id: str, task_name: str = ""):
        """Context manager to track a task's metrics."""
        task_entry = TaskEntry(
            task_id=task_id,
            task_name=task_name,
            agent_name=self.agent_name,
            project_key=self.project_key,
        )
        self._current_task = task_entry
        try:
            yield task_entry
            task_entry.status = "completed"
        except Exception as e:
            task_entry.status = "error"
            raise
        finally:
            task_entry.end_time = time.time()
            with self._lock:
                self.run.tasks.append(task_entry)
            self._current_task = None

    def mark_skipped(self):
        """Increment skipped task count."""
        self.run.skipped += 1

    # =========================================================================
    # LLM Call Tracking
    # =========================================================================

    def llm_call(self, client, messages: List[Dict], max_tokens: int = 4096,
                 model: str = "claude-sonnet-4-20250514", **kwargs) -> Any:
        """
        Make an LLM call and automatically track token usage.

        Args:
            client: Anthropic client instance
            messages: Message list
            max_tokens: Max output tokens
            model: Model name
            **kwargs: Additional args passed to client.messages.create

        Returns:
            The API response object
        """
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )

        # Track tokens
        if hasattr(response, "usage"):
            call = LLMCall(
                model=model,
                input_tokens=getattr(response.usage, "input_tokens", 0),
                output_tokens=getattr(response.usage, "output_tokens", 0),
            )
            if self._current_task:
                self._current_task.llm_calls.append(call)

        return response

    def record_llm_usage(self, model: str, input_tokens: int, output_tokens: int):
        """Manually record LLM usage (for non-standard API calls)."""
        call = LLMCall(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
        if self._current_task:
            self._current_task.llm_calls.append(call)

    # =========================================================================
    # Run Finalization
    # =========================================================================

    def finalize_run(self):
        """
        Finalize the run: save local log, sync to Hubstaff, report to queue.
        """
        self.run.end_time = time.time()

        # 1. Save to local log
        self._save_local_log()

        # 2. Sync to Hubstaff if available
        self._sync_hubstaff()

        # 3. Report to orchestrator queue
        self._report_to_queue()

    # =========================================================================
    # Local Time Log
    # =========================================================================

    def _save_local_log(self):
        """Append run data to persistent local log file."""
        log_file = LOG_DIR / f"{self.project_key}.jsonl"
        try:
            entry = self.run.to_dict()
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[AgentMetrics] Failed to save local log: {e}")

    @staticmethod
    def get_local_log(project_key: str, days: int = 30) -> List[Dict]:
        """Read local log entries for a project (last N days)."""
        log_file = LOG_DIR / f"{project_key}.jsonl"
        if not log_file.exists():
            return []

        cutoff = time.time() - (days * 86400)
        entries = []
        try:
            with open(log_file) as f:
                for line in f:
                    if line.strip():
                        entry = json.loads(line)
                        # Filter by date
                        start = entry.get("start_time", "")
                        if start:
                            entry_time = datetime.fromisoformat(start).timestamp()
                            if entry_time >= cutoff:
                                entries.append(entry)
        except Exception as e:
            print(f"[AgentMetrics] Failed to read local log: {e}")
        return entries

    @staticmethod
    def get_billing_summary(project_key: str, days: int = 30) -> Dict[str, Any]:
        """Get billing summary for a project."""
        entries = AgentMetrics.get_local_log(project_key, days)

        total_cost = sum(e.get("cost_usd", 0) for e in entries)
        total_billable = sum(e.get("billable_usd", 0) for e in entries)
        total_tokens = sum(e.get("total_tokens", 0) for e in entries)
        total_tasks = sum(e.get("tasks_processed", 0) for e in entries)
        total_wall = sum(e.get("wall_seconds", 0) for e in entries)

        billing = PROJECT_BILLING.get(project_key, {})

        return {
            "project_key": project_key,
            "period_days": days,
            "runs": len(entries),
            "tasks_processed": total_tasks,
            "total_tokens": total_tokens,
            "cost_usd": round(total_cost, 4),
            "billable_usd": round(total_billable, 4),
            "multiplier": billing.get("multiplier", DEFAULT_BILLING_MULTIPLIER),
            "hourly_rate": billing.get("hourly_rate", 0),
            "total_wall_hours": round(total_wall / 3600, 2),
        }

    # =========================================================================
    # Hubstaff Sync
    # =========================================================================

    def _sync_hubstaff(self):
        """Sync time entries to Hubstaff if available."""
        try:
            hubstaff_token = os.getenv("HUBSTAFF_API_TOKEN")
            if not hubstaff_token:
                return  # Hubstaff not configured, skip silently

            user_id = os.getenv("HUBSTAFF_USER_ID")
            if not user_id:
                return

            from services.hubstaff.client import HubstaffClient
            client = HubstaffClient()

            for task in self.run.tasks:
                if task.wall_seconds < 60:
                    continue  # Skip tasks under 1 minute

                note = (
                    f"[{self.agent_name}] [{task.task_id}] {task.task_name[:60]} "
                    f"| {task.total_tokens:,} tokens ${task.cost_usd:.4f}"
                )

                try:
                    # Check for existing entry with same note (dedup)
                    existing = client.get_active_time_entries(user_id=int(user_id))
                    already_logged = any(
                        task.task_id in (e.note or "") for e in existing
                    )
                    if already_logged:
                        continue

                    entry = client.start_time_entry(
                        user_id=int(user_id),
                        note=note,
                    )
                    if entry:
                        # Immediately stop it (log as completed work)
                        import time as _time
                        _time.sleep(1)
                        client.stop_user_active_entries(int(user_id))

                except Exception as e:
                    print(f"[AgentMetrics] Hubstaff sync failed for {task.task_id}: {e}")

        except ImportError:
            pass  # Hubstaff client not available
        except Exception as e:
            print(f"[AgentMetrics] Hubstaff sync error: {e}")

    # =========================================================================
    # Orchestrator Queue
    # =========================================================================

    def _report_to_queue(self):
        """Report run summary to orchestrator update queue (with dedup)."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from services.task_queue import get_task_queue, BackgroundTask

            queue = get_task_queue()

            # Dedup: skip if same agent+project reported <5 min ago
            report_key = f"{self.agent_name}:{self.project_key}"
            for tid in list(queue._task_order)[-10:]:
                existing = queue._tasks.get(tid)
                if existing and existing.user_request == report_key:
                    if existing.created_at > time.time() - 300:
                        return  # Skip duplicate

            task = BackgroundTask(
                id=f"{self.agent_name}-{self.project_key}-{int(time.time())}",
                user_request=report_key,
                context=None,
                session_id=f"agent-{self.agent_name}-{self.project_key}",
                status="completed",
                result=json.dumps(self.run.to_dict()),
                created_at=time.time(),
                completed_at=time.time(),
                reported=False,
            )

            with queue._lock:
                queue._tasks[task.id] = task
                queue._task_order.append(task.id)

        except Exception as e:
            print(f"[AgentMetrics] Queue report failed: {e}")
