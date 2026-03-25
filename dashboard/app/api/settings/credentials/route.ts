import { NextRequest, NextResponse } from "next/server";
import { readFileSync, writeFileSync, existsSync } from "fs";
import { resolve } from "path";

// Path to the Orchestrator .env file
const ENV_PATH = resolve(process.cwd(), "..", "Orchestrator", ".env");

// Credential categories
const CATEGORIES: Record<string, { label: string; keys: string[] }> = {
  ai: {
    label: "AI / LLM",
    keys: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEFAULT_MODEL", "ORCHESTRATOR_LLM"],
  },
  ticketing: {
    label: "Ticketing & Project Management",
    keys: ["CLICKUP_API_TOKEN", "CLICKUP_DEFAULT_LIST_ID", "CLICKUP_MLN_LIST_ID", "ZENDESK_SUBDOMAIN", "ZENDESK_EMAIL", "ZENDESK_API_TOKEN", "ASANA_PERSONAL_ACCESS_TOKEN", "AIRTABLE_BASE_ID", "AIRTABLE_TABLE_ID", "AIRTABLE_PERSONAL_ACCESS_TOKEN"],
  },
  communication: {
    label: "Communication",
    keys: ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET", "SLACK_USER_TOKEN"],
  },
  email: {
    label: "Email & Google",
    keys: ["GOOGLE_CREDENTIALS_JSON", "GOOGLE_TOKEN_JSON"],
  },
  time_tracking: {
    label: "Time Tracking",
    keys: ["HARVEST_ACCESS_TOKEN", "HARVEST_ACCOUNT_ID", "HUBSTAFF_CLIENT_ID", "HUBSTAFF_CLIENT_SECRET", "HUBSTAFF_REFRESH_TOKEN", "HUBSTAFF_USER_ID", "HUBSTAFF_ORG_ID"],
  },
  devops: {
    label: "DevOps & Code",
    keys: ["GITHUB_TOKEN", "DEVOPS_ROOT", "COMPOSER_AUTH"],
  },
  auth: {
    label: "Authentication & Security",
    keys: ["SERVICE_API_KEY", "SESSION_SECRET_KEY", "ALLOWED_EMAILS", "REQUIRE_APPROVAL", "WEBHOOK_SECRET"],
  },
  accounting: {
    label: "Accounting",
    keys: ["UPWORK_SYNC_URL"],
  },
};

function parseEnvFile(content: string): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    let value = trimmed.slice(eqIdx + 1).trim();
    // Remove surrounding quotes
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    vars[key] = value;
  }
  return vars;
}

function maskValue(value: string): string {
  if (!value) return "";
  if (value.length <= 8) return "••••••••";
  return value.slice(0, 4) + "••••" + value.slice(-4);
}

// GET: Read all credentials (masked)
export async function GET() {
  try {
    if (!existsSync(ENV_PATH)) {
      return NextResponse.json({ error: "Env file not found" }, { status: 404 });
    }

    const content = readFileSync(ENV_PATH, "utf-8");
    const vars = parseEnvFile(content);

    // Build categorized output with masked values
    const categorized: Record<string, {
      label: string;
      credentials: { key: string; value_masked: string; is_set: boolean }[];
    }> = {};

    const categorizedKeys = new Set<string>();

    for (const [catId, cat] of Object.entries(CATEGORIES)) {
      categorized[catId] = {
        label: cat.label,
        credentials: cat.keys.map((key) => {
          categorizedKeys.add(key);
          const value = vars[key] || "";
          return {
            key,
            value_masked: value ? maskValue(value) : "",
            is_set: !!value,
          };
        }),
      };
    }

    // Collect uncategorized keys
    const uncategorized = Object.keys(vars)
      .filter((k) => !categorizedKeys.has(k))
      .map((key) => ({
        key,
        value_masked: maskValue(vars[key]),
        is_set: !!vars[key],
      }));

    if (uncategorized.length > 0) {
      categorized["other"] = {
        label: "Other",
        credentials: uncategorized,
      };
    }

    return NextResponse.json({
      categories: categorized,
      env_path: ENV_PATH,
      total_keys: Object.keys(vars).length,
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to read credentials" }, { status: 500 });
  }
}

// PUT: Update a single credential
export async function PUT(req: NextRequest) {
  try {
    const { key, value } = await req.json();

    if (!key || typeof key !== "string") {
      return NextResponse.json({ error: "Missing key" }, { status: 400 });
    }

    if (!existsSync(ENV_PATH)) {
      return NextResponse.json({ error: "Env file not found" }, { status: 404 });
    }

    const content = readFileSync(ENV_PATH, "utf-8");
    const lines = content.split("\n");
    let found = false;

    const updated = lines.map((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("#") || !trimmed) return line;
      const eqIdx = trimmed.indexOf("=");
      if (eqIdx === -1) return line;
      const lineKey = trimmed.slice(0, eqIdx).trim();
      if (lineKey === key) {
        found = true;
        // Preserve any inline comment
        return `${key}=${value}`;
      }
      return line;
    });

    if (!found) {
      // Append new key
      updated.push(`${key}=${value}`);
    }

    writeFileSync(ENV_PATH, updated.join("\n"));

    return NextResponse.json({
      success: true,
      key,
      value_masked: maskValue(value),
      note: "Orchestrator restart required for changes to take effect",
    });
  } catch (error) {
    return NextResponse.json({ error: "Failed to update credential" }, { status: 500 });
  }
}
