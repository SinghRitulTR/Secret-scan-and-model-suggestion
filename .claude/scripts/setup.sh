#!/bin/bash
# =============================================================
# Claude AI Workflow — One-Time Machine Setup
#
# Installs hooks, agents, skills, and git pre-commit protection
# globally so they work across ALL repos on this machine.
#
# Usage:
#   bash setup.sh                   # install everything (no prompts)
#   bash setup.sh --interactive     # choose what to install
#   bash setup.sh --only-hook       # install ONLY the git pre-commit hook
#   bash setup.sh --skip-agents     # skip agents
#   bash setup.sh --skip-skills     # skip skills
#   bash setup.sh --skip-hooks      # skip Claude Code hooks
#   bash setup.sh --skip-routing    # skip routing config
#   bash setup.sh --skip-global-hook # skip git pre-commit hook
#
# Re-run any time you pull updates to this repo.
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLAUDE_SRC="$REPO_DIR/.claude"
CLAUDE_GLOBAL="$HOME/.claude"
GIT_HOOKS_DIR="$HOME/.git-hooks"

# Colours
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✔${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "  ${RED}✘${NC}  $1"; }
info() { echo -e "  ${CYAN}→${NC}  $1"; }

# =============================================================
# PARSE FLAGS
# =============================================================
INTERACTIVE=0
ONLY_HOOK=0
SKIP_AGENTS=0
SKIP_SKILLS=0
SKIP_HOOKS=0
SKIP_ROUTING=0
SKIP_GLOBAL_HOOK=0

for arg in "$@"; do
  case $arg in
    --interactive)      INTERACTIVE=1 ;;
    --only-hook)        ONLY_HOOK=1 ;;
    --skip-agents)      SKIP_AGENTS=1 ;;
    --skip-skills)      SKIP_SKILLS=1 ;;
    --skip-hooks)       SKIP_HOOKS=1 ;;
    --skip-routing)     SKIP_ROUTING=1 ;;
    --skip-global-hook) SKIP_GLOBAL_HOOK=1 ;;
    --help|-h)
      echo ""
      echo "Usage: bash setup.sh [options]"
      echo ""
      echo "  (no flags)            Install everything"
      echo "  --interactive         Choose what to install via menu"
      echo "  --only-hook           Install ONLY the git pre-commit secret scanner"
      echo "  --skip-agents         Skip agent installation"
      echo "  --skip-skills         Skip skill installation"
      echo "  --skip-hooks          Skip Claude Code hooks (Write/Edit secret scan)"
      echo "  --skip-routing        Skip routing config installation"
      echo "  --skip-global-hook    Skip global git pre-commit hook"
      echo ""
      exit 0
      ;;
  esac
done

# =============================================================
# HEADER
# =============================================================
echo ""
echo "======================================================="
echo -e "  ${BOLD}Claude AI Workflow — Machine Setup${NC}"
echo "======================================================="
echo "  Repo    : $REPO_DIR"
echo "  Global  : $CLAUDE_GLOBAL"
echo "  Git hooks: $GIT_HOOKS_DIR"
echo "======================================================="
echo ""

# =============================================================
# INTERACTIVE MENU
# =============================================================
if [ "$INTERACTIVE" -eq 1 ]; then
  echo -e "${BOLD}What would you like to install?${NC}"
  echo ""
  echo "  [1] Git pre-commit secret scanner  (global, runs on ALL repos)  ← RECOMMENDED"
  echo "  [2] Claude Code hooks              (blocks secrets on Write/Edit inside Claude)"
  echo "  [3] Agents                         (AI sub-agents for /task workflow)"
  echo "  [4] Skills                         (/task, /gh-cmt-pr, /suggest-model, etc.)"
  echo "  [5] Routing config                 (model selection rules)"
  echo "  [A] All of the above"
  echo "  [Q] Quit"
  echo ""
  read -p "  Enter choices separated by spaces (e.g. 1 3 4 or A): " -r CHOICES
  echo ""

  CHOICES_UPPER=$(echo "$CHOICES" | tr '[:lower:]' '[:upper:]')

  if echo "$CHOICES_UPPER" | grep -q "Q"; then
    echo "  Exiting. Nothing was installed."
    exit 0
  fi

  if ! echo "$CHOICES_UPPER" | grep -q "A"; then
    echo "$CHOICES_UPPER" | grep -qv "1" && SKIP_GLOBAL_HOOK=1
    echo "$CHOICES_UPPER" | grep -qv "2" && SKIP_HOOKS=1
    echo "$CHOICES_UPPER" | grep -qv "3" && SKIP_AGENTS=1
    echo "$CHOICES_UPPER" | grep -qv "4" && SKIP_SKILLS=1
    echo "$CHOICES_UPPER" | grep -qv "5" && SKIP_ROUTING=1
  fi
fi

# --only-hook overrides everything else
if [ "$ONLY_HOOK" -eq 1 ]; then
  SKIP_AGENTS=1
  SKIP_SKILLS=1
  SKIP_HOOKS=1
  SKIP_ROUTING=1
  SKIP_GLOBAL_HOOK=0
fi

# =============================================================
# STEP 0 — Prerequisites check
# =============================================================
echo "[0] Checking prerequisites..."

PREREQ_FAIL=0
NEED_NODE=0
NEED_PYTHON=0

[ "$SKIP_HOOKS" -eq 0 ] && NEED_NODE=1
[ "$SKIP_HOOKS" -eq 0 ] && NEED_PYTHON=1

# Node.js
if [ "$NEED_NODE" -eq 1 ]; then
  if command -v node &>/dev/null; then
    pass "Node.js $(node --version)"
  else
    fail "Node.js not found — required for secret_scan.js hook"
    PREREQ_FAIL=1
  fi
fi

# Python
PYTHON_BIN=""
if [ "$NEED_PYTHON" -eq 1 ] || [ "$SKIP_ROUTING" -eq 0 ]; then
  for candidate in python3 python py \
    "/c/Users/$USERNAME/AppData/Local/Programs/Python/Python312/python.exe" \
    "/c/Users/$USERNAME/AppData/Local/Programs/Python/Python311/python.exe" \
    "/c/Python312/python.exe"; do
    if command -v "$candidate" &>/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      pass "Python: $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"
      break
    fi
  done
  if [ -z "$PYTHON_BIN" ]; then
    fail "Python not found — required for block-scan-project.py hook"
    PREREQ_FAIL=1
  fi
fi

# TruffleHog
TRUFFLEHOG_BIN=""
if [ "$SKIP_GLOBAL_HOOK" -eq 0 ]; then
  for candidate in trufflehog /c/tools/trufflehog /c/tools/trufflehog.exe "C:\\tools\\trufflehog.exe"; do
    if command -v "$candidate" &>/dev/null 2>&1 || [ -f "$candidate" ]; then
      TRUFFLEHOG_BIN="$candidate"
      pass "TruffleHog: $TRUFFLEHOG_BIN"
      break
    fi
  done
  if [ -z "$TRUFFLEHOG_BIN" ]; then
    warn "TruffleHog not found — regex scan will still run, TruffleHog stage will be skipped"
    warn "Install from: https://github.com/trufflesecurity/trufflehog/releases"
    TRUFFLEHOG_BIN="trufflehog"
  fi
fi

# Git
if command -v git &>/dev/null; then
  pass "$(git --version)"
else
  fail "Git not found"
  PREREQ_FAIL=1
fi

if [ "$PREREQ_FAIL" -eq 1 ]; then
  echo ""
  fail "Fix the above prerequisites then re-run this script."
  exit 1
fi

echo ""

# =============================================================
# STEP 1 — Create directories
# =============================================================
echo "[1] Creating directories..."
[ "$SKIP_HOOKS" -eq 0 ]       && mkdir -p "$CLAUDE_GLOBAL/hooks"
[ "$SKIP_AGENTS" -eq 0 ]      && mkdir -p "$CLAUDE_GLOBAL/agents"
[ "$SKIP_SKILLS" -eq 0 ]      && mkdir -p "$CLAUDE_GLOBAL/skills"
[ "$SKIP_GLOBAL_HOOK" -eq 0 ] && mkdir -p "$GIT_HOOKS_DIR"
pass "Directories ready"
echo ""

# =============================================================
# STEP 2 — Claude Code hooks (secret_scan.js, block-scan-project.py)
# =============================================================
if [ "$SKIP_HOOKS" -eq 0 ]; then
  echo "[2] Installing Claude Code hooks..."
  cp "$CLAUDE_SRC/hooks/secret_scan.js"        "$CLAUDE_GLOBAL/hooks/secret_scan.js"
  pass "secret_scan.js → blocks secrets on Write/Edit"
  cp "$CLAUDE_SRC/hooks/block-scan-project.py" "$CLAUDE_GLOBAL/hooks/block-scan-project.py"
  pass "block-scan-project.py → blocks full project scans"

  # Wire hooks into ~/.claude/settings.json — MERGE, never overwrite
  echo ""
  info "Updating ~/.claude/settings.json (merge only)..."
  SETTINGS="$CLAUDE_GLOBAL/settings.json"
  mkdir -p "$(dirname "$SETTINGS")"
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"

  "$PYTHON_BIN" - <<PYEOF
import json, os

settings_path = '$SETTINGS'
claude_global  = '$CLAUDE_GLOBAL'
python_bin     = '$PYTHON_BIN'

with open(settings_path, 'r') as f:
    try:
        settings = json.load(f)
    except json.JSONDecodeError:
        settings = {}

# Ensure hooks structure exists
if 'hooks' not in settings:
    settings['hooks'] = {}
if 'PreToolUse' not in settings['hooks']:
    settings['hooks']['PreToolUse'] = []
if 'PostToolUse' not in settings['hooks']:
    settings['hooks']['PostToolUse'] = []
if 'Notification' not in settings['hooks']:
    settings['hooks']['Notification'] = []

new_hooks = [
    {
        "matcher": "mcp__tr-code-scan-mcp__scan_project",
        "hooks": [{"type": "command", "command": python_bin + " " + claude_global + "/hooks/block-scan-project.py"}]
    },
    {
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": "node " + claude_global + "/hooks/secret_scan.js"}]
    }
]

# Only add if matcher not already present
existing_matchers = [h.get('matcher') for h in settings['hooks']['PreToolUse']]
added = 0
for hook in new_hooks:
    if hook['matcher'] not in existing_matchers:
        settings['hooks']['PreToolUse'].append(hook)
        added += 1

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=2)

if added > 0:
    print(f"  settings.json updated — {added} hook(s) added.")
else:
    print("  settings.json unchanged — hooks already present.")
PYEOF
  echo ""
else
  info "Skipping Claude Code hooks."
  echo ""
fi

# =============================================================
# STEP 3 — Agents
# =============================================================
if [ "$SKIP_AGENTS" -eq 0 ]; then
  echo "[3] Installing agents..."
  AGENT_COUNT=0
  for f in "$CLAUDE_SRC/agents/"*.md; do
    [ -f "$f" ] || continue
    cp "$f" "$CLAUDE_GLOBAL/agents/"
    pass "$(basename "$f")"
    AGENT_COUNT=$((AGENT_COUNT + 1))
  done
  echo "      $AGENT_COUNT agents installed."
  echo ""
else
  info "Skipping agents."
  echo ""
fi

# =============================================================
# STEP 4 — Skills
# =============================================================
if [ "$SKIP_SKILLS" -eq 0 ]; then
  echo "[4] Installing skills..."
  SKILL_COUNT=0
  for dir in "$CLAUDE_SRC/skills/"*/; do
    [ -d "$dir" ] || continue
    SKILL_NAME=$(basename "$dir")
    mkdir -p "$CLAUDE_GLOBAL/skills/$SKILL_NAME"
    cp "$dir"SKILL.md "$CLAUDE_GLOBAL/skills/$SKILL_NAME/SKILL.md"
    pass "/$SKILL_NAME"
    SKILL_COUNT=$((SKILL_COUNT + 1))
  done
  echo "      $SKILL_COUNT skills installed."
  echo ""
else
  info "Skipping skills."
  echo ""
fi

# =============================================================
# STEP 5 — Routing config
# =============================================================
if [ "$SKIP_ROUTING" -eq 0 ]; then
  echo "[5] Installing routing config..."
  if [ -d "$CLAUDE_SRC/config" ]; then
    mkdir -p "$CLAUDE_GLOBAL/config"
    cp "$CLAUDE_SRC/config/model-routing.json" "$CLAUDE_GLOBAL/config/model-routing.json"
    pass "model-routing.json → ~/.claude/config/"
    cp "$CLAUDE_SRC/config/phase-floors.json"  "$CLAUDE_GLOBAL/config/phase-floors.json"
    pass "phase-floors.json  → ~/.claude/config/"
    mkdir -p "$CLAUDE_GLOBAL/data"
    [ -f "$CLAUDE_GLOBAL/data/routing-log.jsonl" ] || echo "" > "$CLAUDE_GLOBAL/data/routing-log.jsonl"
    [ -f "$CLAUDE_GLOBAL/data/stats-cache.json"  ] || echo "{}" > "$CLAUDE_GLOBAL/data/stats-cache.json"
    pass "routing-log.jsonl + stats-cache.json initialised"
  else
    warn "No .claude/config/ found in repo — skipping"
  fi
  echo ""
else
  info "Skipping routing config."
  echo ""
fi

# =============================================================
# STEP 6a — Activate pre-commit framework (if installed)
# =============================================================
if [ "$SKIP_GLOBAL_HOOK" -eq 0 ]; then
  echo "[6a] Activating pre-commit framework..."
  if command -v pre-commit &>/dev/null; then
    pre-commit install
    pass "pre-commit framework activated (.pre-commit-config.yaml)"
  else
    warn "pre-commit not installed — run: pip install pre-commit && pre-commit install"
  fi
  echo ""
fi

# =============================================================
# STEP 6 — Global git pre-commit hook (safe install)
# Runs on EVERY git commit in EVERY repo on this machine.
# If the user already has a global hooks path, we respect it
# and copy our script there instead of overwriting the path.
# =============================================================
if [ "$SKIP_GLOBAL_HOOK" -eq 0 ]; then
  echo "[6] Installing global git pre-commit hook..."

  EXISTING_HOOKS_PATH=$(git config --global core.hooksPath 2>/dev/null || echo "")

  if [ -n "$EXISTING_HOOKS_PATH" ] && [ "$EXISTING_HOOKS_PATH" != "$GIT_HOOKS_DIR" ]; then
    # Respect existing hooks path — drop our script there
    warn "Existing global hooks path detected: $EXISTING_HOOKS_PATH"
    info "Installing pre-commit into your existing hooks path (not changing core.hooksPath)..."
    TARGET_HOOKS_DIR="$EXISTING_HOOKS_PATH"
    mkdir -p "$TARGET_HOOKS_DIR"
  else
    # No existing path — set ours
    TARGET_HOOKS_DIR="$GIT_HOOKS_DIR"
    mkdir -p "$TARGET_HOOKS_DIR"
    git config --global core.hooksPath "$TARGET_HOOKS_DIR"
    pass "git config --global core.hooksPath set to $TARGET_HOOKS_DIR"
  fi

  # Write the pre-commit hook script
  cat > "$TARGET_HOOKS_DIR/pre-commit" <<HOOK
#!/bin/bash
# Global pre-commit secret scanner
# Installed by Claude AI Workflow setup.sh

echo "[pre-commit] Running secret scan..."

STAGED_FILES=\$(git diff --cached --name-only 2>/dev/null)
if [ -z "\$STAGED_FILES" ]; then
  echo "[pre-commit] No staged files. Skipping."
  exit 0
fi

# Stage 1: Regex scan on staged files
SECRET_FOUND=0
for file in \$STAGED_FILES; do
  [ -f "\$file" ] || continue
  if grep -Eq \
    "(AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\\-_]{35}|ghp_[0-9a-zA-Z]{36}|gho_[0-9a-zA-Z]{36}|ghu_[0-9a-zA-Z]{36}|ghr_[0-9a-zA-Z]{36}|github_pat_[A-Za-z0-9_]{82}|sk-[A-Za-z0-9]{48}|sk-proj-[A-Za-z0-9_-]{50}|sk-ant-[A-Za-z0-9_-]{80}|sk_live_[0-9a-zA-Z]{24}|sk_test_[0-9a-zA-Z]{24}|hf_[A-Za-z0-9]{34}|npm_[a-zA-Z0-9]{36}|SG\\.[A-Za-z0-9_-]{22}\\.[A-Za-z0-9_-]{43}|xox[baprs]-[0-9]{10,13}-[0-9]{10,13}|AWS_SECRET_ACCESS_KEY\\s*=\\s*[A-Za-z0-9/+]{40}|BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY)" \
    "\$file" 2>/dev/null; then
    echo "[pre-commit] BLOCKED: Potential secret detected in \$file. Remove before committing."
    SECRET_FOUND=1
  fi
done

[ "\$SECRET_FOUND" -eq 1 ] && exit 1

# Stage 2: TruffleHog (if available)
TRUFFLEHOG="${TRUFFLEHOG_BIN}"
if command -v "\$TRUFFLEHOG" &>/dev/null 2>&1 || [ -f "\$TRUFFLEHOG" ]; then
  "\$TRUFFLEHOG" filesystem . --fail --no-update --json > /dev/null 2>&1
  if [ \$? -ne 0 ]; then
    echo "[pre-commit] BLOCKED: TruffleHog detected secrets. Remove them before committing."
    exit 1
  fi
fi

echo "[pre-commit] Clean — no secrets detected."
exit 0
HOOK

  chmod +x "$TARGET_HOOKS_DIR/pre-commit"
  pass "pre-commit hook installed at $TARGET_HOOKS_DIR/pre-commit"
  echo ""
else
  info "Skipping global git pre-commit hook."
  echo ""
fi

# =============================================================
# STEP 7 — Environment variable check
# =============================================================
echo "[7] Checking environment variables..."

check_env() {
  local var="$1"
  local desc="$2"
  if [ -n "${!var}" ]; then
    pass "$var is set"
  else
    warn "$var not set — $desc"
  fi
}

check_env "GITHUB_TOKEN"        "required for GitHub MCP (PR creation, reviews)"
check_env "ADO_MCP_AUTH_TOKEN"  "required for Azure DevOps MCP (story fetch)"
check_env "TR_CODE_SCAN_BINARY" "required for tr-code-scan-mcp security scanning"

echo ""
echo "======================================================="
echo -e "  ${GREEN}${BOLD}Setup Complete!${NC}"
echo "======================================================="
echo ""

# Summary of what was installed
[ "$SKIP_GLOBAL_HOOK" -eq 0 ] && echo "  ✔  Git pre-commit secret scanner (global)"
[ "$SKIP_HOOKS" -eq 0 ]       && echo "  ✔  Claude Code hooks (Write/Edit secret scan)"
[ "$SKIP_AGENTS" -eq 0 ]      && echo "  ✔  Agents → ~/.claude/agents/"
[ "$SKIP_SKILLS" -eq 0 ]      && echo "  ✔  Skills → ~/.claude/skills/"
[ "$SKIP_ROUTING" -eq 0 ]     && echo "  ✔  Routing config → ~/.claude/config/"
echo ""

MISSING_ENVS=0
for v in GITHUB_TOKEN ADO_MCP_AUTH_TOKEN TR_CODE_SCAN_BINARY; do
  [ -z "${!v}" ] && MISSING_ENVS=$((MISSING_ENVS + 1))
done

if [ "$MISSING_ENVS" -gt 0 ]; then
  echo "  ACTION REQUIRED — add these to your ~/.bashrc or ~/.zshrc:"
  echo ""
  echo "    export GITHUB_TOKEN=<your GitHub PAT>"
  echo "    export ADO_MCP_AUTH_TOKEN=<your ADO PAT>"
  echo "    export TR_CODE_SCAN_BINARY=<path to tr-code-scan binary>"
  echo ""
  echo "  Then reload: source ~/.bashrc"
  echo ""
fi

echo "  Open any project and run: claude"
echo "  No .claude/ folder needed per repo."
echo ""
