# Message Approval System

The team check-in agent now includes a message approval system that allows you to review and approve messages before they are sent.

## Features

- **Message Queue**: All messages are queued for approval before sending
- **Web UI**: Simple HTML interface to review and approve messages
- **Manual Triggers**: Trigger follow-ups or morning check-ins manually
- **API Endpoints**: REST API for programmatic access

## Setup

### 1. Start the API Server

The approval system uses the FastAPI server. Make sure it's running:

```bash
cd /home/steve/Agent007/Orchestrator
python start_api.py
```

The API will be available at `http://localhost:8502`

### 2. Open the Approval UI

Open the HTML file in your browser:

```bash
# Option 1: Open directly
open agents/team_checkin/approval_ui.html

# Option 2: Serve via Python
cd agents/team_checkin
python -m http.server 8080
# Then open http://localhost:8080/approval_ui.html
```

Or integrate it into your existing dashboard.

## API Endpoints

### Get Pending Messages
```
GET /team-checkin/messages/pending
```

Returns all messages awaiting approval.

### Get Specific Message
```
GET /team-checkin/messages/{message_id}
```

Get details of a specific message.

### Approve Message
```
POST /team-checkin/messages/{message_id}/approve
```

Approve and immediately send a message.

### Reject Message
```
POST /team-checkin/messages/{message_id}/reject
```

Reject a message (won't be sent).

### Trigger Follow-up
```
POST /team-checkin/trigger/followup
Body: { "member_name": "John Doe" }  // Optional, omit for all members
```

Manually trigger follow-up check-ins.

### Trigger Morning Check-in
```
POST /team-checkin/trigger/morning
```

Manually trigger morning check-ins for all members.

### Get Team Members
```
GET /team-checkin/members
```

Get list of all team members and their status.

## Usage

### Automatic Check-ins

When the agent runs automatically (via cron or daemon), it will:
1. Generate messages
2. Queue them for approval
3. Wait for your approval via the UI

### Manual Triggers

Use the UI buttons or API to manually trigger:
- **Follow-up**: Check members who are quiet and generate follow-up messages
- **Morning Check-in**: Send morning greetings to all team members

### Approval Workflow

1. Messages appear in the approval UI
2. Review the message content and context
3. Click "Approve & Send" to send immediately
4. Or click "Reject" to discard

## Message Queue Storage

Messages are stored in:
```
config/message_queue.json
```

This file contains:
- Pending messages (awaiting approval)
- Message history (approved, rejected, sent, failed)

Old messages are automatically cleaned up after 7 days.

## Integration with Dashboard

You can integrate the approval UI into your existing Next.js dashboard by:

1. Creating a new page/route for team check-in
2. Using the API endpoints to fetch and display messages
3. Adding approval/rejection buttons

Example React component:

```tsx
import { useState, useEffect } from 'react';

export function TeamCheckinApproval() {
  const [messages, setMessages] = useState([]);
  
  useEffect(() => {
    fetch('http://localhost:8502/team-checkin/messages/pending')
      .then(res => res.json())
      .then(setMessages);
  }, []);
  
  const approveMessage = async (id: string) => {
    await fetch(`http://localhost:8502/team-checkin/messages/${id}/approve`, {
      method: 'POST'
    });
    // Refresh messages
  };
  
  // Render messages...
}
```

## Configuration

The message queue is automatically initialized when the agent starts. No additional configuration needed.

## Troubleshooting

### Messages not appearing
- Check that the agent is running and generating messages
- Verify the API server is running on port 8502
- Check browser console for CORS errors (if accessing from different origin)

### Messages not sending after approval
- Check Slack token is configured correctly
- Verify member has `slack_user_id` set
- Check agent logs for errors

### API errors
- Ensure FastAPI server is running
- Check that `api_team_checkin.py` is imported in `api.py`
- Verify all dependencies are installed
