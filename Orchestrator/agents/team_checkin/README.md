# Team Check-in and Time Tracking Agent

An automated agent that handles team check-ins, activity monitoring, and time tracking enforcement. It runs periodically during work hours (8 AM - 5 PM EST, weekdays) and sends personalized messages from your Slack account.

## Features

- **Morning Greetings**: Sends personalized morning check-ins with task priorities and updates
- **Activity Monitoring**: Checks GitHub commits and Slack messages to detect team activity
- **Smart Follow-ups**: Sends follow-up messages when team members are quiet
- **Time Tracking**: Automatically starts/stops Hubstaff timers based on activity
- **Task Integration**: Pulls task priorities and updates from ClickUp/Zendesk
- **LLM-Powered Messages**: Uses Claude (with OpenAI fallback) to generate natural, personalized messages
- **Message Approval**: Review and approve messages before sending via web UI
- **Manual Triggers**: Manually trigger follow-ups or morning check-ins on demand

## Setup

### 1. Install Dependencies

```bash
cd /home/steve/Agent007/Orchestrator/agents/team_checkin
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file or set the following environment variables:

```bash
# Slack Configuration (REQUIRED)
export SLACK_USER_TOKEN="xoxp-your-user-token-here"  # Personal user token, not bot token

# GitHub Configuration (REQUIRED for activity checking)
export GITHUB_TOKEN="ghp_your-github-token-here"

# LLM Configuration (REQUIRED)
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
export OPENAI_API_KEY="sk-your-key-here"  # Fallback

# Hubstaff Configuration (REQUIRED for time tracking)
export HUBSTAFF_API_TOKEN="your-hubstaff-token-here"
export HUBSTAFF_ORG_ID="12345"  # Optional

# ClickUp Configuration (OPTIONAL, for task priorities)
export CLICKUP_API_TOKEN="your-clickup-token-here"

# Zendesk Configuration (OPTIONAL)
export ZENDESK_EMAIL="your-email@example.com"
export ZENDESK_API_TOKEN="your-zendesk-token-here"
export ZENDESK_SUBDOMAIN="your-subdomain"
```

### 3. Configure Team Member Mappings

The agent can **auto-detect team members** from ClickUp active tasks. You just need to map ClickUp users to their Slack/GitHub/Hubstaff IDs.

Create the user mapping file:

```bash
cp config/user_mapping.json.example config/user_mapping.json
```

Edit `config/user_mapping.json` with mappings. You can use either ClickUp user ID or email as the key:

```json
{
  "12345": {
    "slack_user_id": "U01234567",
    "github_username": "johndoe",
    "hubstaff_user_id": 12345,
    "repos": ["collegewise1/cw-magento"]
  },
  "john.doe@example.com": {
    "slack_user_id": "U01234567",
    "github_username": "johndoe",
    "hubstaff_user_id": 12345
  }
}
```

**Note:** The agent will automatically:
- Detect team members who have active tasks assigned in ClickUp
- Pull their priority tasks and due dates
- Cache the results for performance
- Only include members who have at least one mapping (Slack, GitHub, or Hubstaff)

### 4. Manual Team Configuration (Optional)

If you prefer manual configuration or want to override auto-detection, copy the example config:

```bash
cp config/team.json.example config/team.json
```

Edit `config/team.json` with your team members:

```json
[
  {
    "name": "John Doe",
    "slack_user_id": "U01234567",
    "github_username": "johndoe",
    "hubstaff_user_id": 12345,
    "clickup_user_id": "abc123",
    "priority_tasks": [
      {
        "name": "Implement user authentication",
        "due_date": "2026-02-10",
        "reason": "Blocking other features",
        "task_id": "task_123"
      }
    ],
    "current_task_id": "task_123",
    "repos": [
      "collegewise1/cw-magento",
      "collegewise1/api-service"
    ]
  }
]
```

**Field Descriptions:**
- `name`: Team member's name
- `slack_user_id`: Slack user ID (find in Slack profile URL or via API)
- `github_username`: GitHub username for activity checking
- `hubstaff_user_id`: Hubstaff user ID (numeric)
- `clickup_user_id`: ClickUp user ID (optional, auto-detected if not provided)
- `priority_tasks`: Array of priority tasks with due dates (auto-populated from ClickUp)
- `current_task_id`: Current active task ID for time tracking
- `repos`: List of GitHub repos to monitor (format: `owner/repo`)

**Auto-Detection vs Manual Config:**
- **Auto-detection (recommended)**: Agent scans ClickUp for active tasks and automatically includes assignees
- **Manual config**: Use `team.json` for full control or to override auto-detection
- Use `--no-auto-detect` flag to disable auto-detection
- Use `--refresh-team-cache` to force refresh of cached team members

### 4. Get Required Tokens

#### Slack User Token
1. Go to https://api.slack.com/apps
2. Create a new app or use existing
3. Go to "OAuth & Permissions"
4. Add scopes: `chat:write`, `im:write`, `im:read`, `users:read`
5. Install to workspace
6. Copy the "User OAuth Token" (starts with `xoxp-`)

#### GitHub Token
1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Scopes: `repo` (for private repos) or `public_repo` (for public only)

#### Hubstaff Token
1. Go to Hubstaff dashboard
2. Navigate to Settings → API
3. Generate API token
4. Note your Organization ID if needed

#### ClickUp Token
1. Go to ClickUp Settings → Apps → API
2. Generate API token

## Message Approval System

**All messages are queued for approval before sending!**

The agent includes a web-based approval system where you can:
- Review generated messages before they're sent
- Approve or reject messages
- Manually trigger follow-ups or morning check-ins

### Accessing the Approval UI

1. **Start the API server** (if not already running):
   ```bash
   cd /home/steve/Agent007/Orchestrator
   python start_api.py
   ```

2. **Open the approval UI**:
   - Option 1: Open `agents/team_checkin/approval_ui.html` directly in your browser
   - Option 2: Serve it via Python: `python -m http.server 8080` then open `http://localhost:8080/approval_ui.html`

3. **Review and approve messages**:
   - Messages appear automatically when generated
   - Click "Approve & Send" to send immediately
   - Click "Reject" to discard

### Manual Triggers

Use the UI buttons or API to manually trigger:
- **Trigger Follow-up**: Check quiet members and generate follow-up messages
- **Trigger Morning Check-in**: Send morning greetings to all members

See `README_APPROVAL.md` for detailed API documentation.

## Usage

### One-Time Run (for Cron/Systemd)

Run the agent once (useful for cron jobs):

```bash
python main.py
```

### Long-Running Daemon

Run as a daemon that checks every 2 hours:

```bash
python main.py --daemon
```

With custom interval:

```bash
python main.py --daemon --interval 1.5  # Check every 1.5 hours
```

### Custom Configuration

```bash
python main.py --config /path/to/team.json --state /path/to/state.json
```

## Scheduling with Cron

Add to your crontab to run every 2 hours during work hours:

```bash
# Edit crontab
crontab -e

# Add this line (runs every 2 hours from 8 AM to 5 PM EST, weekdays)
0 8-17/2 * * 1-5 cd /home/steve/Agent007/Orchestrator/agents/team_checkin && /usr/bin/python3 main.py >> logs/cron.log 2>&1
```

## Scheduling with Systemd

Create a systemd service:

```ini
# /etc/systemd/system/team-checkin.service
[Unit]
Description=Team Check-in Agent
After=network.target

[Service]
Type=simple
User=steve
WorkingDirectory=/home/steve/Agent007/Orchestrator/agents/team_checkin
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 main.py --daemon
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable team-checkin.service
sudo systemctl start team-checkin.service
```

## Auto-Detection

The agent can automatically detect team members from ClickUp:

1. **Scans ClickUp** for all active (non-closed) tasks across all teams/spaces/lists
2. **Extracts assignees** from those tasks
3. **Maps to other services** using `user_mapping.json` (Slack, GitHub, Hubstaff)
4. **Identifies priority tasks** (high priority or due within 7 days)
5. **Caches results** for 6 hours (configurable)

**Benefits:**
- No manual team configuration needed
- Always up-to-date with current task assignments
- Automatically includes/excludes people based on active work
- Priority tasks are automatically identified

**Cache Management:**
- Cache is stored in `config/team_cache.json`
- Refreshes automatically every 6 hours
- Use `--refresh-team-cache` to force immediate refresh
- Use `--no-auto-detect` to disable and use manual config only

## How It Works

### Morning Check-in (8-9 AM EST)

1. Checks if this is the first run of the day
2. For each team member:
   - Generates personalized morning greeting using LLM
   - Includes priority tasks with due dates
   - Asks for updates on urgent tasks
   - Sends via Slack DM (appears as from you, not a bot)
   - Starts Hubstaff timer
   - Updates ClickUp task status to "in progress"

### Follow-up Check-ins (Every 2 Hours)

1. Checks for recent activity:
   - GitHub commits in monitored repos
   - Slack messages/DMs
2. If activity found → skip member for this cycle
3. If quiet AND no response to previous nudge:
   - Generates follow-up message using LLM
   - Sends via Slack DM
4. If no response after 2+ hours:
   - Stops Hubstaff timer automatically

### State Management

The agent maintains state in `config/state.json`:
- `last_nudged`: When member was last messaged
- `last_activity`: When member was last active
- `timer_stopped`: Whether timer was stopped today
- `responded_today`: Whether member responded today
- `morning_greeting_sent`: Whether morning greeting was sent today
- `done_for_today`: Whether member indicated they're done

## Customization

### Message Style

Edit the LLM prompts in `agent.py`:
- `_generate_morning_message()`: Morning greeting prompt
- `_generate_followup_message()`: Follow-up message prompt

### Work Hours

Edit in `agent.py`:
```python
WORK_START_HOUR = 8  # 8 AM
WORK_END_HOUR = 17    # 5 PM
CHECK_INTERVAL_HOURS = 2  # Every 2 hours
```

### Activity Check Window

Edit in `agent.py`:
```python
def _check_github_activity(self, member: TeamMember, hours: int = 3):
    # Check last 3 hours of activity
```

## Troubleshooting

### Messages Not Sending

- Check `SLACK_USER_TOKEN` is set correctly (must be user token, not bot token)
- Verify token has required scopes
- Check logs in `logs/agent.log`

### GitHub Activity Not Detected

- Verify `GITHUB_TOKEN` has `repo` scope
- Check `github_username` matches actual GitHub username
- Ensure repos are in correct format: `owner/repo`

### Hubstaff Timer Not Starting/Stopping

- Verify `HUBSTAFF_API_TOKEN` is correct
- Check `hubstaff_user_id` matches actual user ID
- Check Hubstaff API permissions

### LLM Errors

- Verify API keys are set
- Check API rate limits
- Fallback to OpenAI should work automatically

## Logs

Logs are written to:
- Console (stdout)
- `logs/agent.log` (file)

View recent logs:
```bash
tail -f logs/agent.log
```

## Security Notes

- **Never commit** `.env` or `config/team.json` to version control
- Use environment variables or secure secret management
- User tokens have full access - keep them secure
- Consider using a dedicated Slack app with minimal scopes

## License

Part of the Agent007 project.
