import { NextRequest, NextResponse } from "next/server";

/**
 * Dashboard Auth Middleware
 *
 * Checks for a valid `dashboard_session` cookie on every request.
 * If missing/invalid, redirects to the dashboard's own /login page.
 *
 * Auth flow:
 *   1. User hits dashboard → middleware sees no cookie → redirect to /login page
 *   2. User clicks "Sign in with Google" → /api/auth/start → Orchestrator /auth/login
 *   3. Orchestrator handles Google OAuth → redirects back to /api/auth/callback?token=...
 *   4. Dashboard /api/auth/callback validates token → sets dashboard_session cookie
 *   5. Subsequent requests pass middleware check
 */

const COOKIE_NAME = "dashboard_session";

// Set BYPASS_AUTH=true in .env.local to skip Google OAuth for local dev
const BYPASS_AUTH = process.env.BYPASS_AUTH === "true";

// Paths that skip auth
const PUBLIC_PATHS = [
  "/login",
  "/api/auth/callback",
  "/api/auth/start",
  "/api/auth/logout",
  "/api/health",
  "/_next",
  "/favicon.ico",
];

function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname.startsWith(p));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip auth for public paths and static assets
  if (isPublicPath(pathname)) {
    return NextResponse.next();
  }

  // Local dev: bypass auth entirely when BYPASS_AUTH=true
  if (BYPASS_AUTH) {
    // Inject a fake session cookie if one doesn't exist so downstream
    // code that reads the cookie still works
    const existing = request.cookies.get(COOKIE_NAME);
    if (!existing?.value) {
      const response = NextResponse.next();
      const devSession = JSON.stringify({
        email: "dev@localhost",
        name: "Local Dev",
        picture: "",
        iat: Math.floor(Date.now() / 1000),
        exp: Math.floor(Date.now() / 1000) + 86400 * 30, // 30 days
      });
      response.cookies.set(COOKIE_NAME, devSession, {
        path: "/",
        maxAge: 86400 * 30,
      });
      return response;
    }
    return NextResponse.next();
  }

  // Check for session cookie
  const sessionCookie = request.cookies.get(COOKIE_NAME);
  if (sessionCookie?.value) {
    // Validate the cookie: it's a JSON payload with an expiry
    try {
      const payload = JSON.parse(sessionCookie.value);
      if (payload.exp && payload.exp > Date.now() / 1000) {
        // Valid session — allow through
        return NextResponse.next();
      }
    } catch {
      // Invalid cookie format — fall through to redirect
    }
  }

  // No valid session → redirect to dashboard login page
  const loginUrl = new URL("/login", request.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  // Run middleware on all routes except static files
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
