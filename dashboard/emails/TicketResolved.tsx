import {
  Body,
  Container,
  Head,
  Heading,
  Hr,
  Html,
  Preview,
  Section,
  Text,
} from "@react-email/components";

interface TicketResolvedProps {
  clientName: string;
  ticketSubject: string;
  resolutionSummary: string;
  ticketId?: string;
  senderName?: string;
}

export default function TicketResolved({
  clientName = "Client",
  ticketSubject = "Support Ticket",
  resolutionSummary = "",
  ticketId = "",
  senderName = "Steve",
}: TicketResolvedProps) {
  return (
    <Html>
      <Head />
      <Preview>Resolved: {ticketSubject}</Preview>
      <Body style={main}>
        <Container style={container}>
          <Section style={resolvedBadge}>
            <Text style={resolvedText}>✓ Resolved</Text>
          </Section>
          <Heading style={heading}>{ticketSubject}</Heading>
          {ticketId && <Text style={ticketIdText}>#{ticketId}</Text>}
          <Text style={greeting}>Hi {clientName},</Text>
          <Text style={paragraph}>
            Your ticket has been resolved. Here's what was done:
          </Text>
          <Section style={summarySection}>
            <Text style={summaryText}>{resolutionSummary}</Text>
          </Section>
          <Text style={paragraph}>
            If you have any further issues or questions, don't hesitate to reach out.
          </Text>
          <Text style={signoff}>
            Best,<br />{senderName}
          </Text>
          <Hr style={hr} />
          <Text style={footer}>People Like Software</Text>
        </Container>
      </Body>
    </Html>
  );
}

const main = {
  backgroundColor: "#ffffff",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
};

const container = {
  margin: "0 auto",
  padding: "40px 24px",
  maxWidth: "560px",
};

const resolvedBadge = {
  backgroundColor: "#ecfdf5",
  borderRadius: "6px",
  padding: "8px 16px",
  marginBottom: "20px",
  display: "inline-block" as const,
};

const resolvedText = {
  fontSize: "13px",
  fontWeight: "600" as const,
  color: "#059669",
  margin: "0",
};

const heading = {
  fontSize: "20px",
  fontWeight: "600" as const,
  color: "#111111",
  marginBottom: "4px",
};

const ticketIdText = {
  fontSize: "13px",
  color: "#9ca3af",
  marginBottom: "20px",
};

const greeting = {
  fontSize: "15px",
  lineHeight: "1.6",
  color: "#333333",
  marginBottom: "8px",
};

const paragraph = {
  fontSize: "15px",
  lineHeight: "1.6",
  color: "#333333",
  marginBottom: "16px",
};

const summarySection = {
  backgroundColor: "#f9fafb",
  borderLeft: "3px solid #059669",
  borderRadius: "0 8px 8px 0",
  padding: "16px",
  marginBottom: "20px",
};

const summaryText = {
  fontSize: "14px",
  lineHeight: "1.6",
  color: "#374151",
  margin: "0",
};

const signoff = {
  fontSize: "15px",
  lineHeight: "1.6",
  color: "#333333",
  marginTop: "24px",
};

const hr = {
  borderColor: "#e5e7eb",
  marginTop: "32px",
  marginBottom: "16px",
};

const footer = {
  fontSize: "12px",
  color: "#9ca3af",
};
