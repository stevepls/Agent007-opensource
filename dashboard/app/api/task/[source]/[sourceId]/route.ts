import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || process.env.SESSION_SECRET_KEY || "";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ source: string; sourceId: string }> }
) {
  const { source, sourceId } = await params;
  try {
    const res = await fetch(
      `${ORCHESTRATOR_URL}/api/task/${source}/${sourceId}`,
      {
        headers: { "X-Service-Key": SERVICE_API_KEY },
        cache: "no-store",
      }
    );
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Failed to fetch task detail", detail: null }, { status: 503 });
  }
}
