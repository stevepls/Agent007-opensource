import { NextRequest, NextResponse } from "next/server";

const TEMPORAL_WORKER_URL =
  process.env.TEMPORAL_WORKER_API_URL || "http://localhost:9090";

/**
 * Proxy to the Temporal worker's /metrics endpoint.
 * Returns workflow execution counts by status (running, completed, failed, timed_out).
 */
export async function GET(req: NextRequest) {
  const taskQueue = req.nextUrl.searchParams.get("taskQueue") || "";

  try {
    const url = new URL(`${TEMPORAL_WORKER_URL}/metrics`);
    if (taskQueue) url.searchParams.set("taskQueue", taskQueue);

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
      { error: "Temporal worker API is not reachable", counts: {} },
      { status: 503 }
    );
  }
}
