# SyncAudit

Universal sync audit service for tracking data flow between any source and target systems. Provides visibility, comparison, and mismatch detection for multi-project integrations.

## Features

- **Universal Schema**: Works with any project (WooCommerce→Acuity, Shopify→NAV, Magento→Odoo, etc.)
- **REST API**: Full CRUD + agent-optimized endpoints for LLM consumption
- **Streamlit Dashboard**: Real-time visualization of sync health
- **Field Comparison**: Automatic mismatch detection with severity levels
- **WordPress Integration**: Drop-in plugin for WooCommerce sites
- **Agent-Friendly**: Designed for AI agent queries (CrewAI, LangChain, etc.)

## Quick Start

### 1. Install Dependencies

```bash
cd SyncAudit
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp env.example .env
# Edit .env with your settings
```

### 3. Start the API

```bash
python run_api.py
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 4. Start the Dashboard

```bash
python run_dashboard.py
# Dashboard at http://localhost:8501
```

## API Endpoints

### Events

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/events` | POST | Log a new sync event |
| `/api/events` | GET | List events with filters |
| `/api/events/{id}` | GET | Get single event details |

### Comparison

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/compare/{source_id}` | GET | Compare source vs target data |
| `/api/mismatches` | GET | Get all records with mismatches |

### Statistics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stats` | GET | Summary stats for a project |

### Agent-Optimized

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/summary` | GET | Concise summary for LLM consumption |
| `/api/agent/diagnose/{source_id}` | GET | Full diagnosis of a record |

## WordPress Integration

### Installation (APDriving)

1. Copy files to your WordPress site:
   ```bash
   cp integrations/wordpress/*.php /path/to/wp-content/mu-plugins/
   ```

2. Add to `wp-config.php`:
   ```php
   define('SYNC_AUDIT_API_URL', 'http://localhost:8000');
   define('SYNC_AUDIT_API_KEY', 'your-api-key');
   define('SYNC_AUDIT_PROJECT', 'apdriving');
   ```

3. Hooks are automatically registered for:
   - `woocommerce_order_status_completed`
   - `woocommerce_order_status_processing`
   - `pls_booking_before_acuity_sync`
   - `pls_booking_after_acuity_sync`
   - `pls_booking_sync_failed`

### WP-CLI Commands

```bash
# Verify a single order
wp syncaudit verify 12345

# Verify all orders from last 7 days
wp syncaudit verify-all --days=7
```

## Agent Usage

### Python Client

```python
from utils.agent_client import SyncAuditClient

client = SyncAuditClient("http://localhost:8000")

# Get summary
summary = client.get_summary(project="apdriving")
print(client.format_for_llm(summary))

# Diagnose specific order
diagnosis = client.diagnose("12345", project="apdriving")

# Find mismatches
mismatches = client.get_mismatches(project="apdriving")
```

### CrewAI Integration

```python
from utils.agent_client import SyncAuditClient, create_crewai_tools

client = SyncAuditClient("http://localhost:8000")
tools = create_crewai_tools(client)

# Use in CrewAI agent
agent = Agent(
    role="Sync Auditor",
    goal="Identify and diagnose sync issues",
    tools=tools
)
```

## Data Model

### SyncEvent

| Field | Type | Description |
|-------|------|-------------|
| `project` | string | Project identifier (e.g., "apdriving") |
| `source_system` | string | Source system (e.g., "woocommerce") |
| `target_system` | string | Target system (e.g., "acuity") |
| `source_id` | string | Record ID in source (e.g., order ID) |
| `target_id` | string | Record ID in target (e.g., appointment ID) |
| `event_type` | string | sync_attempt, sync_success, sync_failed, mismatch |
| `status` | string | pending, synced, failed, mismatch |
| `source_data` | JSON | Full data from source system |
| `target_data` | JSON | Full data from target system |
| `mismatches` | JSON | List of field mismatches |

### Mismatch

| Field | Type | Description |
|-------|------|-------------|
| `field` | string | Field name with mismatch |
| `source_value` | string | Value from source system |
| `target_value` | string | Value from target system |
| `severity` | string | critical, high, medium, low |

## Deployment (Railway)

1. Push to GitHub
2. Create new project in Railway
3. Connect GitHub repo
4. Add PostgreSQL plugin
5. Set environment variables:
   - `DATABASE_URL` (auto-set by Railway)
   - `API_KEY`
   - `REQUIRE_API_KEY=true`

## Directory Structure

```
SyncAudit/
├── api/
│   └── main.py              # FastAPI application
├── dashboard/
│   └── app.py               # Streamlit dashboard
├── integrations/
│   └── wordpress/           # WordPress/WooCommerce integration
│       ├── sync-audit-logger.php
│       └── apdriving-sync-audit-hooks.php
├── models/
│   ├── database.py          # SQLAlchemy setup
│   └── sync_event.py        # Data models
├── utils/
│   └── agent_client.py      # Agent client library
├── requirements.txt
├── run_api.py
├── run_dashboard.py
├── Procfile                 # Railway deployment
└── railway.json
```

## License

Internal tool for agency use.
