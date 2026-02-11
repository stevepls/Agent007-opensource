#!/usr/bin/env python3
"""Start the Orchestrator API.

Thin wrapper — api.py loads .env and configures everything itself.
Prefer: python3 -m uvicorn api:app --host 0.0.0.0 --port 8502
"""

import os
from pathlib import Path

os.chdir(Path(__file__).parent)

import uvicorn
from api import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8502"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
