"""
Google Sheets API Client

Provides read/write access to Google Sheets spreadsheets.
Uses the same OAuth token as other Google services.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Credentials = None

# Configuration
CONFIG_DIR = Path(os.getenv("GOOGLE_CONFIG_DIR", os.path.expanduser("~/.config/agent007/google")))
TOKEN_FILE = CONFIG_DIR / "token.json"

SHEETS_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
]


@dataclass
class SheetInfo:
    """Information about a sheet in a spreadsheet."""
    id: int
    title: str
    row_count: int
    column_count: int


@dataclass
class SpreadsheetInfo:
    """Information about a spreadsheet."""
    id: str
    title: str
    url: str
    locale: str
    time_zone: str
    sheets: List[SheetInfo]


class GoogleSheetsClient:
    """Google Sheets API client."""
    
    def __init__(self):
        self._service = None
        self._credentials = None
    
    @property
    def is_available(self) -> bool:
        return GOOGLE_API_AVAILABLE
    
    @property
    def is_authenticated(self) -> bool:
        return self._credentials is not None and self._credentials.valid
    
    def authenticate(self, headless: bool = True) -> bool:
        """Authenticate with Sheets API using existing token."""
        if not GOOGLE_API_AVAILABLE:
            raise ImportError("Google API libraries not installed")
        
        if not TOKEN_FILE.exists():
            raise FileNotFoundError(f"Token not found at {TOKEN_FILE}. Run Google OAuth setup.")
        
        with open(TOKEN_FILE) as f:
            token_data = json.load(f)
        
        self._credentials = Credentials(
            token=token_data['token'],
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes', SHEETS_SCOPES),
        )
        
        if self._credentials.expired and self._credentials.refresh_token:
            self._credentials.refresh(Request())
        
        self._service = build('sheets', 'v4', credentials=self._credentials)
        return True
    
    def get_spreadsheet(self, spreadsheet_id: str) -> SpreadsheetInfo:
        """Get spreadsheet metadata."""
        if not self.is_authenticated:
            self.authenticate()
        
        result = self._service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        
        sheets = []
        for sheet in result.get('sheets', []):
            props = sheet.get('properties', {})
            grid_props = props.get('gridProperties', {})
            sheets.append(SheetInfo(
                id=props.get('sheetId', 0),
                title=props.get('title', ''),
                row_count=grid_props.get('rowCount', 0),
                column_count=grid_props.get('columnCount', 0),
            ))
        
        return SpreadsheetInfo(
            id=result.get('spreadsheetId', ''),
            title=result.get('properties', {}).get('title', ''),
            url=result.get('spreadsheetUrl', ''),
            locale=result.get('properties', {}).get('locale', ''),
            time_zone=result.get('properties', {}).get('timeZone', ''),
            sheets=sheets,
        )
    
    def get_values(self, spreadsheet_id: str, range_notation: str) -> List[List[Any]]:
        """Get values from a range."""
        if not self.is_authenticated:
            self.authenticate()
        
        result = self._service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
        ).execute()
        
        return result.get('values', [])
    
    def update_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """Update values in a range."""
        if not self.is_authenticated:
            self.authenticate()
        
        body = {'values': values}
        result = self._service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption='USER_ENTERED',
            body=body,
        ).execute()
        
        return {
            'updated_range': result.get('updatedRange', ''),
            'updated_rows': result.get('updatedRows', 0),
            'updated_columns': result.get('updatedColumns', 0),
            'updated_cells': result.get('updatedCells', 0),
        }
    
    def append_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
    ) -> Dict[str, Any]:
        """Append values to a table."""
        if not self.is_authenticated:
            self.authenticate()
        
        body = {'values': values}
        result = self._service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body=body,
        ).execute()
        
        updates = result.get('updates', {})
        return {
            'updated_range': updates.get('updatedRange', ''),
            'updated_rows': updates.get('updatedRows', 0),
            'updated_cells': updates.get('updatedCells', 0),
        }
    
    def find_value(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        search_value: str,
    ) -> Optional[Dict[str, Any]]:
        """Find a value in a sheet."""
        values = self.get_values(spreadsheet_id, f"'{sheet_name}'")
        
        for row_idx, row in enumerate(values):
            for col_idx, cell in enumerate(row):
                if str(cell) == str(search_value):
                    return {
                        'row': row_idx + 1,
                        'column': col_idx + 1,
                        'row_data': row,
                    }
        
        return None
    
    def create_spreadsheet(
        self,
        title: str,
        sheet_names: List[str] = None,
    ) -> SpreadsheetInfo:
        """Create a new spreadsheet."""
        if not self.is_authenticated:
            self.authenticate()
        
        sheets = []
        if sheet_names:
            sheets = [{'properties': {'title': name}} for name in sheet_names]
        else:
            sheets = [{'properties': {'title': 'Sheet1'}}]
        
        body = {
            'properties': {'title': title},
            'sheets': sheets,
        }
        
        result = self._service.spreadsheets().create(body=body).execute()
        return self.get_spreadsheet(result['spreadsheetId'])
    
    def export_to_csv(
        self,
        spreadsheet_id: str,
        sheet_name: str = None,
    ) -> str:
        """Export a sheet to CSV format."""
        if sheet_name:
            range_notation = f"'{sheet_name}'"
        else:
            # Get first sheet name
            info = self.get_spreadsheet(spreadsheet_id)
            if info.sheets:
                range_notation = f"'{info.sheets[0].title}'"
            else:
                range_notation = 'Sheet1'
        
        values = self.get_values(spreadsheet_id, range_notation)
        
        lines = []
        for row in values:
            # Escape commas and quotes
            escaped = []
            for cell in row:
                cell_str = str(cell)
                if ',' in cell_str or '"' in cell_str:
                    cell_str = '"' + cell_str.replace('"', '""') + '"'
                escaped.append(cell_str)
            lines.append(','.join(escaped))
        
        return '\n'.join(lines)


# Singleton
_client: Optional[GoogleSheetsClient] = None


def get_sheets_client() -> GoogleSheetsClient:
    """Get the global Sheets client."""
    global _client
    if _client is None:
        _client = GoogleSheetsClient()
    return _client
