#!/usr/bin/env node
/**
 * Post a JSON payload to Slack incoming webhook.
 * Env: SLACK_WEBHOOK_URL (required), SLACK_PAYLOAD (JSON string)
 */
const webhook = process.env.SLACK_WEBHOOK_URL?.trim();
if (!webhook) {
  console.log("SLACK_WEBHOOK_URL not set; skipping Slack notification.");
  process.exit(0);
}

let payload;
try {
  payload = JSON.parse(process.env.SLACK_PAYLOAD || "{}");
} catch {
  console.error("SLACK_PAYLOAD must be valid JSON");
  process.exit(1);
}

const res = await fetch(webhook, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

if (!res.ok) {
  const text = await res.text();
  console.error(`Slack webhook failed: ${res.status} ${text}`);
  process.exit(1);
}

console.log("Slack notification sent.");
