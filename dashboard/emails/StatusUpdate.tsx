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

interface StatusUpdateProps {
  clientName: string;
  projectName: string;
  statusItems: { label: string; value: string }[];
  message: string;
  senderName?: string;
}

export default function StatusUpdate({
  clientName = "Client",
  projectName = "Project",
  statusItems = [],
  message = "",
  senderName = "Steve",
}: StatusUpdateProps) {
  return (
    <Html>
      <Head />
      <Preview>{projectName} — Status Update</Preview>
      <Body style={main}>
        <Container style={container}>
          <Heading style={heading}>
            {projectName}
          </Heading>
          <Text style={greeting}>Hi {clientName},</Text>
          <Text style={paragraph}>{message}</Text>

          {statusItems.length > 0 && (
            <Section style={statusSection}>
              {statusItems.map((item, i) => (
                <div key={i} style={statusRow}>
                  <span style={statusLabel}>{item.label}</span>
                  <span style={statusValue}>{item.value}</span>
                </div>
              ))}
            </Section>
          )}

          <Text style={paragraph}>
            Let me know if you have any questions.
          </Text>
          <Text style={signoff}>
            Best,<br />{senderName}
          </Text>
          <Hr style={hr} />
          <Text style={footer}>
            People Like Software
          </Text>
        </Container>
      </Body>
    </Html>
  );
}

// Styles — clean, minimal, professional
const main = {
  backgroundColor: "#ffffff",
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
};

const container = {
  margin: "0 auto",
  padding: "40px 24px",
  maxWidth: "560px",
};

const heading = {
  fontSize: "20px",
  fontWeight: "600" as const,
  color: "#111111",
  marginBottom: "24px",
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

const statusSection = {
  backgroundColor: "#f9fafb",
  borderRadius: "8px",
  padding: "16px",
  marginBottom: "20px",
};

const statusRow = {
  display: "flex" as const,
  justifyContent: "space-between" as const,
  padding: "6px 0",
  fontSize: "14px",
  borderBottom: "1px solid #e5e7eb",
};

const statusLabel = {
  color: "#6b7280",
  fontWeight: "500" as const,
};

const statusValue = {
  color: "#111827",
  fontWeight: "600" as const,
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
