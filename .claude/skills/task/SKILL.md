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
- **Model selection**: Use ROUTING_TABLE[agent_name] to determine the model for each cognitive phase sub-agent spawn. Mechanical phases (preflight-build-check, secret-exposure-scanner, gh-cmt-pr) always use Haiku. Never pass SELECTED_MODEL — use the routing table.
- **Confidence evaluation**: After every cognitive phase sub-agent returns, spawn `confidence-evaluator` (model: haiku) with the original prompt and the agent's response. If score < 70, escalate one tier and re-spawn the phase agent. Log every attempt to `.claude/data/routing-log.jsonl`.
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

### 1b-confirm: Story Understanding Check

Compose a plain-English summary of what you understand from the story — 2–4 sentences covering what will be built, who it serves, and the key outcomes. Do NOT use bullet points.

Output in this format:
> **My understanding:** <plain-English summary>

Use `AskUserQuestion` to ask: **"Is this what you want to do, or would you like to clarify something before I proceed?"**

Options: "Yes, proceed", "No, let me clarify"

**If "Yes, proceed":** continue to Phase 1c.

**If "No, let me clarify" or custom clarification:**
1. Acknowledge the clarification
2. Revise the plain-English understanding
3. Output updated `> **My understanding:**`
4. Ask again with same two options
5. Repeat until user confirms "Yes, proceed"

---

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

### 1d: Routing Table Construction — Model Advisor

Spawn a sub-agent (subagent_type: `model-advisor`, model: `sonnet`) with:
> STORY_NUMBER: <story-number or blank if ad-hoc>
> STORY_CONTENT: title: <title> | description: <description> | AC: <acceptance criteria> | type: <STORY_TYPE>

**STOP and WAIT** for model-advisor to return before continuing.

**Parse the structured block** from model-advisor output:
Find the section between `---ROUTING_RECOMMENDATIONS---` and `---END_ROUTING_RECOMMENDATIONS---`.
Read each `key: value` line and extract the values.

Build **ROUTING_TABLE** from the parsed values, converting model names to full IDs:
- haiku  → claude-haiku-4-5-20251001
- sonnet → claude-sonnet-4-6
- opus   → claude-opus-4-6

Store **STORY_COMPLEXITY** from the `story_demand:` line (LOW/MEDIUM/HIGH).
Store **TOTAL_PREDICTED_TOKENS** from the `total_tokens:` line.

**Apply safety floors:**
Read `.claude/config/phase-floors.json`. For any phase where ROUTING_TABLE model is cheaper than the floor, upgrade to the floor model.

**Apply manual overrides:**
Read `.claude/settings.json`. If `model_overrides` key exists, apply any matching entries on top of ROUTING_TABLE.

Display the routing matrix:

```
Routing Matrix for AB#<story-number> (via Model Advisor | Demand: <STORY_COMPLEXITY>)

Phase                   Model           Demand        Floor
───────────────────────────────────────────────────────────────────
Phase 3: Preflight      <model>         LOW           haiku
Phase 4: Planning       <model>         <demand>      sonnet
Phase 5: Implementation <model>         <demand>      sonnet
Phase 6: Secret Scan    <model>         LOW           haiku
Phase 7a: Tests         <model>         <demand>      sonnet
Phase 7b: Security      <model>         <demand>      sonnet
Phase 8: Build Verify   <model>         LOW           haiku
Phase 9: Code Review    <model>         <demand>      sonnet
Phase 10: Commit/PR     <model>         LOW           haiku

Predicted tokens this run: ~<TOTAL_PREDICTED_TOKENS>
Confidence threshold:  70/100 (escalate if below)
Escalation path:       haiku → sonnet → opus
```

Use `AskUserQuestion` to ask: **"Model Advisor routing is ready."**

Options:
1. "Use model-advisor routing (Recommended)"
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

Set Phase 1 task to `completed`.

---

### 1e: Token Prediction

Display the token estimate from the model-advisor output:

```
┌─────────────────────────────────────────────────────┐
│              TOKEN PREDICTION                        │
└─────────────────────────────────────────────────────┘

  Story demand:        <STORY_COMPLEXITY>
  Predicted tokens:    ~<TOTAL_PREDICTED_TOKENS>

  Note: Actual usage depends on codebase size and
  fix iterations. Run /cost at the end for exact amount.
```

Use `AskUserQuestion` to ask: **"Predicted token usage: ~<TOTAL_PREDICTED_TOKENS> tokens. Proceed?"**
Options: "Yes, proceed", "No, cancel workflow"

If "No": mark all remaining tasks as `deleted` and stop.

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

Present the returned plan to the user.

**This phase is interactive — iterate with the user using the same sub-agent:**

1. Present the plan and ask: **"Here is the implementation plan. What do you think? You can ask questions, request changes, or approve it to move forward."**
2. **STOP and WAIT** for user input.
3. If the user requests changes, **resume** the same sub-agent (using its agent ID) with the feedback. Present the revised plan. Repeat until the user explicitly approves (e.g., "looks good", "proceed", "approved").

Only exit Phase 4 once the user has approved the final plan.

Output: `**Phase 4** — Plan approved: N changes across M files`

### 4c: Confidence Evaluation & Mid-Workflow Re-evaluation

Spawn confidence-evaluator (subagent_type: `confidence-evaluator`, model: `haiku`) with:
> QUERY: Story AB#<story-number>: <title>. Acceptance criteria: <criteria>
> ANSWER: <full plan text returned by planner>

If score < 70:
- Escalate: determine next tier above ROUTING_TABLE["implementation-planner"] (sonnet→opus)
- Re-spawn implementation-planner at escalation model with same prompt
- Re-run confidence-evaluator on new output
- Update ROUTING_TABLE["implementation-planner"] to escalation model for logging

Log to ROUTING_LOG: { phase: "planning", model: <final model used>, confidence: <score>, escalated: <true/false> }

**Mid-workflow scope check — Codebase Signals:**
Examine the approved plan and extract these four signals:

- **files_in_plan** — count all distinct file paths mentioned in the plan
- **components_touched** — count distinct services, modules, or layers involved (e.g. auth service, API layer, database layer each count as 1)
- **security_related** — true if plan touches auth, tokens, encryption, permissions, session management, or payment logic
- **estimated_lines** — if the planner estimated lines of code to be added/modified, capture that number (use 0 if not mentioned)

Upgrade STORY_COMPLEXITY one tier (LOW→MEDIUM, MEDIUM→HIGH) if ANY of the following are true AND current STORY_COMPLEXITY is not already HIGH:

| Signal | Threshold | Reason |
|--------|-----------|--------|
| files_in_plan | > 8 | More files = wider blast radius |
| components_touched | > 3 | Cross-component changes have ripple effects |
| security_related | true | Auth/payment/encryption — never underestimate |
| estimated_lines | > 500 | Large change needs more careful reasoning |

If upgrade triggered:
  - Update STORY_COMPLEXITY
  - Re-read ROUTING_TABLE entries for phases 5–9 using new complexity from model-routing.json
  - Output:
    ```
    ⚡ Codebase scope larger than story suggested.
       Signal(s): <list which signals triggered>
       Upgrading complexity: <OLD> → <NEW>
       Phases 5–9 routing updated.
    ```

If no upgrade triggered:
  - Output: `✓ Scope check passed. Complexity confirmed: <STORY_COMPLEXITY>`

Set Phase 4 task to `completed`.

---

## Phase 5: Implementation

Set Phase 5 task to `in_progress`.

Spawn a sub-agent (subagent_type: `implementation-executor`, model: ROUTING_TABLE["implementation-executor"]). Prompt:

> Story: AB#<story-number>, components: <all components>, files: <all file paths from plan>, plan: <full approved plan>, codebase patterns: <key patterns from planning>

After the sub-agent returns, show the user a summary of all files created/modified.

Output: `**Phase 5** — Implementation complete | Files: <list>`

### Phase 5 Confidence Check

Spawn confidence-evaluator (subagent_type: `confidence-evaluator`, model: `haiku`) with:
> QUERY: Implement the following plan for AB#<story-number>: <one-paragraph plan summary>. Expected files: <file list from plan>
> ANSWER: <implementation summary returned by executor>

If score < 70:
- Escalate implementation-executor one tier
- Re-spawn at escalation model with same prompt
- Re-run evaluator

Log to ROUTING_LOG: { phase: "implementation", model: <final model>, confidence: <score>, escalated: <true/false> }

Append to `.claude/data/routing-log.jsonl`:
{"timestamp":"<ISO>","run_id":"AB#<story-number>","phase":"implementation","complexity":"<STORY_COMPLEXITY>","routing_stage":"<stage>","model_decided":"<initial model>","final_model":"<final model>","escalated":<bool>,"confidence_score":<score>,"token_count":0,"retry_count":<n>,"downstream_build_failed":false,"user_revision_requested":false,"pr_number":null,"pr_review_comments":null}

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

Wait for **ALL** spawned sub-agents to return, then:

**Unit Test results:**
- Show a summary of test files created with test method names.
- Output: `**Phase 7 (tests)** — Tests: <N test files, M test methods>`

**Security Scan results:**
- **PASS** (0 vulnerabilities): Output `**Phase 7 (security)** — Security: PASS (0 issues)`.
- **FIXED** (vulnerabilities found and fixed): Output `**Phase 7 (security)** — Security: N vulnerabilities fixed in M files`.

### Phase 7 Confidence Checks & Logging

For each spawned sub-agent that ran:

**Unit tests (if ran):**
Spawn confidence-evaluator with:
> QUERY: Generate unit tests for the following files: <file list>. Tests should cover all implemented logic.
> ANSWER: <test generation summary>
Log to ROUTING_LOG: { phase: "unit-tests", model: <model used>, confidence: <score>, escalated: false }
Append to routing-log.jsonl (same schema as Phase 5, phase: "unit-tests").

**Security scan (if ran):**
Spawn confidence-evaluator with:
> QUERY: Scan these files for security vulnerabilities and fix any found: <file list>
> ANSWER: <security scan result>
Log to ROUTING_LOG: { phase: "security-scan", model: <model used>, confidence: <score>, escalated: false }
Append to routing-log.jsonl (phase: "security-scan").

Note: Do not escalate on Phase 7 — these run in parallel and results are accepted as-is. Confidence scores are logged for future routing improvement only.

Set Phase 7 task to `completed`.

Store the complete list of files modified in this phase (test files + security-fixed files) as **POST_PHASE7_FILES** — Phase 8 will include these in its build check.

Proceed to Phase 8 automatically.

---

## Phase 8: Build Verification

Set Phase 8 task to `in_progress`.

Spawn a sub-agent (subagent_type: `build-verifier`, model: ROUTING_TABLE["build-verifier"]). Prompt:

> Story: AB#<story-number>, files: <all Phase 5 files + POST_PHASE7_FILES>, pre-existing errors: <PRE_EXISTING_ERRORS or "None">

**After the sub-agent returns:**

**If the build succeeded:**
Output: `**Phase 8** — Build: PASS`
Proceed to Phase 9.

**If the build failed after 3 attempts:**
Present the errors to the user and use `AskUserQuestion` to ask for guidance.
Options: "Fix issues manually and re-run", "Continue anyway", "Cancel"

### Phase 8 Routing Log

Append to `.claude/data/routing-log.jsonl`:
{"timestamp":"<ISO>","run_id":"AB#<story-number>","phase":"build-verify","complexity":"<STORY_COMPLEXITY>","routing_stage":"COLD_START","model_decided":"<model>","final_model":"<model>","escalated":false,"confidence_score":<90 if PASS else 50>,"token_count":0,"retry_count":0,"downstream_build_failed":false,"user_revision_requested":false,"pr_number":null,"pr_review_comments":null}

Also update downstream_build_failed=true for the Phase 5 implementation log entry if build FAILED.

Set Phase 8 task to `completed`.

---

## Phase 9: Code Review

Set Phase 9 task to `in_progress`.

**Note:** Pass ROUTING_TABLE["code-reviewer"] as context to the task-review skill by including it in the arguments string.

Invoke the `task-review` skill using the **Skill** tool with:
- **arguments**: `AB#<story-number>: <story-title> | <one-paragraph plan summary> | model: <ROUTING_TABLE["code-reviewer"]>`

After the skill returns, output: `**Phase 9** — Review: <verdict from skill>`

Append to `.claude/data/routing-log.jsonl`:
{"timestamp":"<ISO>","run_id":"AB#<story-number>","phase":"code-review","complexity":"<STORY_COMPLEXITY>","routing_stage":"COLD_START","model_decided":"<ROUTING_TABLE["code-reviewer"]>","final_model":"<ROUTING_TABLE["code-reviewer"]>","escalated":false,"confidence_score":85,"token_count":0,"retry_count":0,"downstream_build_failed":false,"user_revision_requested":false,"pr_number":null,"pr_review_comments":null}

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

Update the most recent routing-log.jsonl entries for this run_id: set `pr_number` to PR_NUMBER for all entries where pr_number is null.

Set Phase 10 task to `completed`.

---

## Completion

Rebuild `.claude/data/stats-cache.json` from all entries in routing-log.jsonl:
Group by "phase_COMPLEXITY" key, compute avg_confidence, success_rate, entry_count per group. Write updated stats-cache.json.

After all phases are complete, display:

- **Story**: AB#<number> — <title>
- **Branch**: AB#<number>
- **Complexity**: <STORY_COMPLEXITY>
- **Files**: <count> created, <count> modified
- **Tests**: <count> test files, <count> test methods (or SKIPPED)
- **Build**: PASS / FAIL
- **Security**: PASS / N fixed / SKIPPED
- **Review**: APPROVED / N fixed, M dismissed
- **PR**: <PR URL> (Reviewer: Copilot)

---

### Routing Summary

| Phase | Model Used | Confidence | Escalated |
|-------|-----------|-----------|-----------|
| Phase 3: Preflight | haiku (mechanical) | — | — |
| Phase 4: Planning | <from ROUTING_LOG> | <score>/100 | <yes/no> |
| Phase 5: Implementation | <from ROUTING_LOG> | <score>/100 | <yes/no> |
| Phase 6: Secret Scan | haiku (mechanical) | — | — |
| Phase 7a: Tests | <from ROUTING_LOG> | <score>/100 | no |
| Phase 7b: Security | <from ROUTING_LOG> | <score>/100 | no |
| Phase 8: Build Verify | <from ROUTING_LOG> | <score>/100 | — |
| Phase 9: Code Review | <from ROUTING_LOG> | — | — |
| Phase 10: Commit/PR | haiku (mechanical) | — | — |

---

### Session Stats

| Metric | Value |
|---|---|
| Phases completed | <PHASES_RUN> / 10 |
| Sub-agents spawned | <AGENTS_SPAWNED> |
| Complexity assessed | <STORY_COMPLEXITY> |
| Escalations | <count from ROUTING_LOG> |
| Routing log entries | <new entries added this run> |

> **Tip:** Run `/cost` to see exact token usage. Run `/routing-review` after 20+ runs to get routing improvement recommendations.

Congratulate the user on completing the feature development workflow.
