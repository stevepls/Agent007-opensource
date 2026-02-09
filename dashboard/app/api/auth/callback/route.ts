import { NextRequest, NextResponse } from "next/server";

/**
 * Dashboard Auth Callback
 *
 * Receives a signed token from the Orchestrator after Google OAuth,
 * validates it, and sets a dashboard_session cookie.
 *
 * Flow: Orchestrator redirects here with ?token=<signed_token>
 *
 * On error: redirects to the dashboard's own /login page (NOT back to
 * the Orchestrator) to prevent infinite redirect loops.
 */

const COOKIE_NAME = "dashboard_session";
const SESSION_MAX_AGE = 60 * 60 * 24 * 7; // 7 days in seconds

/**
 * Build the public-facing base URL for this service.
 *
 * Behind Railway's reverse proxy, request.url is an internal address
 * like http://localhost:8080.  We must use forwarded headers (or an
 * explicit env var) to produce the real public URL.
 */
function getPublicBaseUrl(request: NextRequest): string {
  // Prefer explicit env var (most reliable)
  if (process.env.DASHBOARD_PUBLIC_URL) {
    return process.env.DASHBOARD_PUBLIC_URL;
  }
  // Fall back to proxy headers
  const scheme = request.headers.get("x-forwarded-proto") || "https";
  const host = request.headers.get("host") || "localhost:3000";
  return `${scheme}://${host}`;
}

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token");
  const publicBase = getPublicBaseUrl(request);

  if (!token) {
    // No token → send user to dashboard login with error
    const loginUrl = new URL("/login", publicBase);
    loginUrl.searchParams.set("error", "Missing authentication token");
    return NextResponse.redirect(loginUrl);
  }

  // Validate token with the Orchestrator (server-to-server call)
  const orchestratorUrl =
    process.env.ORCHESTRATOR_API_URL ||
    "http://localhost:8502";

  try {
    console.log(`🔑 Verifying token with orchestrator at: ${orchestratorUrl}/auth/verify-token`);
    const verifyResponse = await fetch(
      `${orchestratorUrl}/auth/verify-token?token=${encodeURIComponent(token)}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        // Use short timeout to avoid hanging
        signal: AbortSignal.timeout(10000),
      }
    );

    if (!verifyResponse.ok) {
      const errorText = await verifyResponse.text();
      console.error("Token verification failed:", verifyResponse.status, errorText);
      // Redirect to dashboard's own login page — NOT the orchestrator (avoids redirect loop)
      const loginUrl = new URL("/login", publicBase);
      loginUrl.searchParams.set("error", "Authentication failed. Please try again.");
      return NextResponse.redirect(loginUrl);
    }

    const userData = await verifyResponse.json();

    if (!userData.valid) {
      const loginUrl = new URL("/login", publicBase);
      loginUrl.searchParams.set("error", "Invalid authentication token. Please try again.");
      return NextResponse.redirect(loginUrl);
    }

    // Create dashboard session cookie (store user info + expiry)
    const sessionData = JSON.stringify({
      email: userData.email,
      name: userData.name,
      picture: userData.picture,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE,
    });

    // Redirect to dashboard home with session cookie
    const dashboardUrl = new URL("/", publicBase);
    const response = NextResponse.redirect(dashboardUrl);

    // Detect actual scheme for cookie security
    const actualScheme = request.headers.get("x-forwarded-proto") || request.nextUrl.protocol.replace(":", "");
    response.cookies.set(COOKIE_NAME, sessionData, {
      httpOnly: true,
      secure: actualScheme === "https",
      sameSite: "lax",
      path: "/",
      maxAge: SESSION_MAX_AGE,
    });

    console.log(`✅ Dashboard session created for ${userData.email}`);
    return response;
  } catch (error) {
    console.error("Auth callback error:", error);
    // Redirect to dashboard's own login page — NOT the orchestrator (avoids redirect loop)
    const loginUrl = new URL("/login", publicBase);
    loginUrl.searchParams.set("error", "Authentication service unavailable. Please try again.");
    return NextResponse.redirect(loginUrl);
  }
}
