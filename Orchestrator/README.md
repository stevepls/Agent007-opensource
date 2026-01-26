# Orchestrator

Minimal, trustworthy AI agent system for software development.

## Philosophy

**Build the meta-tool first.** Instead of pre-building everything, this orchestrator builds what you need, when you need it.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI (app.py)                     │
│              Human submits tasks, reviews output             │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Manager Agent                            │
│         Plans, decomposes, delegates, escalates              │
│              NEVER writes code itself                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
┌─────────────────────────┐ ┌─────────────────────────┐
│     Coder Agent         │ │    Reviewer Agent       │
│  Writes complete code   │ │  Finds bugs & issues    │
│  Follows patterns       │ │  Brutally honest        │
│  Uses file tools        │ │  Never adds features    │
└─────────────────────────┘ └─────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│                      File Tools                              │
│  read_file | write_file | list_directory | search_code      │
│            All paths validated within workspace              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Create virtual environment
cd Orchestrator
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys
cp env.example .env
# Edit .env with your API keys

# 4. Run the UI
streamlit run app.py
```

## Configuration

Edit `.env`:

```bash
# Required: At least one LLM provider
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key

# Optional: Default model
DEFAULT_MODEL=claude-3-5-sonnet-20241022

# Workspace: Where agents can read/write
WORKSPACE_ROOT=/home/steve/Agent007

# Safety: Require human approval for file writes
REQUIRE_APPROVAL=true
```

## Usage

### Via Streamlit UI

1. Open http://localhost:8501
2. Configure API keys in sidebar
3. Submit a task description
4. Review agent output
5. Approve or reject file changes

### Via Python

```python
from crews import run_dev_task

result = run_dev_task(
    task_description="Create a FastAPI endpoint for health checks",
    context="The API is in SyncAudit/api/main.py",
    require_review=True
)

print(result["result"])
```

## Agent Roles

### Manager
- **Role**: Technical Project Manager
- **Goal**: Decompose tasks, delegate, ensure quality
- **Rules**:
  - NEVER writes code
  - ALWAYS delegates to specialists
  - Escalates when confidence < 80%
  - Escalates for money/legal/security decisions

### Coder
- **Role**: Senior Software Developer
- **Goal**: Write complete, production-ready code
- **Rules**:
  - ALWAYS produces complete code (no placeholders)
  - Follows existing patterns
  - Includes error handling
  - Never hardcodes secrets

### Reviewer
- **Role**: Senior Code Reviewer
- **Goal**: Find all bugs and issues
- **Rules**:
  - ONLY finds problems (never suggests features)
  - Prioritizes by severity
  - Cites exact lines
  - Provides clear verdicts: APPROVE / NEEDS_CHANGES / REJECT

## File Tools

All file operations are sandboxed to `WORKSPACE_ROOT`:

- `read_file(path)` - Read file contents with line numbers
- `write_file(path, content)` - Write/create files
- `list_directory(path)` - List directory contents
- `search_code(pattern)` - Search codebase with ripgrep

## Safety Features

1. **Workspace Sandboxing**: Agents can only access files within `WORKSPACE_ROOT`
2. **Human Approval**: File writes require explicit approval (configurable)
3. **Code Review**: Reviewer agent checks all code before presenting
4. **Rate Limiting**: API calls are rate-limited to prevent runaway costs
5. **Max Iterations**: Agents have iteration limits to prevent infinite loops

## Example Tasks

```
"Create a Streamlit dashboard for the SyncAudit API"

"Fix the calendar ID fallback issue in AcuitySyncService.php - 
it should fail with a clear error instead of silently reassigning"

"Add a /health endpoint to the FastAPI backend"

"Review the APDriving booking flow and identify data integrity risks"
```

## Troubleshooting

### "ANTHROPIC_API_KEY not set"
Add your API key to `.env` or enter it in the Streamlit sidebar.

### "Path is outside workspace"
The requested file path is outside `WORKSPACE_ROOT`. Adjust the workspace setting.

### Agent seems stuck
Check the terminal for verbose output. The agent may be waiting for a tool response or hit an error.

## Development

```bash
# Run with debug output
DEBUG=true streamlit run app.py

# Run security scan
bandit -r . -ll
```
