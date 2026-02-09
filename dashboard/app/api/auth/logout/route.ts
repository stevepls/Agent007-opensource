import { NextRequest, NextResponse } from "next/server";

/**
 * Dashboard Logout
 *
 * Clears the dashboard session cookie and redirects to the
 * Orchestrator's logout endpoint (which clears its cookie too).
 */

const COOKIE_NAME = "dashboard_session";

export async function GET(request: NextRequest) {
  const orchestratorUrl =
    process.env.ORCHESTRATOR_PUBLIC_URL ||
    process.env.ORCHESTRATOR_API_URL ||
    "http://localhost:8502";

  // Redirect to Orchestrator logout (which clears its cookie and shows login page)
  const response = NextResponse.redirect(`${orchestratorUrl}/auth/logout`);
  response.cookies.delete(COOKIE_NAME);
  return response;
}

export async function POST(request: NextRequest) {
  // Also support POST for programmatic logout
  return GET(request);
}
