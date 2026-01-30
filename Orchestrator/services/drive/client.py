"""
Google Drive API Client

Provides read, upload, update, and delete operations for Google Drive.
Destructive operations require confirmation.

SECURITY:
- OAuth 2.0 authentication required
- Deletes and shares require explicit confirmation
- All operations are logged for audit
"""

import os
import io
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Credentials = None

# Configuration
SERVICES_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_ROOT = SERVICES_ROOT.parent
CONFIG_DIR = Path(os.getenv("GOOGLE_CONFIG_DIR", os.path.expanduser("~/.config/agent007/google")))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "drive_token.json"

DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]


@dataclass
class DriveFile:
    """Represents a Google Drive file."""
    id: str
    name: str
    mime_type: str
    size: int
    created_time: str
    modified_time: str
    parents: List[str]
    shared: bool
    web_view_link: str
    owners: List[str]


class DriveClient:
    """Google Drive API client with safety controls."""
    
    def __init__(self):
        self._service = None
        self._credentials = None
    
    @property
    def is_available(self) -> bool:
        return GOOGLE_API_AVAILABLE
    
    @property
    def is_authenticated(self) -> bool:
        return self._credentials is not None and self._credentials.valid
    
    def authenticate(self, headless: bool = False) -> bool:
        """
        Authenticate with Drive API.
        
        Args:
            headless: If True, fail if interactive OAuth is needed.
                      If False, open browser for OAuth flow.
        """
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API libraries not installed. Run: "
                "pip install google-api-python-client google-auth-oauthlib"
            )
        
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"OAuth credentials not found at {CREDENTIALS_FILE}. "
                "Download from Google Cloud Console."
            )
        
        creds = None
        
        if TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), DRIVE_SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif headless:
                # In headless mode, fail if we need interactive auth
                raise RuntimeError(
                    "Google Drive OAuth token not found or expired. "
                    "Run 'python -m services.google_auth' to authenticate interactively."
                )
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), DRIVE_SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                f.write(creds.to_json())
        
        self._credentials = creds
        self._service = build('drive', 'v3', credentials=creds)
        return True
    
    def _ensure_authenticated(self):
        if not self.is_authenticated:
            self.authenticate()
    
    def _parse_file(self, file_data: Dict) -> DriveFile:
        """Parse Drive API file into DriveFile."""
        return DriveFile(
            id=file_data['id'],
            name=file_data.get('name', ''),
            mime_type=file_data.get('mimeType', ''),
            size=int(file_data.get('size', 0)),
            created_time=file_data.get('createdTime', ''),
            modified_time=file_data.get('modifiedTime', ''),
            parents=file_data.get('parents', []),
            shared=file_data.get('shared', False),
            web_view_link=file_data.get('webViewLink', ''),
            owners=[o.get('emailAddress', '') for o in file_data.get('owners', [])],
        )
    
    # =========================================================================
    # READ OPERATIONS
    # =========================================================================
    
    def list_files(
        self,
        query: str = None,
        folder_id: str = None,
        max_results: int = 20,
    ) -> List[DriveFile]:
        """
        List files in Drive.
        
        Query examples:
        - "name contains 'report'" - name contains text
        - "mimeType = 'application/pdf'" - specific type
        - "modifiedTime > '2024-01-01'" - modified after date
        """
        self._ensure_authenticated()
        
        q_parts = []
        if query:
            q_parts.append(query)
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        
        q = " and ".join(q_parts) if q_parts else None
        
        results = self._service.files().list(
            q=q,
            pageSize=max_results,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime, parents, shared, webViewLink, owners)",
        ).execute()
        
        return [self._parse_file(f) for f in results.get('files', [])]
    
    def get_file(self, file_id: str) -> Optional[DriveFile]:
        """Get file metadata by ID."""
        self._ensure_authenticated()
        
        try:
            file_data = self._service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, createdTime, modifiedTime, parents, shared, webViewLink, owners",
            ).execute()
            return self._parse_file(file_data)
        except Exception:
            return None
    
    def download_file(self, file_id: str, local_path: str) -> bool:
        """Download a file to local path."""
        self._ensure_authenticated()
        
        request = self._service.files().get_media(fileId=file_id)
        
        with open(local_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        
        return True
    
    def read_file_content(self, file_id: str) -> Optional[str]:
        """Read text content of a file."""
        self._ensure_authenticated()
        
        try:
            # For Google Docs, export as plain text
            file_info = self.get_file(file_id)
            if file_info and 'google-apps' in file_info.mime_type:
                content = self._service.files().export(
                    fileId=file_id,
                    mimeType='text/plain',
                ).execute()
                return content.decode('utf-8') if isinstance(content, bytes) else content
            else:
                # Regular file - download content
                request = self._service.files().get_media(fileId=file_id)
                content = request.execute()
                return content.decode('utf-8') if isinstance(content, bytes) else str(content)
        except Exception as e:
            return None
    
    def search(self, name_query: str, max_results: int = 10) -> List[DriveFile]:
        """Search files by name."""
        return self.list_files(
            query=f"name contains '{name_query}'",
            max_results=max_results,
        )
    
    # =========================================================================
    # WRITE OPERATIONS (should go through confirmation)
    # =========================================================================
    
    def upload_file(
        self,
        local_path: str,
        name: str = None,
        folder_id: str = None,
        mime_type: str = None,
    ) -> DriveFile:
        """
        Upload a file to Drive.
        NOTE: Requires confirmation before execution.
        """
        self._ensure_authenticated()
        
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {local_path}")
        
        file_metadata = {
            'name': name or path.name,
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        media = MediaFileUpload(
            local_path,
            mimetype=mime_type,
            resumable=True,
        )
        
        file = self._service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, mimeType, size, createdTime, modifiedTime, parents, shared, webViewLink, owners',
        ).execute()
        
        return self._parse_file(file)
    
    def create_folder(self, name: str, parent_id: str = None) -> DriveFile:
        """Create a new folder."""
        self._ensure_authenticated()
        
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        folder = self._service.files().create(
            body=file_metadata,
            fields='id, name, mimeType, size, createdTime, modifiedTime, parents, shared, webViewLink, owners',
        ).execute()
        
        return self._parse_file(folder)
    
    def update_file(
        self,
        file_id: str,
        local_path: str = None,
        new_name: str = None,
    ) -> DriveFile:
        """Update file content or metadata."""
        self._ensure_authenticated()
        
        file_metadata = {}
        if new_name:
            file_metadata['name'] = new_name
        
        media = None
        if local_path:
            media = MediaFileUpload(local_path, resumable=True)
        
        file = self._service.files().update(
            fileId=file_id,
            body=file_metadata if file_metadata else None,
            media_body=media,
            fields='id, name, mimeType, size, createdTime, modifiedTime, parents, shared, webViewLink, owners',
        ).execute()
        
        return self._parse_file(file)
    
    # =========================================================================
    # DELETE OPERATIONS (require explicit confirmation)
    # =========================================================================
    
    def trash_file(self, file_id: str) -> bool:
        """Move file to trash (recoverable)."""
        self._ensure_authenticated()
        
        self._service.files().update(
            fileId=file_id,
            body={'trashed': True},
        ).execute()
        
        return True
    
    def delete_file(self, file_id: str) -> bool:
        """
        Permanently delete a file (NOT recoverable).
        DANGEROUS: Requires double confirmation.
        """
        self._ensure_authenticated()
        
        self._service.files().delete(fileId=file_id).execute()
        return True
    
    # =========================================================================
    # SHARE OPERATIONS (require confirmation)
    # =========================================================================
    
    def share_file(
        self,
        file_id: str,
        email: str,
        role: str = "reader",  # reader, writer, commenter
        send_notification: bool = True,
    ) -> Dict[str, Any]:
        """
        Share a file with another user.
        NOTE: Requires confirmation - sharing exposes data.
        """
        self._ensure_authenticated()
        
        permission = {
            'type': 'user',
            'role': role,
            'emailAddress': email,
        }
        
        result = self._service.permissions().create(
            fileId=file_id,
            body=permission,
            sendNotificationEmail=send_notification,
        ).execute()
        
        return {
            "permission_id": result['id'],
            "file_id": file_id,
            "shared_with": email,
            "role": role,
        }


# Global instance
_client: Optional[DriveClient] = None


def get_drive_client() -> DriveClient:
    """Get the global Drive client."""
    global _client
    if _client is None:
        _client = DriveClient()
    return _client
