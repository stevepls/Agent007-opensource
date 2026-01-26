"""
Google Drive Tools for CrewAI Agents

Provides safe, controlled access to Google Drive.
Destructive operations (delete, share) require manual confirmation.
"""

import sys
from pathlib import Path
from typing import List
from crewai.tools import BaseTool

TOOLS_ROOT = Path(__file__).parent
ORCHESTRATOR_ROOT = TOOLS_ROOT.parent
sys.path.insert(0, str(ORCHESTRATOR_ROOT))

from governance.audit import get_audit_logger


class DriveListFilesTool(BaseTool):
    """List files in Google Drive."""
    
    name: str = "drive_list_files"
    description: str = """List files in Google Drive.
    Input: optional search query using Drive syntax
    Examples:
      - "" (empty) - list recent files
      - "name contains 'report'" - search by name
      - "mimeType = 'application/pdf'" - filter by type"""
    
    def _run(self, query: str = "") -> str:
        from services.drive.client import get_drive_client
        
        try:
            client = get_drive_client()
            if not client.is_authenticated:
                return "Google Drive not authenticated. Run setup to authenticate."
            
            files = client.list_files(query=query or None, max_results=15)
            
            if not files:
                return "No files found."
            
            lines = ["Drive files:\n"]
            for f in files:
                icon = "📁" if "folder" in f.mime_type else "📄"
                size = f"{f.size / 1024:.1f}KB" if f.size else ""
                lines.append(f"{icon} {f.name} {size}")
                lines.append(f"   ID: {f.id}")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class DriveSearchTool(BaseTool):
    """Search for files in Drive."""
    
    name: str = "drive_search"
    description: str = """Search for files by name.
    Input: search term"""
    
    def _run(self, search_term: str) -> str:
        from services.drive.client import get_drive_client
        
        if not search_term:
            return "Please provide a search term."
        
        try:
            client = get_drive_client()
            if not client.is_authenticated:
                return "Not authenticated."
            
            files = client.search(search_term, max_results=10)
            
            if not files:
                return f"No files found matching '{search_term}'."
            
            lines = [f"Found {len(files)} file(s):\n"]
            for f in files:
                lines.append(f"• {f.name} (ID: {f.id})")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error: {e}"


class DriveReadFileTool(BaseTool):
    """Read content of a text file."""
    
    name: str = "drive_read_file"
    description: str = """Read the text content of a Drive file.
    Input: file ID
    Works with Google Docs, text files, etc."""
    
    def _run(self, file_id: str) -> str:
        from services.drive.client import get_drive_client
        
        if not file_id:
            return "Please provide a file ID."
        
        try:
            client = get_drive_client()
            if not client.is_authenticated:
                return "Not authenticated."
            
            content = client.read_file_content(file_id.strip())
            
            if content is None:
                return f"Could not read file {file_id}. It may be binary or inaccessible."
            
            # Truncate if too long
            if len(content) > 5000:
                return f"File content (truncated to 5000 chars):\n\n{content[:5000]}\n\n... [truncated]"
            
            return f"File content:\n\n{content}"
            
        except Exception as e:
            return f"Error: {e}"


class DriveGetFileTool(BaseTool):
    """Get file metadata."""
    
    name: str = "drive_get_file"
    description: str = """Get metadata about a Drive file.
    Input: file ID"""
    
    def _run(self, file_id: str) -> str:
        from services.drive.client import get_drive_client
        
        if not file_id:
            return "Please provide a file ID."
        
        try:
            client = get_drive_client()
            if not client.is_authenticated:
                return "Not authenticated."
            
            f = client.get_file(file_id.strip())
            
            if not f:
                return f"File {file_id} not found."
            
            return (
                f"File: {f.name}\n"
                f"ID: {f.id}\n"
                f"Type: {f.mime_type}\n"
                f"Size: {f.size / 1024:.1f}KB\n"
                f"Created: {f.created_time}\n"
                f"Modified: {f.modified_time}\n"
                f"Shared: {'Yes' if f.shared else 'No'}\n"
                f"Link: {f.web_view_link}"
            )
            
        except Exception as e:
            return f"Error: {e}"


class DriveQueueUploadTool(BaseTool):
    """Queue a file upload for confirmation."""
    
    name: str = "drive_queue_upload"
    description: str = """Queue a file upload to Google Drive.
    Requires human approval before execution.
    
    Input format: JSON with fields:
    - local_path: path to local file (REQUIRED)
    - name: name in Drive (optional, defaults to filename)
    - folder_id: destination folder ID (optional)
    
    Example: {"local_path": "/path/to/file.pdf", "name": "Report Q1.pdf"}"""
    
    def _run(self, input_json: str) -> str:
        import json
        from services.message_queue import get_message_queue, MessageType
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        local_path = data.get("local_path")
        if not local_path:
            return "Missing required field: local_path"
        
        path = Path(local_path)
        if not path.exists():
            return f"File not found: {local_path}"
        
        queue = get_message_queue()
        msg = queue.queue(
            msg_type=MessageType.DRIVE_UPLOAD,
            channel="google_drive",
            content=f"Upload: {path.name}",
            metadata={
                "local_path": local_path,
                "name": data.get("name", path.name),
                "folder_id": data.get("folder_id"),
            },
            created_by="agent",
            requires_approval=True,
        )
        
        get_audit_logger().log_tool_use(
            agent="drive",
            tool="drive_queue_upload",
            input_data={"path": local_path},
            output_data={"queue_id": msg.id},
        )
        
        return (
            f"✓ Upload queued for approval\n"
            f"Queue ID: {msg.id}\n"
            f"File: {path.name}\n"
            f"Status: PENDING APPROVAL"
        )


class DriveQueueDeleteTool(BaseTool):
    """Queue a file deletion for confirmation."""
    
    name: str = "drive_queue_delete"
    description: str = """Queue a file for deletion (move to trash).
    Requires human approval before execution.
    
    Input: file ID to delete
    
    NOTE: This is a DESTRUCTIVE operation. Use with caution."""
    
    def _run(self, file_id: str) -> str:
        from services.drive.client import get_drive_client
        from services.message_queue import get_message_queue, MessageType
        
        if not file_id:
            return "Please provide a file ID."
        
        file_id = file_id.strip()
        
        # Get file info first
        try:
            client = get_drive_client()
            file_info = client.get_file(file_id) if client.is_authenticated else None
            file_name = file_info.name if file_info else file_id
        except Exception:
            file_name = file_id
        
        queue = get_message_queue()
        msg = queue.queue(
            msg_type=MessageType.DRIVE_DELETE,
            channel="google_drive",
            content=f"Delete: {file_name}",
            subject=f"⚠️ DELETE: {file_name}",
            metadata={
                "file_id": file_id,
                "file_name": file_name,
            },
            created_by="agent",
            requires_approval=True,
        )
        
        get_audit_logger().log_tool_use(
            agent="drive",
            tool="drive_queue_delete",
            input_data={"file_id": file_id},
            output_data={"queue_id": msg.id},
        )
        
        return (
            f"⚠️ Delete queued for approval\n"
            f"Queue ID: {msg.id}\n"
            f"File: {file_name} ({file_id})\n"
            f"Status: PENDING APPROVAL\n\n"
            "A human MUST approve this deletion."
        )


class DriveQueueShareTool(BaseTool):
    """Queue a file share for confirmation."""
    
    name: str = "drive_queue_share"
    description: str = """Queue sharing a file with another user.
    Requires human approval before execution.
    
    Input format: JSON with fields:
    - file_id: file ID to share (REQUIRED)
    - email: email address to share with (REQUIRED)
    - role: permission level - "reader", "writer", or "commenter" (default: reader)
    
    Example: {"file_id": "abc123", "email": "client@example.com", "role": "reader"}
    
    NOTE: This EXPOSES DATA to another person. Use with caution."""
    
    def _run(self, input_json: str) -> str:
        import json
        from services.drive.client import get_drive_client
        from services.message_queue import get_message_queue, MessageType
        
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return "Invalid JSON input."
        
        file_id = data.get("file_id")
        email = data.get("email")
        role = data.get("role", "reader")
        
        if not file_id:
            return "Missing required field: file_id"
        if not email:
            return "Missing required field: email"
        if role not in ("reader", "writer", "commenter"):
            return "Invalid role. Use: reader, writer, or commenter"
        
        # Get file info
        try:
            client = get_drive_client()
            file_info = client.get_file(file_id) if client.is_authenticated else None
            file_name = file_info.name if file_info else file_id
        except Exception:
            file_name = file_id
        
        queue = get_message_queue()
        msg = queue.queue(
            msg_type=MessageType.DRIVE_SHARE,
            channel=email,
            content=f"Share '{file_name}' with {email} as {role}",
            subject=f"⚠️ SHARE: {file_name} → {email}",
            metadata={
                "file_id": file_id,
                "file_name": file_name,
                "email": email,
                "role": role,
            },
            created_by="agent",
            requires_approval=True,
        )
        
        get_audit_logger().log_tool_use(
            agent="drive",
            tool="drive_queue_share",
            input_data={"file_id": file_id, "email": email, "role": role},
            output_data={"queue_id": msg.id},
        )
        
        return (
            f"⚠️ Share queued for approval\n"
            f"Queue ID: {msg.id}\n"
            f"File: {file_name}\n"
            f"Share with: {email}\n"
            f"Permission: {role}\n"
            f"Status: PENDING APPROVAL\n\n"
            "A human MUST approve this share."
        )


def get_drive_tools() -> List[BaseTool]:
    """Get all Drive tools for CrewAI agents."""
    return [
        DriveListFilesTool(),
        DriveSearchTool(),
        DriveReadFileTool(),
        DriveGetFileTool(),
        DriveQueueUploadTool(),
        DriveQueueDeleteTool(),
        DriveQueueShareTool(),
    ]
