"""
Google Sheets Tools

CrewAI tools for interacting with Google Sheets.
Provides read/write access to spreadsheet data.

SECURITY:
- Read operations are always allowed
- Write operations require confirmation through governance
"""

from typing import Any, Type, Optional, List
from pydantic import BaseModel, Field

try:
    from crewai.tools import BaseTool
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    BaseTool = object

from ..services.sheets import GoogleSheetsClient, get_sheets_client
from ..governance.confirmations import require_confirmation, ConfirmationLevel


# =============================================================================
# Read Tools
# =============================================================================

class SheetsGetInfoInput(BaseModel):
    """Input for getting spreadsheet info."""
    spreadsheet_id: str = Field(..., description="The Google Sheets spreadsheet ID (from URL)")


class SheetsGetInfoTool(BaseTool if CREWAI_AVAILABLE else object):
    """Get spreadsheet metadata and list of sheets."""
    
    name: str = "sheets_get_info"
    description: str = "Get information about a Google Sheets spreadsheet including its title and list of sheets"
    args_schema: Type[BaseModel] = SheetsGetInfoInput
    
    def _run(self, spreadsheet_id: str) -> str:
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured. Set up OAuth credentials."
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            spreadsheet = client.get_spreadsheet(spreadsheet_id)
            
            result = f"""
## Spreadsheet: {spreadsheet.title}

**ID:** {spreadsheet.id}
**URL:** {spreadsheet.url}
**Locale:** {spreadsheet.locale}
**Timezone:** {spreadsheet.time_zone}

### Sheets ({len(spreadsheet.sheets)})
"""
            for sheet in spreadsheet.sheets:
                result += f"• **{sheet.title}** ({sheet.row_count} rows × {sheet.column_count} cols)\n"
            
            return result
            
        except Exception as e:
            return f"❌ Error: {e}"


class SheetsReadRangeInput(BaseModel):
    """Input for reading a range."""
    spreadsheet_id: str = Field(..., description="The spreadsheet ID")
    range_notation: str = Field(..., description="A1 notation (e.g., 'Sheet1!A1:C10' or just 'Sheet1')")


class SheetsReadRangeTool(BaseTool if CREWAI_AVAILABLE else object):
    """Read values from a spreadsheet range."""
    
    name: str = "sheets_read_range"
    description: str = "Read values from a Google Sheets range using A1 notation (e.g., 'Sheet1!A1:C10')"
    args_schema: Type[BaseModel] = SheetsReadRangeInput
    
    def _run(self, spreadsheet_id: str, range_notation: str) -> str:
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured"
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            values = client.get_values(spreadsheet_id, range_notation)
            
            if not values:
                return f"No data found in range: {range_notation}"
            
            # Format as table
            result = f"## Data from {range_notation}\n\n"
            result += f"Rows: {len(values)}\n\n"
            
            # Show header row
            if values:
                result += "| " + " | ".join(str(cell)[:30] for cell in values[0]) + " |\n"
                result += "|" + "|".join("---" for _ in values[0]) + "|\n"
                
                # Show data rows (max 20)
                for row in values[1:21]:
                    result += "| " + " | ".join(str(cell)[:30] for cell in row) + " |\n"
                
                if len(values) > 21:
                    result += f"\n... and {len(values) - 21} more rows"
            
            return result
            
        except Exception as e:
            return f"❌ Error: {e}"


class SheetsFindValueInput(BaseModel):
    """Input for finding a value."""
    spreadsheet_id: str = Field(..., description="The spreadsheet ID")
    sheet_name: str = Field(..., description="Name of the sheet to search")
    search_value: str = Field(..., description="Value to search for")


class SheetsFindValueTool(BaseTool if CREWAI_AVAILABLE else object):
    """Find a value in a spreadsheet."""
    
    name: str = "sheets_find_value"
    description: str = "Search for a value in a Google Sheets spreadsheet and return its location"
    args_schema: Type[BaseModel] = SheetsFindValueInput
    
    def _run(self, spreadsheet_id: str, sheet_name: str, search_value: str) -> str:
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured"
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            result = client.find_value(spreadsheet_id, sheet_name, search_value)
            
            if not result:
                return f"Value '{search_value}' not found in sheet '{sheet_name}'"
            
            return f"""
## Found: {search_value}

**Location:** Row {result['row']}, Column {result['column']}
**Sheet:** {sheet_name}

**Row Data:**
{result['row_data']}
"""
            
        except Exception as e:
            return f"❌ Error: {e}"


# =============================================================================
# Write Tools (require confirmation)
# =============================================================================

class SheetsUpdateRangeInput(BaseModel):
    """Input for updating a range."""
    spreadsheet_id: str = Field(..., description="The spreadsheet ID")
    range_notation: str = Field(..., description="A1 notation (e.g., 'Sheet1!A1:C3')")
    values: str = Field(..., description="Values as JSON 2D array, e.g., [[\"A\",\"B\"],[1,2]]")


class SheetsUpdateRangeTool(BaseTool if CREWAI_AVAILABLE else object):
    """Update values in a spreadsheet range. Requires confirmation."""
    
    name: str = "sheets_update_range"
    description: str = "Update values in a Google Sheets range. REQUIRES HUMAN CONFIRMATION."
    args_schema: Type[BaseModel] = SheetsUpdateRangeInput
    
    def _run(self, spreadsheet_id: str, range_notation: str, values: str) -> str:
        import json
        
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured"
        
        try:
            parsed_values = json.loads(values)
        except json.JSONDecodeError as e:
            return f"❌ Invalid JSON for values: {e}"
        
        # Count cells being updated
        cell_count = sum(len(row) for row in parsed_values)
        
        confirmation = require_confirmation(
            action=f"Update {cell_count} cells in Google Sheets",
            details=f"Range: {range_notation}\nValues: {values[:200]}...",
            level=ConfirmationLevel.STANDARD,
        )
        
        if not confirmation.approved:
            return f"❌ Action requires approval. Confirmation ID: {confirmation.id}"
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            result = client.update_values(spreadsheet_id, range_notation, parsed_values)
            
            return f"""
✅ Updated Google Sheets

**Range:** {result['updated_range']}
**Cells Updated:** {result['updated_cells']}
**Rows Updated:** {result['updated_rows']}
"""
            
        except Exception as e:
            return f"❌ Error: {e}"


class SheetsAppendRowsInput(BaseModel):
    """Input for appending rows."""
    spreadsheet_id: str = Field(..., description="The spreadsheet ID")
    sheet_name: str = Field(..., description="Name of the sheet to append to")
    rows: str = Field(..., description="Rows as JSON 2D array, e.g., [[\"A\",\"B\"],[1,2]]")


class SheetsAppendRowsTool(BaseTool if CREWAI_AVAILABLE else object):
    """Append rows to a spreadsheet. Requires confirmation."""
    
    name: str = "sheets_append_rows"
    description: str = "Append new rows to the end of a Google Sheets table. REQUIRES HUMAN CONFIRMATION."
    args_schema: Type[BaseModel] = SheetsAppendRowsInput
    
    def _run(self, spreadsheet_id: str, sheet_name: str, rows: str) -> str:
        import json
        
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured"
        
        try:
            parsed_rows = json.loads(rows)
        except json.JSONDecodeError as e:
            return f"❌ Invalid JSON for rows: {e}"
        
        confirmation = require_confirmation(
            action=f"Append {len(parsed_rows)} rows to Google Sheets",
            details=f"Sheet: {sheet_name}\nFirst row: {parsed_rows[0] if parsed_rows else 'empty'}",
            level=ConfirmationLevel.STANDARD,
        )
        
        if not confirmation.approved:
            return f"❌ Action requires approval. Confirmation ID: {confirmation.id}"
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            result = client.append_values(
                spreadsheet_id,
                f"'{sheet_name}'",
                parsed_rows,
            )
            
            return f"""
✅ Appended to Google Sheets

**Sheet:** {sheet_name}
**Rows Added:** {result['updated_rows']}
**Cells Added:** {result['updated_cells']}
"""
            
        except Exception as e:
            return f"❌ Error: {e}"


class SheetsCreateInput(BaseModel):
    """Input for creating a spreadsheet."""
    title: str = Field(..., description="Title for the new spreadsheet")
    sheet_names: str = Field(default="Sheet1", description="Comma-separated sheet names")


class SheetsCreateTool(BaseTool if CREWAI_AVAILABLE else object):
    """Create a new spreadsheet. Requires confirmation."""
    
    name: str = "sheets_create"
    description: str = "Create a new Google Sheets spreadsheet. REQUIRES HUMAN CONFIRMATION."
    args_schema: Type[BaseModel] = SheetsCreateInput
    
    def _run(self, title: str, sheet_names: str = "Sheet1") -> str:
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured"
        
        sheets = [s.strip() for s in sheet_names.split(",") if s.strip()]
        
        confirmation = require_confirmation(
            action=f"Create new Google Sheets spreadsheet",
            details=f"Title: {title}\nSheets: {', '.join(sheets)}",
            level=ConfirmationLevel.STANDARD,
        )
        
        if not confirmation.approved:
            return f"❌ Action requires approval. Confirmation ID: {confirmation.id}"
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            spreadsheet = client.create_spreadsheet(title, sheets)
            
            return f"""
✅ Created Google Sheets Spreadsheet

**Title:** {spreadsheet.title}
**ID:** {spreadsheet.id}
**URL:** {spreadsheet.url}

**Sheets:**
{chr(10).join(f"• {s.title}" for s in spreadsheet.sheets)}
"""
            
        except Exception as e:
            return f"❌ Error: {e}"


class SheetsExportCsvInput(BaseModel):
    """Input for exporting to CSV."""
    spreadsheet_id: str = Field(..., description="The spreadsheet ID")
    sheet_name: str = Field(default="", description="Sheet name (optional, defaults to first sheet)")


class SheetsExportCsvTool(BaseTool if CREWAI_AVAILABLE else object):
    """Export a sheet to CSV format."""
    
    name: str = "sheets_export_csv"
    description: str = "Export a Google Sheets sheet to CSV format"
    args_schema: Type[BaseModel] = SheetsExportCsvInput
    
    def _run(self, spreadsheet_id: str, sheet_name: str = "") -> str:
        client = get_sheets_client()
        
        if not client.is_available:
            return "❌ Google Sheets not configured"
        
        try:
            if not client.is_authenticated:
                client.authenticate(headless=True)
            
            csv_content = client.export_to_csv(
                spreadsheet_id,
                sheet_name if sheet_name else None,
            )
            
            # Show preview
            lines = csv_content.split("\n")
            preview = "\n".join(lines[:20])
            
            return f"""
## CSV Export

**Sheet:** {sheet_name or '(first sheet)'}
**Rows:** {len(lines)}

### Preview (first 20 rows):
```csv
{preview}
```

{"... truncated" if len(lines) > 20 else ""}
"""
            
        except Exception as e:
            return f"❌ Error: {e}"


# =============================================================================
# Tool Collection
# =============================================================================

def get_sheets_tools() -> List:
    """Get all Google Sheets tools."""
    if not CREWAI_AVAILABLE:
        return []
    
    return [
        SheetsGetInfoTool(),
        SheetsReadRangeTool(),
        SheetsFindValueTool(),
        SheetsUpdateRangeTool(),
        SheetsAppendRowsTool(),
        SheetsCreateTool(),
        SheetsExportCsvTool(),
    ]
