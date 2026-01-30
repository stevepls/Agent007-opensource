"""
Unified Google OAuth2 Authentication

Provides shared authentication for all Google APIs:
- Gmail
- Google Sheets  
- Google Drive
- Google Calendar (future)

Uses a single credentials.json and token.json for all services.

Setup:
1. Go to https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client ID (Desktop app)
3. Download JSON → ~/.config/agent007/google/credentials.json
4. Run authenticate() to get tokens
"""

import os
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    Credentials = None
    InstalledAppFlow = None
    Request = None
    build = None


# Configuration
CONFIG_DIR = Path(os.getenv("GOOGLE_CONFIG_DIR", os.path.expanduser("~/.config/agent007/google")))
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "unified_token.json"

# Combined scopes for all Google services
ALL_SCOPES = [
    # Gmail
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
    
    # Google Sheets
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    
    # Google Drive
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.metadata.readonly',
    
    # Google Calendar (for future use)
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events',
]


@dataclass
class GoogleAuthStatus:
    """Status of Google authentication."""
    available: bool  # Libraries installed
    credentials_exist: bool  # credentials.json exists
    token_exists: bool  # token.json exists
    authenticated: bool  # Valid credentials
    scopes: List[str]  # Active scopes
    email: Optional[str]  # Authenticated account email


class GoogleAuth:
    """
    Unified Google OAuth2 authentication manager.
    
    Provides a single authentication flow for all Google services.
    All clients (Gmail, Sheets, Drive) can use the same credentials.
    """
    
    _instance: Optional['GoogleAuth'] = None
    _credentials: Optional[Credentials] = None
    _initialized: bool = False
    
    def __new__(cls):
        """Singleton pattern - only one auth instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _ensure_initialized(self):
        """Load existing token if available."""
        if self._initialized:
            return
        self._initialized = True
        
        if GOOGLE_API_AVAILABLE and TOKEN_FILE.exists():
            try:
                self._credentials = Credentials.from_authorized_user_file(
                    str(TOKEN_FILE), ALL_SCOPES
                )
                # Refresh if expired
                if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                    self._credentials.refresh(Request())
                    self._save_token()
            except Exception:
                pass  # Will require re-authentication
    
    @property
    def is_available(self) -> bool:
        """Check if Google API libraries are installed."""
        return GOOGLE_API_AVAILABLE
    
    @property
    def credentials_exist(self) -> bool:
        """Check if credentials.json exists."""
        return CREDENTIALS_FILE.exists()
    
    @property
    def token_exists(self) -> bool:
        """Check if token.json exists."""
        return TOKEN_FILE.exists()
    
    @property
    def is_authenticated(self) -> bool:
        """Check if we have valid credentials."""
        self._ensure_initialized()
        return self._credentials is not None and self._credentials.valid
    
    @property
    def credentials(self) -> Optional[Credentials]:
        """Get current credentials (may need refresh)."""
        self._ensure_initialized()
        if self._credentials and self._credentials.expired and self._credentials.refresh_token:
            self._credentials.refresh(Request())
            self._save_token()
        return self._credentials
    
    def get_status(self) -> GoogleAuthStatus:
        """Get current authentication status."""
        self._ensure_initialized()
        email = None
        scopes = []
        
        if self._credentials:
            scopes = list(self._credentials.scopes or [])
            # Try to get email from userinfo
            if self.is_authenticated:
                try:
                    service = build('oauth2', 'v2', credentials=self._credentials)
                    user_info = service.userinfo().get().execute()
                    email = user_info.get('email')
                except Exception:
                    pass
        
        return GoogleAuthStatus(
            available=self.is_available,
            credentials_exist=self.credentials_exist,
            token_exists=self.token_exists,
            authenticated=self.is_authenticated,
            scopes=scopes,
            email=email,
        )
    
    def _save_token(self):
        """Save current credentials to token file."""
        if self._credentials:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                f.write(self._credentials.to_json())
    
    def authenticate(self, scopes: List[str] = None) -> bool:
        """
        Authenticate with Google APIs.
        
        Args:
            scopes: Optional list of scopes. Defaults to ALL_SCOPES.
        
        Returns:
            True if authentication successful.
        
        Raises:
            ImportError: If Google API libraries not installed.
            FileNotFoundError: If credentials.json not found.
        """
        if not GOOGLE_API_AVAILABLE:
            raise ImportError(
                "Google API libraries not installed. Run:\n"
                "pip install google-api-python-client google-auth-oauthlib"
            )
        
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"OAuth credentials not found at:\n{CREDENTIALS_FILE}\n\n"
                "Setup instructions:\n"
                "1. Go to https://console.cloud.google.com/apis/credentials\n"
                "2. Create OAuth 2.0 Client ID (Desktop app)\n"
                "3. Download JSON and save to the path above"
            )
        
        use_scopes = scopes or ALL_SCOPES
        
        # Try to load existing token
        if TOKEN_FILE.exists():
            self._credentials = Credentials.from_authorized_user_file(
                str(TOKEN_FILE), use_scopes
            )
        
        # Refresh or get new token
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(Request())
            else:
                # Need new authorization
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), use_scopes
                )
                # Use fixed port for Web OAuth clients (must match Google Cloud Console redirect URI)
                self._credentials = flow.run_local_server(port=8080)
            
            self._save_token()
        
        return True
    
    def revoke(self) -> bool:
        """Revoke current credentials and delete token file."""
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self._credentials = None
        return True
    
    # =========================================================================
    # Service builders
    # =========================================================================
    
    def get_gmail_service(self):
        """Get Gmail API service."""
        if not self.is_authenticated:
            self.authenticate()
        return build('gmail', 'v1', credentials=self._credentials)
    
    def get_sheets_service(self):
        """Get Sheets API service."""
        if not self.is_authenticated:
            self.authenticate()
        return build('sheets', 'v4', credentials=self._credentials)
    
    def get_drive_service(self):
        """Get Drive API service."""
        if not self.is_authenticated:
            self.authenticate()
        return build('drive', 'v3', credentials=self._credentials)
    
    def get_calendar_service(self):
        """Get Calendar API service."""
        if not self.is_authenticated:
            self.authenticate()
        return build('calendar', 'v3', credentials=self._credentials)


# Global instance
_auth: Optional[GoogleAuth] = None


def get_google_auth() -> GoogleAuth:
    """Get the global Google auth manager."""
    global _auth
    if _auth is None:
        _auth = GoogleAuth()
    return _auth


def check_google_setup() -> dict:
    """
    Quick check of Google setup status.
    
    Returns dict with:
    - installed: bool - libraries installed
    - credentials: bool - credentials.json exists
    - authenticated: bool - valid token exists
    - setup_instructions: str - what to do next
    """
    auth = get_google_auth()
    
    result = {
        "installed": auth.is_available,
        "credentials": auth.credentials_exist,
        "authenticated": False,
        "setup_instructions": "",
    }
    
    if not auth.is_available:
        result["setup_instructions"] = (
            "Install Google API libraries:\n"
            "pip install google-api-python-client google-auth-oauthlib"
        )
    elif not auth.credentials_exist:
        result["setup_instructions"] = (
            f"Download OAuth credentials to:\n{CREDENTIALS_FILE}\n\n"
            "1. Go to https://console.cloud.google.com/apis/credentials\n"
            "2. Create OAuth 2.0 Client ID (Desktop app)\n"
            "3. Download JSON and save to path above"
        )
    else:
        # Try to authenticate
        try:
            if auth.token_exists:
                auth.authenticate()
                result["authenticated"] = auth.is_authenticated
        except Exception:
            pass
        
        if not result["authenticated"]:
            result["setup_instructions"] = (
                "Run authentication:\n"
                "python -c \"from services.google_auth import get_google_auth; "
                "get_google_auth().authenticate()\""
            )
        else:
            result["setup_instructions"] = "✅ Google APIs ready!"
    
    return result
