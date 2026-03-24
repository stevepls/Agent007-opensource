import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || process.env.SESSION_SECRET_KEY || "";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const maxItems = searchParams.get("max_items") || "15";

    const res = await fetch(
      `${ORCHESTRATOR_URL}/api/briefing?max_items=${maxItems}`,
      { headers: { "Content-Type": "application/json", "X-Service-Key": SERVICE_API_KEY }, cache: "no-store" }
    );

    if (!res.ok) {
      return NextResponse.json(
        { error: "Failed to fetch briefing", status: res.status },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Briefing service unavailable", greeting: "", items: [], summary: {} },
      { status: 503 }
    );
  }
}
