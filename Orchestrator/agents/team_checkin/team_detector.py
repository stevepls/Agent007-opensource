"""
Team Member Auto-Detection from ClickUp

Automatically detects team members based on who has active tasks assigned in ClickUp.
Caches the results for performance.
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict, field
import sys

# Add parent directories to path
AGENT_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = AGENT_ROOT.parent.parent
SERVICES_ROOT = ORCHESTRATOR_ROOT / "services"
sys.path.insert(0, str(ORCHESTRATOR_ROOT))
sys.path.insert(0, str(SERVICES_ROOT))

from services.tickets.clickup_client import ClickUpClient
from services.slack.client import SlackClient
from services.hubstaff.client import HubstaffClient


@dataclass
class ClickUpUser:
    """Represents a ClickUp user."""
    id: int
    username: str
    email: str
    name: str
    initials: str = ""
    profile_picture: Optional[str] = None


@dataclass
class DetectedTeamMember:
    """Team member detected from ClickUp tasks."""
    clickup_user_id: int
    clickup_username: str
    clickup_name: str
    clickup_email: str
    active_tasks: List[Dict[str, Any]] = field(default_factory=list)
    priority_tasks: List[Dict[str, Any]] = field(default_factory=list)
    # Mapped IDs (from user_mapping.json)
    slack_user_id: Optional[str] = None
    github_username: Optional[str] = None
    hubstaff_user_id: Optional[int] = None
    repos: List[str] = field(default_factory=list)


class TeamDetector:
    """Detects team members from ClickUp active tasks."""
    
    def __init__(
        self,
        clickup_client: Optional[ClickUpClient] = None,
        cache_path: Optional[Path] = None,
        mapping_path: Optional[Path] = None,
        auto_detect_slack: bool = True,
        auto_detect_hubstaff: bool = True
    ):
        """
        Initialize team detector.
        
        Args:
            clickup_client: ClickUp client instance
            cache_path: Path to cache file for detected members
            mapping_path: Path to user mapping file (ClickUp -> Slack/GitHub/Hubstaff)
            auto_detect_slack: Automatically detect Slack IDs by email
            auto_detect_hubstaff: Automatically detect Hubstaff IDs by email
        """
        self.cache_path = cache_path or AGENT_ROOT / "config" / "team_cache.json"
        self.mapping_path = mapping_path or AGENT_ROOT / "config" / "user_mapping.json"
        self.auto_detect_slack = auto_detect_slack
        self.auto_detect_hubstaff = auto_detect_hubstaff
        
        self.logger = logging.getLogger(__name__)
        
        # Initialize ClickUp client
        if clickup_client:
            self.clickup = clickup_client
        else:
            clickup_token = os.getenv('CLICKUP_API_TOKEN')
            if clickup_token:
                self.clickup = ClickUpClient(clickup_token)
            else:
                self.clickup = None
                self.logger.warning("CLICKUP_API_TOKEN not set. Team detection disabled.")
        
        # Initialize Slack client for auto-detection
        self.slack = None
        if self.auto_detect_slack:
            try:
                # Try to get token from environment or config file
                slack_token = os.getenv('SLACK_USER_TOKEN')
                if not slack_token:
                    # Try loading from slack-secrets.yml (same as SlackClient does)
                    try:
                        import yaml
                        secrets_file = Path.home() / '.config' / 'devops' / 'slack-secrets.yml'
                        if secrets_file.exists():
                            with open(secrets_file) as f:
                                secrets = yaml.safe_load(f)
                                slack_token = secrets.get('user_token') if secrets else None
                    except Exception:
                        pass
                
                if slack_token:
                    self.slack = SlackClient(user_token=slack_token)
                    if self.slack.connect():
                        self.logger.info("✅ Slack client initialized for auto-detection")
                    else:
                        self.logger.warning("Slack client failed to connect")
                        self.slack = None
                else:
                    self.logger.warning("SLACK_USER_TOKEN not found - Slack auto-detection disabled")
            except Exception as e:
                self.logger.warning(f"Slack auto-detection disabled: {e}")
                self.slack = None
        
        # Initialize Hubstaff client for auto-detection
        self.hubstaff = None
        if self.auto_detect_hubstaff:
            try:
                hubstaff_token = os.getenv('HUBSTAFF_API_TOKEN')
                if hubstaff_token:
                    org_id = os.getenv('HUBSTAFF_ORG_ID')
                    self.hubstaff = HubstaffClient(
                        api_token=hubstaff_token,
                        org_id=int(org_id) if org_id else None
                    )
                    self.logger.info("✅ Hubstaff client initialized for auto-detection")
            except Exception as e:
                self.logger.warning(f"Hubstaff auto-detection disabled: {e}")
        
        # Load user mapping
        self.user_mapping = self._load_user_mapping()
    
    def _load_user_mapping(self) -> Dict[str, Dict[str, Any]]:
        """Load user mapping from ClickUp IDs to other services."""
        if not self.mapping_path.exists():
            self.logger.info(f"User mapping file not found at {self.mapping_path}. Creating example.")
            self._create_example_mapping()
            return {}
        
        try:
            with open(self.mapping_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading user mapping: {e}")
            return {}
    
    def _create_example_mapping(self):
        """Create example user mapping file."""
        example = {
            "clickup_user_id_or_email": {
                "slack_user_id": "U01234567",
                "github_username": "johndoe",
                "hubstaff_user_id": 12345,
                "repos": [
                    "collegewise1/cw-magento"
                ]
            }
        }
        
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.mapping_path, 'w') as f:
            json.dump(example, f, indent=2)
        
        self.logger.info(f"Created example mapping at {self.mapping_path}. Please edit it with your team mappings.")
    
    def _save_user_mapping(self):
        """Save user mapping to disk."""
        try:
            self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.mapping_path, 'w') as f:
                json.dump(self.user_mapping, f, indent=2)
            self.logger.info(f"💾 Saved updated user mappings to {self.mapping_path}")
        except Exception as e:
            self.logger.error(f"Error saving user mapping: {e}")
    
    def _clickup_api_request(self, method: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Make direct ClickUp API request using curl (for endpoints not in client)."""
        token = os.getenv('CLICKUP_API_TOKEN')
        if not token:
            return None
        
        url = f"https://api.clickup.com/api/v2{endpoint}"
        
        cmd = ["curl", "-sS", "-X", method, "-H", f"Authorization: {token}", "-H", "Content-Type: application/json"]
        
        if data:
            cmd.extend(["-d", json.dumps(data)])
        
        cmd.append(url)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            self.logger.error(f"ClickUp API request error: {e}")
        
        return None
    
    def get_all_teams(self) -> List[Dict[str, Any]]:
        """Get all teams from ClickUp."""
        result = self._clickup_api_request("GET", "/team")
        if result and "teams" in result:
            return result["teams"]
        return []
    
    def get_all_spaces(self, team_id: str) -> List[Dict[str, Any]]:
        """Get all spaces in a team."""
        result = self._clickup_api_request("GET", f"/team/{team_id}/space")
        if result and "spaces" in result:
            return result["spaces"]
        return []
    
    def get_all_lists(self, space_id: str) -> List[Dict[str, Any]]:
        """Get all lists in a space."""
        result = self._clickup_api_request("GET", f"/space/{space_id}/list")
        if result and "lists" in result:
            return result["lists"]
        return []
    
    def get_active_tasks_from_list(self, list_id: str) -> List[Dict[str, Any]]:
        """Get active (non-closed) tasks from a list."""
        if not self.clickup:
            return []
        
        try:
            # Get tasks directly from API to preserve assignee IDs
            result = self._clickup_api_request("GET", f"/list/{list_id}/task?include_closed=false")
            if result and "tasks" in result:
                return result["tasks"]
            
            # Fallback to client if API fails
            tasks = self.clickup.list_tasks(list_id, include_closed=False)
            # Convert ClickUpTask objects to dicts
            task_dicts = []
            for task in tasks:
                task_dict = {
                    "id": task.id,
                    "name": task.name,
                    "status": {"status": task.status},
                    "priority": {"priority": task.priority or 3},
                    "due_date": int(task.date_due.timestamp() * 1000) if task.date_due else None,
                    "url": task.url,
                    "date_created": int(task.date_created.timestamp() * 1000),
                    "date_updated": int(task.date_updated.timestamp() * 1000),
                    "assignees": []  # Will be populated from API response
                }
                task_dicts.append(task_dict)
            return task_dicts
        except Exception as e:
            self.logger.error(f"Error getting tasks from list {list_id}: {e}")
            return []
    
    def get_all_active_tasks(self, team_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all active tasks across all teams/spaces/lists.
        
        Args:
            team_id: Optional team ID to limit search
        
        Returns:
            List of task dictionaries
        """
        if not self.clickup:
            self.logger.warning("ClickUp client not available")
            return []
        
        all_tasks = []
        
        # Get teams
        teams = self.get_all_teams()
        if not teams:
            self.logger.warning("No teams found in ClickUp")
            return []
        
        for team in teams:
            if team_id and team["id"] != team_id:
                continue
            
            team_id_val = team["id"]
            self.logger.info(f"Scanning team: {team.get('name', team_id_val)}")
            
            # Get spaces
            spaces = self.get_all_spaces(team_id_val)
            for space in spaces:
                space_id = space["id"]
                
                # Get lists
                lists = self.get_all_lists(space_id)
                for lst in lists:
                    list_id = lst["id"]
                    tasks = self.get_active_tasks_from_list(list_id)
                    all_tasks.extend(tasks)
                    
                    if tasks:
                        self.logger.debug(f"Found {len(tasks)} active tasks in list: {lst.get('name', list_id)}")
        
        self.logger.info(f"Found {len(all_tasks)} total active tasks")
        return all_tasks
    
    def get_clickup_users(self, team_id: Optional[str] = None) -> Dict[int, ClickUpUser]:
        """Get all ClickUp users from task assignees (since /team/{id}/member endpoint may not be available)."""
        users = {}
        
        # Get all active tasks to extract user info from assignees
        all_tasks = self.get_all_active_tasks(team_id)
        
        # Collect unique assignees with their info
        seen_user_ids = set()
        for task in all_tasks:
            assignees = task.get("assignees", [])
            for assignee in assignees:
                # Handle both dict format {"id": 123, "username": "..."} and direct ID
                if isinstance(assignee, dict):
                    user_id = assignee.get("id")
                    if not user_id:
                        continue
                    try:
                        user_id = int(user_id)
                    except (ValueError, TypeError):
                        continue
                    
                    if user_id not in seen_user_ids:
                        seen_user_ids.add(user_id)
                        users[user_id] = ClickUpUser(
                            id=user_id,
                            username=assignee.get("username", ""),
                            email=assignee.get("email", ""),
                            name=assignee.get("name") or assignee.get("username", f"User {user_id}"),
                            initials=assignee.get("initials", ""),
                            profile_picture=assignee.get("profilePicture") or assignee.get("profile_picture")
                        )
                else:
                    # Just an ID, create minimal user
                    try:
                        user_id = int(assignee)
                        if user_id not in seen_user_ids:
                            seen_user_ids.add(user_id)
                            users[user_id] = ClickUpUser(
                                id=user_id,
                                username=f"user_{user_id}",
                                email="",
                                name=f"User {user_id}",
                                initials="",
                                profile_picture=None
                            )
                    except (ValueError, TypeError):
                        continue
        
        self.logger.info(f"Retrieved {len(users)} ClickUp users from task assignees")
        return users
    
    def detect_team_members(
        self,
        refresh_cache: bool = False,
        max_cache_age_hours: int = 6
    ) -> List[DetectedTeamMember]:
        """
        Detect team members from active ClickUp tasks.
        
        Args:
            refresh_cache: Force refresh even if cache is recent
            max_cache_age_hours: Maximum cache age before refresh
        
        Returns:
            List of detected team members
        """
        # Check cache first
        if not refresh_cache:
            cached = self._load_cache()
            if cached:
                cache_age = (datetime.now() - datetime.fromisoformat(cached.get("cached_at", "2000-01-01"))).total_seconds() / 3600
                if cache_age < max_cache_age_hours:
                    self.logger.info(f"Using cached team members (age: {cache_age:.1f} hours)")
                    return [DetectedTeamMember(**m) for m in cached.get("members", [])]
        
        if not self.clickup:
            self.logger.error("ClickUp client not available for team detection")
            return []
        
        self.logger.info("🔍 Detecting team members from ClickUp active tasks...")
        
        # Get all active tasks
        all_tasks = self.get_all_active_tasks()
        
        # Get ClickUp users
        users = self.get_clickup_users()
        
        # Group tasks by assignee
        assignee_tasks: Dict[int, List[Dict[str, Any]]] = {}
        
        for task in all_tasks:
            assignees = task.get("assignees", [])
            if not assignees:
                continue
            
            for assignee in assignees:
                # Handle both dict format {"id": 123} and direct ID
                assignee_id = assignee.get("id") if isinstance(assignee, dict) else assignee
                if not assignee_id:
                    continue
                
                # Convert to int if possible
                try:
                    assignee_id = int(assignee_id)
                except (ValueError, TypeError):
                    continue
                
                if assignee_id not in assignee_tasks:
                    assignee_tasks[assignee_id] = []
                
                # Extract relevant task info
                status_obj = task.get("status", {})
                priority_obj = task.get("priority", {})
                
                task_info = {
                    "id": task.get("id"),
                    "name": task.get("name"),
                    "status": status_obj.get("status", "") if isinstance(status_obj, dict) else str(status_obj),
                    "priority": priority_obj.get("priority", 3) if isinstance(priority_obj, dict) else (priority_obj or 3),
                    "due_date": task.get("due_date"),
                    "url": task.get("url"),
                    "date_created": task.get("date_created"),
                    "date_updated": task.get("date_updated")
                }
                assignee_tasks[assignee_id].append(task_info)
        
        # Build detected team members
        detected_members = []
        
        for assignee_id, tasks in assignee_tasks.items():
            user = users.get(assignee_id)
            if not user:
                self.logger.warning(f"User {assignee_id} not found in users list")
                continue
            
            # Get priority tasks (high priority or due soon)
            priority_tasks = []
            for task in tasks:
                priority = task.get("priority", 3)
                # Ensure priority is an integer
                try:
                    priority = int(priority) if priority else 3
                except (ValueError, TypeError):
                    priority = 3
                
                due_date = task.get("due_date")
                
                # High priority (1=Urgent, 2=High) or due within 7 days
                is_priority = priority <= 2
                if due_date:
                    try:
                        due_dt = datetime.fromtimestamp(int(due_date) / 1000)
                        days_until = (due_dt - datetime.now()).days
                        is_priority = is_priority or (days_until <= 7 and days_until >= 0)
                    except:
                        pass
                
                if is_priority:
                    priority_tasks.append(task)
            
            # Create detected member
            member = DetectedTeamMember(
                clickup_user_id=assignee_id,
                clickup_username=user.username,
                clickup_name=user.name,
                clickup_email=user.email,
                active_tasks=tasks,
                priority_tasks=priority_tasks
            )
            
            # Apply user mapping
            mapping_key = str(assignee_id)
            if mapping_key not in self.user_mapping:
                # Try email as fallback
                mapping_key = user.email
            
            # Get existing mapping or create new one
            if mapping_key in self.user_mapping:
                mapping = self.user_mapping[mapping_key].copy()
            else:
                mapping = {}
            
            # Auto-detect Slack ID by email if not already mapped
            if not mapping.get("slack_user_id") and user.email and self.slack and self.slack.is_connected:
                try:
                    slack_user = self.slack.get_user_by_email(user.email)
                    if slack_user:
                        mapping["slack_user_id"] = slack_user.id
                        self.logger.info(f"✅ Auto-detected Slack ID for {user.name}: {slack_user.id}")
                except Exception as e:
                    self.logger.debug(f"Could not auto-detect Slack ID for {user.email}: {e}")
            
            # Auto-detect Hubstaff ID by email if not already mapped
            if not mapping.get("hubstaff_user_id") and user.email and self.hubstaff:
                try:
                    hubstaff_id = self.hubstaff.get_user_id_by_email(user.email)
                    if hubstaff_id:
                        mapping["hubstaff_user_id"] = hubstaff_id
                        self.logger.info(f"✅ Auto-detected Hubstaff ID for {user.name}: {hubstaff_id}")
                except Exception as e:
                    self.logger.debug(f"Could not auto-detect Hubstaff ID for {user.email}: {e}")
            
            # Apply mappings to member
            member.slack_user_id = mapping.get("slack_user_id")
            member.github_username = mapping.get("github_username")
            member.hubstaff_user_id = mapping.get("hubstaff_user_id")
            member.repos = mapping.get("repos", [])
            
            # Save updated mapping back (only if we have new data)
            if mapping.get("slack_user_id") or mapping.get("hubstaff_user_id") or mapping.get("github_username"):
                self.user_mapping[mapping_key] = mapping
                # Also save with email as key if different
                if user.email and mapping_key != user.email:
                    self.user_mapping[user.email] = mapping
            
            detected_members.append(member)
        
        # Sort by number of active tasks (most active first)
        detected_members.sort(key=lambda m: len(m.active_tasks), reverse=True)
        
        self.logger.info(f"✅ Detected {len(detected_members)} team members with active tasks")
        
        # Save updated user mappings
        self._save_user_mapping()
        
        # Cache results
        self._save_cache(detected_members)
        
        return detected_members
    
    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """Load cached team members."""
        if not self.cache_path.exists():
            return None
        
        try:
            with open(self.cache_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading cache: {e}")
            return None
    
    def _save_cache(self, members: List[DetectedTeamMember]):
        """Save team members to cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "cached_at": datetime.now().isoformat(),
                "members": [asdict(m) for m in members]
            }
            with open(self.cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2, default=str)
            self.logger.info(f"💾 Cached {len(members)} team members")
        except Exception as e:
            self.logger.error(f"Error saving cache: {e}")
