import { NextRequest, NextResponse } from "next/server";

/**
 * Dashboard Auth Middleware
 *
 * Checks for a valid `dashboard_session` cookie on every request.
 * If missing/invalid, redirects to the Orchestrator's Google OAuth login
 * with a `next_service` param so it bounces back after auth.
 *
 * Auth flow:
 *   1. User hits dashboard → middleware sees no cookie → redirect to Orchestrator /auth/login
 *   2. Orchestrator handles Google OAuth → redirects back to /api/auth/callback?token=...
 *   3. Dashboard /api/auth/callback validates token → sets dashboard_session cookie
 *   4. Subsequent requests pass middleware check
 */

const COOKIE_NAME = "dashboard_session";

// Paths that skip auth
const PUBLIC_PATHS = [
  "/api/auth/callback",
  "/api/auth/logout",
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

  // No valid session → redirect to Orchestrator login
  const orchestratorUrl =
    process.env.ORCHESTRATOR_PUBLIC_URL ||
    process.env.ORCHESTRATOR_API_URL ||
    "http://localhost:8502";

  // Build the callback URL that the Orchestrator should redirect to after login
  const scheme = request.headers.get("x-forwarded-proto") || "https";
  const host = request.headers.get("host") || "localhost:3000";
  const callbackUrl = `${scheme}://${host}/api/auth/callback`;

  const loginUrl = `${orchestratorUrl}/auth/login?next_service=${encodeURIComponent(callbackUrl)}`;

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
