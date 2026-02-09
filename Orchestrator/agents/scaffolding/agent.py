"""
Project Task Scaffolding Agent

SME agent triggered every 15 minutes per project. Only one instance runs per project.

Responsibilities:
1. Pull tasks in "Pending AI Scaffolding" status from ClickUp
2. Review ticket description, comments, deadlines, urgency
3. Create branch from main with proper naming convention
4. Do the scaffolding work in the branch
5. Push branch to GitHub
6. Comment on the ClickUp ticket with branch link
7. Move ticket to "to do" when scaffolding is complete
"""

import os
import re
import json
import logging
import subprocess
import sys
import fcntl
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

# Add parent paths
AGENT_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = AGENT_ROOT.parent.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

# Load environment
from dotenv import load_dotenv
load_dotenv(ORCHESTRATOR_ROOT / ".env")

from services.tickets.clickup_client import ClickUpClient, ClickUpTask, get_clickup_client
from services.github.client import GitHubClient, get_github_client
from .config import PROJECT_CONFIGS, BRANCH_PREFIXES, DEFAULT_PREFIX, LOCK_DIR

# Hubstaff (optional)
try:
    from services.hubstaff.client import HubstaffClient
    HUBSTAFF_AVAILABLE = True
except ImportError:
    HUBSTAFF_AVAILABLE = False
    HubstaffClient = None

logger = logging.getLogger("scaffolding_agent")


@dataclass
class ScaffoldingConfig:
    """Configuration for a scaffolding run."""
    project_key: str
    clickup_list_id: str
    github_repo: str
    github_ssh_url: str
    local_path: str
    default_branch: str = "main"
    status_pending: str = "pending ai scaffolding"
    status_done: str = "to do"
    stack: List[str] = field(default_factory=list)
    hubstaff_project_id: Optional[int] = None
    hubstaff_user_id: Optional[int] = None

    @classmethod
    def from_project_key(cls, project_key: str) -> "ScaffoldingConfig":
        """Create config from a project key."""
        cfg = PROJECT_CONFIGS.get(project_key)
        if not cfg:
            raise ValueError(f"Unknown project: {project_key}. Available: {list(PROJECT_CONFIGS.keys())}")
        return cls(
            project_key=project_key,
            clickup_list_id=cfg["clickup_list_id"],
            github_repo=cfg["github_repo"],
            github_ssh_url=cfg["github_ssh_url"],
            local_path=cfg["local_path"],
            default_branch=cfg.get("default_branch", "main"),
            status_pending=cfg.get("status_pending", "pending ai scaffolding"),
            status_done=cfg.get("status_done", "to do"),
            stack=cfg.get("stack", []),
            hubstaff_project_id=cfg.get("hubstaff_project_id"),
            hubstaff_user_id=cfg.get("hubstaff_user_id"),
        )


@dataclass
class TaskMetrics:
    """Metrics for a single task."""
    task_id: str
    task_name: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    sandbox_seconds: float = 0
    files_changed: int = 0
    commits: int = 0

    @property
    def wall_seconds(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0

    @property
    def cost_usd(self) -> float:
        # Claude Sonnet pricing
        return (self.input_tokens / 1_000_000 * 3.0) + (self.output_tokens / 1_000_000 * 15.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "wall_seconds": round(self.wall_seconds, 1),
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 4),
            "sandbox_seconds": round(self.sandbox_seconds, 1),
            "files_changed": self.files_changed,
            "commits": self.commits,
        }


@dataclass
class RunMetrics:
    """Metrics for a complete agent run."""
    project_key: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    tasks: List[TaskMetrics] = field(default_factory=list)
    skipped_tasks: int = 0

    @property
    def wall_seconds(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def total_tokens(self) -> int:
        return sum(t.input_tokens + t.output_tokens for t in self.tasks)

    @property
    def total_cost_usd(self) -> float:
        return sum(t.cost_usd for t in self.tasks)

    @property
    def total_llm_calls(self) -> int:
        return sum(t.llm_calls for t in self.tasks)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"📊 **Scaffolding Run: {self.project_key}**",
            f"Duration: {self.wall_seconds:.0f}s",
            f"Tasks: {len(self.tasks)} processed, {self.skipped_tasks} skipped",
            f"LLM: {self.total_llm_calls} calls, {self.total_tokens:,} tokens, ${self.total_cost_usd:.4f}",
        ]
        for t in self.tasks:
            lines.append(f"  • {t.task_name[:50]} — {t.wall_seconds:.0f}s, ${t.cost_usd:.4f}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_key": self.project_key,
            "wall_seconds": round(self.wall_seconds, 1),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_llm_calls": self.total_llm_calls,
            "tasks_processed": len(self.tasks),
            "tasks_skipped": self.skipped_tasks,
            "tasks": [t.to_dict() for t in self.tasks],
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class TaskResult:
    """Result of processing a single task."""
    task_id: str
    task_name: str
    status: str  # "completed", "blocked", "error", "skipped"
    branch_name: Optional[str] = None
    branch_url: Optional[str] = None
    pr_url: Optional[str] = None
    comment: str = ""
    error: Optional[str] = None


class ScaffoldingAgent:
    """
    Project Task Scaffolding Agent.

    Acts as an SME for a specific project. Pulls tasks from ClickUp
    in "Pending AI Scaffolding" status, creates branches, does the work,
    and updates the tickets.
    """

    def __init__(self, config: ScaffoldingConfig):
        self.config = config
        self._clickup: Optional[ClickUpClient] = None
        self._github: Optional[GitHubClient] = None
        self._llm_client = None
        self._sandbox_runner = None
        self.results: List[TaskResult] = []
        self.run_metrics: Optional[RunMetrics] = None
        self._current_task_metrics: Optional[TaskMetrics] = None

        # Universal metrics tracker
        try:
            from services.agent_metrics import AgentMetrics
            self.metrics = AgentMetrics(agent_name="scaffolding", project_key=config.project_key)
        except ImportError:
            self.metrics = None

        # State file to track last run timestamps
        self.state_file = Path(__file__).parent / "state" / f"{config.project_key}.json"
        self.state_file.parent.mkdir(exist_ok=True)

        # Setup logging
        self.logger = logging.getLogger(f"scaffolding.{config.project_key}")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def clickup(self) -> ClickUpClient:
        if self._clickup is None:
            self._clickup = get_clickup_client()
        return self._clickup

    @property
    def github(self) -> GitHubClient:
        if self._github is None:
            self._github = get_github_client(self.config.local_path)
        return self._github

    @property
    def llm(self):
        """Lazy-load Anthropic client for LLM calls."""
        if self._llm_client is None:
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self._llm_client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                self.logger.warning("anthropic not installed, LLM features disabled")
        return self._llm_client

    @property
    def sandbox(self):
        """Lazy-load the sandbox runner. Prefers local Docker, falls back to GHA."""
        if self._sandbox_runner is None:
            try:
                from agents.scaffolding.sandbox import LocalDockerRunner, GitHubActionsRunner
                # Check env for runner preference
                runner_type = os.getenv("SANDBOX_RUNNER", "local")
                if runner_type == "github":
                    github_repo = self.config.github_repo
                    if github_repo:
                        runner = GitHubActionsRunner(repo=github_repo)
                        if runner.is_available():
                            self._sandbox_runner = runner
                            self.logger.info("Sandbox: GitHub Actions runner")
                            return self._sandbox_runner
                    self.logger.warning("GHA runner not available, falling back to local")

                runner = LocalDockerRunner()
                if runner.is_available():
                    self._sandbox_runner = runner
                    self.logger.info("Sandbox: Local Docker runner")
                else:
                    self.logger.warning("Docker not available — sandbox disabled")
            except ImportError as e:
                self.logger.warning(f"Sandbox import failed: {e}")
        return self._sandbox_runner

    @property
    def hubstaff(self) -> Optional["HubstaffClient"]:
        """Lazy-load Hubstaff client."""
        if not hasattr(self, "_hubstaff"):
            self._hubstaff = None
            if HUBSTAFF_AVAILABLE and os.getenv("HUBSTAFF_API_TOKEN"):
                try:
                    self._hubstaff = HubstaffClient()
                    self.logger.info("Hubstaff time tracking enabled")
                except Exception as e:
                    self.logger.warning(f"Hubstaff init failed: {e}")
        return self._hubstaff

    # =========================================================================
    # Hubstaff Time Tracking
    # =========================================================================

    def _start_time_tracking(self, task: ClickUpTask) -> Optional[int]:
        """Start Hubstaff time entry for a task. Returns entry ID or None."""
        if not self.hubstaff:
            return None

        user_id = self.config.hubstaff_user_id
        if not user_id:
            # Try to get from env
            user_id = os.getenv("HUBSTAFF_USER_ID")
            if user_id:
                user_id = int(user_id)

        if not user_id:
            self.logger.debug("No Hubstaff user_id configured, skipping time tracking")
            return None

        custom_id = self.get_custom_task_id(task)
        note = f"[{custom_id}] {task.name[:80]}"

        try:
            entry = self.hubstaff.start_time_entry(
                user_id=user_id,
                project_id=self.config.hubstaff_project_id,
                note=note,
            )
            if entry:
                self.logger.info(f"  ⏱️  Time tracking started: {note}")
                return entry.id
        except Exception as e:
            self.logger.warning(f"Failed to start Hubstaff timer: {e}")

        return None

    def _stop_time_tracking(self, entry_id: int):
        """Stop a Hubstaff time entry."""
        if not self.hubstaff or not entry_id:
            return

        try:
            self.hubstaff.stop_time_entry(entry_id)
            self.logger.info("  ⏱️  Time tracking stopped")
        except Exception as e:
            self.logger.warning(f"Failed to stop Hubstaff timer: {e}")

    # =========================================================================
    # Locking (one instance per project)
    # =========================================================================

    def _get_lock_path(self) -> Path:
        """Get lock file path for this project."""
        os.makedirs(LOCK_DIR, exist_ok=True)
        return Path(LOCK_DIR) / f"{self.config.project_key}.lock"

    def _acquire_lock(self) -> Optional[int]:
        """Acquire project lock. Returns file descriptor or None."""
        lock_path = self._get_lock_path()
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Write PID
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())
            return fd
        except (OSError, BlockingIOError):
            self.logger.info(f"Another instance already running for {self.config.project_key}")
            return None

    def _release_lock(self, fd: int):
        """Release project lock."""
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            lock_path = self._get_lock_path()
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass

    # =========================================================================
    # ClickUp Operations
    # =========================================================================

    def fetch_pending_tasks(self, skip_unchanged: bool = True) -> List[ClickUpTask]:
        """
        Fetch tasks in 'Pending AI Scaffolding' status.
        
        If skip_unchanged=True, only returns tasks that were updated
        since we last interacted with them.
        """
        self.logger.info(f"Fetching tasks with status: '{self.config.status_pending}'")
        
        # Fetch all open tasks and filter by status in code
        # (ClickUp API status filter can be unreliable with spaces/encoding)
        all_tasks = self.clickup.list_tasks(
            list_id=self.config.clickup_list_id,
            include_closed=False,
        )
        tasks = [
            t for t in all_tasks
            if t.status.lower().strip() == self.config.status_pending.lower().strip()
        ]
        
        if skip_unchanged:
            # Filter to only tasks that changed since we last touched them
            fresh_tasks = [t for t in tasks if self._was_task_updated_since_last_touch(t)]
            self.logger.info(
                f"Found {len(fresh_tasks)} fresh task(s) (out of {len(tasks)} pending, {len(all_tasks)} open)"
            )
            return fresh_tasks
        else:
            self.logger.info(f"Found {len(tasks)} pending task(s) (out of {len(all_tasks)} open)")
            return tasks

    def get_task_details(self, task: ClickUpTask) -> Dict[str, Any]:
        """Get full task details including comments."""
        details = {
            "id": task.id,
            "name": task.name,
            "description": task.description or "",
            "status": task.status,
            "priority": task.priority_name,
            "assignees": task.assignees,
            "tags": task.tags,
            "due_date": task.date_due.isoformat() if task.date_due else None,
            "url": task.url,
            "custom_fields": task.custom_fields,
        }

        # Fetch comments
        comments = self.clickup.get_comments(task.id)
        details["comments"] = [
            {"user": c.user, "text": c.text, "date": c.date.isoformat()}
            for c in comments
        ]

        return details

    def update_task_status(self, task_id: str, status: str) -> bool:
        """Update task status."""
        result = self.clickup.update_task(task_id, status=status)
        return result is not None

    def add_task_comment(self, task_id: str, comment: str) -> bool:
        """Add a comment to a task."""
        return self.clickup.add_comment(task_id, comment)

    # =========================================================================
    # Branch Naming
    # =========================================================================

    def determine_branch_prefix(self, task: ClickUpTask) -> str:
        """Determine branch prefix from task name/description."""
        text = f"{task.name} {task.description or ''}".lower()
        for keyword, prefix in BRANCH_PREFIXES.items():
            if keyword in text:
                return prefix
        return DEFAULT_PREFIX

    def get_custom_task_id(self, task: ClickUpTask) -> str:
        """Get custom task ID (e.g. PHY-6) from custom fields, fallback to internal ID."""
        # Check custom_fields dict (populated by ClickUpTask.from_dict)
        for field_name, value in task.custom_fields.items():
            if "task id" in field_name.lower().strip() and value:
                # Skip malformed values (duplicated IDs, etc.)
                if isinstance(value, str) and len(value) < 30:
                    return value
        return task.id

    def generate_branch_name(self, task: ClickUpTask) -> str:
        """Generate branch name: prefix/custom-task-id (e.g. bugfix/PHY-6)."""
        prefix = self.determine_branch_prefix(task)
        ticket_id = self.get_custom_task_id(task)
        return f"{prefix}/{ticket_id}"

    # =========================================================================
    # Git/Branch Operations
    # =========================================================================

    def _run_git(self, args: List[str], cwd: str = None, timeout: int = 300) -> Tuple[int, str, str]:
        """Run a git command in the project directory."""
        cmd = ["git"] + args
        work_dir = cwd or self.config.local_path

        try:
            result = subprocess.run(
                cmd, cwd=work_dir,
                capture_output=True, text=True, timeout=timeout,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def _run_gh(self, args: List[str], cwd: str = None) -> Tuple[int, str, str]:
        """Run a gh CLI command."""
        cmd = ["gh"] + args
        work_dir = cwd or self.config.local_path

        try:
            result = subprocess.run(
                cmd, cwd=work_dir,
                capture_output=True, text=True, timeout=60,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def ensure_repo_ready(self) -> bool:
        """Ensure local repo exists and is up to date."""
        local_path = Path(self.config.local_path)

        if not local_path.exists():
            self.logger.info(f"Cloning repository to {local_path}")
            parent = local_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            code, _, err = self._run_git(
                ["clone", "--depth", "1", "--no-single-branch",
                 self.config.github_ssh_url, str(local_path)],
                cwd=str(parent),
                timeout=600,
            )
            if code != 0:
                self.logger.error(f"Clone failed: {err}")
                return False
            # Unshallow so we have full history for branching
            self._run_git(["fetch", "--unshallow"], timeout=600)

        # Fetch latest
        self.logger.info("Fetching latest from remote...")
        code, _, err = self._run_git(["fetch", "origin", "--prune"], timeout=600)
        if code != 0:
            self.logger.warning(f"Fetch warning: {err}")

        # Ensure we're on the default branch and up to date
        code, _, _ = self._run_git(["checkout", self.config.default_branch])
        if code != 0:
            # Try common alternatives
            for alt in ["master", "main", "production"]:
                code, _, _ = self._run_git(["checkout", alt])
                if code == 0:
                    self.logger.info(f"Using branch '{alt}' as default")
                    self.config.default_branch = alt
                    break
            else:
                self.logger.warning(f"Could not checkout any default branch")
        code, _, _ = self._run_git(["pull", "origin", self.config.default_branch], timeout=600)

        return True

    def branch_exists(self, branch_name: str) -> Tuple[bool, bool]:
        """Check if branch exists locally and/or remotely. Returns (local, remote)."""
        _, local_out, _ = self._run_git(["branch", "--list", branch_name])
        local_exists = bool(local_out.strip())

        _, remote_out, _ = self._run_git(["ls-remote", "--heads", "origin", branch_name])
        remote_exists = bool(remote_out.strip())

        return local_exists, remote_exists

    def get_branch_diff_summary(self, branch_name: str) -> str:
        """Get a summary of changes on a branch vs main."""
        code, out, _ = self._run_git([
            "log", f"origin/{self.config.default_branch}..origin/{branch_name}",
            "--oneline", "--no-decorate",
        ])
        return out if code == 0 else ""

    def create_branch(self, branch_name: str, task: ClickUpTask) -> Tuple[bool, str]:
        """
        Create a branch for a task. Handles existing branches intelligently.

        Returns (success, message).
        """
        local_exists, remote_exists = self.branch_exists(branch_name)

        if remote_exists:
            # Branch exists on remote - check if it covers the issue
            diff_summary = self.get_branch_diff_summary(branch_name)
            if diff_summary:
                # Analyze if existing branch addresses the task
                analysis = self._analyze_existing_branch(branch_name, diff_summary, task)
                if analysis == "covers":
                    msg = f"Branch `{branch_name}` already exists and appears to address this issue."
                    self.logger.info(msg)
                    return True, msg
                elif analysis == "partial":
                    # Create versioned alternative
                    alt_branch = f"{branch_name}-v2"
                    _, alt_remote = self.branch_exists(alt_branch)
                    v = 2
                    while alt_remote:
                        v += 1
                        alt_branch = f"{branch_name}-v{v}"
                        _, alt_remote = self.branch_exists(alt_branch)

                    self.logger.info(f"Creating alternative branch: {alt_branch}")
                    code, _, err = self._run_git(["checkout", "-b", alt_branch, f"origin/{self.config.default_branch}"])
                    if code != 0:
                        return False, f"Failed to create branch {alt_branch}: {err}"
                    return True, f"Created {alt_branch} (existing branch partially addresses issue)"
                else:
                    # Unrelated changes - create versioned alternative
                    alt_branch = f"{branch_name}-v2"
                    _, alt_remote = self.branch_exists(alt_branch)
                    v = 2
                    while alt_remote:
                        v += 1
                        alt_branch = f"{branch_name}-v{v}"
                        _, alt_remote = self.branch_exists(alt_branch)

                    self.logger.info(f"Existing branch has unrelated changes, creating: {alt_branch}")
                    code, _, err = self._run_git(["checkout", "-b", alt_branch, f"origin/{self.config.default_branch}"])
                    if code != 0:
                        return False, f"Failed to create branch {alt_branch}: {err}"
                    return True, f"Created {alt_branch} (existing branch has unrelated changes)"
            else:
                # Branch exists but is empty/same as main
                self.logger.info(f"Branch {branch_name} exists but has no changes, reusing")
                code, _, _ = self._run_git(["checkout", branch_name])
                code2, _, _ = self._run_git(["pull", "origin", branch_name])
                return True, f"Reusing existing branch {branch_name}"

        # Create fresh branch from default branch
        self.logger.info(f"Creating new branch: {branch_name}")
        code, _, err = self._run_git(["checkout", "-b", branch_name, f"origin/{self.config.default_branch}"])
        if code != 0:
            return False, f"Failed to create branch: {err}"
        return True, f"Created new branch {branch_name}"

    def _analyze_existing_branch(self, branch_name: str, diff_summary: str, task: ClickUpTask) -> str:
        """Analyze if existing branch addresses the task. Returns 'covers', 'partial', or 'unrelated'."""
        if not self.llm:
            # Without LLM, assume unrelated for safety
            return "unrelated"

        try:
            response = self._llm_call(
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze if this existing branch addresses the task.

TASK: {task.name}
DESCRIPTION: {(task.description or '')[:500]}

BRANCH: {branch_name}
COMMITS:
{diff_summary[:1000]}

Reply with exactly one word: "covers" (fully addresses), "partial" (partially addresses), or "unrelated" (different work)."""
                }],
            )
            result = response.content[0].text.strip().lower()
            if result in ("covers", "partial", "unrelated"):
                return result
        except Exception as e:
            self.logger.warning(f"LLM analysis failed: {e}")

        return "unrelated"

    def push_branch(self, branch_name: str) -> bool:
        """Push branch to remote."""
        code, _, err = self._run_git(["push", "-u", "origin", branch_name])
        if code != 0:
            self.logger.error(f"Push failed: {err}")
            return False
        return True

    def get_branch_url(self, branch_name: str) -> str:
        """Get GitHub URL for a branch."""
        return f"https://github.com/{self.config.github_repo}/tree/{branch_name}"

    # =========================================================================
    # Task Analysis (LLM-powered)
    # =========================================================================

    def analyze_task(self, task_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a task using LLM to understand:
        - What needs to be done
        - Urgency / impact assessment
        - Whether it's blocked
        - Files likely to be modified
        """
        if not self.llm:
            return {
                "summary": task_details["name"],
                "action_items": ["Review task manually"],
                "urgency": "normal",
                "blocked": False,
                "blocked_reason": None,
                "files_to_modify": [],
            }

        task_text = json.dumps(task_details, indent=2, default=str)
        stack_info = ", ".join(self.config.stack)

        try:
            response = self._llm_call(
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze this ClickUp task for a {stack_info} project.

TASK:
{task_text[:3000]}

IMPORTANT: Ignore any comments about git errors, branch issues, or repository problems. Those are handled separately and are NOT blockers. Only set blocked=true for actual dependency or requirements issues (e.g. missing API keys, waiting on client response, needs design approval).

Respond in JSON:
{{
    "summary": "one-line summary of what needs to be done",
    "action_items": ["list", "of", "specific", "actions"],
    "urgency": "critical|high|normal|low",
    "blocked": false,
    "blocked_reason": null,
    "files_to_modify": ["list/of/likely/files"],
    "branch_prefix": "bugfix|feature|update|upgrade|hotfix|project"
}}"""
                }],
            )
            text = response.content[0].text.strip()
            # Extract JSON from response
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text)
        except Exception as e:
            self.logger.warning(f"Task analysis failed: {e}")
            return {
                "summary": task_details["name"],
                "action_items": ["Review task manually"],
                "urgency": "normal",
                "blocked": False,
                "blocked_reason": None,
                "files_to_modify": [],
            }

    # =========================================================================
    # Metrics Finalization
    # =========================================================================

    def _finalize_task_metrics(self, work_result: Optional[Dict] = None):
        """Finalize current task metrics and add to run metrics."""
        if not self._current_task_metrics:
            return
        self._current_task_metrics.end_time = time.time()
        if work_result:
            self._current_task_metrics.files_changed = len(work_result.get("files_changed", []))
            self._current_task_metrics.commits = work_result.get("commits", 0)
            sandbox = work_result.get("sandbox_result")
            if sandbox and hasattr(sandbox, "commands"):
                self._current_task_metrics.sandbox_seconds = sum(
                    c.duration_seconds for c in sandbox.commands
                )
        if self.run_metrics:
            self.run_metrics.tasks.append(self._current_task_metrics)
        # Log summary
        m = self._current_task_metrics
        self.logger.info(
            f"  📊 Task metrics: {m.wall_seconds:.0f}s wall, "
            f"{m.llm_calls} LLM calls, {m.input_tokens + m.output_tokens:,} tokens, "
            f"${m.cost_usd:.4f}"
        )

    # =========================================================================
    # LLM Call with Token Tracking
    # =========================================================================

    def _llm_call(self, messages: List[Dict], max_tokens: int = 4096, model: str = "claude-sonnet-4-20250514") -> Any:
        """
        Make an LLM call and track token usage in current task metrics + universal metrics.
        Returns the response object.
        """
        # Use universal metrics if available (tracks to both local + universal)
        if self.metrics and self.metrics._current_task:
            response = self.metrics.llm_call(self.llm, messages=messages, max_tokens=max_tokens, model=model)
        else:
            response = self.llm.messages.create(model=model, max_tokens=max_tokens, messages=messages)

        # Also track in local task metrics (for backward compat)
        if self._current_task_metrics and hasattr(response, "usage"):
            self._current_task_metrics.llm_calls += 1
            self._current_task_metrics.input_tokens += getattr(response.usage, "input_tokens", 0)
            self._current_task_metrics.output_tokens += getattr(response.usage, "output_tokens", 0)
        return response

    # =========================================================================
    # Queue Reporting
    # =========================================================================

    def _report_to_queue(self, metrics: RunMetrics):
        """
        Submit run summary to the orchestrator update queue.
        Deduplicates by checking for recent identical reports.
        """
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from services.task_queue import get_task_queue
            from services.task_queue import BackgroundTask

            queue = get_task_queue()

            # Check for duplicate — don't re-submit if same project reported <5 min ago
            for tid in list(queue._task_order)[-10:]:  # Check last 10 tasks
                existing = queue._tasks.get(tid)
                if existing and existing.user_request.startswith(f"scaffolding:{metrics.project_key}"):
                    if existing.created_at > time.time() - 300:
                        self.logger.debug("Skipping queue update (duplicate <5 min)")
                        return

            # Build summary result
            summary = metrics.summary()
            result_json = json.dumps(metrics.to_dict())

            task = BackgroundTask(
                id=f"scaffolding-{metrics.project_key}-{int(time.time())}",
                user_request=f"scaffolding:{metrics.project_key}",
                context=None,
                session_id=f"agent-scaffolding-{metrics.project_key}",
                status="completed",
                result=result_json,
                created_at=time.time(),
                completed_at=time.time(),
                reported=False,
            )

            with queue._lock:
                queue._tasks[task.id] = task
                queue._task_order.append(task.id)

            self.logger.info(f"Reported run to orchestrator queue: {task.id}")

        except Exception as e:
            self.logger.warning(f"Failed to report to queue: {e}")

    # =========================================================================
    # State Management
    # =========================================================================

    def _load_state(self) -> Dict[str, Any]:
        """Load the agent's state from disk."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception as e:
                self.logger.warning(f"Failed to load state: {e}")
        return {
            "last_run": None,
            "last_list_check": None,
            "task_timestamps": {},  # task_id -> last_processed_timestamp
        }

    def _save_state(self, state: Dict[str, Any]):
        """Save the agent's state to disk."""
        try:
            state["last_run"] = datetime.now().isoformat()
            self.state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            self.logger.warning(f"Failed to save state: {e}")

    def _has_list_changed(self) -> bool:
        """
        Check if the ClickUp list has any updates since our last check.
        
        Fetches the most recent task from the list and compares its date_updated
        to our last_list_check timestamp. If no tasks are newer, we can skip.
        """
        state = self._load_state()
        last_check = state.get("last_list_check")
        
        if not last_check:
            # First run, process everything
            return True
        
        try:
            last_check_dt = datetime.fromisoformat(last_check)
            
            # Get recent tasks from the list
            all_tasks = self.clickup.list_tasks(
                list_id=self.config.clickup_list_id,
                include_closed=False,
            )
            
            # Sort by date_updated, most recent first
            tasks = sorted(all_tasks, key=lambda t: t.date_updated, reverse=True)
            
            # If any task was updated after our last check, process
            for task in tasks[:10]:  # Check up to 10 most recent
                if task.date_updated > last_check_dt:
                    self.logger.info(f"  List has updates (task {task.id} updated {task.date_updated})")
                    return True
            
            self.logger.info(f"  No updates since {last_check_dt.strftime('%Y-%m-%d %H:%M')}")
            return False
            
        except Exception as e:
            self.logger.warning(f"Failed to check list changes: {e}")
            # On error, process anyway (fail open)
            return True

    def _was_task_updated_since_last_touch(self, task: ClickUpTask) -> bool:
        """
        Check if this task was updated since we last interacted with it.
        
        Compares task.date_updated to:
        1. Our last comment timestamp on this task
        2. The task_timestamps cache in state
        
        Returns True if the task is "fresh" and should be processed.
        """
        state = self._load_state()
        
        # Check our own comments on this task
        try:
            comments = self.clickup.get_comments(task.id)
            our_comments = [c for c in comments if "ScaffoldingAgent" in c.text or "Scaffolding" in c.text]
            
            if our_comments:
                latest_our_comment = max(our_comments, key=lambda c: c.date)
                # If task wasn't updated since our last comment, skip it
                if task.date_updated <= latest_our_comment.date:
                    self.logger.info(f"  Task {task.id} not updated since our last comment ({latest_our_comment.date}), skipping")
                    return False
        except Exception as e:
            self.logger.warning(f"Failed to check task comments: {e}")
        
        # Also check cached timestamp
        cached_ts = state.get("task_timestamps", {}).get(task.id)
        if cached_ts:
            try:
                cached_dt = datetime.fromisoformat(cached_ts)
                if task.date_updated <= cached_dt:
                    self.logger.info(f"  Task {task.id} not updated since {cached_dt}, skipping")
                    return False
            except Exception:
                pass
        
        # Task is fresh, process it
        return True

    def _mark_task_processed(self, task_id: str):
        """Mark a task as processed in the state cache."""
        state = self._load_state()
        if "task_timestamps" not in state:
            state["task_timestamps"] = {}
        state["task_timestamps"][task_id] = datetime.now().isoformat()
        self._save_state(state)

    # =========================================================================
    # Comment Deduplication
    # =========================================================================

    def _was_recently_blocked(self, task_id: str) -> bool:
        """
        Check if this task's MOST RECENT agent interaction was a blocking comment.
        
        Only returns True if:
        - The most recent agent comment is a "Scaffolding Blocked" message
        - AND it was posted within the last 48 hours
        
        If the most recent comment is "Scaffolding complete", we proceed
        (user may have fixed the blocker and moved it back to pending).
        """
        from datetime import datetime, timedelta
        
        try:
            comments = self.clickup.get_comments(task_id)
            recent_cutoff = datetime.now() - timedelta(hours=48)
            
            # Find the most recent agent comment
            agent_comments = [
                c for c in comments
                if "ScaffoldingAgent" in c.text or "Scaffolding" in c.text
            ]
            
            if not agent_comments:
                return False
            
            most_recent = max(agent_comments, key=lambda c: c.date)
            
            # Only block if:
            # 1. Most recent comment is a blocking one
            # 2. AND it's within 48 hours
            is_blocking_comment = "Scaffolding Blocked" in most_recent.text
            is_recent = most_recent.date > recent_cutoff
            
            return is_blocking_comment and is_recent
            
        except Exception as e:
            self.logger.warning(f"Failed to check blocked status: {e}")
            return False  # On error, process the task

    def _should_comment_blocked(self, task_id: str, reason: str) -> bool:
        """
        Check if we should add a blocking comment.
        Returns False if a similar blocking comment was added in the last 48 hours.
        """
        from datetime import datetime, timedelta
        
        try:
            comments = self.clickup.get_comments(task_id)
            recent_cutoff = datetime.now() - timedelta(hours=48)
            
            for comment in comments:
                # Skip old comments
                if comment.date < recent_cutoff:
                    continue
                
                # Check if this is a blocking comment with similar reason
                if "Scaffolding Blocked" in comment.text:
                    # Extract the reason from the comment
                    if "Reason:" in comment.text:
                        existing_reason = comment.text.split("Reason:")[1].split("\n")[0].strip()
                        # Simple similarity check: do they share key words?
                        reason_words = set(reason.lower().split())
                        existing_words = set(existing_reason.lower().split())
                        overlap = reason_words & existing_words
                        # If >50% overlap, consider it the same blocker
                        if len(overlap) > len(reason_words) * 0.5:
                            return False
            
            return True
        except Exception as e:
            self.logger.warning(f"Failed to check for duplicate blocking comments: {e}")
            # On error, allow the comment (fail open)
            return True

    # =========================================================================
    # Work Execution
    # =========================================================================

    def _execute_work(self, task: ClickUpTask, details: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt to do the actual work described in the ticket.

        Uses LLM to generate code changes, configuration, or detailed
        implementation notes. Commits changes to the current branch.

        Returns dict with:
            - summary: what was done
            - files_changed: list of files modified
            - commits: number of commits made
            - needs_human: whether human follow-up is needed
        """
        if not self.llm:
            return {"summary": "LLM not available, manual work required.", "files_changed": [], "commits": 0, "needs_human": True}

        custom_id = self.get_custom_task_id(task)
        stack_info = ", ".join(self.config.stack)

        # Build context about the repo structure
        repo_context = self._get_repo_context()

        task_text = json.dumps(details, indent=2, default=str)

        try:
            response = self._llm_call(
                messages=[{
                    "role": "user",
                    "content": f"""You are an SME for a {stack_info} project. Analyze this ticket and produce actionable code changes or detailed implementation instructions.

TICKET: {custom_id} - {task.name}
DESCRIPTION:
{(details.get('description') or '')[:2000]}

COMMENTS:
{json.dumps(details.get('comments', []), default=str)[:1000]}

PROJECT STRUCTURE:
{repo_context[:2000]}

ANALYSIS:
{json.dumps(analysis, default=str)[:1000]}

Your response MUST be valid JSON with this structure:
{{
    "can_implement": true/false,
    "implementation_type": "code_changes" | "configuration" | "investigation" | "manual_steps",
    "summary": "What was done or needs to be done",
    "files": [
        {{
            "path": "relative/path/to/file",
            "action": "create" | "modify" | "note",
            "content": "full file content for create, or description of changes for modify/note",
            "description": "what this change does"
        }}
    ],
    "sandbox_commands": [
        {{
            "id": "short_id",
            "run": "shell command to run inside a Docker container with the project mounted at /workspace",
            "timeout": 120,
            "continue_on_error": false
        }}
    ],
    "manual_steps": ["list of steps that require human action, if any"],
    "notes": "additional context or warnings"
}}

CRITICAL JSON RULES:
- ALL strings in JSON must be properly escaped (use \\n for newlines, \\" for quotes, \\\\ for backslashes)
- Code content in "content" fields must be escaped as a JSON string
- Do NOT include markdown code blocks inside JSON strings
- If content is large, ensure all special characters are escaped
- LIMIT your response to 3-4 files maximum. If more files are needed, create the most critical ones and list remaining as manual_steps.
- Keep each file's content under 100 lines. If a file would be longer, create a minimal working version.

Rules:
- If you CAN write the code, write it. Include full file content for new files.
- If you can only partially implement, do what you can and list manual_steps.
- If it requires investigation/testing that you can't do, set can_implement=false and provide detailed manual_steps.
- For Magento 2: use proper module structure, follow M2 conventions.
- Be specific about file paths. The theme is at app/design/frontend/Phytoextractum/default/
- Keep changes minimal and focused on the ticket scope.
- Use sandbox_commands for things that need a runtime: composer require/install, bin/magento commands, npm/node builds.
- The sandbox is a Docker container with PHP {', '.join(self.config.stack)}, Composer 2, Node/npm, MySQL client.
- Do NOT put sandbox_commands for pure file creation — use "files" for that.
- Common sandbox_commands: "composer require vendor/package --no-interaction", "bin/magento module:enable Vendor_Module", "composer install --no-interaction".
- NEVER directly modify composer.json or composer.lock via "files" — always use sandbox_commands with "composer require" instead.
- NEVER modify package.json or package-lock.json via "files" — use sandbox_commands with "npm install" instead.
- After creating new module files, include a sandbox_command to validate: "composer validate --no-check-publish" or "php -l path/to/file.php".
- For Docker test environments (docker-compose.yml), put them in "docker-setup/" or "docker/" directory (root-level docker-compose.yml is in .gitignore).
- When creating test infrastructure, include README.md in the same directory with setup instructions.
- BEFORE creating custom modules, check if functionality already exists in vendor packages (e.g., FishPig already has admin config, don't duplicate it).
- Prefer configuring existing modules over creating custom wrappers. Only create custom code if truly needed."""
                }],
            )
            text = response.content[0].text.strip()
            
            # Extract JSON more robustly
            # Try to find JSON block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if json_match:
                text = json_match.group(1)
            elif "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            else:
                # Try to find JSON object in the text
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    text = json_match.group(0)

            # Try to parse JSON, with fallback error handling
            try:
                work_plan = json.loads(text)
            except json.JSONDecodeError as e:
                self.logger.warning(f"JSON parse error at position {e.pos}: {e.msg}")
                # Try to fix common issues: unescaped newlines in strings
                # This is a simple heuristic - replace unescaped newlines in string values
                # Find string values and escape newlines
                fixed_text = re.sub(r'(?<!\\)"(?:(?<!\\)\\.|(?<!\\)[^"\\])*?(?<!\\)"', 
                                   lambda m: m.group(0).replace('\n', '\\n').replace('\r', '\\r'),
                                   text)
                try:
                    work_plan = json.loads(fixed_text)
                except:
                    # Last resort: return a manual work plan
                    self.logger.error(f"Could not parse JSON even after fixes. First 500 chars: {text[:500]}")
                    work_plan = {
                        "can_implement": False,
                        "implementation_type": "manual_steps",
                        "summary": f"Failed to parse work plan JSON. Error: {e.msg}",
                        "files": [],
                        "manual_steps": [
                            "Review the ticket requirements",
                            "Implement the changes manually",
                            f"See ticket description: {task.name}"
                        ],
                        "notes": "LLM generated invalid JSON. Manual implementation required."
                    }
        except Exception as e:
            self.logger.warning(f"Work planning failed: {e}")
            return {"summary": f"Failed to generate work plan: {e}", "files_changed": [], "commits": 0, "needs_human": True}

        # Execute the work plan
        files_changed = []
        commit_count = 0

        if work_plan.get("can_implement") and work_plan.get("files"):
            for file_spec in work_plan["files"]:
                file_path = file_spec.get("path", "")
                action = file_spec.get("action", "note")
                content = file_spec.get("content", "")

                if not file_path or action == "note":
                    continue

                full_path = Path(self.config.local_path) / file_path

                try:
                    if action == "create" and content:
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        full_path.write_text(content)
                        self._run_git(["add", file_path])
                        files_changed.append(file_path)
                        self.logger.info(f"    Created: {file_path}")

                    elif action == "modify" and content:
                        if full_path.exists():
                            # For modify, content is the full new content
                            full_path.write_text(content)
                            self._run_git(["add", file_path])
                            files_changed.append(file_path)
                            self.logger.info(f"    Modified: {file_path}")
                        else:
                            # File doesn't exist, create it
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            full_path.write_text(content)
                            self._run_git(["add", file_path])
                            files_changed.append(file_path)
                            self.logger.info(f"    Created (new): {file_path}")

                except Exception as e:
                    self.logger.warning(f"    Failed to write {file_path}: {e}")

            # Commit file changes before sandbox (sandbox may depend on them)
            if files_changed:
                commit_msg = f"[{custom_id}] {work_plan.get('summary', task.name)[:72]}"
                code, _, err = self._run_git(["commit", "-m", commit_msg])
                if code == 0:
                    commit_count = 1
                    self.logger.info(f"    Committed: {commit_msg}")
                else:
                    self.logger.warning(f"    Commit failed: {err}")

        # Run sandbox commands if any
        sandbox_result = None
        if work_plan.get("sandbox_commands") and self.sandbox:
            sandbox_result = self._run_sandbox(work_plan["sandbox_commands"], custom_id)
            if sandbox_result:
                # Add any files changed by the sandbox (filtered)
                for f in sandbox_result.files_changed:
                    if f not in files_changed and not self._is_system_file(f):
                        files_changed.append(f)
                
                # Commit sandbox changes (only code files, not Magento system files)
                # First, add only specific allowed patterns
                COMMIT_PATTERNS = [
                    "composer.json",
                    "composer.lock",
                    "app/code/",
                    "app/design/",
                    "app/etc/config.php",  # Module enable/disable
                    "docker/",             # Test infrastructure
                    "docker-setup/",       # Test infrastructure
                    "*.md",
                ]
                for pattern in COMMIT_PATTERNS:
                    self._run_git(["add", pattern])
                
                # Remove any system files that snuck in
                self._unstage_system_files()
                
                code2, _, _ = self._run_git(["diff", "--cached", "--quiet"])
                if code2 != 0:  # There are staged changes
                    sandbox_msg = f"[{custom_id}] Sandbox: {', '.join(c['id'] for c in work_plan['sandbox_commands'][:3])}"
                    code3, _, err3 = self._run_git(["commit", "-m", sandbox_msg])
                    if code3 == 0:
                        commit_count += 1
                        self.logger.info(f"    Committed sandbox changes: {sandbox_msg}")
        elif work_plan.get("sandbox_commands") and not self.sandbox:
            self.logger.warning("    Sandbox commands requested but no runner available")

        # Build summary
        summary_parts = []
        if work_plan.get("summary"):
            summary_parts.append(work_plan["summary"])

        if work_plan.get("manual_steps"):
            summary_parts.append("\n**Manual steps required:**")
            for i, step in enumerate(work_plan["manual_steps"], 1):
                summary_parts.append(f"  {i}. {step}")

        if work_plan.get("notes"):
            summary_parts.append(f"\n**Notes:** {work_plan['notes']}")

        # Add file descriptions
        if work_plan.get("files"):
            for f in work_plan["files"]:
                if f.get("action") == "note" and f.get("description"):
                    summary_parts.append(f"\n**{f['path']}:** {f['description']}")

        # Add sandbox results
        if sandbox_result:
            summary_parts.append(f"\n**Sandbox ({sandbox_result.runner_type}):** {'✅ passed' if sandbox_result.success else '❌ failed'}")
            for cmd in sandbox_result.commands:
                status = "✅" if cmd.exit_code == 0 else "❌"
                summary_parts.append(f"  {status} `{cmd.id}` ({cmd.duration_seconds}s)")
                if cmd.exit_code != 0 and cmd.stderr:
                    summary_parts.append(f"    Error: {cmd.stderr[:200]}")
        elif work_plan.get("sandbox_commands") and not self.sandbox:
            summary_parts.append("\n⚠️ **Sandbox commands were requested but Docker is not available.** Manual execution required:")
            for sc in work_plan["sandbox_commands"]:
                summary_parts.append(f"  - `{sc['run']}`")

        return {
            "summary": "\n".join(summary_parts),
            "files_changed": files_changed,
            "commits": commit_count,
            "needs_human": not work_plan.get("can_implement", False) or bool(work_plan.get("manual_steps")),
            "sandbox_result": sandbox_result.summary() if sandbox_result else None,
        }

    def _run_sandbox(self, sandbox_commands: List[Dict], custom_id: str) -> Optional[Any]:
        """
        Execute sandbox commands using the configured runner.

        Translates the LLM's sandbox_commands into SandboxCommand objects
        and runs them via the sandbox runner (local Docker or GHA).
        """
        from agents.scaffolding.sandbox import SandboxCommand as SandboxCmd

        commands = []
        for sc in sandbox_commands:
            commands.append(SandboxCmd(
                id=sc.get("id", f"cmd-{len(commands)}"),
                run=sc.get("run", ""),
                timeout=sc.get("timeout", 120),
                workdir=sc.get("workdir", "/workspace"),
                continue_on_error=sc.get("continue_on_error", False),
            ))

        if not commands:
            return None

        self.logger.info(f"    Running {len(commands)} sandbox command(s)...")
        for cmd in commands:
            self.logger.info(f"      [{cmd.id}] {cmd.run}")

        # Determine image based on stack — prefer specific stacks over generic
        SANDBOX_IMAGE_MAP = {
            "magento2": "agent-sandbox-magento2",
            "laravel": "agent-sandbox-laravel",
            "php": "agent-sandbox-magento2",  # Default PHP sandbox
        }
        image = "agent-sandbox-magento2"  # Default
        for s in self.config.stack:
            if s in SANDBOX_IMAGE_MAP:
                image = SANDBOX_IMAGE_MAP[s]
                break

        # Environment variables for the sandbox
        env = {}
        # Pass composer auth if available
        composer_auth = os.getenv("COMPOSER_AUTH")
        if composer_auth:
            env["COMPOSER_AUTH"] = composer_auth

        result = self.sandbox.execute(
            workspace_path=self.config.local_path,
            commands=commands,
            image=image,
            env=env,
        )

        self.logger.info(f"    Sandbox result: {'✅' if result.success else '❌'}")
        for cmd_result in result.commands:
            status = "✅" if cmd_result.exit_code == 0 else "❌"
            self.logger.info(f"      {status} [{cmd_result.id}] exit={cmd_result.exit_code} ({cmd_result.duration_seconds}s)")
            if cmd_result.exit_code != 0:
                self.logger.warning(f"        stderr: {cmd_result.stderr[:300]}")

        return result

    def _is_system_file(self, file_path: str) -> bool:
        """Check if a file is a Magento system file that shouldn't be committed."""
        # These are auto-generated by Magento runtime, not code changes
        SYSTEM_PATTERNS = [
            "generated/",
            "var/",
            "pub/static/",
            "pub/media/",
            ".user.ini",
            "vendor/",
            "node_modules/",
        ]
        
        # Special case: root-level .htaccess and pub/.htaccess are usually not modified
        # by custom code (Magento manages them). But allow if they don't already exist on main.
        if file_path in [".htaccess", "pub/.htaccess"]:
            # Check if this file exists on the base branch
            code, _, _ = self._run_git(["show", f"{self.config.default_branch}:{file_path}"])
            if code == 0:
                # File exists on main, so this is a modification we should ignore
                return True
            # File is new, allow it (might be needed for dev environment)
        
        for pattern in SYSTEM_PATTERNS:
            if pattern in file_path or file_path.endswith(pattern.rstrip("/")):
                return True
        return False

    def _get_actual_committed_files(self, branch_name: str) -> List[str]:
        """Get the actual files committed in this branch (vs. base branch)."""
        try:
            code, output, _ = self._run_git([
                "diff",
                "--name-only",
                f"{self.config.default_branch}...{branch_name}"
            ])
            if code == 0 and output:
                files = [f.strip() for f in output.split("\n") if f.strip()]
                # Filter out system files
                return [f for f in files if not self._is_system_file(f)]
            return []
        except Exception as e:
            self.logger.warning(f"Failed to get committed files: {e}")
            return []

    def _unstage_system_files(self):
        """Remove system files from git staging area."""
        # Get list of staged files
        code, staged, _ = self._run_git(["diff", "--cached", "--name-only"])
        if code != 0 or not staged:
            return

        # Unstage system files
        for file_path in staged.strip().split("\n"):
            if self._is_system_file(file_path):
                self._run_git(["reset", "HEAD", file_path])
                self.logger.debug(f"    Unstaged system file: {file_path}")

    def _get_repo_context(self) -> str:
        """Get a summary of the repo structure for the LLM."""
        lines = []
        repo = Path(self.config.local_path)

        # Theme structure
        theme_dir = repo / "app" / "design" / "frontend"
        if theme_dir.exists():
            for item in sorted(theme_dir.rglob("*"))[:30]:
                if item.is_file() and not any(x in str(item) for x in ['.git', 'node_modules', 'vendor']):
                    lines.append(str(item.relative_to(repo)))

        # Custom modules
        code_dir = repo / "app" / "code"
        if code_dir.exists():
            for vendor in sorted(code_dir.iterdir()):
                if vendor.is_dir():
                    for module in sorted(vendor.iterdir()):
                        if module.is_dir():
                            lines.append(f"app/code/{vendor.name}/{module.name}/")

        # Composer
        composer_json = repo / "composer.json"
        if composer_json.exists():
            lines.append("composer.json (exists)")

        return "\n".join(lines[:50])

    # =========================================================================
    # Core Processing
    # =========================================================================

    def process_task(self, task: ClickUpTask) -> TaskResult:
        """Process a single task through the scaffolding pipeline."""
        self.logger.info(f"Processing task: [{task.id}] {task.name}")

        # Initialize task metrics
        self._current_task_metrics = TaskMetrics(task_id=task.id, task_name=task.name, start_time=time.time())
        self._last_work_result = None  # Stashed by inner method for metrics

        # Use universal metrics context manager if available
        if self.metrics:
            custom_id = self.get_custom_task_id(task) if hasattr(task, 'custom_fields') else task.id
            with self.metrics.track_task(custom_id, task.name):
                try:
                    return self._process_task_inner(task)
                finally:
                    self._finalize_task_metrics(self._last_work_result)
        else:
            try:
                return self._process_task_inner(task)
            finally:
                self._finalize_task_metrics(self._last_work_result)

    def _process_task_inner(self, task: ClickUpTask) -> TaskResult:
        """Inner task processing (wrapped by process_task for metrics)."""

        # Check if task was recently blocked (skip analysis if so)
        if self._was_recently_blocked(task.id):
            self.logger.info(f"  Task was blocked <48h ago, skipping to avoid duplicate work")
            if self.run_metrics:
                self.run_metrics.skipped_tasks += 1
            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                status="blocked",
                comment="Recently blocked, skipping",
            )

        # Start time tracking
        time_entry_id = self._start_time_tracking(task)

        # 1. Get full task details
        details = self.get_task_details(task)

        # 2. Analyze the task
        analysis = self.analyze_task(details)
        self.logger.info(f"  Analysis: {analysis.get('summary', 'N/A')}")

        # 3. Check if blocked (only trust explicit blockers, not LLM guesses about git/repo state)
        if analysis.get("blocked"):
            reason = analysis.get("blocked_reason", "")
            # Ignore false positives about git/branch/repo issues — we verify those ourselves
            git_false_positives = ["origin/main", "branch", "repository", "clone", "git", "commit"]
            is_git_false_positive = any(fp in reason.lower() for fp in git_false_positives)
            if not is_git_false_positive:
                self._stop_time_tracking(time_entry_id)
                
                # Check if we already commented this blocking reason recently
                if not self._should_comment_blocked(task.id, reason):
                    self.logger.info(f"  Already commented this blocker recently, skipping duplicate")
                    return TaskResult(
                        task_id=task.id,
                        task_name=task.name,
                        status="blocked",
                        comment=reason,
                    )
                
                comment = f"🚧 **Scaffolding Blocked**\n\nReason: {reason}\n\nWill retry on next run."
                self.add_task_comment(task.id, comment)
                return TaskResult(
                    task_id=task.id,
                    task_name=task.name,
                    status="blocked",
                    comment=reason,
                )

        # 4. Generate branch name using custom task ID
        prefix = analysis.get("branch_prefix") or self.determine_branch_prefix(task)
        ticket_id = self.get_custom_task_id(task)
        branch_name = f"{prefix}/{ticket_id}"

        # 5. Create branch
        success, branch_msg = self.create_branch(branch_name, task)
        if not success:
            self._stop_time_tracking(time_entry_id)
            self.add_task_comment(task.id, f"⚠️ Branch creation failed: {branch_msg}")
            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                status="error",
                error=branch_msg,
            )

        # Check if branch already covers the issue
        if "already exists and appears to address" in branch_msg:
            self._stop_time_tracking(time_entry_id)
            branch_url = self.get_branch_url(branch_name)
            comment = (
                f"🔗 Branch `{branch_name}` already addresses this issue.\n"
                f"Branch: {branch_url}"
            )
            self.add_task_comment(task.id, comment)
            self.update_task_status(task.id, self.config.status_done)
            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                status="completed",
                branch_name=branch_name,
                branch_url=branch_url,
                comment="Existing branch covers this issue",
            )

        # Determine actual branch name (may have been versioned)
        actual_branch = branch_msg.split("Created ")[-1].split(" (")[0] if "Created" in branch_msg else branch_name
        # Get current branch to confirm
        _, current, _ = self._run_git(["branch", "--show-current"])
        if current:
            actual_branch = current

        # 6. Attempt to do the actual work described in the ticket
        work_result = self._execute_work(task, details, analysis)
        self._last_work_result = work_result  # Stash for metrics finalization

        # 7. Push branch to GitHub
        pushed = self.push_branch(actual_branch)
        branch_url = self.get_branch_url(actual_branch)

        # Stop time tracking
        self._stop_time_tracking(time_entry_id)

        if pushed:
            # 8. Comment on ticket with ACTUAL committed files (not planned files)
            work_summary = work_result.get("summary", "Branch created, no code changes.")
            
            # Get actual files committed (from git diff, not LLM plan)
            actual_files = self._get_actual_committed_files(actual_branch)
            files_str = "\n".join(f"  - `{f}`" for f in actual_files) if actual_files else "  _No files modified_"

            comment = (
                f"🌿 **Scaffolding complete**\n\n"
                f"Branch: `{actual_branch}`\n"
                f"Link: {branch_url}\n\n"
                f"**Summary:** {analysis.get('summary', task.name)}\n\n"
                f"**Work done:**\n{work_summary}\n\n"
                f"**Files changed:**\n{files_str}\n\n"
                f"---\n"
                f"_Agent: ScaffoldingAgent/{self.config.project_key} | Model: claude-sonnet-4-20250514_"
            )
            self.add_task_comment(task.id, comment)

            # 9. Move to "to do"
            self.update_task_status(task.id, self.config.status_done)
            self.logger.info(f"  ✅ Task scaffolded: {actual_branch}")

            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                status="completed",
                branch_name=actual_branch,
                branch_url=branch_url,
                comment="scaffolding complete",
            )
        else:
            comment = (
                f"⚠️ Branch `{actual_branch}` created locally but push failed.\n"
                f"Manual push needed."
            )
            self.add_task_comment(task.id, comment)

            return TaskResult(
                task_id=task.id,
                task_name=task.name,
                status="blocked",
                branch_name=actual_branch,
                comment="Push to remote failed",
            )

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    def run(self) -> List[TaskResult]:
        """
        Main execution loop.

        1. Acquire lock (only one instance per project)
        2. Ensure repo is ready
        3. Fetch pending tasks
        4. Process each task
        5. Return results
        """
        self.logger.info(f"=== Scaffolding Agent: {self.config.project_key} ===")

        # Initialize run metrics
        self.run_metrics = RunMetrics(project_key=self.config.project_key)

        # Acquire lock
        lock_fd = self._acquire_lock()
        if lock_fd is None:
            self.logger.info("Another instance running, exiting.")
            return []

        try:
            # Check if list has any updates since last run
            if not self._has_list_changed():
                self.logger.info("No changes in list since last check, nothing to do.")
                # Update timestamp so we don't re-check the same window next run
                state = self._load_state()
                state["last_list_check"] = datetime.now().isoformat()
                self._save_state(state)
                return []

            # Ensure repo is ready
            if not self.ensure_repo_ready():
                self.logger.error("Repository not ready, aborting.")
                return []

            # Fetch pending tasks (only those updated since we last touched them)
            tasks = self.fetch_pending_tasks(skip_unchanged=True)
            if not tasks:
                self.logger.info("No fresh tasks to process.")
                # Update state to record this check
                state = self._load_state()
                state["last_list_check"] = datetime.now().isoformat()
                self._save_state(state)
                return []

            # Process each task
            self.results = []
            for task in tasks:
                try:
                    result = self.process_task(task)
                    self.results.append(result)
                    
                    # Mark task as processed in state
                    self._mark_task_processed(task.id)

                    # Return to default branch between tasks
                    self._run_git(["checkout", self.config.default_branch])
                except Exception as e:
                    self.logger.error(f"Error processing task {task.id}: {e}")
                    self._finalize_task_metrics()  # Capture metrics even on error
                    self.results.append(TaskResult(
                        task_id=task.id,
                        task_name=task.name,
                        status="error",
                        error=str(e),
                    ))
                    # Try to recover
                    self._run_git(["checkout", self.config.default_branch])
            
            # Update state after successful run
            state = self._load_state()
            state["last_list_check"] = datetime.now().isoformat()
            self._save_state(state)

            # Finalize run metrics
            self.run_metrics.end_time = time.time()

            # Summary
            completed = sum(1 for r in self.results if r.status == "completed")
            blocked = sum(1 for r in self.results if r.status == "blocked")
            errors = sum(1 for r in self.results if r.status == "error")

            self.logger.info(
                f"=== Done: {completed} completed, {blocked} blocked, {errors} errors ==="
            )
            self.logger.info(self.run_metrics.summary())

            # Save metrics to state
            state = self._load_state()
            state["last_run_metrics"] = self.run_metrics.to_dict()
            self._save_state(state)

            # Universal metrics: save local log, sync Hubstaff, report to queue
            if self.metrics:
                self.metrics.finalize_run()
            else:
                self._report_to_queue(self.run_metrics)

            return self.results

        finally:
            self._release_lock(lock_fd)
