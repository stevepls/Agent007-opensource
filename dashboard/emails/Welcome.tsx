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

interface WelcomeProps {
  clientName: string;
  projectName: string;
  senderName?: string;
}

export default function Welcome({
  clientName = "Client",
  projectName = "Project",
  senderName = "Steve",
}: WelcomeProps) {
  return (
    <Html>
      <Head />
      <Preview>Welcome to People Like Software — {projectName}</Preview>
      <Body style={main}>
        <Container style={container}>
          <Heading style={heading}>
            Welcome aboard
          </Heading>
          <Text style={greeting}>Hi {clientName},</Text>
          <Text style={paragraph}>
            We're excited to get started on <strong>{projectName}</strong>.
          </Text>
          <Text style={paragraph}>Here's what to expect:</Text>
          <Section style={listSection}>
            <Text style={listItem}>
              <strong>1.</strong> We'll set up your project workspace in ClickUp — you'll get an invite shortly
            </Text>
            <Text style={listItem}>
              <strong>2.</strong> You can reach us anytime via email or your dedicated Slack channel
            </Text>
            <Text style={listItem}>
              <strong>3.</strong> We'll send regular status updates as work progresses
            </Text>
            <Text style={listItem}>
              <strong>4.</strong> For support issues, email support@peoplelikesoftware.com
            </Text>
          </Section>
          <Text style={paragraph}>
            Your primary contact is <strong>{senderName}</strong> ({senderName.toLowerCase()}@peoplelikesoftware.com).
          </Text>
          <Text style={paragraph}>
            Looking forward to working together.
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

const heading = {
  fontSize: "24px",
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

const listSection = {
  backgroundColor: "#f9fafb",
  borderRadius: "8px",
  padding: "16px 20px",
  marginBottom: "20px",
};

const listItem = {
  fontSize: "14px",
  lineHeight: "1.8",
  color: "#374151",
  marginBottom: "4px",
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
