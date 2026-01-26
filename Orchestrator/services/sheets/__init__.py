"""
Google Sheets Service

Provides read/write access to Google Sheets spreadsheets.
Uses the same OAuth credentials as Gmail/Drive.
"""

from .client import (
    GoogleSheetsClient,
    get_sheets_client,
    Spreadsheet,
    Sheet,
    CellRange,
)

__all__ = [
    "GoogleSheetsClient",
    "get_sheets_client",
    "Spreadsheet",
    "Sheet",
    "CellRange",
]
