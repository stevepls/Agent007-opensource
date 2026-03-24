import { NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || process.env.SESSION_SECRET_KEY || "";

export async function GET() {
  try {
    const res = await fetch(`${ORCHESTRATOR_URL}/health`, {
      headers: { "X-Service-Key": SERVICE_API_KEY },
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json({ agents: [] }, { status: res.status });
    }

    const data = await res.json();
    const proactive = data.proactive || { running: false, jobs: [] };

    return NextResponse.json({
      scheduler_running: proactive.running,
      agents: proactive.jobs || [],
    });
  } catch {
    return NextResponse.json({ scheduler_running: false, agents: [] }, { status: 503 });
  }
}
