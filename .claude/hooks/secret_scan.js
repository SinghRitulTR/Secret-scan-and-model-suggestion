#!/usr/bin/env node
/**
 * Pre-tool-use hook to block writing files containing secrets.
 * Intercepts Write, Edit operations and scans content for secrets.
 * Based on senior's recommended approach.
 */

const fs = require('fs');

// Secret patterns to detect
const SECRET_PATTERNS = [
  // AWS
  { name: 'AWS Access Key', pattern: /AKIA[0-9A-Z]{16}/g },
  { name: 'AWS Secret Key', pattern: /[0-9a-zA-Z/+]{40}/g },
  
  // GitHub
  { name: 'GitHub Token', pattern: /ghp_[0-9a-zA-Z]{36}/g },
  { name: 'GitHub OAuth', pattern: /gho_[0-9a-zA-Z]{36}/g },
  { name: 'GitHub App Token', pattern: /ghu_[0-9a-zA-Z]{36}/g },
  { name: 'GitHub Refresh Token', pattern: /ghr_[0-9a-zA-Z]{36}/g },
  
  // Azure
  { name: 'Azure Storage Key', pattern: /[A-Za-z0-9+/]{86}==/g },
  
  // Google
  { name: 'Google API Key', pattern: /AIza[0-9A-Za-z-_]{35}/g },
  
  // Generic
  { name: 'Private Key', pattern: /-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/g },
  { name: 'Password Assignment', pattern: /password\s*[=:]\s*['"][^'"]{8,}['"]/gi },
  { name: 'API Key Assignment', pattern: /api[_-]?key\s*[=:]\s*['"][^'"]{16,}['"]/gi },
  { name: 'Secret Assignment', pattern: /secret\s*[=:]\s*['"][^'"]{16,}['"]/gi },
  { name: 'Token Assignment', pattern: /token\s*[=:]\s*['"][^'"]{20,}['"]/gi },
  { name: 'Bearer Token', pattern: /Bearer\s+[a-zA-Z0-9_-]{20,}/g },
  
  // Connection Strings
  { name: 'Database Connection String', pattern: /mongodb(\+srv)?:\/\/[^:]+:[^@]+@/gi },
  { name: 'SQL Connection String', pattern: /Server=.+;.*Password=[^;]+/gi },
  
  // JWT
  { name: 'JWT Token', pattern: /eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+/g },
  
  // Slack
  { name: 'Slack Token', pattern: /xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*/g },
  
  // Stripe
  { name: 'Stripe Key', pattern: /sk_live_[0-9a-zA-Z]{24,}/g },
  
  // npm
  { name: 'npm Token', pattern: /npm_[a-zA-Z0-9]{36}/g },
];

// Sensitive file patterns
const SENSITIVE_FILES = [
  /\.env$/i,
  /\.env\.[a-z]+$/i,
  /\.pem$/i,
  /\.key$/i,
  /\.p12$/i,
  /\.pfx$/i,
  /id_rsa/i,
  /id_dsa/i,
  /id_ecdsa/i,
  /id_ed25519/i,
  /credentials\.json$/i,
  /secrets\.json$/i,
  /secrets\.ya?ml$/i,
];

// Allowed exceptions (test/example files)
const ALLOWED_PATTERNS = [
  /\.env\.example$/i,
  /\.env\.sample$/i,
  /\.env\.template$/i,
  /test[s]?\//i,
  /example[s]?\//i,
  /fixture[s]?\//i,
  /mock[s]?\//i,
  /placeholder/i,
  /changeme/i,
  /your[_-]?api[_-]?key/i,
  /xxx+/i,
  /dummy/i,
  /fake/i,
  /sample/i,
];

function isAllowedContent(content) {
  const lowerContent = content.toLowerCase();
  return ALLOWED_PATTERNS.some(pattern => pattern.test(lowerContent));
}

function isAllowedFile(filepath) {
  return ALLOWED_PATTERNS.some(pattern => pattern.test(filepath));
}

function isSensitiveFile(filepath) {
  if (isAllowedFile(filepath)) return false;
  return SENSITIVE_FILES.some(pattern => pattern.test(filepath));
}

function maskSecret(value) {
  if (value.length <= 8) return '****';
  return value.substring(0, 4) + '*'.repeat(Math.min(value.length - 4, 16));
}

function scanContent(content) {
  const findings = [];
  
  for (const { name, pattern } of SECRET_PATTERNS) {
    // Reset pattern lastIndex for global patterns
    pattern.lastIndex = 0;
    const matches = content.match(pattern);
    if (matches) {
      for (const match of matches) {
        // Skip if it looks like a placeholder
        if (isAllowedContent(match)) continue;
        
        findings.push({ 
          type: name, 
          masked: maskSecret(match) 
        });
      }
    }
  }
  
  return findings;
}

function main() {
  let inputData = '';
  
  // Read from stdin
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => { inputData += chunk; });
  
  process.stdin.on('end', () => {
    try {
      const input = JSON.parse(inputData);
      const toolName = input.tool_name || '';
      const toolInput = input.tool_input || {};
      
      // Only check Write, Edit operations
      if (!['Write', 'Edit'].includes(toolName)) {
        process.exit(0);
      }
      
      const filepath = toolInput.file_path || toolInput.path || '';
      const content = toolInput.content || toolInput.new_string || '';
      
      // Check if it's a sensitive file type
      if (isSensitiveFile(filepath)) {
        const result = {
          decision: 'block',
          reason: `BLOCKED: "${filepath}" is a sensitive file type that may contain secrets. Use .env.example for templates instead.`
        };
        console.log(JSON.stringify(result));
        process.exit(0);
      }
      
      // Scan content for secrets
      const findings = scanContent(content);
      
      if (findings.length > 0) {
        const findingsList = findings.slice(0, 3).map(f => `${f.type}: ${f.masked}`).join(', ');
        const extra = findings.length > 3 ? ` (+${findings.length - 3} more)` : '';
        const result = {
          decision: 'block',
          reason: `BLOCKED: Potential secrets detected - ${findingsList}${extra}. Remove secrets and use environment variables instead.`
        };
        console.log(JSON.stringify(result));
        process.exit(0);
      }
      
      // No issues found, allow
      process.exit(0);
      
    } catch (e) {
      // If parsing fails, allow (fail open)
      process.exit(0);
    }
  });
}

main();
