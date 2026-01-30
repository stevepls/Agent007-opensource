#!/usr/bin/env python3
"""
Fetch and analyze Google Sheets data
"""

import os
import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use unified token
os.environ["GOOGLE_CONFIG_DIR"] = os.path.expanduser("~/.config/agent007/google")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Configuration
GOOGLE_CONFIG_DIR = Path(os.path.expanduser("~/.config/agent007/google"))
UNIFIED_TOKEN_FILE = GOOGLE_CONFIG_DIR / "unified_token.json"
CREDENTIALS_FILE = GOOGLE_CONFIG_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Spreadsheet IDs from URLs
SHEETS = [
    {
        "name": "LCP Shopify Migration Estimate",
        "id": "1_xMZOYo2mwRzQFgdqumhuphL_KzKwaSe3pejr9Lyoyc",
    },
    {
        "name": "Second Spreadsheet",
        "id": "1AKRK_nAKoDwSUnzl5r9L_KaOD8aNMl8EeROJYZuGYdc",
    },
]


def get_authenticated_service():
    """Authenticate using unified token."""
    if not UNIFIED_TOKEN_FILE.exists():
        raise FileNotFoundError(f"Token file not found: {UNIFIED_TOKEN_FILE}")
    
    creds = Credentials.from_authorized_user_file(str(UNIFIED_TOKEN_FILE), SCOPES)
    
    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        with open(UNIFIED_TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    
    return build("sheets", "v4", credentials=creds)


def main():
    print("=" * 60)
    print("Google Sheets Data Fetcher")
    print("=" * 60)
    
    print("\nAuthenticating with Google...")
    try:
        service = get_authenticated_service()
        print("✓ Authenticated successfully")
    except Exception as e:
        print(f"ERROR: Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Fetch each spreadsheet
    for sheet_info in SHEETS:
        print(f"\n{'=' * 60}")
        print(f"Spreadsheet: {sheet_info['name']}")
        print(f"ID: {sheet_info['id']}")
        print("=" * 60)
        
        try:
            # Get metadata
            result = service.spreadsheets().get(spreadsheetId=sheet_info["id"]).execute()
            title = result.get("properties", {}).get("title", "Unknown")
            sheets = result.get("sheets", [])
            
            print(f"\nTitle: {title}")
            print(f"URL: {result.get('spreadsheetUrl', '')}")
            print(f"Sheets: {len(sheets)}")
            
            for sheet_data in sheets:
                props = sheet_data.get("properties", {})
                sheet_title = props.get("title", "Sheet")
                grid = props.get("gridProperties", {})
                
                print(f"\n--- Sheet: {sheet_title} ---")
                print(f"Rows: {grid.get('rowCount', 0)}, Columns: {grid.get('columnCount', 0)}")
                
                # Get all data from this sheet
                try:
                    range_result = service.spreadsheets().values().get(
                        spreadsheetId=sheet_info["id"],
                        range=f"'{sheet_title}'"
                    ).execute()
                    
                    values = range_result.get("values", [])
                    
                    if not values:
                        print("  (empty sheet)")
                        continue
                    
                    # Print header
                    header = values[0] if values else []
                    print(f"Columns: {header}")
                    
                    # Print data rows
                    print(f"\nData ({len(values) - 1} rows):")
                    print("-" * 100)
                    
                    for i, row in enumerate(values):
                        # Make sure all rows have same length as header
                        padded_row = row + [''] * (max(len(header), 1) - len(row))
                        
                        if i == 0:
                            # Header row
                            print("| " + " | ".join(str(c)[:40].ljust(40) for c in padded_row[:3]) + " |")
                            print("-" * 100)
                        else:
                            # Data row - limit to first 30 rows for display
                            if i <= 30:
                                print("| " + " | ".join(str(c)[:40].ljust(40) for c in padded_row[:3]) + " |")
                            elif i == 31:
                                print(f"... ({len(values) - 31} more rows)")
                    
                    print("-" * 100)
                    
                    # Calculate totals if there's a numeric column
                    print("\n📊 Summary:")
                    for col_idx, col_name in enumerate(header):
                        try:
                            # Try to sum numeric columns
                            numeric_values = []
                            for row in values[1:]:
                                if col_idx < len(row) and row[col_idx]:
                                    try:
                                        val = float(str(row[col_idx]).replace(',', '').replace('$', ''))
                                        numeric_values.append(val)
                                    except ValueError:
                                        pass
                            
                            if numeric_values:
                                total = sum(numeric_values)
                                avg = total / len(numeric_values)
                                print(f"  {col_name}: Total={total:.2f}, Avg={avg:.2f}, Count={len(numeric_values)}")
                        except:
                            pass
                    
                except Exception as e:
                    print(f"  Error reading sheet: {e}")
        
        except Exception as e:
            print(f"ERROR accessing spreadsheet: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
