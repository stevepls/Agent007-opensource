# Known Issues & Deferred Work

Last updated: 2026-02-11

## Critical — Secrets Rotation Needed

All API keys in local `.env` files should be rotated as a precaution. Files are untracked (not in git history) but contain plaintext production credentials:

| Service | File |
|---------|------|
| Anthropic, OpenAI, Harvest, Airtable, Zendesk, ClickUp, Slack, Asana, Hubstaff, GitHub | `Orchestrator/.env` |
| Anthropic, OpenAI | `dashboard/.env.local` |
| QuickBooks, Upwork | `Accounting/upwork-sync/.env.production` |
| Airtable, Harvest | `TicketManagement/airtable-fetcher/credentials.env` |

## High — Webhook Server Not Deployed

The Zendesk ↔ ClickUp real-time sync webhook server (`DevOps/webhook-server/`) is not deployed to Railway. Without it, ticket/task sync between Zendesk and ClickUp is manual only (via Orchestrator tools on-demand).

**To deploy:**
1. Add a new service in Railway pointing to `DevOps/webhook-server/`
2. Set env vars: `ZENDESK_EMAIL`, `ZENDESK_API_TOKEN`, `CLICKUP_API_TOKEN`, `WEBHOOK_SECRET`
3. Configure webhook URLs in Zendesk and ClickUp dashboards
4. Note: lives in separate DevOps repo — won't auto-deploy from Agent007 repo

**Generated WEBHOOK_SECRET (not yet used):** set in Railway, Zendesk, and ClickUp when deploying.

## High — SyncAudit Service Disabled

SyncAudit auto-deploys are intentionally disabled. The service has known issues:
- `API_KEY` env var not validated at startup (rejects all requests if missing)
- Health check doesn't verify database connectivity
- Dashboard has broken import (`get_session()` doesn't exist — should be `get_db_session()`)
- No query `limit` validation (DoS risk)

## Medium — Remaining Code Issues

| Issue | Location | Status |
|-------|----------|--------|
| Debug endpoints exposed in production | `Orchestrator/api.py:729-768` | Open |
| `SERVICE_API_KEY` defaults to empty string | `Orchestrator/api.py:177` | Open |
| Session cookie not cryptographically verified | `dashboard/middleware.ts:46-54` | Open |
| Hardcoded staging URLs in CORS/redirects | `Orchestrator/api_auth.py:47-61` | Open |
| No CSRF protection on approve/cancel routes | `dashboard/app/api/agent/` | Open |
| Bare `except:` clauses swallowing errors | `Orchestrator/services/notification_hub.py` | Open |
| Race condition in `/api/approve` (no deduplication) | `Orchestrator/api.py:812` | Open |
| No timeout on streaming responses | `Orchestrator/api_chat.py:889` | Open |
| DB connection pool too small for production | `SyncAudit/models/database.py:28` | Open |

## Resolved — 2026-02-11

- SQL injection in database client (`Orchestrator/services/database/client.py`) — fixed with identifier validation + parameterized queries
- Webhook signature verification bypass (`DevOps/webhook-server/server.py`) — fixed, `WEBHOOK_SECRET` now required
- Health check config exposure in webhook server — removed
- Naive `datetime.now()` in orchestrator task descriptions — fixed to UTC
- Agent had no tool to check current time mid-task — added `get_current_datetime` tool
- GitHub Actions deploy workflow deprecated — Railway native deploys enabled
