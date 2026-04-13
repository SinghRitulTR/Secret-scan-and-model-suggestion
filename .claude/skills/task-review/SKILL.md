---
name: task-review
description: Runs code review for a task workflow phase, with iterative fix-cycle support
argument-hint: "AB#<story-number>: <story-title> | <plan-summary>"
allowed-tools: Agent, AskUserQuestion
---

You are running the code review phase of the task workflow.

Arguments: `$ARGUMENTS` — format: `AB#<story-number>: <story-title> | <plan-summary>`

Parse from arguments:
- **STORY_NUMBER**: numeric part of `AB#<n>`
- **STORY_TITLE**: the story title (between `:` and `|`)
- **PLAN_SUMMARY**: everything after the `|`

---

## Step 1: Spawn Code Reviewer

Spawn a sub-agent (subagent_type: `code-reviewer`). Prompt:

> Story: AB#<STORY_NUMBER>, title: <STORY_TITLE>, approved plan: <PLAN_SUMMARY>

**Save the returned agent ID as REVIEWER_AGENT_ID.**

## Step 2: Evaluate Results

- **APPROVED** (no MUST_FIX items): Output verdict `APPROVED` with any SUGGESTION items listed for awareness, then return.

- **CHANGES_REQUESTED** (has MUST_FIX or SHOULD_FIX items):
  1. Present ALL findings to the user, grouped by severity.
  2. Use `AskUserQuestion` to ask: **"The code review found issues (listed above). How would you like to proceed?"**
     Options: "Fix selected items (specify below)", "Dismiss all and proceed", "Cancel"
  3. Based on response:
     - **"Dismiss all and proceed"**: output verdict `CHANGES_REQUESTED (all dismissed)` and return.
     - **"Fix selected items"**: ask the user to list which finding IDs to fix (e.g., "MF-1, SF-2"). Then **resume** the same reviewer sub-agent using **REVIEWER_AGENT_ID**:
       > The user has approved fixing the following findings: [list by ID and description]. Switch to FIX_AND_REREVIEW mode: apply those fixes, then re-review the changed files. Return a final verdict (APPROVED or remaining CHANGES_REQUESTED with unfixed items).
     - Wait for the resumed agent to return. Present results. Max 2 fix cycles total, then escalate to user with remaining issues.
     - **"Cancel"**: output verdict `CANCELLED` and return.

## Step 3: Return Verdict

Output the final line: `**Review verdict**: <APPROVED / CHANGES_REQUESTED (N fixed, M dismissed, K suggestions) / CANCELLED>`
