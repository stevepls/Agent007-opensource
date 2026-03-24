import { NextRequest, NextResponse } from "next/server";

/**
 * Auth Start Endpoint
 *
 * Redirects the user to the Orchestrator's /auth/login endpoint
 * which initiates the Google OAuth flow. This is called when the
 * user clicks "Sign in with Google" on the dashboard login page.
 *
 * Optionally receives geolocation query params (lat, lng, geo)
 * and forwards them so the Orchestrator can log login location.
 */
export async function GET(request: NextRequest) {
  const orchestratorUrl =
    process.env.ORCHESTRATOR_PUBLIC_URL ||
    process.env.ORCHESTRATOR_API_URL ||
    "http://localhost:8502";

  const scheme = request.headers.get("x-forwarded-proto") || "https";
  const host = request.headers.get("host") || "localhost:3000";
  const callbackUrl = `${scheme}://${host}/api/auth/callback`;

  const loginParams = new URLSearchParams({
    next_service: callbackUrl,
  });

  const lat = request.nextUrl.searchParams.get("lat");
  const lng = request.nextUrl.searchParams.get("lng");
  const geo = request.nextUrl.searchParams.get("geo");

  if (lat) loginParams.set("geo_lat", lat);
  if (lng) loginParams.set("geo_lng", lng);
  if (geo) loginParams.set("geo_name", geo);

  const loginUrl = `${orchestratorUrl}/auth/login?${loginParams.toString()}`;

  return NextResponse.redirect(loginUrl);
}
