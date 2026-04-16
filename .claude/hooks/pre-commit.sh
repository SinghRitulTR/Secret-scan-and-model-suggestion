#!/bin/bash
echo "Running secret scan..."

# Step 1: Regex scan on staged files (catches fake but correctly formatted keys)
STAGED_FILES=$(git diff --cached --name-only)
for file in $STAGED_FILES; do
  if [ -f "$file" ]; then
    if grep -Eq "(AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{35}|ghp_[0-9a-zA-Z]{36}|gho_[0-9a-zA-Z]{36}|ghu_[0-9a-zA-Z]{36}|ghr_[0-9a-zA-Z]{36}|github_pat_[A-Za-z0-9_]{82}|sk-[A-Za-z0-9]{48}|sk-proj-[A-Za-z0-9_-]{50}|sk-ant-[A-Za-z0-9_-]{80}|sk_live_[0-9a-zA-Z]{24}|sk_test_[0-9a-zA-Z]{24}|hf_[A-Za-z0-9]{34}|npm_[a-zA-Z0-9]{36}|SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}|xox[baprs]-[0-9]{10,13}-[0-9]{10,13}|AWS_SECRET_ACCESS_KEY\s*=\s*[A-Za-z0-9/+]{40}|aws_secret_access_key\s*[=:]\s*['\"]?[A-Za-z0-9/+]{40}|api[_-]?key\s*[=:]\s*['\"][^'\"]{16,}['\"]|password\s*[=:]\s*['\"][^'\"]{8,}['\"]|secret\s*[=:]\s*['\"][^'\"]{16,}['\"]|token\s*[=:]\s*['\"][^'\"]{20,}['\"]|BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY)" "$file"; then
      echo "BLOCKED: Potential secret pattern found in $file. Remove it before committing."
      exit 1
    fi
  fi
done

# Step 2: TruffleHog for verified real secrets
C:/tools/trufflehog.exe filesystem --directory=. --fail --no-update 2>/dev/null
if [ $? -ne 0 ]; then
  echo "BLOCKED: TruffleHog detected secrets. Remove them before committing."
  exit 1
fi

echo "No secrets detected. Proceeding with commit."
exit 0
