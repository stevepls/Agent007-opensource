import { NextRequest, NextResponse } from "next/server";

/**
 * Dashboard Auth Callback
 *
 * Receives a signed token from the Orchestrator after Google OAuth,
 * validates it, and sets a dashboard_session cookie.
 *
 * Flow: Orchestrator redirects here with ?token=<signed_token>
 */

const COOKIE_NAME = "dashboard_session";
const SESSION_MAX_AGE = 60 * 60 * 24 * 7; // 7 days in seconds

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token");

  if (!token) {
    return new NextResponse("Missing token parameter", { status: 400 });
  }

  // Validate token with the Orchestrator
  const orchestratorUrl =
    process.env.ORCHESTRATOR_INTERNAL_URL ||
    process.env.ORCHESTRATOR_API_URL ||
    "http://localhost:8502";

  try {
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
      // Redirect to orchestrator login
      const loginUrl = getLoginUrl(request);
      return NextResponse.redirect(loginUrl);
    }

    const userData = await verifyResponse.json();

    if (!userData.valid) {
      const loginUrl = getLoginUrl(request);
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
    const dashboardUrl = new URL("/", request.url);
    const response = NextResponse.redirect(dashboardUrl);
    response.cookies.set(COOKIE_NAME, sessionData, {
      httpOnly: true,
      secure: request.nextUrl.protocol === "https:",
      sameSite: "lax",
      path: "/",
      maxAge: SESSION_MAX_AGE,
    });

    console.log(`✅ Dashboard session created for ${userData.email}`);
    return response;
  } catch (error) {
    console.error("Auth callback error:", error);
    const loginUrl = getLoginUrl(request);
    return NextResponse.redirect(loginUrl);
  }
}

function getLoginUrl(request: NextRequest): string {
  const orchestratorUrl =
    process.env.ORCHESTRATOR_PUBLIC_URL ||
    process.env.ORCHESTRATOR_API_URL ||
    "http://localhost:8502";

  const scheme = request.headers.get("x-forwarded-proto") || "https";
  const host = request.headers.get("host") || "localhost:3000";
  const callbackUrl = `${scheme}://${host}/api/auth/callback`;

  return `${orchestratorUrl}/auth/login?next_service=${encodeURIComponent(callbackUrl)}`;
}
