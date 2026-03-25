import { NextRequest, NextResponse } from "next/server";

const TEMPORAL_WORKER_URL =
  process.env.TEMPORAL_WORKER_API_URL || "http://localhost:9090";

/**
 * Proxy to the Temporal worker for individual workflow details.
 *
 * GET /api/temporal/workflows/:workflowId               → describe
 * GET /api/temporal/workflows/:workflowId?history=true   → full event history
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ workflowId: string }> }
) {
  const { workflowId } = await params;
  const includeHistory = req.nextUrl.searchParams.get("history") === "true";

  const path = includeHistory
    ? `/workflows/${encodeURIComponent(workflowId)}/history`
    : `/workflows/${encodeURIComponent(workflowId)}`;

  try {
    const res = await fetch(`${TEMPORAL_WORKER_URL}${path}`, {
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
      { error: "Temporal worker API is not reachable" },
      { status: 503 }
    );
  }
}
