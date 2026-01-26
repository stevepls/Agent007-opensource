# Airtable Ticket Fetcher

This script fetches tickets assigned to `cw-testing@theforgelab.com` from an Airtable base and organizes them by creation date.

## Setup

1. **Run the setup script:**
   ```bash
   ./setup_and_run.sh
   ```

2. **Get your Airtable credentials:**
   - Go to [Airtable Developer Hub](https://airtable.com/developers/web/api/introduction)
   - Create a Personal Access Token
   - Find your Base ID from your Airtable URL (starts with 'app')
   - Note your table name (e.g., 'Tickets', 'Issues', etc.)

## Usage

### Basic Usage
```bash
./fetch_airtable_tickets.py --token YOUR_TOKEN --base-id YOUR_BASE_ID --table YOUR_TABLE_NAME
```

### With Custom Options
```bash
./fetch_airtable_tickets.py \
  --token patXXXXXXXXXXXXXX \
  --base-id appXXXXXXXXXXXXXX \
  --table Tickets \
  --email cw-testing@theforgelab.com \
  --output airtable-tickets
```

## Configuration

You can copy `airtable_config.json.example` to `airtable_config.json` and modify it with your actual credentials for easier use.

## Output Structure

The script creates a folder structure like this:

```
airtable-tickets/
├── 2024-01-15/
│   ├── recXXXXXX_Ticket_Title.json
│   ├── recXXXXXX_Ticket_Title.txt
│   └── ...
├── 2024-01-16/
│   └── ...
└── fetch_summary.txt
```

## Features

- ✅ **Filters by email** - Only fetches tickets assigned to specified email
- ✅ **Date-based organization** - Creates subfolders by creation date (YYYY-MM-DD)
- ✅ **Multiple formats** - Saves both JSON (structured) and TXT (readable) versions
- ✅ **Error handling** - Handles API rate limits and parsing errors
- ✅ **Progress tracking** - Shows fetch progress and creates summary
- ✅ **Flexible configuration** - Easy to modify for different fields/tables

## Troubleshooting

1. **"No module named 'requests'"** - Run `pip3 install -r requirements.txt`
2. **"Permission denied"** - Run `chmod +x fetch_airtable_tickets.py`
3. **"Invalid token"** - Check your Personal Access Token
4. **"Table not found"** - Verify your Base ID and table name

## Field Mapping

The script looks for these common field names:
- **Title fields**: Title, Subject, Name, Summary
- **Date fields**: Created, Date Created, Created Time
- **Assignee fields**: Assigned Email, Assignee, Assigned To
- **Status fields**: Status, State, Current Status

If your Airtable uses different field names, you may need to modify the script accordingly. 