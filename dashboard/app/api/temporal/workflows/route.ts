import { NextRequest, NextResponse } from "next/server";

const TEMPORAL_WORKER_URL =
  process.env.TEMPORAL_WORKER_API_URL || "http://localhost:9090";

/**
 * Proxy to the Temporal worker's /workflows endpoint.
 *
 * GET /api/temporal/workflows?status=Running&limit=20&type=recurringPaymentCycle
 *
 * Supports query params: status, type, limit, query (raw visibility query).
 */
export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;

  try {
    const url = new URL(`${TEMPORAL_WORKER_URL}/workflows`);
    for (const [key, value] of params.entries()) {
      url.searchParams.set(key, value);
    }

    const res = await fetch(url.toString(), { cache: "no-store" });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Worker returned ${res.status}` },
        { status: res.status }
      );
    }

    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json(
      { error: "Temporal worker API is not reachable", workflows: [] },
      { status: 503 }
    );
  }
}
