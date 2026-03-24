import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || process.env.SESSION_SECRET_KEY || "";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const project = searchParams.get("project");
    const limit = searchParams.get("limit") || "50";

    const url = new URL(`${ORCHESTRATOR_URL}/api/queue`);
    if (project) url.searchParams.set("project", project);
    url.searchParams.set("limit", limit);

    const res = await fetch(url.toString(), {
      headers: { "Content-Type": "application/json", "X-Service-Key": SERVICE_API_KEY },
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch queue", status: res.status },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Queue service unavailable", items: [], summary: {} },
      { status: 503 }
    );
  }
}
