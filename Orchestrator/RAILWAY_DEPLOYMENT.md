# Railway Deployment Checklist

## ✅ What's Already Done

1. **railway.json** - Configured with NIXPACKS builder and health check
2. **Procfile** - Defines how to start the API
3. **requirements.txt** - All dependencies listed
4. **start_api.py** - Entry point script that loads .env and starts uvicorn
5. **Health Check Endpoint** - `/health` endpoint configured in railway.json

## ⚠️ What Needs to Be Done

### 1. Environment Variables in Railway

Set these in Railway dashboard → Your Service → Variables:

#### Required (Core Functionality)
- `ANTHROPIC_API_KEY` - For LLM (Claude) - **REQUIRED**
- `PORT` - Railway sets this automatically, but can override if needed

#### Required (Team Check-in Agent)
- `SLACK_USER_TOKEN` - Slack user token (xoxp-...) - **REQUIRED for team check-in**
- `CLICKUP_API_TOKEN` - ClickUp API token - **REQUIRED for team check-in**

#### Optional (Enhanced Features)
- `OPENAI_API_KEY` - Fallback LLM provider
- `GITHUB_TOKEN` - For GitHub activity checking in team check-in
- `HUBSTAFF_API_TOKEN` - For time tracking in team check-in
- `HUBSTAFF_ORG_ID` - Hubstaff organization ID
- `SLACK_BOT_TOKEN` - Slack bot token (if using bot features)
- `HARVEST_ACCESS_TOKEN` - For Harvest time tracking
- `HARVEST_ACCOUNT_ID` - Harvest account ID

### 2. File System Considerations

The Orchestrator uses local file storage for:
- Message queue data (`data/message_queue/`)
- Team check-in cache (`agents/team_checkin/config/team_cache.json`)
- User mappings (`agents/team_checkin/config/user_mapping.json`)

**Railway Note**: Railway provides ephemeral storage. For production, consider:
- Using Railway's volume mounts for persistent data
- Or migrating to a database (PostgreSQL) for message queue and state

### 3. Slack Secrets File

The team check-in agent loads Slack tokens from:
- `~/.config/devops/slack-secrets.yml` (local)
- Or environment variables (Railway)

**For Railway**: Use environment variables instead of the config file.

### 4. Testing After Deployment

1. Check health endpoint: `https://your-app.railway.app/health`
2. Test team check-in API: `https://your-app.railway.app/team-checkin/members`
3. Verify message queue: `https://your-app.railway.app/team-checkin/messages/pending`

## 🚀 Deployment Steps

1. **Connect Repository to Railway**
   - Link your GitHub repo to Railway
   - Railway will auto-detect the `railway.json` config

2. **Set Environment Variables**
   - Go to Variables tab
   - Add all required variables listed above

3. **Deploy**
   - Railway will automatically build and deploy
   - Uses NIXPACKS to detect Python and install dependencies
   - Runs `Procfile` command to start the API

4. **Monitor**
   - Check logs in Railway dashboard
   - Verify health check passes
   - Test API endpoints

## 📝 Current Status

- ✅ All deployment files ready
- ⚠️  Environment variables need to be set in Railway
- ⚠️  Consider persistent storage for message queue data
- ✅ Health check configured
- ✅ API entry point ready

## 🔧 Procfile Command

```
web: python3 start_api.py
```

This will:
1. Load environment variables from Railway
2. Start uvicorn on the PORT provided by Railway
3. Serve the FastAPI app on `0.0.0.0:$PORT`
