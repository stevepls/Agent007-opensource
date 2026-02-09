"""
Google OAuth2 Authentication for Orchestrator API

Provides:
- /auth/login      → Redirects to Google OAuth consent screen
- /auth/callback   → Handles Google's redirect, sets session cookie
- /auth/logout     → Clears session cookie
- /auth/me         → Returns current user info

Environment Variables:
- GOOGLE_OAUTH_CLIENT_ID     — OAuth2 Client ID (Web application type)
- GOOGLE_OAUTH_CLIENT_SECRET — OAuth2 Client Secret
- SESSION_SECRET_KEY         — Secret key for signing JWT session tokens
- ALLOWED_EMAILS             — Comma-separated list of allowed email addresses (optional, allows all if unset)
- AUTH_ENABLED               — Set to "false" to disable auth (default: true)
"""

import os
import json
import time
import hashlib
import hmac
import base64
import secrets
import collections
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote_plus

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

# ============================================================================
# Configuration
# ============================================================================

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
SESSION_SECRET = os.getenv("SESSION_SECRET_KEY", secrets.token_hex(32))
ALLOWED_EMAILS = [e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()]
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() != "false"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
COOKIE_NAME = "orchestrator_session"

# Cross-domain auth: allowed external services that can receive auth tokens
ALLOWED_REDIRECT_DOMAINS = [
    d.strip() for d in os.getenv("ALLOWED_REDIRECT_DOMAINS", "").split(",") if d.strip()
]
# Auto-include dashboard domain if set
_dashboard_url = os.getenv("DASHBOARD_PUBLIC_URL", "")
if _dashboard_url:
    from urllib.parse import urlparse as _urlparse
    _parsed = _urlparse(_dashboard_url)
    if _parsed.netloc and _parsed.netloc not in ALLOWED_REDIRECT_DOMAINS:
        ALLOWED_REDIRECT_DOMAINS.append(_parsed.netloc)
# Always allow Railway dashboard domain pattern
ALLOWED_REDIRECT_DOMAINS.extend([
    "dashboard-staging-ba60.up.railway.app",
    "localhost:3000",
])

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Rate Limiter (in-memory, per-IP, sliding window)
# ============================================================================

class RateLimiter:
    """Simple in-memory rate limiter using sliding window."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 300):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = collections.defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, respecting proxy headers."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def is_rate_limited(self, request: Request) -> bool:
        """Check if the request should be rate limited."""
        ip = self._get_client_ip(request)
        now = time.time()
        cutoff = now - self.window_seconds

        # Clean old entries
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

        if len(self._requests[ip]) >= self.max_requests:
            return True

        self._requests[ip].append(now)
        return False

    def remaining(self, request: Request) -> int:
        """Get remaining requests for this IP."""
        ip = self._get_client_ip(request)
        now = time.time()
        cutoff = now - self.window_seconds
        recent = [t for t in self._requests[ip] if t > cutoff]
        return max(0, self.max_requests - len(recent))


# 10 login attempts per 5 minutes per IP
login_limiter = RateLimiter(max_requests=10, window_seconds=300)


# ============================================================================
# Session Helpers (simple HMAC-signed JSON tokens — no extra deps)
# ============================================================================

def _sign(payload: dict) -> str:
    """Create a signed session token from payload."""
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    sig = hmac.new(SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify(token: str) -> Optional[dict]:
    """Verify and decode a signed session token. Returns None if invalid."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        expected_sig = hmac.new(SESSION_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload_json = base64.urlsafe_b64decode(payload_b64).decode()
        payload = json.loads(payload_json)
        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def create_session(user_info: dict) -> str:
    """Create a session token for an authenticated user."""
    payload = {
        "email": user_info.get("email", ""),
        "name": user_info.get("name", ""),
        "picture": user_info.get("picture", ""),
        "iat": int(time.time()),
        "exp": int(time.time()) + SESSION_MAX_AGE,
    }
    return _sign(payload)


def create_cross_domain_token(user_info: dict) -> str:
    """Create a short-lived signed token for cross-domain auth handoff."""
    payload = {
        "email": user_info.get("email", ""),
        "name": user_info.get("name", ""),
        "picture": user_info.get("picture", ""),
        "type": "cross_domain",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,  # 5 minutes only
    }
    return _sign(payload)


def _is_allowed_redirect(url: str) -> bool:
    """Check if a redirect URL is allowed (prevent open redirect attacks)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.hostname or ""
        return any(host == d or host.endswith(f".{d}") for d in ALLOWED_REDIRECT_DOMAINS)
    except Exception:
        return False


def get_current_user(request: Request) -> Optional[dict]:
    """Extract current user from session cookie. Returns None if not authenticated."""
    if not AUTH_ENABLED:
        return {"email": "dev@localhost", "name": "Development Mode", "picture": ""}

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return _verify(token)


def _get_redirect_uri(request: Request) -> str:
    """Build the OAuth callback URI based on the current request."""
    # Use X-Forwarded headers if behind a proxy (Railway)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}/auth/callback"


# ============================================================================
# Auth check helper (used by middleware)
# ============================================================================

# Paths that don't require authentication
PUBLIC_PATHS = {
    "/auth/login",
    "/auth/callback",
    "/auth/logout",
    "/auth/login-page",
    "/auth/verify-token",
    "/health",
    # /docs, /redoc, /openapi.json are NOT public — require login
}

PUBLIC_PREFIXES = [
    "/auth/",
]


def is_public_path(path: str) -> bool:
    """Check if a path is accessible without authentication."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ============================================================================
# Login Page
# ============================================================================

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In — Agent007</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
            color: #fff;
        }
        .login-card {
            background: rgba(255,255,255,0.08);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 20px;
            padding: 48px 40px;
            width: 100%;
            max-width: 420px;
            margin: 20px;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        }
        .logo {
            width: 64px;
            height: 64px;
            margin: 0 auto 24px;
            border-radius: 16px;
            background: linear-gradient(135deg, #7c3aed, #db2777);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
        }
        h1 {
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 8px;
            letter-spacing: -0.5px;
        }
        .subtitle {
            color: rgba(255,255,255,0.6);
            font-size: 14px;
            margin-bottom: 36px;
        }
        .google-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            width: 100%;
            padding: 14px 24px;
            border: none;
            border-radius: 12px;
            background: #fff;
            color: #333;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
            min-height: 52px;
        }
        .google-btn:hover {
            background: #f0f0f0;
            transform: translateY(-1px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.2);
        }
        .google-btn:active { transform: translateY(0); }
        .google-btn svg { width: 20px; height: 20px; flex-shrink: 0; }
        .footer {
            margin-top: 32px;
            color: rgba(255,255,255,0.35);
            font-size: 12px;
        }
        .error-msg {
            background: rgba(220,53,69,0.2);
            border: 1px solid rgba(220,53,69,0.3);
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 20px;
            font-size: 14px;
            color: #ff8a8a;
        }
        @media (max-width: 480px) {
            .login-card { padding: 36px 24px; }
            h1 { font-size: 20px; }
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo">⚡</div>
        <h1>Agent007</h1>
        <p class="subtitle">Orchestrator Command Center</p>
        {{ERROR_BLOCK}}
        <a href="/auth/login" class="google-btn">
            <svg viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Sign in with Google
        </a>
        <div class="footer">Authorized users only</div>
    </div>
</body>
</html>"""


# ============================================================================
# Routes
# ============================================================================

@router.get("/login-page", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    """Serve the login page."""
    error_block = ""
    if error:
        # Escape HTML to prevent reflected XSS
        import html as _html
        safe_error = _html.escape(error)
        error_block = f'<div class="error-msg">{safe_error}</div>'
    html = LOGIN_PAGE_HTML.replace("{{ERROR_BLOCK}}", error_block)
    return HTMLResponse(content=html)


@router.get("/login")
async def login(request: Request, next_service: Optional[str] = None):
    """Redirect to Google OAuth consent screen.
    
    Args:
        next_service: Optional URL of an external service to redirect to after login.
                     Must be in ALLOWED_REDIRECT_DOMAINS for security.
    """
    # Rate limit login attempts
    if login_limiter.is_rate_limited(request):
        return RedirectResponse(
            url="/auth/login-page?error=Too+many+login+attempts.+Please+wait+a+few+minutes."
        )

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )

    redirect_uri = _get_redirect_uri(request)

    # Generate state parameter to prevent CSRF
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "state": state,
        "prompt": "select_account",
    }

    # Store state in a short-lived cookie
    response = RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=600,  # 10 minutes
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )

    # Store next_service redirect (if valid) for cross-domain auth
    if next_service and _is_allowed_redirect(next_service):
        response.set_cookie(
            key="auth_next_service",
            value=next_service,
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )

    return response


@router.get("/callback")
async def callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Google OAuth callback."""
    import httpx

    # Rate limit callbacks too
    if login_limiter.is_rate_limited(request):
        return RedirectResponse(
            url="/auth/login-page?error=Too+many+attempts.+Please+wait+a+few+minutes."
        )

    if error:
        return RedirectResponse(url=f"/auth/login-page?error={quote_plus(error)}")

    if not code:
        return RedirectResponse(url="/auth/login-page?error=No+authorization+code+received")

    # Verify state
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        return RedirectResponse(url="/auth/login-page?error=Invalid+state+parameter")

    redirect_uri = _get_redirect_uri(request)

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                error_detail = token_response.json().get("error_description", "Token exchange failed")
                return RedirectResponse(url=f"/auth/login-page?error={quote_plus(error_detail)}")

            tokens = token_response.json()
            access_token = tokens.get("access_token")

            # Fetch user info
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code != 200:
                return RedirectResponse(url="/auth/login-page?error=Failed+to+fetch+user+info")

            user_info = userinfo_response.json()

    except Exception as e:
        return RedirectResponse(url=f"/auth/login-page?error={quote_plus(str(e))}")

    # Check email allowlist
    email = user_info.get("email", "").lower()
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return RedirectResponse(
            url=f"/auth/login-page?error={quote_plus(f'Access denied for {email}. Contact admin.')}"
        )

    # Create session
    session_token = create_session(user_info)

    # Check if this login was initiated by an external service (cross-domain auth)
    next_service = request.cookies.get("auth_next_service")
    if next_service and _is_allowed_redirect(next_service):
        # Create a short-lived cross-domain token and redirect to the external service
        cross_token = create_cross_domain_token(user_info)
        separator = "&" if "?" in next_service else "?"
        redirect_url = f"{next_service}{separator}token={cross_token}"

        response = RedirectResponse(url=redirect_url)
        # Also set Orchestrator session cookie (for direct Orchestrator access)
        response.set_cookie(
            key=COOKIE_NAME,
            value=session_token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
        # Clean up temp cookies
        response.delete_cookie("oauth_state")
        response.delete_cookie("auth_next")
        response.delete_cookie("auth_next_service")
        print(f"✅ User logged in: {email} → redirecting to {next_service}")
        return response

    # Standard flow: redirect to Orchestrator page
    next_url = request.cookies.get("auth_next", "/")

    response = RedirectResponse(url=next_url)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    # Clean up temp cookies
    response.delete_cookie("oauth_state")
    response.delete_cookie("auth_next")
    response.delete_cookie("auth_next_service")

    print(f"✅ User logged in: {email}")
    return response


@router.get("/logout")
async def logout():
    """Clear session and redirect to login."""
    response = RedirectResponse(url="/auth/login-page")
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me")
async def me(request: Request):
    """Get current authenticated user info."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "authenticated": True,
    }


@router.get("/verify-token")
async def verify_token(token: str):
    """Verify a cross-domain auth token. Used by external services to validate tokens."""
    payload = _verify(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if payload.get("type") != "cross_domain":
        raise HTTPException(status_code=401, detail="Invalid token type")
    return {
        "valid": True,
        "email": payload.get("email"),
        "name": payload.get("name"),
        "picture": payload.get("picture"),
    }
