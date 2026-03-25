import { NextRequest, NextResponse } from "next/server";
import { render } from "@react-email/components";
import StatusUpdate from "@/emails/StatusUpdate";
import TicketResolved from "@/emails/TicketResolved";
import Welcome from "@/emails/Welcome";
import { createElement } from "react";

// Template registry
const TEMPLATES: Record<string, React.FC<any>> = {
  "status-update": StatusUpdate,
  "ticket-resolved": TicketResolved,
  "welcome": Welcome,
};

export async function POST(req: NextRequest) {
  try {
    const { template, props } = await req.json();

    if (!template || !TEMPLATES[template]) {
      return NextResponse.json(
        { error: `Unknown template: ${template}. Available: ${Object.keys(TEMPLATES).join(", ")}` },
        { status: 400 }
      );
    }

    const Component = TEMPLATES[template];
    const html = await render(createElement(Component, props || {}));

    return NextResponse.json({
      html,
      template,
      subject: props?.subject || null,
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: `Failed to render template: ${error.message}` },
      { status: 500 }
    );
  }
}

// GET: list available templates
export async function GET() {
  return NextResponse.json({
    templates: Object.keys(TEMPLATES),
  });
}
