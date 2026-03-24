import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || process.env.SESSION_SECRET_KEY || "";

export async function POST(req: NextRequest) {
  try {
    const { item_id } = await req.json();
    const res = await fetch(
      `${ORCHESTRATOR_URL}/api/briefing/dismiss/${item_id}`,
      { method: "POST", headers: { "Content-Type": "application/json", "X-Service-Key": SERVICE_API_KEY } }
    );
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json({ error: "Failed to dismiss" }, { status: 500 });
  }
}
