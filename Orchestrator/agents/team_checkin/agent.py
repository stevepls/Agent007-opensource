"""
Team Check-in Agent

Main agent that orchestrates team check-ins, activity monitoring, and time tracking.
"""

import os
import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import pytz

# Add parent directories to path
AGENT_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = AGENT_ROOT.parent.parent
SERVICES_ROOT = ORCHESTRATOR_ROOT / "services"
sys.path.insert(0, str(ORCHESTRATOR_ROOT))
sys.path.insert(0, str(SERVICES_ROOT))

from services.slack.client import SlackClient
from services.tickets.clickup_client import ClickUpClient
from services.hubstaff.client import HubstaffClient
from agents.team_checkin.team_detector import TeamDetector, DetectedTeamMember
from services.message_queue import get_message_queue, MessageType, MessageStatus

# LLM imports
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


@dataclass
class TeamMember:
    """Represents a team member configuration."""
    name: str
    slack_user_id: Optional[str] = None
    github_username: Optional[str] = None
    hubstaff_user_id: Optional[int] = None
    clickup_user_id: Optional[str] = None
    priority_tasks: List[Dict[str, Any]] = None
    current_task_id: Optional[str] = None
    repos: List[str] = None
    
    def __post_init__(self):
        if self.priority_tasks is None:
            self.priority_tasks = []
        if self.repos is None:
            self.repos = []
    
    @classmethod
    def from_detected(cls, detected: DetectedTeamMember) -> "TeamMember":
        """Create TeamMember from DetectedTeamMember."""
        # Convert priority tasks to the format expected by agent
        priority_tasks = []
        for task in detected.priority_tasks:
            priority_tasks.append({
                "name": task.get("name", ""),
                "due_date": datetime.fromtimestamp(int(task.get("due_date", 0)) / 1000).isoformat() if task.get("due_date") else None,
                "reason": f"Priority: {task.get('priority', 3)}",
                "task_id": task.get("id")
            })
        
        # Use first priority task as current if available
        current_task_id = detected.priority_tasks[0].get("id") if detected.priority_tasks else None
        
        return cls(
            name=detected.clickup_name,
            slack_user_id=detected.slack_user_id,
            github_username=detected.github_username,
            hubstaff_user_id=detected.hubstaff_user_id,
            clickup_user_id=str(detected.clickup_user_id),
            priority_tasks=priority_tasks,
            current_task_id=current_task_id,
            repos=detected.repos
        )


@dataclass
class MemberState:
    """Tracks state for a team member."""
    name: str
    last_nudged: Optional[str] = None  # ISO datetime
    last_activity: Optional[str] = None  # ISO datetime
    timer_stopped: bool = False
    responded_today: bool = False
    morning_greeting_sent: bool = False
    done_for_today: bool = False


class TeamCheckinAgent:
    """Main agent for team check-ins and time tracking."""
    
    EST = pytz.timezone('US/Eastern')
    CHECK_INTERVAL_HOURS = 2
    WORK_START_HOUR = 8
    WORK_END_HOUR = 17  # 5 PM
    
    def __init__(
        self,
        config_path: Optional[Path] = None,
        state_path: Optional[Path] = None,
        log_path: Optional[Path] = None,
        auto_detect: bool = True,
        refresh_team_cache: bool = False
    ):
        """
        Initialize the agent.
        
        Args:
            config_path: Path to team.json config file (fallback/override)
            state_path: Path to state.json file
            log_path: Path to log file
            auto_detect: Whether to auto-detect team members from ClickUp
            refresh_team_cache: Force refresh of team member cache
        """
        self.config_path = config_path or AGENT_ROOT / "config" / "team.json"
        self.state_path = state_path or AGENT_ROOT / "config" / "state.json"
        self.log_path = log_path or AGENT_ROOT / "logs" / "agent.log"
        self.auto_detect = auto_detect
        self.refresh_team_cache = refresh_team_cache
        
        # Setup logging
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_path),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize clients first (needed for team detection)
        self.slack = None
        self.clickup = None
        self.hubstaff = None
        
        # Message queue for approval (uses orchestrator's message queue)
        self.message_queue = get_message_queue()
        
        self._init_clients()
        
        # Register Slack DM sender after clients are initialized
        # This needs to be registered globally so the message queue can use it
        if self.slack and self.slack.is_connected:
            def send_slack_dm(msg):
                """Send Slack DM - registered globally with message queue."""
                try:
                    from agents.team_checkin.agent import TeamMember
                    member = TeamMember(
                        name=msg.metadata.get("member_name", ""),
                        slack_user_id=msg.channel
                    )
                    # Create a temporary agent instance to use the send method
                    # Or use Slack client directly
                    from slack_sdk import WebClient
                    user_token = os.getenv('SLACK_USER_TOKEN')
                    if not user_token:
                        # Try config file
                        try:
                            import yaml
                            secrets_file = Path.home() / '.config' / 'devops' / 'slack-secrets.yml'
                            if secrets_file.exists():
                                with open(secrets_file) as f:
                                    secrets = yaml.safe_load(f)
                                    if secrets:
                                        ut = secrets.get('user_token', '')
                                        if ut and ut.startswith('xoxp-'):
                                            user_token = ut
                        except Exception:
                            pass
                    
                    if not user_token:
                        raise Exception("SLACK_USER_TOKEN not available")
                    
                    client = WebClient(token=user_token)
                    # Open DM channel
                    dm_result = client.conversations_open(users=[msg.channel])
                    channel_id = dm_result['channel']['id']
                    
                    # Send message
                    result = client.chat_postMessage(
                        channel=channel_id,
                        text=msg.content
                    )
                    
                    if result.get('ok'):
                        return True
                    else:
                        raise Exception(f"Slack API error: {result.get('error')}")
                except Exception as e:
                    raise Exception(f"Failed to send Slack DM: {str(e)}")
            
            self.message_queue.register_sender(MessageType.SLACK_DM, send_slack_dm)
            self.logger.info("✅ Registered Slack DM sender with message queue")
        
        # Load team members (auto-detect or from config)
        self.team_members = self._load_team_members()
        self.state = self._load_state()
    
    def _load_team_members(self) -> List[TeamMember]:
        """Load team members - auto-detect from ClickUp or load from config."""
        members = []
        
        # Try auto-detection first
        if self.auto_detect and self.clickup:
            try:
                detector = TeamDetector(
                    clickup_client=self.clickup,
                    cache_path=AGENT_ROOT / "config" / "team_cache.json",
                    mapping_path=AGENT_ROOT / "config" / "user_mapping.json"
                )
                
                detected = detector.detect_team_members(refresh_cache=self.refresh_team_cache)
                
                for detected_member in detected:
                    # Only include members with required mappings (Slack, GitHub, or Hubstaff)
                    if detected_member.slack_user_id or detected_member.github_username or detected_member.hubstaff_user_id:
                        member = TeamMember.from_detected(detected_member)
                        members.append(member)
                        self.logger.info(f"✅ Auto-detected: {member.name} ({len(detected_member.active_tasks)} active tasks)")
                    else:
                        self.logger.warning(f"⚠️ Skipping {detected_member.clickup_name} - no Slack/GitHub/Hubstaff mapping found. Add to user_mapping.json")
                
                if members:
                    self.logger.info(f"📋 Auto-detected {len(members)} team members from ClickUp")
                    return members
            except Exception as e:
                self.logger.error(f"Error in auto-detection: {e}", exc_info=True)
                self.logger.info("Falling back to manual config...")
        
        # Fallback to manual config
        if not self.config_path.exists():
            self.logger.warning(f"Team config not found at {self.config_path}. No team members loaded.")
            return []
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            for member_data in data:
                members.append(TeamMember(**member_data))
            
            self.logger.info(f"📋 Loaded {len(members)} team members from config")
            return members
        except Exception as e:
            self.logger.error(f"Error loading team config: {e}")
            return []
    
    def _load_state(self) -> Dict[str, MemberState]:
        """Load state from JSON file."""
        if not self.state_path.exists():
            return {}
        
        try:
            with open(self.state_path, 'r') as f:
                data = json.load(f)
            
            state = {}
            for name, state_data in data.items():
                state[name] = MemberState(**state_data)
            
            return state
        except Exception as e:
            self.logger.error(f"Error loading state: {e}")
            return {}
    
    def _save_state(self):
        """Save state to JSON file."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                name: asdict(state)
                for name, state in self.state.items()
            }
            with open(self.state_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")
    
    def _init_clients(self):
        """Initialize API clients."""
        # Slack
        try:
            # Try to get token from environment or config file (same as team detector)
            user_token = os.getenv('SLACK_USER_TOKEN')
            if not user_token:
                # Try loading from slack-secrets.yml (same as SlackClient does)
                try:
                    import yaml
                    secrets_file = Path.home() / '.config' / 'devops' / 'slack-secrets.yml'
                    if secrets_file.exists():
                        with open(secrets_file) as f:
                            secrets = yaml.safe_load(f)
                            if secrets:
                                ut = secrets.get('user_token', '')
                                if ut and ut.startswith('xoxp-'):
                                    user_token = ut
                except Exception:
                    pass
            
            if not user_token:
                self.logger.warning("SLACK_USER_TOKEN not set. Slack features disabled.")
            else:
                self.slack = SlackClient(user_token=user_token)
                if self.slack.connect():
                    self.logger.info("✅ Slack client initialized")
                else:
                    self.logger.warning("Slack client failed to connect")
                    self.slack = None
        except Exception as e:
            self.logger.error(f"Failed to initialize Slack: {e}")
            self.slack = None
        
        # GitHub
        # Note: GitHubClient uses gh CLI, not direct API
        # We'll use gh CLI directly for commit checking
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            self.logger.warning("GITHUB_TOKEN not set. GitHub activity checking may be limited.")
        else:
            # Set GITHUB_TOKEN for gh CLI
            os.environ['GITHUB_TOKEN'] = github_token
            self.logger.info("✅ GitHub token configured")
        
        # ClickUp
        try:
            clickup_token = os.getenv('CLICKUP_API_TOKEN')
            if clickup_token:
                self.clickup = ClickUpClient(clickup_token)
                self.logger.info("✅ ClickUp client initialized")
        except Exception as e:
            self.logger.warning(f"ClickUp not available: {e}")
        
        # Hubstaff
        try:
            hubstaff_token = os.getenv('HUBSTAFF_API_TOKEN')
            if not hubstaff_token:
                self.logger.warning("HUBSTAFF_API_TOKEN not set. Hubstaff features disabled.")
            else:
                org_id = os.getenv('HUBSTAFF_ORG_ID')
                self.hubstaff = HubstaffClient(
                    api_token=hubstaff_token,
                    org_id=int(org_id) if org_id else None
                )
                self.logger.info("✅ Hubstaff client initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize Hubstaff: {e}")
    
    def _is_work_hours(self, dt: datetime) -> bool:
        """Check if datetime is within work hours (8 AM - 5 PM EST, weekdays)."""
        est_dt = dt.astimezone(self.EST)
        
        # Check if weekday (Monday=0, Sunday=6)
        if est_dt.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check if within work hours
        work_start = est_dt.replace(hour=self.WORK_START_HOUR, minute=0, second=0, microsecond=0)
        work_end = est_dt.replace(hour=self.WORK_END_HOUR, minute=0, second=0, microsecond=0)
        
        return work_start <= est_dt < work_end
    
    def _is_first_run_today(self) -> bool:
        """Check if this is the first run of the day."""
        now = datetime.now(self.EST)
        today_start = now.replace(hour=self.WORK_START_HOUR, minute=0, second=0, microsecond=0)
        
        # Check if any member has received morning greeting today
        for member in self.team_members:
            state = self.state.get(member.name)
            if state and state.morning_greeting_sent:
                # Check if it was sent today
                if state.last_nudged:
                    last_nudged = datetime.fromisoformat(state.last_nudged).astimezone(self.EST)
                    if last_nudged.date() == now.date():
                        return False
        
        # First run if we're in the first hour of work
        return today_start <= now < today_start + timedelta(hours=1)
    
    def _get_member_state(self, member: TeamMember) -> MemberState:
        """Get or create state for a member."""
        if member.name not in self.state:
            self.state[member.name] = MemberState(name=member.name)
        return self.state[member.name]
    
    def _check_github_activity(self, member: TeamMember, hours: int = 3) -> bool:
        """Check if member has GitHub activity in the last N hours."""
        if not member.github_username:
            self.logger.debug(f"Skipping GitHub check for {member.name} - no GitHub username")
            return False
        
        try:
            import subprocess
            import json as json_lib
            
            cutoff = datetime.now() - timedelta(hours=hours)
            cutoff_iso = cutoff.isoformat()
            
            # Check commits in repos using gh CLI
            for repo in member.repos:
                try:
                    # Parse owner/repo
                    parts = repo.split('/')
                    if len(parts) != 2:
                        continue
                    owner, repo_name = parts
                    
                    # Use gh api to get recent commits by author
                    cmd = [
                        "gh", "api",
                        f"repos/{owner}/{repo_name}/commits",
                        "-f", f"author={member.github_username}",
                        "-f", "per_page=10",
                        "--jq", ".[] | {sha: .sha, date: .commit.author.date, message: .commit.message}"
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0 and result.stdout:
                        # Parse JSON lines
                        for line in result.stdout.strip().split('\n'):
                            if not line:
                                continue
                            try:
                                commit_data = json_lib.loads(line)
                                commit_date_str = commit_data.get('date', '')
                                if commit_date_str:
                                    # Parse ISO date
                                    commit_date = datetime.fromisoformat(commit_date_str.replace('Z', '+00:00'))
                                    if commit_date > cutoff:
                                        self.logger.info(f"Found GitHub activity for {member.name}: commit in {repo}")
                                        return True
                            except (json_lib.JSONDecodeError, ValueError) as e:
                                continue
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"Timeout checking repo {repo}")
                    continue
                except Exception as e:
                    self.logger.debug(f"Error checking repo {repo}: {e}")
                    continue
            
            return False
        except Exception as e:
            self.logger.error(f"Error checking GitHub activity for {member.name}: {e}")
            return False
    
    def _check_slack_activity(self, member: TeamMember, hours: int = 3) -> bool:
        """Check if member has Slack activity in the last N hours."""
        if not self.slack:
            return False
        
        try:
            # This is a simplified check - in production, you'd want to:
            # 1. Check recent DMs with the member
            # 2. Check messages in relevant channels
            # 3. Check for mentions
            
            # For now, we'll check if they've responded to our messages
            state = self._get_member_state(member)
            if state.responded_today:
                return True
            
            # TODO: Implement actual Slack message checking
            # This would require storing conversation IDs and checking recent messages
            
            return False
        except Exception as e:
            self.logger.error(f"Error checking Slack activity for {member.name}: {e}")
            return False
    
    def _has_recent_activity(self, member: TeamMember) -> bool:
        """Check if member has any recent activity."""
        return self._check_github_activity(member) or self._check_slack_activity(member)
    
    def _get_task_updates(self, member: TeamMember, task_id: str) -> Optional[Dict[str, Any]]:
        """Get recent updates/comments on a task from ClickUp."""
        if not self.clickup or not task_id:
            return None
        
        try:
            task = self.clickup.get_task(task_id)
            if not task:
                return None
            
            # Get task comments/updates
            # Note: ClickUp API v2 doesn't have a direct comments endpoint in the client
            # You'd need to extend the client or use the API directly
            
            return {
                "status": task.status,
                "due_date": task.date_due.isoformat() if task.date_due else None,
                "description": task.description[:500] if task.description else None
            }
        except Exception as e:
            self.logger.error(f"Error getting task updates for {member.name}: {e}")
            return None
    
    def _generate_morning_message(self, member: TeamMember) -> str:
        """Generate morning greeting message using LLM."""
        # Build context
        tasks_text = ""
        urgent_task = None
        closest_deadline = None
        min_days = float('inf')
        
        for task in member.priority_tasks:
            due_date_str = task.get('due_date')
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str).date()
                    days_until = (due_date - datetime.now().date()).days
                    if days_until < min_days:
                        min_days = days_until
                        closest_deadline = task
                except:
                    pass
            
            tasks_text += f"• {task.get('name')} – due {due_date_str or 'TBD'}\n"
            if task.get('reason'):
                tasks_text += f"  ({task.get('reason')})\n"
        
        # Get updates on urgent/closest task
        task_updates = None
        if closest_deadline and closest_deadline.get('task_id'):
            task_updates = self._get_task_updates(member, closest_deadline['task_id'])
        
        # Build prompt
        prompt = f"""Generate a casual, friendly morning check-in message for {member.name}. 

The message should:
- Greet them warmly
- List their priority tasks with due dates
- Ask for an update on the most urgent task ({closest_deadline.get('name') if closest_deadline else 'N/A'})
- Include any relevant context from task updates if available
- Ask for a brief update on important tasks and their game plan
- Focus on the highest priority task with a reason
- End with asking them to reply when online/starting so we can update ticket status and start time tracking

Keep it natural and conversational, like you're texting a colleague. Don't be overly formal.

Priority tasks:
{tasks_text}

Most urgent task: {closest_deadline.get('name') if closest_deadline else 'None'}
Task updates: {json.dumps(task_updates) if task_updates else 'None available'}

Generate the message now:"""

        return self._call_llm(prompt)
    
    def _generate_followup_message(self, member: TeamMember, quiet_hours: float) -> str:
        """Generate follow-up message when member is quiet."""
        # Find priority task
        priority_task = None
        if member.priority_tasks:
            priority_task = member.priority_tasks[0]
        
        prompt = f"""Generate a short, casual follow-up message for {member.name}. 

Context:
- They've been quiet for about {quiet_hours:.1f} hours
- No recent GitHub commits or Slack messages
- Priority task: {priority_task.get('name') if priority_task else 'None'}

The message should:
- Be brief and direct
- Check if they're still good on the priority task
- Ask if they're stuck or ready to wrap
- Mention that you'll pause their timer soon if no response

Keep it casual and friendly, like a quick check-in. Don't be pushy.

Generate the message now:"""

        return self._call_llm(prompt)
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM (Claude first, fallback to OpenAI)."""
        # Try Claude first
        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                try:
                    client = anthropic.Anthropic(api_key=api_key)
                    response = client.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=1000,
                        messages=[{
                            "role": "user",
                            "content": prompt
                        }]
                    )
                    message = response.content[0].text
                    self.logger.info("✅ Generated message using Claude")
                    return message.strip()
                except Exception as e:
                    self.logger.warning(f"Claude API error: {e}, falling back to OpenAI")
        
        # Fallback to OpenAI
        if OPENAI_AVAILABLE:
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                try:
                    client = openai.OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[{
                            "role": "user",
                            "content": prompt
                        }],
                        max_tokens=1000
                    )
                    message = response.choices[0].message.content
                    self.logger.info("✅ Generated message using OpenAI")
                    return message.strip()
                except Exception as e:
                    self.logger.error(f"OpenAI API error: {e}")
        
        # Fallback to template
        self.logger.warning("No LLM available, using template message")
        return f"Hey, just checking in. Let me know if you need anything!"
    
    def _send_slack_dm(self, member: TeamMember, message: str) -> bool:
        """Send a DM to a team member via Slack."""
        if not self.slack:
            self.logger.error("Slack client not available")
            return False
        
        if not member.slack_user_id:
            self.logger.warning(f"Cannot send DM to {member.name} - no Slack user ID")
            return False
        
        try:
            # Open DM channel (returns channel ID)
            channel_id = self.slack.open_dm(member.slack_user_id)
            
            # Post message using user token (so it appears as from the user, not bot)
            # We need to use the user client directly
            if self.slack.has_user_token:
                # Use user client to post as user
                from slack_sdk import WebClient
                user_client = WebClient(token=os.getenv('SLACK_USER_TOKEN'))
                result = user_client.chat_postMessage(
                    channel=channel_id,
                    text=message
                )
                
                if result.get('ok'):
                    self.logger.info(f"✅ Sent DM to {member.name}")
                    return True
                else:
                    self.logger.error(f"Failed to send DM to {member.name}: {result.get('error')}")
                    return False
            else:
                # Fallback to bot client
                result = self.slack.post_message(channel_id, message)
                if result:
                    self.logger.info(f"✅ Sent DM to {member.name} (via bot)")
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error sending DM to {member.name}: {e}")
            return False
    
    def _start_hubstaff_timer(self, member: TeamMember) -> bool:
        """Start Hubstaff timer for a member."""
        if not self.hubstaff:
            return False
        
        if not member.hubstaff_user_id:
            self.logger.debug(f"Skipping Hubstaff timer for {member.name} - no Hubstaff user ID")
            return False
        
        try:
            project_id = None
            task_id = None
            
            # Try to get project/task from current_task_id
            if member.current_task_id and self.clickup:
                # Map ClickUp task to Hubstaff project/task if needed
                # This would require additional configuration
                pass
            
            entry = self.hubstaff.start_time_entry(
                user_id=member.hubstaff_user_id,
                project_id=project_id,
                task_id=task_id,
                note=f"Auto-started for {member.name}"
            )
            
            if entry:
                self.logger.info(f"✅ Started Hubstaff timer for {member.name}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error starting Hubstaff timer for {member.name}: {e}")
            return False
    
    def _stop_hubstaff_timer(self, member: TeamMember) -> bool:
        """Stop Hubstaff timer for a member."""
        if not self.hubstaff:
            return False
        
        if not member.hubstaff_user_id:
            return False
        
        try:
            stopped_count = self.hubstaff.stop_user_active_entries(member.hubstaff_user_id)
            if stopped_count > 0:
                self.logger.info(f"✅ Stopped {stopped_count} Hubstaff timer(s) for {member.name}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error stopping Hubstaff timer for {member.name}: {e}")
            return False
    
    def _update_task_status(self, member: TeamMember, status: str = "in progress") -> bool:
        """Update ClickUp task status."""
        if not self.clickup or not member.current_task_id:
            return False
        
        try:
            # ClickUp client would need an update_task_status method
            # For now, this is a placeholder
            self.logger.info(f"Would update task {member.current_task_id} to {status}")
            return True
        except Exception as e:
            self.logger.error(f"Error updating task status: {e}")
            return False
    
    def _handle_morning_checkin(self, member: TeamMember):
        """Handle morning check-in for a member."""
        state = self._get_member_state(member)
        
        # Skip if already sent today
        if state.morning_greeting_sent:
            if state.last_nudged:
                last_nudged = datetime.fromisoformat(state.last_nudged).astimezone(self.EST)
                if last_nudged.date() == datetime.now(self.EST).date():
                    self.logger.info(f"Skipping {member.name} - morning greeting already sent today")
                    return
        
        # Generate message
        message = self._generate_morning_message(member)
        
        # Queue for approval through orchestrator's message queue
        if member.slack_user_id:
            queued_msg = self.message_queue.queue(
                msg_type=MessageType.SLACK_DM,
                channel=member.slack_user_id,
                content=message,
                subject=f"Morning check-in for {member.name}",
                metadata={
                    "member_name": member.name,
                    "message_type": "morning",
                    "priority_tasks": member.priority_tasks,
                    "current_task_id": member.current_task_id,
                    "team_checkin": True
                },
                created_by="team_checkin_agent",
                requires_approval=True,
                delay_seconds=0  # Send immediately after approval
            )
            
            self.logger.info(f"📝 Queued morning message for {member.name} (ID: {queued_msg.id}) - awaiting approval in orchestrator")
        else:
            self.logger.warning(f"Cannot queue message for {member.name} - no Slack user ID")
    
    def _handle_followup_checkin(self, member: TeamMember):
        """Handle follow-up check-in for a member."""
        state = self._get_member_state(member)
        
        # Skip if they've responded today
        if state.responded_today:
            self.logger.info(f"Skipping {member.name} - already responded today")
            return
        
        # Skip if they're done for today
        if state.done_for_today:
            self.logger.info(f"Skipping {member.name} - marked as done for today")
            return
        
        # Skip if recently nudged (within last 2 hours)
        if state.last_nudged:
            last_nudged = datetime.fromisoformat(state.last_nudged)
            hours_since = (datetime.now() - last_nudged).total_seconds() / 3600
            if hours_since < self.CHECK_INTERVAL_HOURS:
                self.logger.info(f"Skipping {member.name} - nudged {hours_since:.1f} hours ago")
                return
        
        # Check for activity
        if self._has_recent_activity(member):
            self.logger.info(f"Skipping {member.name} - has recent activity")
            # Update last activity
            state.last_activity = datetime.now().isoformat()
            self._save_state()
            return
        
        # Calculate quiet time
        quiet_hours = self.CHECK_INTERVAL_HOURS
        if state.last_activity:
            last_activity = datetime.fromisoformat(state.last_activity)
            quiet_hours = (datetime.now() - last_activity).total_seconds() / 3600
        
        # Generate follow-up message
        message = self._generate_followup_message(member, quiet_hours)
        
        # Queue for approval through orchestrator's message queue
        if member.slack_user_id:
            queued_msg = self.message_queue.queue(
                msg_type=MessageType.SLACK_DM,
                channel=member.slack_user_id,
                content=message,
                subject=f"Follow-up check-in for {member.name}",
                metadata={
                    "member_name": member.name,
                    "message_type": "followup",
                    "quiet_hours": quiet_hours,
                    "priority_task": member.priority_tasks[0].get("name") if member.priority_tasks else None,
                    "team_checkin": True
                },
                created_by="team_checkin_agent",
                requires_approval=True,
                delay_seconds=0  # Send immediately after approval
            )
            
            self.logger.info(f"📝 Queued follow-up message for {member.name} (ID: {queued_msg.id}) - awaiting approval in orchestrator")
        else:
            self.logger.warning(f"Cannot queue message for {member.name} - no Slack user ID")
        
        # If still no response after a reasonable time, stop timer
        # This would be handled in a subsequent run
        # For now, we'll just log it
    
    def _handle_timer_stop(self, member: TeamMember):
        """Stop timer if member hasn't responded and has no activity."""
        state = self._get_member_state(member)
        
        # Skip if already stopped today
        if state.timer_stopped:
            self.logger.info(f"Skipping {member.name} - timer already stopped today")
            return
        
        # Skip if they've responded
        if state.responded_today:
            return
        
        # Skip if they're done for today
        if state.done_for_today:
            return
        
        # Check if we nudged them recently (within last 2 hours)
        if not state.last_nudged:
            return
        
        last_nudged = datetime.fromisoformat(state.last_nudged)
        hours_since_nudge = (datetime.now() - last_nudged).total_seconds() / 3600
        
        # Stop timer if no response after 2+ hours since last nudge
        if hours_since_nudge >= self.CHECK_INTERVAL_HOURS:
            if not self._has_recent_activity(member):
                if self._stop_hubstaff_timer(member):
                    state.timer_stopped = True
                    self._save_state()
                    self.logger.info(f"⏸️ Stopped timer for {member.name} - no activity/response")
    
    def run(self):
        """Run the check-in cycle."""
        now = datetime.now(self.EST)
        self.logger.info(f"🔄 Running check-in cycle at {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Check if within work hours
        if not self._is_work_hours(now):
            self.logger.info("Outside work hours, skipping")
            return
        
        # Determine if this is morning check-in or follow-up
        is_morning = self._is_first_run_today()
        
        for member in self.team_members:
            try:
                if is_morning:
                    self._handle_morning_checkin(member)
                else:
                    self._handle_followup_checkin(member)
                    self._handle_timer_stop(member)
            except Exception as e:
                self.logger.error(f"Error processing {member.name}: {e}", exc_info=True)
        
        self.logger.info("✅ Check-in cycle complete")
