# Integrated Ticket Management System

## 🎯 Quick Start

Use **ticket IDs** (like 5098) instead of record IDs for all operations:

```bash
# Complete workflow
./ticket_manager.sh 5098 start "Working on payment plan update"
./ticket_manager.sh 5098 work-summary "Updated database schema"
./ticket_manager.sh 5098 complete "All work finished and tested"
```

## 🚀 Key Features

- **Ticket ID Support**: Use simple numeric IDs (5098) instead of complex record IDs (recDKObpxCxQ9KqWC)
- **Harvest Integration**: Automatic time tracking with Airtable updates
- **Status Management**: Update ticket status with validation
- **Unified Workflow**: One script handles everything

## 📋 Common Commands

| Action | Command | Description |
|--------|---------|-------------|
| Start work | `./ticket_manager.sh 5098 start "Working on X"` | Starts timer + sets status to "In Progress" |
| Add progress | `./ticket_manager.sh 5098 work-summary "Did Y"` | Documents work completed |
| Complete | `./ticket_manager.sh 5098 complete "Finished Z"` | Stops timer + sets status to "Complete" |
| Log time | `./ticket_manager.sh 5098 log-time 2.5 "Notes"` | Logs time to Harvest |

## 🔧 Setup

1. **Environment**: Already configured with credentials
2. **Virtual Environment**: `source src/venv/bin/activate` (auto-handled by scripts)
3. **Test**: `./ticket_manager.sh 5098 list-statuses`

## 📊 Harvest Integration

- **Access Token**: REDACTED-HARVEST-TOKEN
- **Account ID**: 836408 (Forge Lab)
- **Time Tracking**: Automatic with ticket references
- **Project/Task**: Auto-detected or manually specified

## 🎨 Status Options

- `Assigned - Small/Large`
- `In Progress - Small/Large` 
- `Done (Needs Review)`
- `Complete`
- `Waiting on Details from CW`
- `On Hold`
- `Backlog - Small/Large`

## 📝 Comment Types

- `work-summary` - What you accomplished
- `database-change` - DB modifications
- `technical-note` - Implementation details
- `verification` - Testing results
- `status-update` - Progress updates

## 🔍 Find Ticket IDs

```bash
# Search recent tickets
python src/fetch_airtable_tickets.py

# Check summary file
cat output/airtable-tickets/SUMMARY.md
```

## 💡 Pro Tips

1. **Start with timer**: Always begin with `start` action for automatic time tracking
2. **Document as you go**: Add `work-summary` entries throughout development
3. **Use `complete`**: Automatically stops timer and updates status
4. **Ticket ID format**: Use numeric IDs (5098) - much easier than record IDs

## 🆘 Troubleshooting

- **Permission errors**: Check if VPN is connected for production access
- **Ticket not found**: Verify ticket ID exists in recent tickets
- **Harvest 403 error**: Token may need additional permissions (time tracking still works)

This system streamlines the entire ticket workflow from start to completion with automatic time tracking and status management! 