#!/usr/bin/env python3
"""
Run the SyncAudit Streamlit Dashboard.

Usage:
    python run_dashboard.py
"""

import os
import subprocess
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    port = os.getenv("STREAMLIT_PORT", "8501")
    
    print(f"Starting SyncAudit Dashboard on http://localhost:{port}")
    print()
    
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "dashboard/app.py",
        "--server.port", port,
        "--server.address", "0.0.0.0",
        "--server.headless", "true"
    ])


if __name__ == "__main__":
    main()
