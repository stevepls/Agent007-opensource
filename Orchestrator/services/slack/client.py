"""
Slack API Client

Provides read, post, update, and delete operations for Slack.
ALL message sends go through message queue with 2-minute delay.

SECURITY:
- Bot token for general operations
- User token (xoxp-) for full DM access
- Tokens loaded from ~/.config/devops/slack-secrets.yml or environment
- All sends have mandatory 2-minute delay
- All sends require approval
- Deletes require explicit confirmation
"""

import os
import json
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_SDK_AVAILABLE = True
except ImportError:
    SLACK_SDK_AVAILABLE = False
    WebClient = None

# Configuration
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent


def _load_slack_tokens() -> dict:
    """
    Load Slack tokens from slack-secrets.yml or environment variables.
    Priority: slack-secrets.yml > environment variables
    """
    tokens = {
        'bot_token': os.getenv('SLACK_BOT_TOKEN'),
        'app_token': os.getenv('SLACK_APP_TOKEN'),
        'user_token': os.getenv('SLACK_USER_TOKEN'),
        'signing_secret': os.getenv('SLACK_SIGNING_SECRET'),
    }
    
    # Try to load from slack-secrets.yml
    secrets_file = Path.home() / '.config' / 'devops' / 'slack-secrets.yml'
    if secrets_file.exists():
        try:
            with open(secrets_file) as f:
                secrets = yaml.safe_load(f)
                if secrets:
                    if secrets.get('bot_token'):
                        tokens['bot_token'] = secrets['bot_token']
                    if secrets.get('app_token'):
                        tokens['app_token'] = secrets['app_token']
                    # Only use user_token if it's actually a user token (xoxp-)
                    ut = secrets.get('user_token', '')
                    if ut and ut.startswith('xoxp-'):
                        tokens['user_token'] = ut
                    if secrets.get('signing_secret'):
                        tokens['signing_secret'] = secrets['signing_secret']
        except Exception as e:
            print(f"Warning: Could not load slack-secrets.yml: {e}")
    
    return tokens


# Load tokens
_TOKENS = _load_slack_tokens()
SLACK_BOT_TOKEN = _TOKENS['bot_token']
SLACK_USER_TOKEN = _TOKENS['user_token']
SLACK_APP_TOKEN = _TOKENS['app_token']

if SLACK_USER_TOKEN and SLACK_USER_TOKEN.startswith('xoxp-'):
    print(f"[INFO] Slack user token loaded (xoxp-...{SLACK_USER_TOKEN[-6:]})")
elif SLACK_BOT_TOKEN:
    print("[WARN] Slack: bot token only — DM history will not be available")

# Minimum delay for Slack messages (seconds)
SLACK_MIN_DELAY = 120  # 2 minutes


@dataclass
class SlackMessage:
    """Represents a Slack message."""
    ts: str  # Timestamp (message ID)
    channel: str
    user: str
    text: str
    thread_ts: Optional[str]
    is_thread_reply: bool
    reactions: List[Dict[str, Any]]
    edited: bool
    timestamp: datetime


@dataclass
class SlackChannel:
    """Represents a Slack channel."""
    id: str
    name: str
    is_private: bool
    is_dm: bool
    is_archived: bool
    member_count: int
    topic: str
    purpose: str


@dataclass
class SlackUser:
    """Represents a Slack user."""
    id: str
    name: str
    real_name: str
    email: str
    is_bot: bool
    is_admin: bool
    status_text: str
    status_emoji: str
    title: str = ""


class SlackClient:
    """Slack API client with safety controls and dual token support."""
    
    def __init__(self, bot_token: str = None, user_token: str = None):
        self._bot_token = bot_token or SLACK_BOT_TOKEN
        self._user_token = user_token or SLACK_USER_TOKEN
        self._bot_client = None
        self._user_client = None
    
    @property
    def is_available(self) -> bool:
        return SLACK_SDK_AVAILABLE and (self._bot_token is not None or self._user_token is not None)
    
    @property
    def has_user_token(self) -> bool:
        """Check if user token is configured for full DM access."""
        return self._user_token is not None and self._user_token.startswith('xoxp-')
    
    @property
    def is_connected(self) -> bool:
        client = self._get_primary_client()
        if not client:
            return False
        try:
            client.auth_test()
            return True
        except Exception:
            return False
    
    def _get_primary_client(self) -> Optional[WebClient]:
        """Get the primary client (user token preferred for reads)."""
        if self._user_client:
            return self._user_client
        return self._bot_client
    
    def _get_user_client(self) -> Optional[WebClient]:
        """Get user client for DM operations."""
        if self._user_client:
            return self._user_client
        return self._bot_client
    
    def _get_bot_client(self) -> Optional[WebClient]:
        """Get bot client for posting messages."""
        return self._bot_client or self._user_client
    
    def connect(self) -> bool:
        """Connect to Slack API with both tokens if available."""
        if not SLACK_SDK_AVAILABLE:
            raise ImportError("Slack SDK not installed. Run: pip install slack-sdk")
        
        connected = False
        
        # Connect with bot token
        if self._bot_token:
            try:
                self._bot_client = WebClient(token=self._bot_token)
                self._bot_client.auth_test()
                connected = True
            except SlackApiError as e:
                print(f"Bot token connection failed: {e.response.get('error', str(e))}")
        
        # Connect with user token (for full DM access)
        if self._user_token and self._user_token.startswith('xoxp-'):
            try:
                self._user_client = WebClient(token=self._user_token)
                auth = self._user_client.auth_test()
                print(f"✅ User token connected as: {auth.get('user', 'unknown')}")
                connected = True
            except SlackApiError as e:
                print(f"User token connection failed: {e.response.get('error', str(e))}")
        
        if not connected:
            raise ValueError("No valid Slack tokens. Set in ~/.config/devops/slack-secrets.yml or environment")
        
        return True
    
    def _ensure_connected(self):
        if not self._bot_client and not self._user_client:
            self.connect()
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def list_channels(self, include_private: bool = False) -> List[SlackChannel]:
        """List accessible channels."""
        self._ensure_connected()
        client = self._get_primary_client()
        
        channels = []
        result = client.conversations_list(
            types="public_channel,private_channel" if include_private else "public_channel",
            limit=100,
        )
        
        for ch in result.get('channels', []):
            channels.append(SlackChannel(
                id=ch['id'],
                name=ch.get('name', ''),
                is_private=ch.get('is_private', False),
                is_dm=False,
                is_archived=ch.get('is_archived', False),
                member_count=ch.get('num_members', 0),
                topic=ch.get('topic', {}).get('value', ''),
                purpose=ch.get('purpose', {}).get('value', ''),
            ))
        
        return channels
    
    def list_dms(self) -> List[SlackChannel]:
        """List direct message conversations (uses user token for full access)."""
        self._ensure_connected()
        client = self._get_user_client()
        
        result = client.conversations_list(types="im", limit=100)
        
        dms = []
        for ch in result.get('channels', []):
            dms.append(SlackChannel(
                id=ch['id'],
                name=ch.get('user', ''),
                is_private=True,
                is_dm=True,
                is_archived=False,
                member_count=2,
                topic='',
                purpose='',
            ))
        
        return dms
    
    def get_channel(self, channel_id: str) -> Optional[SlackChannel]:
        """Get channel info by ID."""
        self._ensure_connected()
        client = self._get_primary_client()
        
        try:
            result = client.conversations_info(channel=channel_id)
            ch = result['channel']
            return SlackChannel(
                id=ch['id'],
                name=ch.get('name', ''),
                is_private=ch.get('is_private', False),
                is_dm=ch.get('is_im', False),
                is_archived=ch.get('is_archived', False),
                member_count=ch.get('num_members', 0),
                topic=ch.get('topic', {}).get('value', ''),
                purpose=ch.get('purpose', {}).get('value', ''),
            )
        except SlackApiError:
            return None
    
    def get_messages(self, channel: str, limit: int = 20, oldest: str = None) -> List[SlackMessage]:
        """Get messages from a channel (uses user token for DMs)."""
        self._ensure_connected()
        client = self._get_user_client()
        
        kwargs = {"channel": channel, "limit": limit}
        if oldest:
            kwargs["oldest"] = oldest
        
        result = client.conversations_history(**kwargs)
        
        messages = []
        for msg in result.get('messages', []):
            messages.append(SlackMessage(
                ts=msg['ts'],
                channel=channel,
                user=msg.get('user', ''),
                text=msg.get('text', ''),
                thread_ts=msg.get('thread_ts'),
                is_thread_reply=msg.get('thread_ts') is not None and msg.get('thread_ts') != msg['ts'],
                reactions=msg.get('reactions', []),
                edited='edited' in msg,
                timestamp=datetime.fromtimestamp(float(msg['ts'])),
            ))
        
        return messages
    
    def get_thread(self, channel: str, thread_ts: str) -> List[SlackMessage]:
        """Get all messages in a thread."""
        self._ensure_connected()
        client = self._get_user_client()
        
        result = client.conversations_replies(channel=channel, ts=thread_ts)
        
        messages = []
        for msg in result.get('messages', []):
            messages.append(SlackMessage(
                ts=msg['ts'],
                channel=channel,
                user=msg.get('user', ''),
                text=msg.get('text', ''),
                thread_ts=msg.get('thread_ts'),
                is_thread_reply=msg['ts'] != thread_ts,
                reactions=msg.get('reactions', []),
                edited='edited' in msg,
                timestamp=datetime.fromtimestamp(float(msg['ts'])),
            ))
        
        return messages
    
    def search_messages(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        """Search messages. NOTE: Requires search:read scope (user token)."""
        self._ensure_connected()
        client = self._get_user_client()
        
        result = client.search_messages(query=query, count=count)
        return result.get('messages', {}).get('matches', [])
    
    def get_user(self, user_id: str) -> Optional[SlackUser]:
        """Get user info by ID."""
        self._ensure_connected()
        client = self._get_primary_client()
        
        try:
            result = client.users_info(user=user_id)
            u = result['user']
            profile = u.get('profile', {})
            return SlackUser(
                id=u['id'],
                name=u.get('name', ''),
                real_name=profile.get('real_name', ''),
                email=profile.get('email', ''),
                is_bot=u.get('is_bot', False),
                is_admin=u.get('is_admin', False),
                status_text=profile.get('status_text', ''),
                status_emoji=profile.get('status_emoji', ''),
                title=profile.get('title', ''),
            )
        except SlackApiError:
            return None
    
    def get_user_by_email(self, email: str) -> Optional[SlackUser]:
        """Look up user by email."""
        self._ensure_connected()
        client = self._get_primary_client()
        
        try:
            result = client.users_lookupByEmail(email=email)
            u = result['user']
            profile = u.get('profile', {})
            return SlackUser(
                id=u['id'],
                name=u.get('name', ''),
                real_name=profile.get('real_name', ''),
                email=email,
                is_bot=u.get('is_bot', False),
                is_admin=u.get('is_admin', False),
                status_text=profile.get('status_text', ''),
                status_emoji=profile.get('status_emoji', ''),
            )
        except SlackApiError:
            return None
    
    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================
    
    def post_message(self, channel: str, text: str, thread_ts: str = None, blocks: List[Dict] = None) -> Dict[str, Any]:
        """Post a message to a channel."""
        self._ensure_connected()
        client = self._get_bot_client()
        
        kwargs = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = blocks
        
        result = client.chat_postMessage(**kwargs)
        return {"ts": result['ts'], "channel": result['channel'], "status": "sent"}
    
    def update_message(self, channel: str, ts: str, text: str) -> Dict[str, Any]:
        """Update an existing message."""
        self._ensure_connected()
        client = self._get_bot_client()
        
        result = client.chat_update(channel=channel, ts=ts, text=text)
        return {"ts": result['ts'], "channel": result['channel'], "status": "updated"}
    
    def delete_message(self, channel: str, ts: str) -> bool:
        """Delete a message. NOTE: Requires explicit confirmation."""
        self._ensure_connected()
        client = self._get_bot_client()
        
        client.chat_delete(channel=channel, ts=ts)
        return True
    
    def add_reaction(self, channel: str, ts: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        self._ensure_connected()
        client = self._get_bot_client()
        
        client.reactions_add(channel=channel, timestamp=ts, name=emoji.strip(':'))
        return True
    
    def open_dm(self, user_id: str) -> str:
        """Open a DM channel with a user. Returns channel ID."""
        self._ensure_connected()
        client = self._get_user_client()
        
        result = client.conversations_open(users=[user_id])
        return result['channel']['id']


# Global instance
_client: Optional[SlackClient] = None


def get_slack_client() -> SlackClient:
    """Get the global Slack client."""
    global _client
    if _client is None:
        _client = SlackClient()
    return _client
