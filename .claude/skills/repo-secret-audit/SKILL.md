---
name: repo-secret-audit
description: Scan the entire repository for exposed secrets, API keys, tokens, private keys, and sensitive configuration using TruffleHog.
argument-hint: "[scope: diff|full|history]"
allowed-tools: Bash, Read, Glob, Grep
---

You are running a comprehensive repository secret audit.

## Purpose
Perform a thorough scan of the repository for:
- API keys and access tokens (AWS, Azure, GCP, GitHub, etc.)
- Private keys and certificates (.pem, .key, .p12)
- Environment files (.env, .env.prod, .env.local)
- Credentials and connection strings
- Hardcoded passwords and secrets
- Sensitive configuration files

## Input Arguments
- `diff` - Scan only changes since main branch (fastest)
- `full` - Scan entire current repository state (recommended)
- `history` - Scan full git history (slowest, most thorough)
- No argument defaults to `full`

## Execution

### Step 1: Determine scan scope
```
Argument: $ARGUMENTS
Scope: <diff|full|history>
```

### Step 2: Run appropriate TruffleHog scan

**For `diff` scan:**
```powershell
powershell -ExecutionPolicy Bypass -File .claude\scripts\run_trufflehog.ps1 main . .claude\tmp
```

**For `full` scan:**
```powershell
C:\tools\trufflehog.exe filesystem . --json --fail > .claude\tmp\trufflehog-repo-scan.json 2>&1
```

**For `history` scan:**
```powershell
C:\tools\trufflehog.exe git file://. --json --fail > .claude\tmp\trufflehog-history-scan.json 2>&1
```

### Step 3: Also scan for risky files (regardless of TruffleHog results)
Search for potentially sensitive files:
```bash
git ls-files | grep -iE "\.(env|pem|key|p12|pfx|jks)$|credentials|secrets|id_rsa|id_dsa"
```

### Step 4: Generate comprehensive report

**Output Format:**

```
╔═══════════════════════════════════════════════════════════════╗
║              REPOSITORY SECRET AUDIT REPORT                   ║
╚═══════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────┐
│                      SCAN DETAILS                           │
└─────────────────────────────────────────────────────────────┘

  Repository:  <repo name>
  Scan Type:   <diff|full|history>
  Scan Time:   <timestamp>
  
╔═══════════════════════════════════════════════════════════════╗
║                         RESULTS                               ║
╚═══════════════════════════════════════════════════════════════╝

  Overall Status:      <PASS | FINDINGS DETECTED | ERROR>
  TruffleHog Findings: <count>
  Risky Files Found:   <count>

┌─────────────────────────────────────────────────────────────┐
│                    SECRET FINDINGS                          │
└─────────────────────────────────────────────────────────────┘

| # | Type | File | Line | Confidence | Value |
|---|------|------|------|------------|-------|
| 1 | AWS Access Key | config/aws.yml | 12 | HIGH | AKIA**** |
| 2 | GitHub Token | scripts/deploy.sh | 45 | HIGH | ghp_**** |

┌─────────────────────────────────────────────────────────────┐
│                  RISKY FILES DETECTED                       │
└─────────────────────────────────────────────────────────────┘

| # | File | Risk | Recommendation |
|---|------|------|----------------|
| 1 | .env.local | HIGH | Should not be committed |
| 2 | certs/server.key | HIGH | Private key file |
| 3 | config/credentials.json | HIGH | Credentials file |

╔═══════════════════════════════════════════════════════════════╗
║                     RECOMMENDATIONS                           ║
╚═══════════════════════════════════════════════════════════════╝

IMMEDIATE ACTIONS REQUIRED:
─────────────────────────────────────────────────────────────────
1. Remove identified secrets from source files
2. Rotate any exposed credentials immediately
3. Add sensitive files to .gitignore

IF SECRETS WERE COMMITTED TO HISTORY:
─────────────────────────────────────────────────────────────────
Option A - BFG Repo-Cleaner (recommended):
  $ bfg --delete-files <filename> .
  $ git reflog expire --expire=now --all
  $ git gc --prune=now --aggressive

Option B - git filter-branch:
  $ git filter-branch --force --index-filter \
      "git rm --cached --ignore-unmatch <file>" HEAD

PREVENTION:
─────────────────────────────────────────────────────────────────
1. Use environment variables for all secrets
2. Use a secrets manager (AWS Secrets Manager, Azure Key Vault)
3. Enable pre-commit hooks to prevent future leaks
4. Review .gitignore to exclude sensitive file patterns
5. Run this audit regularly before releases

╔═══════════════════════════════════════════════════════════════╗
║                      AUDIT COMPLETE                           ║
╚═══════════════════════════════════════════════════════════════╝
```

## Safety Rules
- NEVER display full secret values
- ALWAYS mask secrets after first 4 characters
- ALWAYS recommend credential rotation for confirmed findings
- Include git history cleanup instructions for committed secrets
- Provide actionable remediation steps
