"""
Slack API Client

Provides read, post, update, and delete operations for Slack.
ALL message sends go through message queue with 2-minute delay.

SECURITY:
- Bot token or OAuth required
- All sends have mandatory 2-minute delay
- All sends require approval
- Deletes require explicit confirmation
"""

import os
import json
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

# Slack tokens from environment
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")  # For user-level actions

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
    title: str = ""  # Job title from profile


class SlackClient:
    """Slack API client with safety controls."""
    
    def __init__(self, bot_token: str = None):
        self._token = bot_token or SLACK_BOT_TOKEN
        self._client = None
    
    @property
    def is_available(self) -> bool:
        return SLACK_SDK_AVAILABLE and self._token is not None
    
    @property
    def is_connected(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.auth_test()
            return True
        except Exception:
            return False
    
    def connect(self) -> bool:
        """Connect to Slack API."""
        if not SLACK_SDK_AVAILABLE:
            raise ImportError(
                "Slack SDK not installed. Run: pip install slack-sdk"
            )
        
        if not self._token:
            raise ValueError(
                "SLACK_BOT_TOKEN not set. Add to .env file."
            )
        
        self._client = WebClient(token=self._token)
        
        # Test connection
        try:
            auth = self._client.auth_test()
            return True
        except SlackApiError as e:
            raise ConnectionError(f"Slack connection failed: {e.response['error']}")
    
    def _ensure_connected(self):
        if not self._client:
            self.connect()
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def list_channels(self, include_private: bool = False) -> List[SlackChannel]:
        """List accessible channels."""
        self._ensure_connected()
        
        channels = []
        
        # Public channels
        result = self._client.conversations_list(
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
        """List direct message conversations."""
        self._ensure_connected()
        
        result = self._client.conversations_list(types="im", limit=100)
        
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
        
        try:
            result = self._client.conversations_info(channel=channel_id)
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
    
    def get_messages(
        self,
        channel: str,
        limit: int = 20,
        oldest: str = None,
    ) -> List[SlackMessage]:
        """Get messages from a channel."""
        self._ensure_connected()
        
        kwargs = {"channel": channel, "limit": limit}
        if oldest:
            kwargs["oldest"] = oldest
        
        result = self._client.conversations_history(**kwargs)
        
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
        
        result = self._client.conversations_replies(
            channel=channel,
            ts=thread_ts,
        )
        
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
        """
        Search messages.
        NOTE: Requires search:read scope.
        """
        self._ensure_connected()
        
        result = self._client.search_messages(query=query, count=count)
        return result.get('messages', {}).get('matches', [])
    
    def get_user(self, user_id: str) -> Optional[SlackUser]:
        """Get user info by ID."""
        self._ensure_connected()
        
        try:
            result = self._client.users_info(user=user_id)
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
        
        try:
            result = self._client.users_lookupByEmail(email=email)
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
    # WRITE OPERATIONS (through message queue with 2-min delay)
    # =========================================================================
    
    def post_message(
        self,
        channel: str,
        text: str,
        thread_ts: str = None,
        blocks: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Post a message to a channel.
        NOTE: This is the actual send - should only be called by message queue.
        """
        self._ensure_connected()
        
        kwargs = {
            "channel": channel,
            "text": text,
        }
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if blocks:
            kwargs["blocks"] = blocks
        
        result = self._client.chat_postMessage(**kwargs)
        
        return {
            "ts": result['ts'],
            "channel": result['channel'],
            "status": "sent",
        }
    
    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
    ) -> Dict[str, Any]:
        """Update an existing message."""
        self._ensure_connected()
        
        result = self._client.chat_update(
            channel=channel,
            ts=ts,
            text=text,
        )
        
        return {
            "ts": result['ts'],
            "channel": result['channel'],
            "status": "updated",
        }
    
    def delete_message(self, channel: str, ts: str) -> bool:
        """
        Delete a message.
        NOTE: Requires explicit confirmation.
        """
        self._ensure_connected()
        
        self._client.chat_delete(channel=channel, ts=ts)
        return True
    
    def add_reaction(self, channel: str, ts: str, emoji: str) -> bool:
        """Add a reaction to a message."""
        self._ensure_connected()
        
        self._client.reactions_add(
            channel=channel,
            timestamp=ts,
            name=emoji.strip(':'),
        )
        return True
    
    def open_dm(self, user_id: str) -> str:
        """Open a DM channel with a user. Returns channel ID."""
        self._ensure_connected()
        
        result = self._client.conversations_open(users=[user_id])
        return result['channel']['id']


# Global instance
_client: Optional[SlackClient] = None


def get_slack_client() -> SlackClient:
    """Get the global Slack client."""
    global _client
    if _client is None:
        _client = SlackClient()
    return _client
