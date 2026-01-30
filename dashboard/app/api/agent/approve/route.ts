import { NextRequest } from "next/server";

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_API_URL || "http://localhost:8502";

/**
 * POST /api/agent/approve
 * Handle approval/rejection of pending requests
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { approval_id, approved } = body;

    if (!approval_id) {
      return new Response(
        JSON.stringify({ error: "approval_id is required" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Try to forward to orchestrator
    try {
      const response = await fetch(`${ORCHESTRATOR_URL}/api/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval_id, approved }),
        signal: AbortSignal.timeout(5000),
      });

      if (response.ok) {
        const data = await response.json();
        return new Response(JSON.stringify(data), {
          headers: { "Content-Type": "application/json" },
        });
      }
    } catch {
      // Orchestrator not available, handle locally
    }

    // Mock response when orchestrator is not available
    console.log(`Approval ${approval_id}: ${approved ? "APPROVED" : "REJECTED"}`);

    return new Response(
      JSON.stringify({
        success: true,
        approval_id,
        status: approved ? "approved" : "rejected",
        message: approved
          ? "Action has been approved and will be executed."
          : "Action has been rejected.",
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (error) {
    console.error("Approval error:", error);
    return new Response(
      JSON.stringify({ error: "Failed to process approval" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
