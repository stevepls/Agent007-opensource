# Railway Environment Variables Setup Scripts

Two scripts to help you set environment variables in Railway:

## 1. Interactive Setup (`setup_railway_env.sh`)

Full-featured interactive script that guides you through setting variables.

### Usage:

```bash
# Interactive mode (default)
./scripts/setup_railway_env.sh

# Read from .env file
./scripts/setup_railway_env.sh --from-env

# Read from specific .env file
./scripts/setup_railway_env.sh --from-env /path/to/.env

# Auto mode (only sets variables found in .env, no prompts)
./scripts/setup_railway_env.sh --auto
```

### Features:
- ✅ Checks Railway CLI installation
- ✅ Verifies login status
- ✅ Links to Railway project if needed
- ✅ Interactive prompts for missing values
- ✅ Reads from .env file
- ✅ Sets required and optional variables
- ✅ Color-coded output

## 2. Quick Setup (`setup_railway_env_quick.sh`)

Fast script that reads from .env and sets all variables in one command.

### Usage:

```bash
# Use default .env file
./scripts/setup_railway_env_quick.sh

# Use custom .env file
./scripts/setup_railway_env_quick.sh /path/to/.env
```

### Features:
- ✅ Quick one-command setup
- ✅ Reads all variables from .env
- ✅ Sets them all at once
- ✅ Minimal output

## Prerequisites

1. **Install Railway CLI:**
   ```bash
   # macOS/Linux
   curl -fsSL https://railway.app/install.sh | sh
   
   # Or via npm
   npm i -g @railway/cli
   ```

2. **Login to Railway:**
   ```bash
   railway login
   ```

3. **Link to your project:**
   ```bash
   cd Orchestrator
   railway link
   ```

## Required Variables

These must be set for the Orchestrator to work:

- `ANTHROPIC_API_KEY` - Claude LLM API key
- `SLACK_USER_TOKEN` - Slack user token (xoxp-...)
- `CLICKUP_API_TOKEN` - ClickUp API token

## Optional Variables

- `OPENAI_API_KEY` - Fallback LLM
- `GITHUB_TOKEN` - GitHub activity checking
- `HUBSTAFF_API_TOKEN` - Time tracking
- `HUBSTAFF_ORG_ID` - Hubstaff org ID
- `SLACK_BOT_TOKEN` - Slack bot token
- `HARVEST_ACCESS_TOKEN` - Harvest integration
- `HARVEST_ACCOUNT_ID` - Harvest account ID
- `DEFAULT_MODEL` - Default LLM model
- `REQUIRE_APPROVAL` - Require approval for file writes

## Example Workflow

1. **Create .env file** (if you don't have one):
   ```bash
   cp env.example .env
   # Edit .env with your values
   ```

2. **Run quick setup:**
   ```bash
   ./scripts/setup_railway_env_quick.sh
   ```

3. **Verify variables:**
   ```bash
   railway variables
   ```

4. **View specific variable:**
   ```bash
   railway variables --kv | grep ANTHROPIC_API_KEY
   ```

## Troubleshooting

### "Railway CLI not found"
Install it: https://docs.railway.app/develop/cli

### "Not logged in"
Run: `railway login`

### "No linked project found"
Run: `railway link` and select your project

### "Failed to set variable"
- Check that you're logged in: `railway whoami`
- Verify project link: `ls -la .railway`
- Check variable name and value are correct

## Manual Setup (Alternative)

If you prefer to set variables manually:

```bash
railway variables --set "ANTHROPIC_API_KEY=your-key"
railway variables --set "SLACK_USER_TOKEN=xoxp-your-token"
railway variables --set "CLICKUP_API_TOKEN=pk_your-token"
# ... etc
```

Or use the Railway dashboard:
1. Go to your project
2. Select your service
3. Go to Variables tab
4. Add variables manually
