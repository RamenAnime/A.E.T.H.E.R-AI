#!/usr/bin/env node
/**
 * Universal repo health: Node, Python, shell installer, or docs-only.
 */
import { execSync, spawnSync } from "node:child_process";
import fs from "node:fs";

const repo = process.env.GITHUB_REPOSITORY || "local/repo";
const ref = process.env.GITHUB_REF_NAME || "local";
const runUrl =
  process.env.GITHUB_SERVER_URL && process.env.GITHUB_RUN_ID
    ? `${process.env.GITHUB_SERVER_URL}/${repo}/actions/runs/${process.env.GITHUB_RUN_ID}`
    : "";

const lines = [`# Project health: ${repo}`, "", `- **Branch:** \`${ref}\``, `- **Time:** ${new Date().toISOString()}`];
if (runUrl) lines.push(`- **Workflow run:** ${runUrl}`);
lines.push("");

const push = (s) => lines.push(s);

function run(cmd, label) {
  push(`## ${label}`);
  push(`\`\`\`bash\n${cmd}\n\`\`\``);
  const r = spawnSync(cmd, { shell: true, encoding: "utf8", maxBuffer: 12 * 1024 * 1024 });
  const out = [r.stdout, r.stderr].filter(Boolean).join("\n").trim() || "(no output)";
  push("```");
  push(out.slice(0, 12000));
  if (out.length > 12000) push("... (truncated)");
  push("```");
  push(r.status === 0 ? "**Result:** pass\n" : `**Result:** fail (exit ${r.status})\n`);
  return r.status === 0;
}

let allPass = true;

if (fs.existsSync("package.json")) {
  push("### Node.js");
  push("");
  try {
    execSync("npm ci", { stdio: "pipe" });
  } catch {
    try {
      execSync("npm install", { stdio: "pipe" });
    } catch {
      push("**npm install failed**\n");
      allPass = false;
    }
  }
  const scripts = JSON.parse(fs.readFileSync("package.json", "utf8")).scripts || {};
  for (const name of ["lint", "typecheck", "test", "build"]) {
    if (scripts[name]) {
      if (!run(`npm run ${name}`, `npm run ${name}`)) allPass = false;
    }
  }
  push("## npm audit summary");
  const audit = spawnSync("npm audit --json", { shell: true, encoding: "utf8" });
  try {
    const j = JSON.parse(audit.stdout || "{}");
    const v = j.metadata?.vulnerabilities || {};
    push(`critical: ${v.critical ?? 0}, high: ${v.high ?? 0}, moderate: ${v.moderate ?? 0}`);
  } catch {
    push("_(audit output unavailable)_");
  }
  push("");
}

if (fs.existsSync("pyproject.toml")) {
  push("### Python");
  push("");
  if (!run("pip install -e .", "pip install -e .")) allPass = false;
  if (fs.existsSync("tests")) {
    if (!run("pytest tests/ -q", "pytest")) allPass = false;
  } else {
    push("_No tests/ directory; skipped pytest_\n");
  }
}

for (const f of ["mcp-arch.sh", "easy-install.sh"]) {
  if (fs.existsSync(f)) {
    push("### Shell installer");
    push("");
    for (const sh of ["mcp-arch.sh", "easy-install.sh", "install/preflight.sh", "install/packages.sh"]) {
      if (fs.existsSync(sh) && !run(`bash -n "${sh}"`, `bash -n ${sh}`)) allPass = false;
    }
  }
}

const mdFiles = fs.readdirSync(".", { withFileTypes: true }).filter((d) => d.isFile() && d.name.endsWith(".md"));
if (!fs.existsSync("package.json") && !fs.existsSync("pyproject.toml") && !fs.existsSync("mcp-arch.sh")) {
  push("### Documentation repo");
  push("");
  if (!fs.existsSync("README.md")) {
    push("**Missing README.md**");
    allPass = false;
  } else {
    push("- README.md present");
  }
  push(`- Markdown files in root: ${mdFiles.map((f) => f.name).join(", ") || "(none)"}`);
  push("");
}

push("---");
push(allPass ? "**Overall: checks passed**" : "**Overall: one or more checks failed**");
push("");
push("## Stopping point");
push("Comment `/approve-continue` on the linked issue to run the enhancement review pass.");

const report = lines.join("\n");
fs.writeFileSync("health-report.md", report);
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, report);
process.exit(allPass ? 0 : 1);
