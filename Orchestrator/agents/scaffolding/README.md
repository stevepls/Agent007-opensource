# Project Task Scaffolding Agent

**SME agent** that pulls tasks from ClickUp and implements them with code + sandbox validation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ ScaffoldingAgent (Python)                                       │
│ ────────────────────────────────────────────────────────────────│
│ 1. Pull tasks from ClickUp (status: "Pending AI Scaffolding")   │
│ 2. Analyze with LLM (urgency, action items, branch prefix)      │
│ 3. Create branch (prefix/TICKET-ID)                             │
│ 4. Generate code + sandbox commands                             │
│ 5. Write code to files                                           │
│ 6. Run sandbox (composer, bin/magento, npm validation)          │
│ 7. Commit + push branch                                          │
│ 8. Update ClickUp with results                                   │
│ 9. Track time in Hubstaff (optional)                            │
└───────────────┬─────────────────────────────────────────────────┘
                │
                ├──► DevOps/sandbox/ (LocalDockerRunner)
                │    └─► Docker container (agent-sandbox-magento2)
                │        - PHP 8.2 + Magento extensions
                │        - Composer 2 with auth.json mounted
                │        - Node/npm, MySQL client, jq
                │        - Executes: commands.json → output.json
                │
                └──► DevOps/sandbox/ (GitHubActionsRunner) [Phase 3]
                     └─► GHA workflow (same Dockerfile + MySQL/ES services)
```

## Completed Test — Phyto Project

| Ticket | Code Generated | Sandbox Ran | Result |
|---|---|---|---|
| **PHY-6** Header Search | 3 files, 391 lines (LESS, phtml) | ✅ PHP syntax + LESS validated | Ready for review |
| **PHY-5** USPS Shipping | 6 files, 289 lines (full M2 module) | ✅ PHP validated | Ready for staging |
| **PHY-4** FishPig WP Integration | 4 files + `composer require fishpig/...` | ✅ Composer installed package (250s) | Installed, needs WP setup |
| **PHY-2** OpenTelemetry | 4 files, 156 lines (M2 module) | ⚠️ HTTP transport (gRPC needs ext-grpc) | Working, use HTTP |

All tickets:
- Have branches on GitHub with commits
- Include ClickUp comments with: work summary, files changed, sandbox results, manual steps, agent/model attribution
- Moved to "to do" status

## Configuration

### Project Setup (`config.py`)

```python
PROJECT_CONFIGS = {
    "phyto": {
        "name": "Phyto-PDXAromatics",
        "clickup_list_id": "901109466310",
        "github_repo": "pdxaromatics/magento2",
        "github_ssh_url": "git@github.com:pdxaromatics/magento2.git",
        "local_path": "/home/steve/Sites/phyto/phytom2-repo",
        "default_branch": "main",
        "stack": ["php", "magento2", "mysql", "elasticsearch"],
        "status_pending": "pending ai scaffolding",
        "status_done": "to do",
        "hubstaff_project_id": None,  # Optional: for time tracking
        "hubstaff_user_id": None,
    },
}
```

### Environment Variables

Required in `.env`:
- `CLICKUP_API_TOKEN` — ClickUp API access
- `ANTHROPIC_API_KEY` — LLM for task analysis + code generation
- `COMPOSER_AUTH` — JSON with Magento marketplace keys (auto-mounted from project's `auth.json`)

Optional:
- `HUBSTAFF_API_TOKEN` + `HUBSTAFF_USER_ID` — Time tracking per task
- `SANDBOX_RUNNER=local` (default) or `github` (Phase 3)

## Usage

```bash
cd /home/steve/Agent007/Orchestrator

# Preview pending tasks
python3 -m agents.scaffolding.main --project phyto --dry-run

# Run once for phyto
python3 -m agents.scaffolding.main --project phyto

# Run for all projects
python3 -m agents.scaffolding.main --all

# Run as scheduler (every 15 minutes)
python3 -m agents.scaffolding.main --schedule --interval 900

# Get JSON output
python3 -m agents.scaffolding.main --project phyto --json
```

## Sandbox

**Location:** `DevOps/sandbox/` (shared infrastructure)

### Local Docker Runner (Active)

- **Image:** `agent-sandbox-magento2` (975MB)
- **Runtime:** Ephemeral container per task, auto-destroyed
- **Mounts:** `/workspace` (project repo), `/task` (commands.json), `/results` (output.json)
- **Auth:** Auto-mounts `auth.json` from project or `~/.config/composer/auth.json`
- **Limits:** 4 CPU, 4GB RAM, 10 min timeout
- **Extensions:** All Magento extensions + ext-grpc (building)
- **Filters:** System files (`generated/`, `var/`, `pub/.htaccess`, `.user.ini`, `vendor/`) excluded from commits

### GitHub Actions Runner (Phase 3 — Ready)

- **Workflow:** `DevOps/sandbox/workflows/sandbox.yml`
- **Services:** MySQL 8.0, Elasticsearch 7.17
- **Trigger:** `workflow_dispatch` from agent
- **Artifacts:** Downloads `sandbox-results` artifact with output.json
- **Same Dockerfile:** Identical execution environment

## Files Created

```
Orchestrator/agents/scaffolding/
├── __init__.py                    # Package API
├── agent.py                       # ScaffoldingAgent class (1000+ lines)
├── config.py                      # Project configs
├── main.py                        # CLI + scheduler
└── sandbox/
    └── __init__.py                # Re-exports from DevOps/sandbox/

DevOps/sandbox/                    # Shared infrastructure
├── __init__.py                    # Package API
├── Dockerfile.magento2            # Sandbox image (PHP 8.2, Composer, ext-grpc)
├── entrypoint.sh                  # commands.json executor with filtering
├── runner.py                      # Abstract + LocalDockerRunner (350 lines)
├── github_runner.py               # GitHubActionsRunner (250 lines)
└── workflows/
    └── sandbox.yml                # GHA workflow template

Orchestrator/docs/
└── PHYTO_TEAM_MIGRATION_GUIDE.md # Team guide for Bitbucket → GitHub switch
```

## Branch Naming Convention

Format: `prefix/CUSTOM-TASK-ID`

Prefixes determined by LLM analysis or keywords:
- `bugfix` — bugs, fixes, errors, crashes, issues
- `feature` — new features, additions, implementations
- `update` — changes, modifications, adjustments
- `upgrade` — version upgrades, migrations
- `hotfix` — urgent, critical, emergency
- `project` — setup, configuration, initialization

Examples:
- `update/PHY-6` — Header search styling update
- `feature/PHY-5` — USPS shipping feature
- `feature/PHY-4` — FishPig integration

## Smart Branch Handling

If branch already exists:
1. **LLM analyzes** existing commits vs. ticket requirements
2. **"covers"** — Reuses branch, comments on ticket, moves to "to do"
3. **"partial"** — Creates versioned branch (`-v2`, `-v3`)
4. **"unrelated"** — Creates versioned branch

## Lock System

One instance per project using `fcntl` file locks:
- Lock file: `/tmp/scaffolding-agent-locks/{project_key}.lock`
- Contains PID of running instance
- Prevents concurrent runs on same project
- Auto-released on completion or crash

## ClickUp Comment Format

```markdown
🌿 **Scaffolding complete**

Branch: `feature/PHY-5`
Link: https://github.com/pdxaromatics/magento2/tree/feature/PHY-5

**Summary:** Implement conditional USPS shipping logic...

**Work done:**
Created custom USPS shipping module...

**Sandbox (local-docker):** ✅ passed
  ✅ `install_deps` (45s)
  ❌ `bin_magento` (2s) — needs database

**Files changed:**
  - `app/code/Pls/UspsShipping/Model/Carrier/Usps.php`
  - `app/code/Pls/UspsShipping/etc/config.xml`
  ...

---
_Agent: ScaffoldingAgent/phyto | Model: claude-sonnet-4-20250514_
```

## Sandbox Build

```bash
cd /home/steve/Agent007/DevOps/sandbox

# Build (first time: ~10 min with ext-grpc)
docker build -t agent-sandbox-magento2 -f Dockerfile.magento2 .

# Test
docker run --rm \
  -v /path/to/repo:/workspace:rw \
  -v /tmp/task:/task:ro \
  -v /tmp/results:/results:rw \
  agent-sandbox-magento2
```

**Current build:** Running in background (~10 min for ext-grpc). The existing image works for all tasks — ext-grpc only needed for OpenTelemetry with gRPC transport (HTTP transport works without it).

## Migration to GitHub Actions (Phase 3)

When ready:
1. Copy `DevOps/sandbox/` to each project repo as `.github/sandbox/`
2. Copy `DevOps/sandbox/workflows/sandbox.yml` to `.github/workflows/`
3. Set `SANDBOX_RUNNER=github` environment variable
4. Agent automatically switches to GHA runner (MySQL + ES included)

## Next Steps

- ✅ Scaffold working locally with Docker
- 🔄 ext-grpc building (~10 min, optional)
- ⏳ Add more projects to `config.py`
- ⏳ Set up cron/systemd for 15-minute intervals
- ⏳ Move to VPS for always-on operation
- ⏳ Port to GitHub Actions for heavy builds

---

**Status:** Production-ready for local use. Tested on 4 Phyto tickets with real Magento 2 codebase.
