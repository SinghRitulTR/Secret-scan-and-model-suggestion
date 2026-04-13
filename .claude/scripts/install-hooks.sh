#!/bin/bash
# =============================================================
# Claude AI Workflow — One-Time Developer Machine Setup
# Centralizes hooks, agents, and skills to ~/.claude/ so they
# work across ALL projects on this machine automatically.
#
# Run ONCE after cloning this repo:
#   bash .claude/scripts/install-hooks.sh
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
CLAUDE_DIR="$HOME/.claude"
GIT_HOOKS_DIR="$HOME/.git-hooks"

echo ""
echo "======================================"
echo " Claude AI Workflow — Machine Setup"
echo "======================================"
echo " Template : $TEMPLATE_DIR"
echo " Target   : $CLAUDE_DIR"
echo ""

# --------------------------------------------------------------
# STEP 1 — Create directories
# --------------------------------------------------------------
echo "[1/6] Creating directories..."
mkdir -p "$CLAUDE_DIR/hooks"
mkdir -p "$CLAUDE_DIR/agents"
mkdir -p "$CLAUDE_DIR/skills"
mkdir -p "$GIT_HOOKS_DIR"
echo "      Done."

# --------------------------------------------------------------
# STEP 2 — Copy Claude hook scripts
# These run inside Claude Code on every Write/Edit
# --------------------------------------------------------------
echo "[2/6] Copying hook scripts..."
cp "$TEMPLATE_DIR/.claude/hooks/secret_scan.js"          "$CLAUDE_DIR/hooks/secret_scan.js"
cp "$TEMPLATE_DIR/.claude/hooks/block-scan-project.py"   "$CLAUDE_DIR/hooks/block-scan-project.py"
echo "      Done."

# --------------------------------------------------------------
# STEP 3 — Copy agents
# All 8 agents become available in every project
# --------------------------------------------------------------
echo "[3/6] Copying agents..."
cp "$TEMPLATE_DIR/.claude/agents/"*.md "$CLAUDE_DIR/agents/"
echo "      Done."

# --------------------------------------------------------------
# STEP 4 — Copy skills
# All skills (/task, /gh-cmt-pr etc.) available in every project
# --------------------------------------------------------------
echo "[4/6] Copying skills..."
cp -r "$TEMPLATE_DIR/.claude/skills/"* "$CLAUDE_DIR/skills/"
echo "      Done."

# --------------------------------------------------------------
# STEP 5 — Update ~/.claude/settings.json with hooks config
# Safely merges hooks into existing settings without overwriting
# --------------------------------------------------------------
echo "[5/6] Updating ~/.claude/settings.json..."

SETTINGS="$CLAUDE_DIR/settings.json"

if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

python3 - <<EOF
import json

with open('$SETTINGS', 'r') as f:
    settings = json.load(f)

settings['hooks'] = {
    "PreToolUse": [
        {
            "matcher": "mcp__tr-code-scan-mcp__scan_project",
            "hooks": [{"type": "command", "command": "python3 $CLAUDE_DIR/hooks/block-scan-project.py"}]
        },
        {
            "matcher": "Write|Edit",
            "hooks": [{"type": "command", "command": "node $CLAUDE_DIR/hooks/secret_scan.js"}]
        }
    ],
    "PostToolUse": [],
    "Notification": []
}

with open('$SETTINGS', 'w') as f:
    json.dump(settings, f, indent=2)

print("      settings.json updated.")
EOF

# --------------------------------------------------------------
# STEP 6 — Install global git pre-commit hook
# Runs on every git commit in EVERY repo on this machine
# --------------------------------------------------------------
echo "[6/6] Installing global git pre-commit hook..."
cp "$TEMPLATE_DIR/.claude/hooks/pre-commit.sh" "$GIT_HOOKS_DIR/pre-commit"
chmod +x "$GIT_HOOKS_DIR/pre-commit"
git config --global core.hooksPath "$GIT_HOOKS_DIR"
echo "      Done."

# --------------------------------------------------------------
# Done
# --------------------------------------------------------------
echo ""
echo "======================================"
echo " Setup Complete!"
echo "======================================"
echo ""
echo " What was installed:"
echo "   ~/.claude/hooks/secret_scan.js        → blocks secrets on Write/Edit"
echo "   ~/.claude/hooks/block-scan-project.py → blocks full project scans"
echo "   ~/.claude/agents/  (8 agents)         → available in all projects"
echo "   ~/.claude/skills/  (6 skills)         → available in all projects"
echo "   ~/.git-hooks/pre-commit               → secret scan on every git commit"
echo "   ~/.claude/settings.json               → hooks config added"
echo ""
echo " IMPORTANT — Add these to your ~/.bashrc or ~/.zshrc:"
echo "   export GITHUB_TOKEN=your_github_token"
echo "   export ADO_MCP_AUTH_TOKEN=your_ado_pat"
echo "   export TR_CODE_SCAN_BINARY=/path/to/scanner"
echo ""
echo " Then open ANY project and run: claude"
echo " No .claude/ copying needed ever again."
echo ""
