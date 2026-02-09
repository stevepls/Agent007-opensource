import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || process.env.SESSION_SECRET_KEY || "";

export async function GET(req: NextRequest) {
  const status = req.nextUrl.searchParams.get("status") || "";

  try {
    const url = new URL(`${ORCHESTRATOR_URL}/api/tasks`);
    if (status) url.searchParams.set("status", status);

    const res = await fetch(url.toString(), {
      headers: {
        "X-Service-Key": SERVICE_API_KEY,
      },
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Orchestrator returned ${res.status}` },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json(
      { error: "Failed to reach orchestrator", tasks: [], status: {} },
      { status: 502 }
    );
  }
}
