#!/usr/bin/env python3
"""
Run the SyncAudit API server.

Usage:
    python run_api.py              # Development mode with reload
    python run_api.py --prod       # Production mode
"""

import os
import sys
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    # Check for production mode
    prod_mode = "--prod" in sys.argv
    
    print(f"Starting SyncAudit API on http://{host}:{port}")
    print(f"Mode: {'Production' if prod_mode else 'Development'}")
    print(f"API Docs: http://{host}:{port}/docs")
    print()
    
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=not prod_mode,
        log_level="info" if prod_mode else "debug"
    )


if __name__ == "__main__":
    main()
