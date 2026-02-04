"""
Google Drive API Client

Provides access to Google Drive for document storage and retrieval.
Uses unified Google authentication (google_auth module).
"""

import os
import io
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# Google API imports
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    build = None

# Import unified Google auth
import sys
SERVICES_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SERVICES_ROOT))

from google_auth import get_google_auth

@dataclass
class DriveFile:
    """Represents a Google Drive file."""
    id: str
    name: str
    mime_type: str
    size: Optional[int] = None
    created_time: Optional[str] = None
    modified_time: Optional[str] = None
    web_view_link: Optional[str] = None
    parents: Optional[List[str]] = None


class DriveClient:
    """
    Google Drive API client using unified authentication.
    
    Supports:
    - List files/folders
    - Search files
    - Download files
    - Upload files
    - Get file metadata
    """

    def __init__(self):
        """Initialize Drive client with unified Google auth."""
        if not GOOGLE_API_AVAILABLE:
            raise ImportError("Google API libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib")
        
        self._service = None
        self._auth = get_google_auth()

    @property
    def is_authenticated(self) -> bool:
        """Check if authenticated with Google."""
        return self._auth.is_authenticated if self._auth else False

    @property
    def service(self):
        """Get or create Drive API service."""
        if self._service is None:
            auth = get_google_auth()
            
            if not auth.is_authenticated:
                raise RuntimeError(
                    "Not authenticated with Google. "
                    "Run: python -m services.google_auth"
                )
            
            creds = auth.credentials
            self._service = build('drive', 'v3', credentials=creds)
            self._auth = auth
        
        return self._service

    def list_files(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
        page_size: int = 100,
        order_by: str = "modifiedTime desc"
    ) -> List[DriveFile]:
        """
        List files from Google Drive.
        
        Args:
            folder_id: If provided, list files in this folder
            query: Drive API query string (e.g., "name contains 'report'")
            page_size: Number of files per page
            order_by: Sort order (e.g., "modifiedTime desc", "name")
        
        Returns:
            List of DriveFile objects
        """
        try:
            # Build query
            q_parts = []
            if folder_id:
                q_parts.append(f"'{folder_id}' in parents")
            if query:
                q_parts.append(query)
            q_parts.append("trashed=false")
            
            final_query = " and ".join(q_parts)
            
            results = self.service.files().list(
                q=final_query,
                pageSize=page_size,
                orderBy=order_by,
                fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, parents)"
            ).execute()
            
            files = results.get('files', [])
            
            return [
                DriveFile(
                    id=f['id'],
                    name=f['name'],
                    mime_type=f['mimeType'],
                    size=int(f.get('size', 0)) if 'size' in f else None,
                    created_time=f.get('createdTime'),
                    modified_time=f.get('modifiedTime'),
                    web_view_link=f.get('webViewLink'),
                    parents=f.get('parents')
                )
                for f in files
            ]
        
        except Exception as e:
            print(f"Error listing Drive files: {e}")
            return []

    def search_files(self, search_term: str, max_results: int = 20) -> List[DriveFile]:
        """
        Search for files by name.
        
        Args:
            search_term: Text to search for in file names
            max_results: Maximum number of results
        
        Returns:
            List of matching DriveFile objects
        """
        query = f"name contains '{search_term}'"
        return self.list_files(query=query, page_size=max_results)

    def get_file_metadata(self, file_id: str) -> Optional[DriveFile]:
        """
        Get metadata for a specific file.
        
        Args:
            file_id: Google Drive file ID
        
        Returns:
            DriveFile object or None if not found
        """
        try:
            file = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, size, createdTime, modifiedTime, webViewLink, parents"
            ).execute()
            
            return DriveFile(
                id=file['id'],
                name=file['name'],
                mime_type=file['mimeType'],
                size=int(file.get('size', 0)) if 'size' in file else None,
                created_time=file.get('createdTime'),
                modified_time=file.get('modifiedTime'),
                web_view_link=file.get('webViewLink'),
                parents=file.get('parents')
            )
        
        except Exception as e:
            print(f"Error getting file metadata: {e}")
            return None

    def download_file(self, file_id: str, output_path: str) -> bool:
        """
        Download a file from Google Drive.
        
        Args:
            file_id: Google Drive file ID
            output_path: Local path to save file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"Download {int(status.progress() * 100)}%")
            
            return True
        
        except Exception as e:
            print(f"Error downloading file: {e}")
            return False

    def upload_file(
        self,
        file_path: str,
        name: Optional[str] = None,
        folder_id: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Local path to file
            name: Name for file in Drive (defaults to filename)
            folder_id: Parent folder ID (optional)
            mime_type: MIME type (auto-detected if not provided)
        
        Returns:
            File ID if successful, None otherwise
        """
        try:
            file_metadata = {
                'name': name or Path(file_path).name
            }
            
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            media = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=True
            )
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, webViewLink'
            ).execute()
            
            print(f"✅ Uploaded: {file.get('name')} (ID: {file.get('id')})")
            return file.get('id')
        
        except Exception as e:
            print(f"Error uploading file: {e}")
            return None


# Singleton instance
_drive_client: Optional[DriveClient] = None

def get_drive_client() -> DriveClient:
    """Get or create the singleton Drive client."""
    global _drive_client
    if _drive_client is None:
        _drive_client = DriveClient()
    return _drive_client


if __name__ == "__main__":
    # Test Drive client
    client = get_drive_client()
    
    print("📁 Listing recent files from Google Drive:")
    files = client.list_files(page_size=10)
    
    for f in files:
        print(f"  - {f.name} ({f.mime_type})")
        if f.web_view_link:
            print(f"    {f.web_view_link}")
