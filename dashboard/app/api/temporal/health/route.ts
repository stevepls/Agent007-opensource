import { NextResponse } from "next/server";

const TEMPORAL_WORKER_URL =
  process.env.TEMPORAL_WORKER_API_URL || "http://localhost:9090";

/**
 * Proxy to the Temporal worker's /health endpoint.
 * Returns worker run state, poller status, and Temporal server connectivity.
 */
export async function GET() {
  try {
    const res = await fetch(`${TEMPORAL_WORKER_URL}/health`, {
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Worker returned ${res.status}` },
        { status: res.status }
      );
    }

    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json(
      {
        status: "unreachable",
        temporal_server_reachable: false,
        worker: null,
        error: "Temporal worker API is not reachable",
      },
      { status: 503 }
    );
  }
}
