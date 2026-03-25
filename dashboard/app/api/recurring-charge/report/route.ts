import { NextRequest, NextResponse } from "next/server";

const MAGENTO_API_URL =
  process.env.CW_MAGENTO_API_URL || "https://collegewise.com";
const MAGENTO_API_TOKEN = process.env.CW_MAGENTO_API_TOKEN || "";

/**
 * Proxy to the Magento ReportGenerator API.
 *
 * GET  /api/recurring-charge/report              → pre-run report JSON
 * GET  /api/recurring-charge/report?type=post    → post-run report JSON
 * POST /api/recurring-charge/report?channel=     → deliver to slack | email
 */
export async function GET(req: NextRequest) {
  const chargeDate =
    req.nextUrl.searchParams.get("date") ||
    new Date().toISOString().split("T")[0];
  const reportType = req.nextUrl.searchParams.get("type") || "pre";
  const magentoPath =
    reportType === "post" ? "report/post" : "report";

  try {
    const url = new URL(
      `${MAGENTO_API_URL}/rest/V1/recurring-charge/${magentoPath}`
    );
    url.searchParams.set("chargeDate", chargeDate);

    const res = await fetch(url.toString(), {
      headers: {
        Authorization: `Bearer ${MAGENTO_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Magento returned ${res.status}` },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: "Recurring charge report unavailable", sections: {} },
      { status: 503 }
    );
  }
}

export async function POST(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel") || "slack";
  const body = await req.json().catch(() => ({}));

  const endpoint =
    channel === "email"
      ? "report/email"
      : "report/slack";

  try {
    const res = await fetch(
      `${MAGENTO_API_URL}/rest/V1/recurring-charge/${endpoint}`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${MAGENTO_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }
    );

    const data = await res.json();
    return NextResponse.json(data, { status: res.ok ? 200 : 502 });
  } catch (error) {
    return NextResponse.json(
      { error: `Failed to send report via ${channel}` },
      { status: 503 }
    );
  }
}
