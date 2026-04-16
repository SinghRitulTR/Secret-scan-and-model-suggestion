# AI-Powered Feature Development Workflow with Intelligent Model Routing

## Brief Description

This project automates the entire software feature delivery lifecycle — from reading an Azure DevOps story to opening a reviewed, tested, and scanned Pull Request on GitHub — using Claude AI agents as the development engine.

A developer types one command: `/task 234314`. The system reads the story, understands it, asks for confirmation, picks the right AI model for each step, writes code, writes tests, scans for secrets and vulnerabilities, builds the project, reviews the code, and opens a PR — all without any manual steps in between.

The key idea is that **not every step needs the same AI model**. Running a build check is a mechanical task — it just executes a command and reads the output. Writing a complex implementation plan for a multi-system feature requires deep reasoning. Treating them the same wastes money. This system classifies every phase as either **mechanical** (always uses the cheapest model, Haiku) or **cognitive** (uses the right model based on complexity and learned history), saving up to 75% compared to running everything at the highest model tier.

The system also **learns over time**. Every run is logged. After enough runs, it stops using static defaults and starts picking models based on actual performance data — automatically promoting cheaper models when they consistently deliver high-quality output, and upgrading when they don't.

---

## What Is This?

This project is a **fully automated feature development pipeline** built on top of Claude Code. When a developer types `/task 234314` (an ADO story number), the system:

1. Fetches the story from Azure DevOps
2. Assesses the complexity of the work
3. Selects the right AI model for each development phase (not always the most expensive one)
4. Plans → Implements → Tests → Security-scans → Builds → Reviews → Commits → Creates a PR
5. Learns from every run to make better model decisions next time

The central innovation is **Intelligent Model Routing** — the system does not blindly use the same AI model for every task. It routes cheaper models (Haiku) to simple or mechanical tasks and reserves more capable (expensive) models (Sonnet, Opus) for complex reasoning phases, saving significant cost without sacrificing quality.

---

## Table of Contents

1. [Quick Setup](#1-quick-setup)
2. [System Architecture](#2-system-architecture)
3. [Mechanical vs Cognitive Phases](#3-mechanical-vs-cognitive-phases)
4. [How the ADO Story Is Read and Summarized](#4-how-the-ado-story-is-read-and-summarized)
5. [The /task Workflow — All 10 Phases](#5-the-task-workflow--all-10-phases)
6. [Intelligent Model Routing](#6-intelligent-model-routing)
7. [The Three Learning Stages](#7-the-three-learning-stages)
8. [Confidence Evaluation — The Quality Gate](#8-confidence-evaluation--the-quality-gate)
9. [Cost & Token Estimation](#9-cost--token-estimation)
10. [All Agents Explained](#10-all-agents-explained)
11. [All Skills Explained](#11-all-skills-explained)
12. [Security — Secret Scanning Layers](#12-security--secret-scanning-layers)
13. [Configuration Files](#13-configuration-files)
14. [Data Files — The Learning Loop](#14-data-files--the-learning-loop)
15. [How Everything Connects](#15-how-everything-connects)
16. [Usage Guide](#16-usage-guide)

---

## 1. Quick Setup

> Run this **once per machine**. After setup, every repo on your machine gets all hooks, agents, and skills automatically — no `.claude/` copying needed.

### Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| [Claude Code](https://claude.ai/code) | The AI engine that runs all workflows | Required |
| [Node.js](https://nodejs.org) v16+ | Runs `secret_scan.js` hook | Required |
| Python 3.8+ | Runs `block-scan-project.py` hook | Required |
| [TruffleHog](https://github.com/trufflesecurity/trufflehog/releases) | Secret detection in pre-commit and Phase 6 | Recommended |
| Git | Version control | Required |

### Step 1 — Clone the repo

```bash
git clone <repo-url>
cd automatedpr
```

### Step 2 — Run the setup script

```bash
bash .claude/scripts/setup.sh
```

By default this installs everything. You can also choose what to install:

```bash
bash .claude/scripts/setup.sh --interactive      # menu to pick what you want
bash .claude/scripts/setup.sh --only-hook        # install ONLY the git pre-commit scanner
bash .claude/scripts/setup.sh --skip-agents      # skip agents
bash .claude/scripts/setup.sh --skip-skills      # skip skills
bash .claude/scripts/setup.sh --skip-global-hook # skip git pre-commit hook
```

The script does the following:

```
[0] Checks prerequisites (Node, Python, TruffleHog, Git)
[1] Creates ~/.claude/hooks/, ~/.claude/agents/, ~/.claude/skills/, ~/.git-hooks/
[2] Copies hook scripts → ~/.claude/hooks/
[3] Copies all agents  → ~/.claude/agents/
[4] Copies all skills  → ~/.claude/skills/
[5] Merges hooks into  → ~/.claude/settings.json (never overwrites existing config)
[5b] Installs routing config → ~/.claude/config/
[6] Installs global git pre-commit hook → ~/.git-hooks/pre-commit
    (respects existing core.hooksPath if already set)
[7] Checks environment variables
```

### Step 3 — Set environment variables

Add these to your `~/.bashrc` or `~/.zshrc`:

```bash
export GITHUB_TOKEN=<your GitHub Personal Access Token>
export ADO_MCP_AUTH_TOKEN=<your Azure DevOps PAT>
export TR_CODE_SCAN_BINARY=<path to tr-code-scan binary>
```

Then reload:

```bash
source ~/.bashrc
```

### Step 4 — Open any project with Claude Code

```bash
cd /path/to/any-repo
claude
```

All skills, agents, and hooks are now active globally. No setup needed per project.

### Re-running after updates

Pull the latest from `master` and re-run the same script — it updates all installed files with the latest versions:

```bash
git pull origin master
bash .claude/scripts/setup.sh
```

---

### What Gets Installed Where

```
~/.claude/
├── hooks/
│   ├── secret_scan.js           ← fires on every Write/Edit inside Claude
│   ├── block-scan-project.py   ← blocks scan_project MCP tool
│   └── block-git-add.py        ← blocks broad git add . / git add -A
├── agents/
│   ├── implementation-planner.md
│   ├── implementation-executor.md
│   ├── build-verifier.md
│   ├── code-reviewer.md
│   ├── preflight-build-check.md
│   ├── secret-exposure-scanner.md
│   ├── security-scanner.md
│   ├── unit-test-generator.md
│   ├── adaptive-router.md
│   └── confidence-evaluator.md
├── skills/
│   ├── task/SKILL.md            ← /task
│   ├── gh-cmt-pr/SKILL.md       ← /gh-cmt-pr
│   ├── repo-secret-audit/SKILL.md ← /repo-secret-audit
│   ├── pr-review-fix/SKILL.md   ← /pr-review-fix
│   ├── task-review/SKILL.md     ← /task-review
│   └── suggest-model/SKILL.md   ← /suggest-model
└── settings.json                ← hooks config (merged, not overwritten)

~/.git-hooks/
└── pre-commit                   ← secret scan on every git commit in every repo
```

---

## 1. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        ENTRY POINTS                                  │
│                                                                      │
│   /task 234314          /suggest-model "add login"    /adaptive-query│
│   (full workflow)       (cost preview)                (routing test) │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    ROUTING INTELLIGENCE LAYER                        │
│                                                                      │
│  adaptive-router ──reads──► phase-floors.json                        │
│       │                     model-routing.json                       │
│       │                     routing-log.jsonl  (history)             │
│       │                     stats-cache.json   (aggregates)          │
│       │                     embeddings-cache.jsonl (semantic)        │
│       │                     settings.json      (overrides)           │
│       │                                                              │
│       └──outputs──► ROUTING_TABLE (which model per phase)            │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    COGNITIVE PHASE AGENTS                            │
│                                                                      │
│  implementation-planner  →  confidence-evaluator  →  escalate?      │
│  implementation-executor →  confidence-evaluator  →  escalate?      │
│  unit-test-generator     →  confidence-evaluator  →  (log only)     │
│  security-scanner        →  confidence-evaluator  →  (log only)     │
│  build-verifier          →  confidence-evaluator  →  (log only)     │
│  code-reviewer           (via /task-review skill)                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    MECHANICAL PHASE AGENTS                           │
│  (always haiku — fixed overhead, no routing needed)                  │
│                                                                      │
│  preflight-build-check   secret-exposure-scanner   gh-cmt-pr        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    FEEDBACK LOOP                                     │
│                                                                      │
│  routing-log.jsonl ──rebuild──► stats-cache.json                    │
│  /routing-review ──writes──► settings.json model_overrides          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. The /task Workflow — All 10 Phases

### How to Start

```
/task 234314
```

All 10 phases are created as tasks upfront so you can track progress in real time. Each phase is set to `in_progress` when it starts and `completed` when it finishes. If the workflow stops early, all remaining phases are marked `deleted`.

---

### Phase 1 — Story Retrieval & Setup

This is the most important setup phase. It does five things:

**1a — Create Phase Roadmap**
Creates all 10 tasks upfront so progress is visible from the start.

**1b — Fetch Story from ADO**
Pulls the user story from Azure DevOps using `mcp__ado__wit_get_work_item`. Displays: Story ID, Title, Description, Acceptance Criteria. Then asks you to confirm the understanding in plain English before proceeding. If your intent is different from what the story says, you clarify here before any code is written.

**1c — Story Type Classification**
Classifies the story as: `FEATURE`, `BUG`, `REFACTOR`, or `CHORE`.

- **FEATURE / BUG** → Full 10-phase workflow
- **REFACTOR** → Asks if you want to skip the security scan
- **CHORE** → Offers Fast Track mode (skips preflight, tests, security)

**1d — Routing Table Construction**
This is where the intelligence kicks in. See [Section 3](#3-intelligent-model-routing) for full details. The output is a routing matrix like:

```
Routing Matrix for AB#234314 (Complexity: MEDIUM)

Phase                  Model     Stage        Floor
──────────────────────────────────────────────────────
Phase 3: Preflight     haiku     mechanical   haiku
Phase 4: Planning      sonnet    COLD_START   sonnet
Phase 5: Implementation sonnet   COLD_START   sonnet
Phase 6: Secret Scan   haiku     mechanical   haiku
Phase 7a: Tests        sonnet    COLD_START   sonnet
Phase 7b: Security     sonnet    COLD_START   sonnet
Phase 8: Build Verify  haiku     COLD_START   haiku
Phase 9: Code Review   sonnet    COLD_START   sonnet
Phase 10: Commit/PR    haiku     mechanical   haiku

Confidence threshold:  70/100 (escalate if below)
Escalation path:       haiku → sonnet → opus
```

You can override to "all Opus", "all Sonnet", "all Haiku", or use the intelligent routing.

**1e — Blended Cost Estimate**
Before spending anything, the system shows you a cost prediction:

```
┌─────────────────────────────────────────────────────┐
│           TOKEN & COST PREDICTION                    │
└─────────────────────────────────────────────────────┘
  Complexity:          MEDIUM
  Estimated cost:      ~$0.64  (intelligent routing)
  vs. all-Opus:        ~$2.52  (estimated savings: 75%)
```

You can cancel here if the cost is too high.

---

### Phase 2 — Branch Creation

Creates the feature branch named `AB#<story-number>` from main. If the branch already exists, it switches to it and rebases on main. Checks for uncommitted local changes first and warns you before doing anything destructive.

---

### Phase 3 — Pre-flight Build Check

Before writing any code, runs the existing project build to capture what errors already existed. These are stored as `PRE_EXISTING_ERRORS` so the build-verifier in Phase 8 does not try to fix problems it didn't cause.

This phase always uses **Haiku** (fast, cheap — just running a command and reading output).

---

### Phase 4 — Implementation Planning

**Delegates to the `implementation-planner` sub-agent** (never plans inline — keeps main context clean).

The planner:
- Reads the codebase to understand patterns
- Produces a detailed plan: which files to create/modify, function signatures, dependencies, risks
- Returns the plan for you to review

This phase is **interactive** — you can ask questions, request changes, and the same sub-agent is resumed with your feedback until you say "looks good". Only then does it proceed.

After you approve:
- A **confidence evaluator** scores the plan quality (0–100)
- If score < 70, the planner is re-run at a higher model tier
- The plan is examined for **codebase scope signals** that might require upgrading the complexity tier (see below)

**Mid-workflow complexity upgrade:**

| Signal | Threshold | Reason |
|--------|-----------|--------|
| Files in plan | > 8 | More files = wider blast radius |
| Components touched | > 3 | Cross-component ripple effects |
| Security-related | true | Auth/payment/encryption — never underestimate |
| Estimated lines | > 500 | Large change needs more careful reasoning |

If any signal triggers, complexity is upgraded (e.g., MEDIUM → HIGH) and the routing table for phases 5–9 is recalculated with the higher tier.

---

### Phase 5 — Implementation

**Delegates to the `implementation-executor` sub-agent** with the full approved plan.

The executor:
- Creates and modifies files according to the plan
- Checks for drift (when the real codebase differs from what the plan assumed)
- Re-reads files after writing to verify correctness
- Returns a summary of all files created and modified

After implementation:
- Confidence evaluator scores the output
- If score < 70, implementation is re-run at the next model tier
- If files outside the plan were modified, an **ad-hoc investigation agent** is spawned automatically to determine if the unexpected modification should be reverted
- Routing result is logged to `routing-log.jsonl`

---

### Phase 6 — Secret Exposure Check

Before running any tests or scans, checks that no secrets (API keys, tokens, passwords) were accidentally committed.

Uses `secret-exposure-scanner` (always Haiku) which:
- Runs TruffleHog on changed files
- Scans `.env` files
- Checks git diff for credential patterns

**Three possible outcomes:**
- **PASS** — no secrets, proceed automatically
- **REVIEW_REQUIRED** — possible false positives, asks you to confirm
- **BLOCKED** — real secrets found, workflow cannot continue until fixed

---

### Phase 7 — Tests & Security Scan (Parallel)

Both sub-agents are spawned **in a single message** so they run in parallel:

**Unit Test Generator:**
- Discovers the project's test framework (pytest, jest, etc.) and naming conventions
- Creates minimum 3 tests per public method: happy path, error case, edge case
- Follows existing patterns exactly

**Security Scanner:**
- Uses the `mcp__tr-code-scan-mcp` MCP tools to scan changed files
- Groups vulnerabilities by type (SQL injection, XSS, etc.)
- Fetches fix patterns and applies them
- Re-scans to verify fixes

Confidence scores are logged for both but escalation is not triggered in Phase 7 (parallel agents, results accepted as-is, data improves routing over time).

---

### Phase 8 — Build Verification

Spawns `build-verifier` which:
- Auto-detects the build system (gradle/maven/npm/pip/cargo)
- Runs the build
- If it fails, diagnoses the error, applies a fix, and retries — up to 3 times
- Pre-existing errors (from Phase 3) are excluded from "things to fix"

If build fails after 3 attempts, an **ad-hoc root-cause agent** is spawned automatically to diagnose why and suggest a targeted fix.

The routing log records whether the build passed or failed, and back-populates the Phase 5 implementation log entry with `downstream_build_failed: true` if it failed.

---

### Phase 9 — Code Review

Invokes the `/task-review` skill which spawns `code-reviewer` with:
- The story context
- The approved plan summary
- The full git diff

The reviewer categorizes findings as:
- **MUST_FIX** — bugs, security holes, broken patterns
- **SHOULD_FIX** — non-critical issues
- **SUGGESTION** — optional improvements

This phase is **interactive with up to 2 fix cycles**: you select which MUST_FIX items to address, the reviewer applies fixes and re-reviews, then you decide on remaining items.

**Verdict**: `APPROVED` (no MUST_FIX remaining) or `CHANGES_REQUESTED`.

---

### Phase 10 — Commit and PR

Invokes the `/gh-cmt-pr` skill which:
1. Checks you are not on main/master
2. Detects the GitHub repo from `git remote`
3. Stages specific files (never `git add .` — avoids accidental secret staging)
4. Creates a commit
5. Pushes the branch
6. Checks if a PR already exists (skips creation if so)
7. Creates a **Draft PR** with title format: `AB#<story>: <description>`
8. Adds GitHub Copilot as reviewer
9. Assigns the PR to you
10. Applies 'AI Generated' label

After the PR is created, the PR number is written back to all routing log entries for this run.

---

### Completion Summary

After all phases, the system displays:
- Files created/modified counts
- Test file and method counts
- Build result
- Security scan result
- Code review verdict
- PR URL
- A **routing summary table** showing which model was used per phase, confidence score, and whether escalation happened
- Session stats (phases completed, agents spawned, escalation count)
- Rebuilds `stats-cache.json` from the new routing log entries

---

## 3. Intelligent Model Routing

### The Problem It Solves

Running every phase at Opus-level costs ~$2.50 per feature. Most phases don't need that power. A preflight build check is running a command and reading output — Haiku does that perfectly well. A security scan is pattern matching — Sonnet handles it. Only complex planning with ambiguous requirements and multi-system implementation truly benefits from Opus.

The routing system assigns models by answering: *"What is the minimum model that will produce confident, high-quality output for this specific phase at this complexity level?"*

### Two Configuration Files Drive This

**`phase-floors.json`** — Hard minimum model per phase. The routing system can never go below these.

```json
{
  "floors": {
    "implementation-planner":  "sonnet",
    "implementation-executor": { "LOW": "haiku", "MEDIUM": "sonnet", "HIGH": "sonnet" },
    "unit-test-generator":     "sonnet",
    "security-scanner":        "sonnet",
    "build-verifier":          "haiku",
    "code-reviewer":           "sonnet"
  },
  "mechanical_phases": ["preflight-build-check", "secret-exposure-scanner", "gh-cmt-pr"]
}
```

**`model-routing.json`** — Starting model presets by complexity, plus learning thresholds.

```json
{
  "routing": {
    "implementation-planner":  { "LOW": "sonnet", "MEDIUM": "sonnet", "HIGH": "opus" },
    "implementation-executor": { "LOW": "haiku",  "MEDIUM": "sonnet", "HIGH": "opus" },
    "build-verifier":          { "LOW": "haiku",  "MEDIUM": "haiku",  "HIGH": "sonnet" },
    "code-reviewer":           { "LOW": "sonnet", "MEDIUM": "sonnet", "HIGH": "opus" }
  },
  "confidence_threshold": 70,
  "learning": {
    "cold_start_threshold": 20,
    "mature_threshold": 100,
    "min_success_rate": 0.75,
    "min_confidence_score": 70
  }
}
```

### Complexity Assessment

Before building the routing table, the system assesses story complexity — not by keyword matching but by reasoning:

- How many systems does this touch?
- How many distinct acceptance criteria?
- Is there ambiguity or missing detail?
- Are there security/auth implications?
- How many story points (if present)?

Output is **LOW**, **MEDIUM**, or **HIGH**.

Then the routing table maps each phase to its starting model based on that complexity.

### Manual Override

You can override routing in three ways:

1. **At runtime** — when `/task` shows the routing matrix, choose "Override: all Opus/Sonnet/Haiku"
2. **Via settings.json** — add `model_overrides` to always use a specific model for a phase
3. **Via /routing-review** — automatically writes data-driven overrides to `settings.json`

---

## 4. The Three Learning Stages

The routing system becomes more accurate as it accumulates run history. Each phase independently progresses through three stages based on how many times it has been run at that complexity level.

### Stage 1: COLD_START (0–19 runs)

Uses the static defaults from `model-routing.json`. No history = no learning. Safe but not optimized.

### Stage 2: LEARNING (20–99 runs)

Reads `stats-cache.json` which contains aggregated statistics per (phase, complexity) group.

For each candidate model in cost order (haiku → sonnet → opus), computes:

```
score = avg_confidence × success_rate
```

With a recency boost: if the last 10 runs for a model have higher average confidence than the overall average, the score gets a 10% boost (recent performance matters more than old data).

**Picks the cheapest model** where:
- `score ≥ 70`
- `success_rate ≥ 0.75`
- Model is at or above the phase floor

If no model passes both thresholds, falls back to the floor model.

### Stage 3: MATURE (100+ runs)

Uses `embeddings-cache.jsonl` for **semantic similarity matching**.

Finds the 5 most similar past queries to the current one by counting shared significant words between the new query and stored query summaries.

Uses the most common model that succeeded for those 5 similar past queries.

This is the most intelligent stage — it adapts routing based on the *type* of work being asked, not just the phase name.

---

## 5. Confidence Evaluation — The Quality Gate

### What It Is

After every cognitive phase (planning, implementation, tests, security, build, code review), a `confidence-evaluator` sub-agent scores the output quality from 0 to 100.

**Critically: the evaluator does not know which model produced the answer.** It sees only the original query and the answer. This prevents it from being biased by model tier.

### How Scoring Works

Start at 100 and deduct:

| Issue | Deduction |
|-------|-----------|
| Each requirement/question in query not addressed | −15 |
| Answer is generic, not specific to context | −10 |
| Hedging phrase found ("might", "probably", "could be", "I think", "possibly", "perhaps", "not sure", "may need to") | −8 each |
| Unstated assumption not supported by query | −10 each |
| Answer contradicts itself | −20 |
| Answer is incomplete or cuts off | −15 |

Floor is 0. Score cannot go negative.

### What Happens Based on Score

**Score ≥ 70:** Output accepted. Routing decision was correct. Logged as success.

**Score < 70:** Escalation triggered:
- haiku → escalate to sonnet
- sonnet → escalate to opus
- opus → accept as-is with LOW_CONFIDENCE flag (no higher tier available)

The phase agent is re-spawned at the escalation model, the evaluator re-runs, and the new score is logged.

**Note:** Phase 7 (tests + security) does NOT escalate. Both agents run in parallel and results are accepted as-is. Confidence scores are still logged to improve future routing decisions.

### Why This Matters

Without the confidence gate, if a LOW complexity task was routed to Haiku and Haiku produced a weak plan, the implementation would be based on a weak plan. The confidence gate catches this automatically and escalates before the downstream phases inherit the problem.

---

## 6. Cost & Token Estimation

### Where It Shows Up

1. **`/suggest-model "description"`** — before running `/task`, preview cost
2. **Phase 1e of `/task`** — before any work starts, confirm the budget

### How Tokens Are Estimated

#### Input Tokens (per phase)
```
input_tokens = (story_description_chars ÷ 4)   ← story context
             + 800                              ← fixed agent system prompt overhead
             + prior_phase_outputs              ← cumulative context passed forward
```

Prior phase outputs grow each phase (context is passed forward):
- Planning: no prior context
- Implementation: gets plan output (~1,200 tokens)
- Tests: gets plan + implementation (~4,700 tokens)
- Build: gets implementation + tests (~5,300 tokens)
- Code Review: gets implementation + tests + build (~5,700 tokens)

#### Output Tokens (cold start defaults)

| Phase | LOW | MEDIUM | HIGH |
|-------|-----|--------|------|
| Planning | 800 | 1,200 | 2,000 |
| Implementation | 2,500 | 4,000 | 6,500 |
| Tests | 1,200 | 2,000 | 3,000 |
| Security | 600 | 900 | 1,200 |
| Build Verify | 300 | 400 | 600 |
| Code Review | 700 | 1,100 | 1,800 |

After 10+ runs, actual historical averages from `routing-log.jsonl` replace these defaults, improving accuracy by ~40%.

#### Pricing Applied
```
haiku:  $0.80/M input tokens,  $4.00/M output tokens
sonnet: $3.00/M input tokens,  $15.00/M output tokens
opus:   $15.00/M input tokens, $75.00/M output tokens
```

#### Confidence Evaluator Cost (added for each cognitive phase)
```
eval_input  = phase_output_tokens + 400 (fixed evaluator prompt)
eval_output = ~150 tokens (small JSON response)
eval_model  = haiku
eval_cost   = ((eval_input/1M) × $0.80) + ((150/1M) × $4.00)
```
6 evaluator calls per run total.

#### Escalation Cost (expected value)
```
escalation_cost = escalation_rate × (output_tokens × next_tier_output_price_per_token)
```
Default escalation rate: 15% (until real history exists).

#### `/task` Blended Rates (simplified display)
```
opus:   $10/M tokens (blended)
sonnet: $6/M tokens  (blended)
haiku:  $2/M tokens  (blended)
```

---

## 7. All Agents Explained

### `adaptive-router`
**Model:** Haiku (the routing decision itself is cheap)

Reads config files and routing history to decide which Claude model to use for a given phase and complexity. Returns a JSON decision with the chosen model ID, routing stage, floor constraint, and one-sentence reasoning. Always runs on Haiku because choosing which model to use is a structured lookup task, not a reasoning task.

---

### `confidence-evaluator`
**Model:** Haiku (evaluation is pattern matching, not reasoning)

Receives only: the original query, and the answer produced by another agent. Scores 0–100 using the deduction rubric. Does not know which model produced the answer. Returns JSON: `{ score, flags[], reasoning }`.

---

### `query-executor`
**Model:** Determined by adaptive-router

General-purpose answer agent used by `/adaptive-query` to test the routing pipeline. Answers the query as completely and concretely as possible. Used for testing only, not in the main `/task` workflow.

---

### `implementation-planner`
**Model:** From ROUTING_TABLE (floor: sonnet)

Read-only exploration agent. Reads the codebase to understand existing patterns, then produces a detailed implementation plan: files to create/modify, function signatures, dependencies, edge cases, and risks. Does NOT write any files.

---

### `implementation-executor`
**Model:** From ROUTING_TABLE (floor: haiku/sonnet depending on complexity)

Creates and modifies files according to the approved plan. Reads existing files before modifying them. Checks for drift (real codebase differs from plan assumptions). Re-reads files after writing to verify correctness. Returns a summary of all files touched.

---

### `unit-test-generator`
**Model:** From ROUTING_TABLE (floor: sonnet)

Discovers the project's test framework, assertion style, naming conventions, and file organization by reading existing tests. Creates minimum 3 tests per public method: happy path, error/exception, edge case. Follows existing patterns exactly — consistency over preference.

---

### `security-scanner`
**Model:** From ROUTING_TABLE (floor: sonnet)

Uses MCP `mcp__tr-code-scan-mcp__scan_files` to scan changed files. Groups vulnerabilities by type (SQL injection, XSS, path traversal, etc.) and severity (CRITICAL → HIGH → MEDIUM). Fetches fix patterns from the MCP knowledge base. Applies fixes and re-scans to verify. Reports vulnerabilities found and fixed.

---

### `build-verifier`
**Model:** From ROUTING_TABLE (floor: haiku)

Auto-detects the build system (gradle/maven/npm/pip/cargo/etc.) and runs the build. If it fails, diagnoses the error, applies a targeted fix, and retries — up to 3 attempts. Pre-existing errors (from Phase 3) are not touched. Reports PASS or FAIL with error counts.

---

### `code-reviewer`
**Model:** From ROUTING_TABLE (floor: sonnet)

Runs in two modes:

**REVIEW mode:** Analyzes the full git diff against the approved plan. Flags issues in three tiers: MUST_FIX (bugs, security holes, broken patterns), SHOULD_FIX (non-critical), SUGGESTION (optional). Returns verdict: APPROVED (no MUST_FIX) or CHANGES_REQUESTED.

**FIX_AND_REREVIEW mode:** Applies approved fixes from the review, then re-reviews only the modified files.

---

### `secret-exposure-scanner`
**Model:** Always Haiku (mechanical phase)

Runs TruffleHog on changed files via PowerShell script. Scans `.env` files on disk and git diff. Returns one of: PASS, REVIEW_REQUIRED, BLOCKED, or ERROR, plus masked finding details.

---

### `preflight-build-check`
**Model:** Always Haiku (mechanical phase)

Read-only diagnostic. Runs the project build before any changes are made. Reports PASS or FAIL with error list. Does NOT fix anything — its only job is to record what was already broken before any code was written.

---

## 8. All Skills Explained

Skills are high-level workflows invoked by the user via slash commands.

### `/task [story-number]`

The main entry point. Runs the full 10-phase feature development lifecycle described in Section 2. Integrates all agents, all routing, all quality gates into a single automated workflow.

---

### `/suggest-model [description]`

**With a description:** Assesses complexity, reads routing config and history, predicts tokens per phase, applies pricing, and displays a full routing matrix with line-item cost estimates including evaluator calls and escalation risk.

**Without arguments:** Shows the current routing system status — total runs logged, per-phase performance (average confidence, escalation rate, average token count), routing stages currently active, and cost efficiency vs. all-Opus baseline.

---

### `/adaptive-query [query]`

Standalone test of the routing pipeline without running a full feature workflow. Routes a single query through: classify → route → execute → evaluate → escalate if needed → log → display result.

Use this to:
- Test that routing is working correctly
- Warm up the routing log before running real tasks
- Validate escalation behavior

Each run logs to `routing-log.jsonl` and rebuilds `stats-cache.json` so it contributes to the learning loop.

---

### `/routing-review`

Analyzes the full routing history and applies 5 data-driven rules:

| Rule | Trigger | Action |
|------|---------|--------|
| Escalation rate too high | > 30% for a phase+complexity | Upgrade that phase's default model |
| Downstream build failures | > 30% builds failing after implementation | Upgrade implementation model |
| Token count too low | < 400 avg tokens consistently | Downgrade opportunity |
| User revision rate high | > 20% of runs needed revision | Upgrade model |
| PR review comments high | > 5 avg comments (HIGH complexity) | Upgrade code-reviewer model |

Shows recommendations and asks which to apply. Approved changes are written to `settings.json` as `model_overrides`, which the routing system respects on all future runs.

Intended to be run every 20–30 tasks as the system accumulates data.

---

### `/task-review [story | model]`

Invoked by `/task` in Phase 9 but can also be run standalone to review any code changes against a story.

- Spawns `code-reviewer` with story context
- Supports up to 2 iterative fix cycles
- Returns final verdict: APPROVED or CHANGES_REQUESTED with counts

---

### `/gh-cmt-pr [story: description]`

Invoked by `/task` in Phase 10 but can also be run standalone to commit and create a PR.

- Verifies you are not on main/master
- Shows you exactly what will be staged (excludes: `.env`, credentials, build output, IDE dirs, `.claude/` directory)
- Asks for confirmation before staging
- Creates a commit with specific file names (never `git add .`)
- Creates a Draft PR with Copilot as reviewer
- Assigns the PR to the current GitHub user
- Applies 'AI Generated' label

---

### `/repo-secret-audit [scope]`

Comprehensive secret scan of the repository. Scope options: `diff` (changes since main), `full` (current state), `history` (full git history — slowest).

Runs TruffleHog plus supplemental grep-based searches for:
- Key/secret/token/password assignments (including commented lines)
- 32-char hex values
- High-entropy base64 strings (40+ chars)
- Webhook/callback URLs with embedded credentials
- `user:pass@host` patterns in URLs

Checks risky file types: `.env`, `.pem`, `.key`, `.p12`, `.pfx`, `.jks`, and files named `credentials`, `secrets`, `id_rsa`, etc.

---

### `/pr-review-fix [PR reference]`

Fetches review comments from a GitHub PR and applies approved fixes.

1. Loads all open review threads
2. Categorizes each comment: ACTIONABLE, AMBIGUOUS, QUESTION, NITPICK, FILE_DELETE, INVALID
3. Presents the full analysis
4. Resolves AMBIGUOUS comments by asking you
5. Requires explicit confirmation for FILE_DELETE operations
6. Applies fixes to specific files (grouped by file)
7. Shows NITPICKs separately and lets you choose which to fix
8. Does NOT commit or push — you do that after reviewing the changes

---

## 9. Security — Secret Scanning Layers

The system has **three independent layers** of secret protection. A secret has to get past all three to ever reach a remote:

```
Layer 1 — Write/Edit Hook (Claude Code)
  secret_scan.js fires before every file write inside Claude.
  Blocks the write entirely if a secret pattern is found.

Layer 2 — Phase 6: Secret Exposure Check (during /task)
  secret-exposure-scanner agent runs TruffleHog on all changed files.
  Blocks the workflow with BLOCKED status. Cannot proceed until fixed.

Layer 3 — Git Pre-commit Hook (every git commit, every repo)
  pre-commit runs regex scan + TruffleHog before the commit is recorded.
  Blocks the commit entirely.
```

### Layer 1 — `secret_scan.js`

Fires automatically on every `Write` or `Edit` tool call inside Claude Code.

Patterns covered (BLOCK — write is denied):
- AWS access/secret keys (`AKIA...`, `aws_secret_access_key`)
- GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghr_`, `github_pat_`)
- OpenAI keys (`sk-...`)
- Anthropic keys (`sk-ant-...`)
- Stripe live/test keys (`sk_live_`, `sk_test_`)
- HuggingFace tokens (`hf_...`)
- npm tokens (`npm_...`)
- SendGrid keys (`SG....`)
- Slack tokens and webhooks (`xox...`)
- Private keys (RSA, EC, DSA, OpenSSH)
- Bearer tokens in Authorization headers
- Connection strings with embedded passwords (MongoDB, PostgreSQL, Redis)
- URLs with embedded credentials (`user:pass@host`)

Patterns covered (REVIEW — write is allowed with a warning):
- Generic `password = "..."` assignments
- Generic `secret = "..."` / `token = "..."` assignments

Smart false-positive exclusions: test files, fixtures, mocks, placeholder values (`changeme`, `dummy`, `example`, `xxx`) are never blocked.

### Layer 2 — `secret-exposure-scanner` agent (Phase 6 of `/task`)

Runs automatically during the `/task` workflow after implementation:

1. Runs TruffleHog `--only-verified` on all changed files
2. Scans `.env*` files on disk even if not committed
3. Greps `git diff origin/main` for credential patterns

Returns one of:
- `SECRET_SCAN: PASS` — proceed automatically
- `SECRET_SCAN: REVIEW_REQUIRED` — possible false positives, asks you
- `SECRET_SCAN: BLOCKED` — real verified secret, workflow stops

### Layer 3 — Git Pre-commit Hook

Installed globally by `setup.sh`. Runs on every `git commit` in every repo.

Two stages:
1. **Regex scan** — greps every staged file for known secret formats
2. **TruffleHog** — runs filesystem scan on the whole repo

Blocks the commit with a clear error message if either stage fires.

### Standalone Audit — `/repo-secret-audit`

Run at any time to audit the full repo:

```bash
/repo-secret-audit           # full working tree + full history
/repo-secret-audit diff      # only changes since main (fast)
/repo-secret-audit full      # full working tree only
/repo-secret-audit history   # full git history only (slow)
```

Outputs a structured report with masked findings, risky file detection, and BFG/git filter-branch cleanup instructions if secrets were committed to history.

---

## 10. Configuration Files

### `.claude/config/phase-floors.json`

Hard minimum model constraints per phase. The routing system can upgrade above these but never below. Think of these as safety guarantees: "implementation planning will never run below Sonnet, no matter what the routing algorithm decides."

Also defines which phases are "mechanical" (always Haiku, no routing needed) and the full model ID strings for each model name.

### `.claude/config/model-routing.json`

Starting model presets by phase and complexity. Used by the routing system when history is sparse (COLD_START stage) or as a reference point for what the "expected" model should be. Also defines the learning thresholds: when COLD_START ends (20 runs), when MATURE begins (100 runs), minimum success rate (75%), minimum confidence score (70), recency window (last 10 runs), and recency weight (2×).

### `.claude/settings.json`

Standard Claude Code settings file. Relevant sections for routing:
- `model_overrides` — manually pin specific agents to specific models
- Written by `/routing-review` when data-driven improvements are approved

---

## 10. Data Files — The Learning Loop

### `.claude/data/routing-log.jsonl`

**Append-only.** Every routing decision and outcome is logged here. One JSON object per line.

```json
{
  "timestamp": "2026-04-13T10:23:45Z",
  "run_id": "AB#234314",
  "phase": "implementation",
  "complexity": "MEDIUM",
  "routing_stage": "COLD_START",
  "model_decided": "sonnet",
  "final_model": "sonnet",
  "escalated": false,
  "escalation_count": 0,
  "confidence_score": 87,
  "token_count": 3820,
  "retry_count": 0,
  "downstream_build_failed": false,
  "user_revision_requested": false,
  "pr_number": 42,
  "pr_review_comments": 3
}
```

This file is the source of truth for all learning. Never modified, only appended.

### `.claude/data/stats-cache.json`

Rebuilt after every run. Aggregates `routing-log.jsonl` by `phase_COMPLEXITY` key.

```json
{
  "implementation_MEDIUM": {
    "avg_confidence": 84.3,
    "success_rate": 0.87,
    "entry_count": 23,
    "avg_token_count": 3950
  }
}
```

Used by the LEARNING stage routing algorithm to pick models without re-reading and re-aggregating the full log every time.

### `.claude/data/embeddings-cache.jsonl`

Query history for the MATURE stage. Stores the first 150 characters of each query alongside which model was used and whether it succeeded.

```json
{
  "query_summary": "Add OAuth2 login with Google and GitHub providers to the authentication service",
  "phase": "implementation",
  "complexity": "HIGH",
  "final_model": "opus",
  "success": true
}
```

When a new query comes in at MATURE stage, the system finds the 5 most similar past queries by word overlap and uses the model that worked for them.

---

## 11. How Everything Connects

Here is a trace of what happens when you run `/task 234314`:

```
1. /task fetches story AB#234314 from ADO
   └── Confirms understanding with user

2. Story classified as FEATURE

3. Routing table built:
   ├── Reads model-routing.json (MEDIUM complexity presets)
   ├── Reads phase-floors.json (floor constraints)
   ├── Reads routing-log.jsonl (0 entries → all phases = COLD_START)
   └── Displays routing matrix + cost estimate → user approves

4. Branch AB#234314 created from main

5. preflight-build-check spawned (haiku) → PASS
   └── No pre-existing errors stored

6. implementation-planner spawned (sonnet, COLD_START)
   ├── Returns detailed plan
   ├── User reviews and approves
   ├── confidence-evaluator spawned (haiku) → score: 82
   ├── Score ≥ 70 → no escalation
   ├── Scope check: 5 files, 2 components → no complexity upgrade
   └── Routing log: { phase: "planning", model: "sonnet", confidence: 82, escalated: false }

7. implementation-executor spawned (sonnet, COLD_START)
   ├── Creates 3 files, modifies 2
   ├── confidence-evaluator spawned (haiku) → score: 79
   ├── Score ≥ 70 → no escalation
   └── Routing log: { phase: "implementation", model: "sonnet", confidence: 79, escalated: false }
       → routing-log.jsonl appended

8. secret-exposure-scanner spawned (haiku) → PASS

9. unit-test-generator (sonnet) + security-scanner (sonnet) spawned in parallel
   ├── Tests: 4 test files, 18 methods
   ├── Security: 0 vulnerabilities
   ├── confidence-evaluator × 2 (haiku) → scores: 88, 91
   └── Routing log entries added for both

10. build-verifier spawned (haiku, COLD_START)
    ├── Build: PASS
    └── Routing log: { phase: "build-verify", confidence: 90 }

11. /task-review invoked → code-reviewer spawned (sonnet)
    ├── Finds 2 MUST_FIX, 1 SHOULD_FIX
    ├── User approves fixes
    ├── code-reviewer re-runs in FIX_AND_REREVIEW mode
    └── Verdict: APPROVED

12. /gh-cmt-pr invoked (haiku)
    ├── Stages specific files
    ├── Creates commit
    ├── Pushes branch
    └── Creates Draft PR #42 with Copilot reviewer

13. PR number 42 back-populated into all routing-log entries for AB#234314
    stats-cache.json rebuilt

14. Final summary displayed
    → 6 routing log entries added
    → System now has data toward LEARNING stage for these phases
```

---

## 12. Usage Guide

### First Run (everything is COLD_START)

```bash
# Preview cost and routing before starting
/suggest-model "Add user profile page with avatar upload and bio editing"

# Run the full workflow
/task 234314
```

### Warming Up the Routing System

```bash
# Test routing without running a full task
/adaptive-query "Design a REST API endpoint for user authentication with JWT tokens"
/adaptive-query "Write unit tests for a UserService class with CRUD operations"
/adaptive-query "Review this Python function for security vulnerabilities"
```

After 20+ runs for a phase, it enters LEARNING stage and starts optimizing model selection based on actual performance data.

### Checking Routing Performance

```bash
# See current routing status and per-phase stats
/suggest-model

# Get data-driven improvement recommendations
/routing-review
```

### Reviewing a PR

```bash
# Apply review comments from a PR
/pr-review-fix https://github.com/owner/repo/pull/42

# Or just the PR number (reads git remote for owner/repo)
/pr-review-fix 42
```

### Secret Scanning

```bash
# Scan only changes since main (fastest)
/repo-secret-audit diff

# Scan full repository state
/repo-secret-audit full

# Scan entire git history (thorough but slow)
/repo-secret-audit history
```

---

## Key Design Decisions

**All sub-agents run in foreground.** No `run_in_background: true`. Each phase waits for the previous one. This keeps the main context aware of what each phase produced, enables confidence evaluation, and allows the workflow to react to failures immediately.

**Routing table is built once per story.** The routing decision is made in Phase 1 using the story complexity assessment and locked in. It can be updated if the complexity is upgraded after planning, but it does not change per-agent-invocation mid-workflow.

**The confidence evaluator is always Haiku.** Evaluating quality is a structured scoring task — reading text against a rubric and deducting points. Haiku does this well and cheaply, making the quality gate essentially free to run.

**Floors are never violated.** Even if the LEARNING stage determines Haiku could work for implementation planning at LOW complexity, the floor (sonnet) prevents that. Floors represent human judgment about minimum safe quality levels, and the routing system works within those bounds.

**`routing-log.jsonl` is append-only.** It is the audit trail for all routing decisions. It can be used to understand why a run cost what it did, debug quality issues, and feed the learning algorithm. Never modified in place.

**Commits never use `git add .`** The `/gh-cmt-pr` skill stages files by explicit name and excludes a hardcoded list of sensitive directories (`.env`, credentials, `.claude/`, build output, IDE directories). This prevents accidental secret exposure even if a scan was missed.
