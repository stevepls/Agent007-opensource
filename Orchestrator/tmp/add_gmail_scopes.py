#!/usr/bin/env python3
"""
Add Gmail scopes to the unified token.
"""

import os
import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

CONFIG_DIR = Path(os.path.expanduser("~/.config/agent007/google"))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
UNIFIED_TOKEN_FILE = CONFIG_DIR / "unified_token.json"

# All scopes we want
ALL_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/gmail.readonly',
]

def main():
    print("Adding Gmail scopes to unified token...")
    print(f"Credentials: {CREDENTIALS_FILE}")
    print(f"Token: {UNIFIED_TOKEN_FILE}")
    
    # Check current token
    if UNIFIED_TOKEN_FILE.exists():
        with open(UNIFIED_TOKEN_FILE) as f:
            token_data = json.load(f)
        current_scopes = token_data.get('scopes', [])
        print(f"\nCurrent scopes: {current_scopes}")
        
        if 'https://www.googleapis.com/auth/gmail.readonly' in current_scopes:
            print("Gmail scope already present!")
            return
    
    print(f"\nRequesting scopes: {ALL_SCOPES}")
    print("\nStarting OAuth flow - a browser window will open...")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE), 
        ALL_SCOPES
    )
    creds = flow.run_local_server(port=8080)
    
    # Save updated token
    with open(UNIFIED_TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())
    
    print(f"\n✓ Token updated with Gmail scopes")
    print(f"Saved to: {UNIFIED_TOKEN_FILE}")


if __name__ == "__main__":
    main()
