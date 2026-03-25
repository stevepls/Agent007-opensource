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

interface ReportSection {
  label: string;
  count: number;
  severity: "critical" | "warning" | "info" | "ok";
  error?: string;
}

interface RecurringChargeReportProps {
  reportDate: string;
  health: "healthy" | "degraded" | "critical";
  totals: { issues: number; warnings: number; ok: number };
  sections: Record<string, ReportSection>;
  generatedAt?: string;
  elapsedMs?: number;
}

const severityColor: Record<string, string> = {
  critical: "#dc3545",
  warning: "#f59e0b",
  info: "#3b82f6",
  ok: "#10b981",
};

const healthColor: Record<string, string> = {
  healthy: "#10b981",
  degraded: "#f59e0b",
  critical: "#dc3545",
};

export default function RecurringChargeReport({
  reportDate = new Date().toISOString().split("T")[0],
  health = "healthy",
  totals = { issues: 0, warnings: 0, ok: 0 },
  sections = {},
  generatedAt = "",
  elapsedMs = 0,
}: RecurringChargeReportProps) {
  const sectionEntries = Object.entries(sections);

  return (
    <Html>
      <Head />
      <Preview>
        Recurring Charge Report — {reportDate} — {health.toUpperCase()}
      </Preview>
      <Body style={main}>
        <Container style={container}>
          <Heading style={heading}>
            Recurring Charge Report
          </Heading>
          <Text style={dateText}>{reportDate}</Text>

          <Section
            style={{
              ...healthBadge,
              backgroundColor: healthColor[health] || "#6b7280",
            }}
          >
            <Text style={healthText}>{health.toUpperCase()}</Text>
          </Section>

          <Section style={summaryRow}>
            <Text style={summaryItem}>
              <span style={{ color: "#dc3545", fontWeight: 700 }}>
                {totals.issues}
              </span>{" "}
              Issues
            </Text>
            <Text style={summaryItem}>
              <span style={{ color: "#f59e0b", fontWeight: 700 }}>
                {totals.warnings}
              </span>{" "}
              Warnings
            </Text>
            <Text style={summaryItem}>
              <span style={{ color: "#10b981", fontWeight: 700 }}>
                {totals.ok}
              </span>{" "}
              OK
            </Text>
          </Section>

          <Hr style={hr} />

          {sectionEntries.map(([key, section]) => (
            <Section key={key} style={sectionRow}>
              <div style={sectionLeft}>
                <span
                  style={{
                    ...dot,
                    backgroundColor:
                      severityColor[section.severity] || "#6b7280",
                  }}
                />
                <Text style={sectionLabel}>{section.label}</Text>
              </div>
              <Text style={sectionCount}>{section.count}</Text>
            </Section>
          ))}

          <Hr style={hr} />
          <Text style={footer}>
            Generated at {generatedAt} ({elapsedMs}ms) — Collegewise Recurring
            Charge Module
          </Text>
        </Container>
      </Body>
    </Html>
  );
}

const main = {
  backgroundColor: "#f8fafc",
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
};

const container = {
  margin: "0 auto",
  padding: "40px 24px",
  maxWidth: "600px",
  backgroundColor: "#ffffff",
  borderRadius: "8px",
};

const heading = {
  fontSize: "22px",
  fontWeight: "700" as const,
  color: "#0f172a",
  marginBottom: "4px",
};

const dateText = {
  fontSize: "14px",
  color: "#64748b",
  marginTop: "0",
  marginBottom: "20px",
};

const healthBadge = {
  textAlign: "center" as const,
  borderRadius: "6px",
  padding: "8px 16px",
  marginBottom: "16px",
};

const healthText = {
  color: "#ffffff",
  fontSize: "14px",
  fontWeight: "700" as const,
  letterSpacing: "0.05em",
  margin: "0",
};

const summaryRow = {
  display: "flex" as const,
  justifyContent: "space-around" as const,
  marginBottom: "8px",
};

const summaryItem = {
  fontSize: "14px",
  color: "#475569",
  textAlign: "center" as const,
};

const hr = {
  borderColor: "#e2e8f0",
  marginTop: "16px",
  marginBottom: "16px",
};

const sectionRow = {
  display: "flex" as const,
  justifyContent: "space-between" as const,
  alignItems: "center" as const,
  padding: "8px 0",
  borderBottom: "1px solid #f1f5f9",
};

const sectionLeft = {
  display: "flex" as const,
  alignItems: "center" as const,
  gap: "8px",
};

const dot = {
  width: "10px",
  height: "10px",
  borderRadius: "50%",
  display: "inline-block",
};

const sectionLabel = {
  fontSize: "14px",
  color: "#334155",
  margin: "0",
};

const sectionCount = {
  fontSize: "16px",
  fontWeight: "700" as const,
  color: "#0f172a",
  margin: "0",
};

const footer = {
  fontSize: "11px",
  color: "#94a3b8",
  textAlign: "center" as const,
};
