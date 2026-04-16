/**
 * PreToolUse hook: centralized secret scanner for Write and Edit operations.
 * Scans content being written/edited for common secret patterns before the file is touched.
 * Returns block decision if high-confidence secrets are detected.
 */

const readline = require("readline");

const SECRET_PATTERNS = [
  // Private keys
  { pattern: /-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/, label: "Private key", severity: "BLOCK" },

  // High-entropy API keys (long alphanumeric strings in assignment context)
  { pattern: /(?:api[_-]?key|apikey|access[_-]?key)\s*[:=]\s*['"]([A-Za-z0-9_\-\/+]{20,})['"]/, label: "API key assignment", severity: "BLOCK" },

  // Bearer tokens / Authorization headers
  { pattern: /Authorization\s*:\s*['"]?Bearer\s+([A-Za-z0-9_\-\.]{20,})/, label: "Bearer token", severity: "BLOCK" },

  // Password assignments (non-placeholder values)
  { pattern: /(?:password|passwd|pwd)\s*[:=]\s*['"]([^'"<>{}\s]{8,})['"]/, label: "Password assignment", severity: "REVIEW" },

  // Secret/token assignments
  { pattern: /(?:secret|token|credential)\s*[:=]\s*['"]([A-Za-z0-9_\-\/+\.]{16,})['"]/, label: "Secret/token assignment", severity: "REVIEW" },

  // AWS-style access keys
  { pattern: /(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}/, label: "AWS access key", severity: "BLOCK" },

  // URLs with embedded credentials
  { pattern: /https?:\/\/[^:@\s"']+:[^@\s"']{4,}@[^/\s"']+/, label: "URL with embedded credentials", severity: "BLOCK" },

  // Connection strings with passwords
  { pattern: /(?:mongodb|postgresql|mysql|redis|amqp):\/\/[^:@\s"']+:[^@\s"']{4,}@/, label: "Connection string with password", severity: "BLOCK" },
];

// Patterns that indicate a value is NOT a real secret (false positive indicators)
const FALSE_POSITIVE_PATTERNS = [
  /(?:example|placeholder|your[_-]?|changeme|xxx+|fake|dummy|sample|test|<|>|\$\{|\{\{)/i,
  /^(true|false|null|undefined|none|empty)$/i,
  /^[*]+$/,  // all asterisks
];

function isFalsePositive(value) {
  if (!value) return true;
  return FALSE_POSITIVE_PATTERNS.some((fp) => fp.test(value));
}

function extractMatchValue(match) {
  // Return captured group 1 if present, otherwise the full match
  return match[1] || match[0];
}

function maskValue(value) {
  if (!value || value.length < 4) return "***";
  return value.substring(0, 4) + "***";
}

function scanContent(content) {
  const findings = [];

  for (const { pattern, label, severity } of SECRET_PATTERNS) {
    const globalPattern = new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : pattern.flags + "g");
    let match;
    while ((match = globalPattern.exec(content)) !== null) {
      const value = extractMatchValue(match);
      if (!isFalsePositive(value)) {
        findings.push({ label, severity, masked: maskValue(value) });
      }
    }
  }

  return findings;
}

async function main() {
  const rl = readline.createInterface({ input: process.stdin });
  let raw = "";
  for await (const line of rl) {
    raw += line + "\n";
  }

  let inputData;
  try {
    inputData = JSON.parse(raw);
  } catch {
    // If we can't parse input, approve to avoid blocking normal operations
    process.stdout.write(JSON.stringify({ decision: "approve" }));
    return;
  }

  const toolName = inputData.tool_name || "";
  const toolInput = inputData.tool_input || {};

  // Extract content to scan based on tool type
  let contentToScan = "";
  if (toolName === "Write") {
    contentToScan = toolInput.content || "";
  } else if (toolName === "Edit") {
    // Only scan the new content being inserted, not the old content being replaced
    contentToScan = toolInput.new_string || "";
  } else {
    process.stdout.write(JSON.stringify({ decision: "approve" }));
    return;
  }

  if (!contentToScan.trim()) {
    process.stdout.write(JSON.stringify({ decision: "approve" }));
    return;
  }

  const findings = scanContent(contentToScan);

  if (findings.length === 0) {
    process.stdout.write(JSON.stringify({ decision: "approve" }));
    return;
  }

  const blockFindings = findings.filter((f) => f.severity === "BLOCK");
  const reviewFindings = findings.filter((f) => f.severity === "REVIEW");

  if (blockFindings.length > 0) {
    const details = blockFindings.map((f) => `${f.label} (${f.masked})`).join(", ");
    process.stdout.write(
      JSON.stringify({
        decision: "block",
        reason: `Secret scan blocked: potential ${details} detected in content being written. Remove the secret and use environment variables or a secrets manager instead.`,
      })
    );
    return;
  }

  // REVIEW findings — warn but allow (these may be false positives)
  if (reviewFindings.length > 0) {
    const details = reviewFindings.map((f) => `${f.label} (${f.masked})`).join(", ");
    // Approve with a warning message in the reason (not a block)
    process.stdout.write(
      JSON.stringify({
        decision: "approve",
        reason: `Secret scan warning: possible ${details} detected. Verify these are not real credentials before committing.`,
      })
    );
    return;
  }

  process.stdout.write(JSON.stringify({ decision: "approve" }));
}

main().catch(() => {
  // On any unexpected error, approve to avoid blocking normal operations
  process.stdout.write(JSON.stringify({ decision: "approve" }));
});
