import { NextRequest, NextResponse } from "next/server";

/**
 * Auth Start Endpoint
 *
 * Redirects the user to the Orchestrator's /auth/login endpoint
 * which initiates the Google OAuth flow. This is called when the
 * user clicks "Sign in with Google" on the dashboard login page.
 */
export async function GET(request: NextRequest) {
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
