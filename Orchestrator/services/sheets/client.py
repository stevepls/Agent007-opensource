"""
Google Sheets API Client

Provides read, write, and update operations for Google Sheets.
Shares OAuth credentials with Gmail and Drive services.

SECURITY:
- OAuth credentials required
- Write operations require confirmation
- Rate limiting respected
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from datetime import datetime

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Credentials = None

from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configuration
GOOGLE_CONFIG_DIR = Path(os.getenv("GOOGLE_CONFIG_DIR", "~/.config/agent007/google")).expanduser()
CREDENTIALS_FILE = GOOGLE_CONFIG_DIR / "credentials.json"
TOKEN_FILE = GOOGLE_CONFIG_DIR / "unified_token.json"

# Scopes required for Sheets access
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",  # Full access
    "https://www.googleapis.com/auth/drive.file",    # Access to files created by app
]


@dataclass
class CellRange:
    """Represents a range of cells."""
    sheet_name: str
    start_row: int
    start_col: int
    end_row: Optional[int] = None
    end_col: Optional[int] = None
    
    def to_a1_notation(self) -> str:
        """Convert to A1 notation (e.g., 'Sheet1!A1:C10')."""
        def col_to_letter(col: int) -> str:
            result = ""
            while col > 0:
                col, remainder = divmod(col - 1, 26)
                result = chr(65 + remainder) + result
            return result
        
        start = f"{col_to_letter(self.start_col)}{self.start_row}"
        
        if self.end_row and self.end_col:
            end = f"{col_to_letter(self.end_col)}{self.end_row}"
            return f"'{self.sheet_name}'!{start}:{end}"
        
        return f"'{self.sheet_name}'!{start}"


@dataclass
class Sheet:
    """Represents a sheet within a spreadsheet."""
    id: int
    title: str
    index: int
    row_count: int
    column_count: int
    
    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "Sheet":
        props = data.get("properties", {})
        grid = props.get("gridProperties", {})
        return cls(
            id=props.get("sheetId", 0),
            title=props.get("title", ""),
            index=props.get("index", 0),
            row_count=grid.get("rowCount", 1000),
            column_count=grid.get("columnCount", 26),
        )


@dataclass
class Spreadsheet:
    """Represents a Google Sheets spreadsheet."""
    id: str
    title: str
    url: str
    sheets: List[Sheet] = field(default_factory=list)
    locale: str = "en_US"
    time_zone: str = "America/New_York"
    
    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "Spreadsheet":
        props = data.get("properties", {})
        sheets = [Sheet.from_api(s) for s in data.get("sheets", [])]
        
        return cls(
            id=data.get("spreadsheetId", ""),
            title=props.get("title", ""),
            url=data.get("spreadsheetUrl", ""),
            sheets=sheets,
            locale=props.get("locale", "en_US"),
            time_zone=props.get("timeZone", "America/New_York"),
        )


class GoogleSheetsClient:
    """Google Sheets API client with safety controls."""
    
    def __init__(self, credentials_file: Path = None, token_file: Path = None):
        self._credentials_file = credentials_file or CREDENTIALS_FILE
        self._token_file = token_file or TOKEN_FILE
        self._service = None
        self._creds = None
    
    @property
    def is_available(self) -> bool:
        return GOOGLE_API_AVAILABLE and self._credentials_file.exists()
    
    @property
    def is_authenticated(self) -> bool:
        if not self._creds:
            return False
        return self._creds.valid
    
    def authenticate(self, headless: bool = False) -> bool:
        """
        Authenticate with Google using unified credentials.
        
        Args:
            headless: If True, fail if browser auth is needed
        """
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API libraries not installed. Run:\n"
                "pip install google-api-python-client google-auth-oauthlib"
            )
        
        # Try unified auth first - use absolute import path
        try:
            from services.google_auth import get_google_auth
            
            auth = get_google_auth()
            if auth.is_authenticated:
                self._creds = auth.credentials
                self._service = build("sheets", "v4", credentials=self._creds)
                return True
            else:
                if headless:
                    raise RuntimeError("Unified auth not authenticated")
        except ImportError:
            # Try relative import
            try:
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent))
                from google_auth import get_google_auth
                
                auth = get_google_auth()
                if auth.is_authenticated:
                    self._creds = auth.credentials
                    self._service = build("sheets", "v4", credentials=self._creds)
                    return True
            except Exception as e:
                pass
        except Exception as e:
            pass
        
        if not self._credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self._credentials_file}\n"
                "Download OAuth credentials from Google Cloud Console."
            )
        
        # Try to load existing token
        if self._token_file.exists():
            self._creds = Credentials.from_authorized_user_file(
                str(self._token_file), SCOPES
            )
        
        # Refresh or get new credentials
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                if headless:
                    raise RuntimeError(
                        "Browser authentication required. Run interactively first."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._credentials_file), SCOPES
                )
                self._creds = flow.run_local_server(port=0)
            
            # Save token for future use
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_file, "w") as f:
                f.write(self._creds.to_json())
        
        # Build service
        self._service = build("sheets", "v4", credentials=self._creds)
        return True
    
    def _ensure_authenticated(self):
        if not self._service:
            self.authenticate(headless=True)
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def get_spreadsheet(self, spreadsheet_id: str) -> Spreadsheet:
        """Get spreadsheet metadata."""
        self._ensure_authenticated()
        
        result = self._service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        
        return Spreadsheet.from_api(result)
    
    def get_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        value_render_option: str = "FORMATTED_VALUE",
    ) -> List[List[Any]]:
        """
        Get values from a range.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            range_notation: A1 notation (e.g., 'Sheet1!A1:C10')
            value_render_option: How values should be rendered
                - FORMATTED_VALUE: As displayed (default)
                - UNFORMATTED_VALUE: Raw values
                - FORMULA: Formulas instead of computed values
        
        Returns:
            2D list of cell values
        """
        self._ensure_authenticated()
        
        result = self._service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueRenderOption=value_render_option,
        ).execute()
        
        return result.get("values", [])
    
    def get_all_values(
        self,
        spreadsheet_id: str,
        sheet_name: str = None,
    ) -> List[List[Any]]:
        """Get all values from a sheet."""
        if sheet_name:
            range_notation = f"'{sheet_name}'"
        else:
            # Get first sheet name
            spreadsheet = self.get_spreadsheet(spreadsheet_id)
            if spreadsheet.sheets:
                range_notation = f"'{spreadsheet.sheets[0].title}'"
            else:
                raise ValueError("Spreadsheet has no sheets")
        
        return self.get_values(spreadsheet_id, range_notation)
    
    def get_row(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row_number: int,
    ) -> List[Any]:
        """Get a single row."""
        range_notation = f"'{sheet_name}'!{row_number}:{row_number}"
        values = self.get_values(spreadsheet_id, range_notation)
        return values[0] if values else []
    
    def get_column(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        column_letter: str,
    ) -> List[Any]:
        """Get a single column."""
        range_notation = f"'{sheet_name}'!{column_letter}:{column_letter}"
        values = self.get_values(spreadsheet_id, range_notation)
        return [row[0] if row else None for row in values]
    
    def find_value(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        search_value: str,
    ) -> Optional[Dict[str, Any]]:
        """Find a value in a sheet. Returns first match."""
        values = self.get_all_values(spreadsheet_id, sheet_name)
        
        for row_idx, row in enumerate(values):
            for col_idx, cell in enumerate(row):
                if str(cell) == str(search_value):
                    return {
                        "row": row_idx + 1,
                        "column": col_idx + 1,
                        "value": cell,
                        "row_data": row,
                    }
        
        return None
    
    # =========================================================================
    # WRITE OPERATIONS (require confirmation)
    # =========================================================================
    
    def update_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
    ) -> Dict[str, Any]:
        """
        Update values in a range.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            range_notation: A1 notation (e.g., 'Sheet1!A1:C10')
            values: 2D list of values to write
            value_input_option: How input should be interpreted
                - USER_ENTERED: Parse as if typed by user
                - RAW: Store exactly as provided
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        body = {"values": values}
        
        result = self._service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption=value_input_option,
            body=body,
        ).execute()
        
        return {
            "updated_cells": result.get("updatedCells", 0),
            "updated_rows": result.get("updatedRows", 0),
            "updated_columns": result.get("updatedColumns", 0),
            "updated_range": result.get("updatedRange", ""),
        }
    
    def append_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED",
        insert_data_option: str = "INSERT_ROWS",
    ) -> Dict[str, Any]:
        """
        Append values to a sheet.
        
        Args:
            spreadsheet_id: The spreadsheet ID
            range_notation: A1 notation for the table to append to
            values: 2D list of values to append
            insert_data_option: How to insert data
                - OVERWRITE: Overwrite existing data
                - INSERT_ROWS: Insert new rows for the data
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        body = {"values": values}
        
        result = self._service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
            valueInputOption=value_input_option,
            insertDataOption=insert_data_option,
            body=body,
        ).execute()
        
        updates = result.get("updates", {})
        return {
            "updated_cells": updates.get("updatedCells", 0),
            "updated_rows": updates.get("updatedRows", 0),
            "updated_range": updates.get("updatedRange", ""),
        }
    
    def clear_values(
        self,
        spreadsheet_id: str,
        range_notation: str,
    ) -> bool:
        """
        Clear values from a range (keeps formatting).
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        self._service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_notation,
        ).execute()
        
        return True
    
    def update_cell(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row: int,
        column: int,
        value: Any,
    ) -> bool:
        """
        Update a single cell.
        
        REQUIRES CONFIRMATION.
        """
        def col_to_letter(col: int) -> str:
            result = ""
            while col > 0:
                col, remainder = divmod(col - 1, 26)
                result = chr(65 + remainder) + result
            return result
        
        cell_ref = f"'{sheet_name}'!{col_to_letter(column)}{row}"
        self.update_values(spreadsheet_id, cell_ref, [[value]])
        return True
    
    # =========================================================================
    # SPREADSHEET MANAGEMENT
    # =========================================================================
    
    def create_spreadsheet(
        self,
        title: str,
        sheets: List[str] = None,
    ) -> Spreadsheet:
        """
        Create a new spreadsheet.
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        body = {
            "properties": {"title": title},
        }
        
        if sheets:
            body["sheets"] = [
                {"properties": {"title": name}}
                for name in sheets
            ]
        
        result = self._service.spreadsheets().create(body=body).execute()
        return Spreadsheet.from_api(result)
    
    def add_sheet(
        self,
        spreadsheet_id: str,
        title: str,
        rows: int = 1000,
        columns: int = 26,
    ) -> Sheet:
        """
        Add a new sheet to an existing spreadsheet.
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        request = {
            "addSheet": {
                "properties": {
                    "title": title,
                    "gridProperties": {
                        "rowCount": rows,
                        "columnCount": columns,
                    }
                }
            }
        }
        
        result = self._service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [request]},
        ).execute()
        
        reply = result.get("replies", [{}])[0]
        return Sheet.from_api(reply.get("addSheet", {}))
    
    def delete_sheet(
        self,
        spreadsheet_id: str,
        sheet_id: int,
    ) -> bool:
        """
        Delete a sheet from a spreadsheet.
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        request = {
            "deleteSheet": {
                "sheetId": sheet_id,
            }
        }
        
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [request]},
        ).execute()
        
        return True
    
    def rename_sheet(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        new_title: str,
    ) -> bool:
        """
        Rename a sheet.
        
        REQUIRES CONFIRMATION.
        """
        self._ensure_authenticated()
        
        request = {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "title": new_title,
                },
                "fields": "title",
            }
        }
        
        self._service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [request]},
        ).execute()
        
        return True
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def export_to_csv(
        self,
        spreadsheet_id: str,
        sheet_name: str = None,
        output_path: str = None,
    ) -> str:
        """Export a sheet to CSV format."""
        values = self.get_all_values(spreadsheet_id, sheet_name)
        
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(values)
        csv_content = output.getvalue()
        
        if output_path:
            with open(output_path, "w", newline="") as f:
                f.write(csv_content)
        
        return csv_content
    
    def import_from_csv(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        csv_path: str,
        clear_first: bool = True,
    ) -> Dict[str, Any]:
        """
        Import CSV data into a sheet.
        
        REQUIRES CONFIRMATION.
        """
        import csv
        
        with open(csv_path, "r", newline="") as f:
            reader = csv.reader(f)
            values = list(reader)
        
        if clear_first:
            self.clear_values(spreadsheet_id, f"'{sheet_name}'")
        
        return self.update_values(
            spreadsheet_id,
            f"'{sheet_name}'!A1",
            values,
        )


# Global instance
_client: Optional[GoogleSheetsClient] = None


def get_sheets_client() -> GoogleSheetsClient:
    """Get the global Google Sheets client."""
    global _client
    if _client is None:
        _client = GoogleSheetsClient()
    return _client
