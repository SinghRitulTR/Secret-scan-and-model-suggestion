---
name: task
description: Full feature development lifecycle — fetch ADO story, branch, plan, implement, secret scan, test, build, security scan, code review, commit and PR
argument-hint: "[story-number]"
allowed-tools: Bash, Read, Glob, Grep, Edit, Write, Agent, AskUserQuestion, Skill, TaskCreate, TaskGet, TaskList, TaskUpdate, mcp__ado__wit_get_work_item, mcp__github__create_pull_request, mcp__github__get_me, mcp__tr-code-scan-mcp__scan_files, mcp__tr-code-scan-mcp__scan_code
---

You are executing a full feature development lifecycle. This is an interactive, multi-phase workflow.

**CRITICAL RULES:**
- You MUST NOT skip any phase unless the user explicitly asks to skip it
- If anything fails, diagnose the issue and ask the user how to proceed
- **Sub-agents**: NEVER use `run_in_background: true`. All sub-agents run in foreground.
- **Model selection**: When a phase specifies `model: \`<name>\``, pass it as the `model` parameter to the Agent tool. If no model is specified, omit the parameter to inherit the parent session's model.
- **Phase transitions**: Use `TaskUpdate` to set the current phase to `completed`, then set the next phase to `in_progress`.
- **Early stop**: If the workflow terminates before completing all phases, mark all remaining `pending` phase tasks as `deleted`.

The user story number is: $ARGUMENTS

---

## Ad-hoc Agent Protocol

Sub-agents may be spawned at any point to investigate a focused concern without exiting the current phase. **User-initiated**: detect intent phrases ("investigate", "check", "look into", "spawn an agent", "analyse", "dig into", "explore", "figure out why", etc.), then spawn and present findings. **Auto-triggered**: spawn immediately (no prompt) for the triggers below. After spawning: announce the trigger, wait for findings, fold results into current phase, resume. Provide the agent with: Goal, Story identifier, current phase, relevant files, error/anomaly. Agent returns: root cause, recommended action. Do NOT use `run_in_background: true`.

| Trigger | Detected in | Auto-spawn goal |
|---------|-------------|-----------------|
| `git diff --name-only` lists a file **not in the approved plan** | Phase 5 (after implementation) | Identify why the unexpected file was modified and whether it should be reverted |
| Build-verifier returns failure **after all 3 attempts**, error not in PRE_EXISTING_ERRORS | Phase 8 (after build-verifier gives up) | Diagnose root cause and suggest a targeted fix |
| Security scanner flags a file **outside the implementation scope** | Phase 7 (after security-scanner returns) | Determine whether the finding is a false positive or a real indirect risk |

---

## Phase 1: Story Retrieval

### 1a: Create Phase Roadmap

Use `TaskCreate` to create all 10 phase tasks (all start as `pending`; set Phase 1 to `in_progress` immediately):
1. Phase 1: Story Retrieval
2. Phase 2: Branch Creation
3. Phase 3: Pre-flight Build Check
4. Phase 4: Implementation Planning
5. Phase 5: Implementation
6. Phase 6: Secret Exposure Check
7. Phase 7: Tests & Security Scan
8. Phase 8: Build Verification
9. Phase 9: Code Review
10. Phase 10: Commit and PR

### 1b: Fetch Story

**If no story number was provided** (i.e., `$ARGUMENTS` is empty or blank), use `AskUserQuestion` to ask:
**"Please provide the ADO user story number (e.g., 234314)."**
**STOP and WAIT** for the user to provide the story number before continuing.

Once you have the story number, use `mcp__ado__wit_get_work_item` to fetch the user story details with:
- **project**: Read CLAUDE.md to identify the ADO project name. If unclear, ask the user.
- **id**: the story number

Extract and display a formatted summary:
- **Story ID**: AB#<number>
- **Title**: <title>
- **Description**: <description>
- **Acceptance Criteria**: <acceptance criteria>

### 1c: Story-Type Classification

Analyze the story title and description to classify it into one of:
- **FEATURE** — new functionality, new endpoint, new service, new integration
- **BUG** — defect fix, error correction, unexpected behavior fix
- **REFACTOR** — code restructuring, cleanup, no new functionality
- **CHORE** — dependency updates, config changes, documentation, CI/CD

Output: `Story classified as **<TYPE>**`

Then, based on the classification, offer workflow adjustments:

**If FEATURE**: No adjustment. Full 9-phase workflow.

**If BUG**: No adjustment. Full 9-phase workflow (bug fixes need both tests and security scan).

**If REFACTOR**:
Use `AskUserQuestion` to ask: **"This looks like a refactor. Would you like to skip any phases?"**
Options: "Full workflow", "Skip security scan", "Cancel"
- If "Cancel": mark all remaining tasks as `deleted` and stop.

**If CHORE**:
Use `AskUserQuestion` to ask: **"This looks like a chore/maintenance task. Full workflow or Fast Track (skips Phase 3 Pre-flight, unit tests, and security scan)?"**
Options: "Full workflow", "Fast Track (skip Phase 3, tests, security)", "Cancel"
- If "Fast Track": mark Phase 3 task as `deleted`. Store **FAST_TRACK = true**, **SKIP_TESTS = true**, **SKIP_SECURITY = true**.
- If "Cancel": mark all remaining tasks as `deleted` and stop.

### 1d: Routing Table Construction

**Step 1 — Assess story complexity inline**

Using the story title, description, and acceptance criteria already retrieved in Phase 1b, reason through these questions to determine **STORY_COMPLEXITY**:

1. **Scope** — How many distinct services, modules, or layers does this touch? (3+ → HIGH signal)
2. **Volume** — How many distinct acceptance criteria are stated? (5+ → HIGH, 3–4 → MEDIUM signal)
3. **Nature of change** — Is this implementing a security/auth/payment *flow* (not just renaming a field)? Is it an architectural change or data migration? (yes → HIGH signal)
4. **Size** — Does this feel like more than 500 lines across more than 8 files? (yes → HIGH signal)
5. **Containment** — Is this clearly scoped to one file or component with 1–2 ACs? (yes → LOW)

Classify as:
- **HIGH** — any signal from questions 1, 3, or 4 triggers, or 5+ ACs
- **MEDIUM** — none of HIGH but 3–4 ACs or touches 2 layers
- **LOW** — contained, 1–2 ACs, single component, no architectural impact

Output: `Story complexity: <STORY_COMPLEXITY> — <one sentence reasoning>`

**Step 2 — Spawn adaptive-router per cognitive phase**

Spawn the following sub-agents **in a single parallel message**, each with `subagent_type: adaptive-router`, `model: claude-haiku-4-5-20251001`. Pass each the same inputs:

> phase: <phase-name>, complexity: <STORY_COMPLEXITY>, query_summary: <first 150 characters of story title + description>

Phases to route: `implementation-planner`, `implementation-executor`, `unit-test-generator`, `security-scanner`, `code-reviewer`

Wait for all 5 to return. Parse the JSON `model`, `stage`, `floor_applied`, and `reasoning` fields from each response.

**Step 3 — Build ROUTING_TABLE**

Map each parsed model name to its full model ID:
- haiku  → claude-haiku-4-5-20251001
- sonnet → claude-sonnet-4-6
- opus   → claude-opus-4-6

Mechanical phases are fixed — do not call adaptive-router for these:
- preflight-build-check → claude-haiku-4-5-20251001
- secret-exposure-scanner → claude-sonnet-4-6
- build-verifier → claude-haiku-4-5-20251001
- gh-cmt-pr → claude-haiku-4-5-20251001

**Apply manual overrides:**
Read `.claude/settings.json`. If `model_overrides` key exists, apply any matching entries on top of ROUTING_TABLE.

**Step 4 — Display routing matrix**

```
Routing Matrix for <story-id> (via Adaptive Router | Complexity: <STORY_COMPLEXITY>)

Phase                   Model           Stage         Floor
───────────────────────────────────────────────────────────────────
Phase 3: Preflight      haiku           MECHANICAL    haiku
Phase 4: Planning       <model>         <stage>       sonnet
Phase 5: Implementation <model>         <stage>       sonnet
Phase 6: Secret Scan    sonnet          MECHANICAL    —
Phase 7a: Tests         <model>         <stage>       sonnet
Phase 7b: Security      <model>         <stage>       sonnet
Phase 8: Build Verify   haiku           MECHANICAL    haiku
Phase 9: Code Review    <model>         <stage>       sonnet
Phase 10: Commit/PR     haiku           MECHANICAL    haiku

Confidence threshold:  70/100 (escalate if below)
Escalation path:       haiku → sonnet → opus
```

Use `AskUserQuestion` to ask: **"Adaptive Router routing is ready."**

Options:
1. "Use adaptive-router routing (Recommended)"
2. "Override: all Opus"
3. "Override: all Sonnet"
4. "Override: all Haiku"

**If option 1:** Use ROUTING_TABLE as built above.
**If option 2:** Set all cognitive phase entries in ROUTING_TABLE to `claude-opus-4-6`.
**If option 3:** Set all cognitive phase entries in ROUTING_TABLE to `claude-sonnet-4-6`.
**If option 4:** Set all cognitive phase entries in ROUTING_TABLE to `claude-haiku-4-5-20251001`. Note: floors still apply.

Also initialize:
- **PHASES_RUN** = 0
- **AGENTS_SPAWNED** = 0
- **ROUTING_LOG** = [] (collect routing events for completion summary)

Increment **PHASES_RUN** by 1 at the end of each phase. Increment **AGENTS_SPAWNED** by 1 each time a sub-agent is spawned.

### 1e: Token Prediction

Read `.claude/config/model-routing.json` → `token_defaults`. For each cognitive phase, look up `token_defaults[phase][STORY_COMPLEXITY]` and sum them. Add 300 for each mechanical phase (preflight, secret-scan, build-verify, commit-pr).

Store as **TOTAL_PREDICTED_TOKENS**.

Display:

```
┌─────────────────────────────────────────────────────┐
│              TOKEN PREDICTION                        │
└─────────────────────────────────────────────────────┘

  Story complexity:    <STORY_COMPLEXITY>
  Predicted tokens:    ~<TOTAL_PREDICTED_TOKENS>

  Note: Actual usage depends on codebase size and
  fix iterations. Run /cost at the end for exact amount.
```

Use `AskUserQuestion` to ask: **"Predicted token usage: ~<TOTAL_PREDICTED_TOKENS> tokens. Proceed?"**
Options: "Yes, proceed", "No, cancel workflow"

If "No": mark all remaining tasks as `deleted` and stop.

Set Phase 1 task to `completed`.

---

## Phase 2: Branch Creation

Set Phase 2 task to `in_progress`.

1. Run `git status` — if there are uncommitted changes, **STOP**, warn the user and ask how to proceed (stash, commit, or continue anyway). Wait for response.

2. Fetch the latest `main` from origin:
```bash
git fetch origin main
```

3. Check if branch `AB#<story-number>` already exists:
```bash
git branch --list "AB#<story-number>"
```
   - **If branch exists**: switch to it and rebase on main:
     ```bash
     git checkout "AB#<story-number>"
     git rebase origin/main
     ```
   - **If branch does not exist**: create it from main:
     ```bash
     git checkout -b "AB#<story-number>" origin/main
     ```

4. Validate you are on the correct feature branch by running `git branch --show-current` and confirming it matches. If it does not match, diagnose the issue and ask the user for guidance.

Set Phase 2 task to `completed`. **Automatically proceed to Phase 3** — no user confirmation needed.

---

## Phase 3: Pre-flight Build Check

**If FAST_TRACK is true or Phase 3 task was marked `deleted`, skip this phase entirely.**

Set Phase 3 task to `in_progress`.

### 3a: Pre-flight Build

Spawn a sub-agent (subagent_type: `preflight-build-check`). Prompt:

> Run the pre-flight build check. Report PASS or FAIL with error details.

**After the sub-agent returns:**

- **Preflight PASS**: Output `**Phase 3** — Pre-flight: PASS`.
- **Preflight FAIL**: Store the returned errors as **PRE_EXISTING_ERRORS**.
  - Output: `**Phase 3** — Pre-flight: FAIL (N errors stored as pre-existing)`
  - Use `AskUserQuestion` to ask: **"Pre-flight build check failed with the errors above. These are pre-existing issues (not caused by your changes). How would you like to proceed?"**
  - Options: "Continue anyway (errors will be tracked)", "Fix first", "Cancel"
  - **STOP and WAIT** for user response.

Set Phase 3 task to `completed`.

---

## Phase 4: Implementation Planning

Set Phase 4 task to `in_progress`.

**You MUST delegate planning to a sub-agent** — do NOT plan inline in the main context. This keeps the main context clean for implementation.

Spawn a sub-agent (subagent_type: `implementation-planner`, model: ROUTING_TABLE["implementation-planner"]). Prompt:

> Story: AB#<story-number>, title: <title>, description: <description>, acceptance criteria: <acceptance criteria>

**After the planner returns**, spawn a `confidence-evaluator` sub-agent:
> original_query: <the full prompt sent to implementation-planner>
> agent_output: <full plan returned>
> phase: implementation-planner

Parse the JSON response. If `recommendation` is `"ESCALATE"`:
- Upgrade ROUTING_TABLE["implementation-planner"] one tier (sonnet → opus; haiku → sonnet)
- Re-spawn `implementation-planner` with the escalated model
- Log escalation: append to ROUTING_LOG

Append a JSON line to `.claude/data/routing-log.jsonl`:
```json
{"timestamp":"<ISO>","run_id":"<story-id>","phase":"implementation-planner","complexity":"<STORY_COMPLEXITY>","routing_stage":"<stage from adaptive-router>","model_decided":"<initial model>","final_model":"<model actually used>","escalated":<true/false>,"confidence_score":<score>,"token_count":0,"retry_count":0,"downstream_build_failed":false,"user_revision_requested":false,"pr_number":null,"pr_review_comments":null}
```

Present the returned plan to the user.

**This phase is interactive — iterate with the user using the same sub-agent:**

1. Present the plan and ask: **"Here is the implementation plan. What do you think? You can ask questions, request changes, or approve it to move forward."**
2. **STOP and WAIT** for user input.
3. If the user requests changes, **resume** the same sub-agent (using its agent ID) with the feedback. Present the revised plan. Repeat until the user explicitly approves (e.g., "looks good", "proceed", "approved").

Only exit Phase 4 once the user has approved the final plan.

Output: `**Phase 4** — Plan approved: N changes across M files`

Set Phase 4 task to `completed`.

---

## Phase 5: Implementation

Set Phase 5 task to `in_progress`.

Spawn a sub-agent (subagent_type: `implementation-executor`, model: ROUTING_TABLE["implementation-executor"]). Prompt:

> Story: AB#<story-number>, components: <all components>, files: <all file paths from plan>, plan: <full approved plan>, codebase patterns: <key patterns from planning>

**After the executor returns**, spawn a `confidence-evaluator` sub-agent:
> original_query: <the full prompt sent to implementation-executor>
> agent_output: <full implementation output>
> phase: implementation-executor

Parse the JSON response. If `recommendation` is `"ESCALATE"`:
- Upgrade ROUTING_TABLE["implementation-executor"] one tier
- Re-spawn `implementation-executor` with the escalated model
- Log escalation: append to ROUTING_LOG

Append a JSON line to `.claude/data/routing-log.jsonl` (same schema as Phase 4).

After the sub-agent returns, show the user a summary of all files created/modified.

Output: `**Phase 5** — Implementation complete | Files: <list>`

---

### Phase 5 Completion

Use `AskUserQuestion` to ask: **"Implementation complete. Ready to generate unit tests and run security scan?"**
Options: "Proceed (tests + security in parallel)", "Review changes first", "Skip tests", "Cancel"

**STOP and WAIT** for user confirmation.

If the user chooses "Review changes first", show the full diff of all changes and wait for further instructions.

Set Phase 5 task to `completed`.

---

## Phase 6: Secret Exposure Check

**If FAST_TRACK is true or SKIP_SECRET_SCAN is true, skip this phase.**

Set Phase 6 task to `in_progress`.

### 6a: Run Secret Scan

Spawn a sub-agent (subagent_type: `secret-exposure-scanner`). Prompt:

> Story: AB#<story-number>, base branch: main, files changed: <list of files from Phase 5>

**After the sub-agent returns:**

- **PASS**: Output `**Phase 6** — Secret Scan: PASS (no secrets detected)`. Proceed to Phase 7.

- **REVIEW_REQUIRED**: Present the findings to the user. Use `AskUserQuestion` to ask: **"TruffleHog flagged potential secrets that need review. How would you like to proceed?"**
  Options: "These are false positives, continue", "I'll fix these issues", "Cancel workflow"
  - If "false positives": proceed to Phase 7
  - If "fix issues": **STOP and WAIT** for user to fix, then re-run Phase 6
  - If "Cancel": mark remaining tasks as `deleted` and stop

- **BLOCKED**: Output `**Phase 6** — Secret Scan: BLOCKED`. Present the masked findings and remediation guidance. Use `AskUserQuestion` to ask: **"Real secrets detected. The workflow cannot proceed until these are removed. What would you like to do?"**
  Options: "I'll fix these now", "Cancel workflow"
  - If "fix now": **STOP and WAIT** for user to fix, then re-run Phase 6
  - If "Cancel": mark remaining tasks as `deleted` and stop

Set Phase 6 task to `completed`.

---

## Phase 7: Tests & Security Scan

**If FAST_TRACK is true, SKIP_TESTS is true, or Phase 7 task was marked `deleted`, skip the unit-test-generator spawn.**
**If SKIP_SECURITY is true, skip the security-scanner spawn.**

**If both sub-agents are skipped, set Phase 7 task to `deleted` and proceed to Phase 8.**

Set Phase 7 task to `in_progress` (unless deleted).

Spawn the applicable sub-agents in a **single message**:

**Sub-agent — Unit Test Generator** (skip if SKIP_TESTS or FAST_TRACK, subagent_type: `unit-test-generator`, model: ROUTING_TABLE["unit-test-generator"]):

> Story: AB#<story-number>, files: <all Phase 5 files with full paths>, what was implemented: <brief description>

**Sub-agent — Security Scanner** (skip if SKIP_SECURITY, subagent_type: `security-scanner`, model: ROUTING_TABLE["security-scanner"]):

> Story: AB#<story-number>, files: <all Phase 5 files with full paths>, pre-existing errors: <PRE_EXISTING_ERRORS or "None">

Wait for **ALL** spawned sub-agents to return, then for each (unit-test-generator and security-scanner), spawn a `confidence-evaluator`:

> original_query: <prompt sent to the agent>
> agent_output: <full output returned>
> phase: <unit-test-generator or security-scanner>

If either scores below 70, escalate that agent's model one tier and re-run it (once). Append a routing-log.jsonl entry for each.

**Unit Test results:**
- Show a summary of test files created with test method names.
- Output: `**Phase 7 (tests)** — Tests: <N test files, M test methods>`

**Security Scan results:**
- **PASS** (0 vulnerabilities): Output `**Phase 7 (security)** — Security: PASS (0 issues)`.
- **FIXED** (vulnerabilities found and fixed): Output `**Phase 7 (security)** — Security: N vulnerabilities fixed in M files`.

Set Phase 7 task to `completed`.

Store the complete list of files modified in this phase (test files + security-fixed files) as **POST_PHASE7_FILES** — Phase 8 will include these in its build check.

Proceed to Phase 8 automatically.

---

## Phase 8: Build Verification

Set Phase 8 task to `in_progress`.

Spawn a sub-agent (subagent_type: `build-verifier`). Prompt:

> Story: AB#<story-number>, files: <all Phase 5 files + POST_PHASE7_FILES>, pre-existing errors: <PRE_EXISTING_ERRORS or "None">

**After the sub-agent returns:**

**If the build succeeded:**
Output: `**Phase 8** — Build: PASS`
Proceed to Phase 9.

**If the build failed after 3 attempts:**
Present the errors to the user and use `AskUserQuestion` to ask for guidance.
Options: "Fix issues manually and re-run", "Continue anyway", "Cancel"

Set Phase 8 task to `completed`.

---

## Phase 9: Code Review

Set Phase 9 task to `in_progress`.

Invoke the `task-review` skill using the **Skill** tool with:
- **arguments**: `AB#<story-number>: <story-title> | <one-paragraph plan summary>`

After the skill returns, spawn a `confidence-evaluator` sub-agent (model: haiku):
> original_query: <the arguments passed to task-review>
> agent_output: <full review output>
> phase: code-reviewer

If score < 70 and ROUTING_TABLE["code-reviewer"] != opus:
- Escalate ROUTING_TABLE["code-reviewer"] one tier
- Re-invoke `task-review` with the escalated model context (note: task-review uses its own model; log the escalation intent)

Append a routing-log.jsonl entry for code-reviewer.

Output: `**Phase 9** — Review: <verdict from skill>`

Set Phase 9 task to `completed`.

---

## Phase 10: Commit and PR

Set Phase 10 task to `in_progress`.

Invoke the `gh-cmt-pr` skill using the **Skill** tool with:
- **arguments**: `AB#<story-number>: <story-title>`

The PR title should follow the format: `AB#<story-number>: <concise description>`

**After the skill returns**, parse the PR URL and number from its output:
- Scan for a URL matching `https://github.com/<owner>/<repo>/pull/<number>`
- Store the full URL as **PR_URL** and the numeric portion as **PR_NUMBER**
- If parsing fails, use `AskUserQuestion` to ask: **"Could not parse the PR URL automatically. Please paste it:"** and extract PR_NUMBER from the user's input.

Set Phase 10 task to `completed`.

---

## Completion

After all phases are complete, display a final summary:

- **Story**: AB#<number> — <title>
- **Branch**: AB#<number>
- **Files**: <count> created, <count> modified
- **Tests**: <count> test files, <count> test methods (or SKIPPED)
- **Build**: PASS / FAIL
- **Security**: PASS / N fixed / SKIPPED
- **Review**: APPROVED / N fixed, M dismissed
- **PR**: <PR URL> (Reviewer: Copilot)

Congratulate the user on completing the feature development workflow.
