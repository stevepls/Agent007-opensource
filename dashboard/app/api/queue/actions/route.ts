import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";

export async function GET(req: NextRequest) {
  try {
    const limit = req.nextUrl.searchParams.get("limit") || "10";
    const res = await fetch(
      `${ORCHESTRATOR_URL}/api/queue/actions?limit=${limit}`,
      { cache: "no-store" }
    );
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ items: {}, count: 0 }, { status: 503 });
  }
}
