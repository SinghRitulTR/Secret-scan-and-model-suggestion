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

Spawn a sub-agent (subagent_type: `implementation-planner`, model: `opus`). Prompt:

> Story: AB#<story-number>, title: <title>, description: <description>, acceptance criteria: <acceptance criteria>

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

Spawn a sub-agent (subagent_type: `implementation-executor`). Prompt:

> Story: AB#<story-number>, components: <all components>, files: <all file paths from plan>, plan: <full approved plan>, codebase patterns: <key patterns from planning>

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

**Sub-agent — Unit Test Generator** (skip if SKIP_TESTS or FAST_TRACK, subagent_type: `unit-test-generator`):

> Story: AB#<story-number>, files: <all Phase 5 files with full paths>, what was implemented: <brief description>

**Sub-agent — Security Scanner** (skip if SKIP_SECURITY, subagent_type: `security-scanner`):

> Story: AB#<story-number>, files: <all Phase 5 files with full paths>, pre-existing errors: <PRE_EXISTING_ERRORS or "None">

Wait for **ALL** spawned sub-agents to return, then:

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

After the skill returns, output: `**Phase 9** — Review: <verdict from skill>`

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
