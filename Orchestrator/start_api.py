#!/usr/bin/env python3
"""Start the Orchestrator API with environment loaded."""

import os
import sys
from pathlib import Path

# Change to script directory
os.chdir(Path(__file__).parent)

# Load .env
from dotenv import load_dotenv
load_dotenv()

# Print status
print("=" * 50)
print("Orchestrator API Starting")
print("=" * 50)
print(f"ANTHROPIC_API_KEY: {'✓ configured' if os.getenv('ANTHROPIC_API_KEY') else '✗ NOT SET'}")
print(f"HARVEST_ACCESS_TOKEN: {'✓ configured' if os.getenv('HARVEST_ACCESS_TOKEN') else '✗ NOT SET'}")
print(f"HARVEST_ACCOUNT_ID: {os.getenv('HARVEST_ACCOUNT_ID', 'NOT SET')}")
print("=" * 50)

# Start server
import uvicorn
from api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8502, log_level="info")
