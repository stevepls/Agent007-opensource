# Security & Infrastructure Review — February 11, 2026

## Summary

Full codebase review of Agent007 covering Orchestrator, Dashboard, SyncAudit, DevOps webhook server, and infrastructure config.

## Fixes Applied

### SQL Injection in Database Client
- **File:** `services/database/client.py` lines 632-672
- **Fix:** Added `_validate_identifier()` regex validation for table names. PostgreSQL queries now use parameterized `:table_name` bind params. MySQL/SQLite use validated identifiers.

### Webhook Signature Bypass
- **File:** `DevOps/webhook-server/server.py` lines 54-56, 444-447
- **Fix:** `WEBHOOK_SECRET` is now required at startup. Removed `if not secret: return True` bypass. Removed config leakage from `/health` endpoint.

### Reliable Date/Time for Agent
- **Files:** `services/tool_registry.py`, `crews/orchestrator_crew.py`, `api_chat.py`
- **Fix:** Registered `get_current_datetime` tool returning UTC, local time, timezone, day of week, and ISO week. Added TIME AWARENESS rules to backstory and system prompt. Fixed naive `datetime.now()` to timezone-aware UTC.

### Railway Deployment
- **File:** `.github/workflows/deploy-railway.yml`
- **Fix:** Deprecated GitHub Actions workflow. Moved to Railway native GitHub integration for auto-deploys (Orchestrator, Dashboard). Webhook server deploy deferred.

## Open Issues

See `/KNOWN_ISSUES.md` at repo root for the full tracking list.

### High Priority (next session)
1. Remove debug endpoints (`api.py:729-768`)
2. Make `SERVICE_API_KEY` mandatory (`api.py:177`)
3. Add cryptographic signing to dashboard session cookie (`middleware.ts:46-54`)
4. Fix hardcoded staging domains in CORS/redirects (`api_auth.py:47-61`)

### Deferred
- Webhook server deployment to Railway (not critical — manual sync available)
- SyncAudit service fixes (disabled for now)
- CSRF protection on dashboard approve/cancel routes
- Streaming response timeouts
- Bare except clause cleanup
