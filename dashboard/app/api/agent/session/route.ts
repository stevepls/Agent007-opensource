import { NextRequest, NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";

export async function POST(request: NextRequest) {
  try {
    const { sessionId, action } = await request.json();
    
    if (!sessionId) {
      return NextResponse.json({ error: "Missing sessionId" }, { status: 400 });
    }

    // Try to notify orchestrator about session
    try {
      await fetch(`${ORCHESTRATOR_URL}/api/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, action }),
        signal: AbortSignal.timeout(2000),
      });
    } catch {
      // Orchestrator might not be available, that's ok
      console.log("[Session] Orchestrator not available for session sync");
    }

    return NextResponse.json({ 
      success: true, 
      sessionId,
      action,
      timestamp: Date.now() 
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: "Failed to process session", details: error.message },
      { status: 500 }
    );
  }
}
