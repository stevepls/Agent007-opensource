import { NextRequest, NextResponse } from "next/server";

/**
 * Geolocation endpoint — accepts raw browser coordinates and returns them.
 * Reverse geocoding (Google Maps) can be wired in later; for now we just
 * echo the lat/lng so the client has a consistent fetch path.
 */
export async function GET(request: NextRequest) {
  const lat = request.nextUrl.searchParams.get("lat");
  const lng = request.nextUrl.searchParams.get("lng");

  if (!lat || !lng) {
    return NextResponse.json({ error: "Missing lat/lng parameters" }, { status: 400 });
  }

  const latitude = parseFloat(lat);
  const longitude = parseFloat(lng);
  if (isNaN(latitude) || isNaN(longitude)) {
    return NextResponse.json({ error: "Invalid lat/lng values" }, { status: 400 });
  }

  return NextResponse.json({
    latitude,
    longitude,
    displayName: `${latitude.toFixed(4)}°, ${longitude.toFixed(4)}°`,
  });
}
