---
name: pr-review-fix
description: Fetch GitHub PR review comments, analyze validity, and apply approved fixes interactively
argument-hint: "<github-pr-url>"
allowed-tools: mcp__github__pull_request_read, AskUserQuestion, Bash, Read, Edit, Write, Glob, Grep, Agent
---

You are working through GitHub PR review comments and applying valid fixes. You must NOT blindly apply every comment — analyze each one, ask when unsure, and always confirm before deleting files.

Arguments: `$ARGUMENTS` — a GitHub PR URL or `owner/repo#<number>` or just a PR number if the repo is detectable from git remote.

---

## Step 0: Parse PR Reference

Extract **OWNER**, **REPO**, and **PR_NUMBER** from `$ARGUMENTS`:

- Full URL: `https://github.com/OWNER/REPO/pull/NUMBER` → parse directly
- Short form: `OWNER/REPO#NUMBER` → parse directly
- Number only: run `git remote get-url origin` to derive OWNER and REPO

If parsing fails, use `AskUserQuestion`:
> "Could not parse a PR reference from the arguments. Please provide the GitHub PR URL or owner/repo#number:"

---

## Step 1: Fetch PR Context

Run in parallel:
1. `mcp__github__pull_request_read` with `method: "get"` — get PR title, description, base/head branch, state
2. `mcp__github__pull_request_read` with `method: "get_review_comments"` — get all review threads
3. `mcp__github__pull_request_read` with `method: "get_reviews"` — get review verdicts (APPROVED, CHANGES_REQUESTED, etc.)

**If the PR is already merged or closed:** inform the user and ask whether to continue:
> "This PR is already [merged/closed]. Do you still want to process its review comments?"

---

## Step 2: Build Comment Inventory

From the review threads, build a list of comments. For each thread:
- Extract: thread ID, file path, line number(s), comment body, author, resolved/unresolved status, outdated flag
- **Skip** threads that are already **resolved** or **outdated** (flag them as SKIPPED in the report)

Present a summary table before analyzing:

```
Found N review threads:
  - X unresolved (will analyze)
  - Y resolved   (skipping)
  - Z outdated   (skipping)
```

---

## Step 3: Analyze Each Comment

For each unresolved comment, classify it into one of these categories. Be thoughtful — read the file/line context before classifying.

### Categories

| Category | Meaning |
|---|---|
| `ACTIONABLE` | Clear, specific change requested — you can implement it |
| `AMBIGUOUS` | Vague, unclear intent, or conflicting options — need clarification |
| `QUESTION` | Reviewer is asking a question, not requesting a change |
| `NITPICK` | Style/preference comment without a clear right answer |
| `FILE_DELETE` | Comment requests deletion of a file or directory |
| `INVALID` | Comment is factually wrong, already addressed, or not applicable to this codebase |

**Rules:**
- If you are not confident about the intent → classify as `AMBIGUOUS`
- If a comment says "remove this file", "delete this class", "drop this" → classify as `FILE_DELETE` regardless of phrasing
- If the comment references a line that no longer exists in the current HEAD → classify as `INVALID` (outdated diff)
- Read the actual file at the referenced path + line before classifying — never classify based on comment text alone

---

## Step 4: Present Full Analysis to User

Before making any changes, present the complete analysis:

```
PR Review Comment Analysis — PR #<NUMBER>: <TITLE>
================================================

[C-1] ACTIONABLE — <file>:<line>
  Author: <name>
  Comment: "<comment text>"
  Proposed fix: <one-line description of what you'll do>

[C-2] AMBIGUOUS — <file>:<line>
  Author: <name>
  Comment: "<comment text>"
  Unclear because: <your reasoning>

[C-3] FILE_DELETE — <file>
  Author: <name>
  Comment: "<comment text>"

[C-4] QUESTION — <file>:<line>
  Author: <name>
  Comment: "<comment text>"
  No code change needed.

[C-5] INVALID — <file>:<line>
  Author: <name>
  Comment: "<comment text>"
  Reason skipping: <your reasoning>

[C-6] NITPICK — <file>:<line>
  Author: <name>
  Comment: "<comment text>"

Skipped (resolved/outdated): N threads
```

Use `AskUserQuestion` to ask:
> "Above is my analysis of N review comments. How would you like to proceed?"

Options:
1. "Apply all ACTIONABLE fixes, ask me about AMBIGUOUS/FILE_DELETE" ← default
2. "Review each fix individually before applying"
3. "Select specific comment IDs to fix (e.g., C-1, C-3)"
4. "Cancel"

---

## Step 5: Resolve AMBIGUOUS Comments

For **each** `AMBIGUOUS` comment (before applying any fixes if option 1 was chosen), use `AskUserQuestion`:

> "Comment [C-X] by <author> on `<file>:<line>` is unclear:
>
> **Comment:** "<full comment text>"
>
> **My interpretation:** <your best guess>
>
> What should I do?"

Options:
1. "Apply your interpretation"
2. "Apply this instead: [user types custom instruction]" — show "Other" option
3. "Skip this comment"
4. "Mark as resolved without changes"

Save the user's instruction for this comment ID before moving on.

---

## Step 6: Confirm FILE_DELETE Comments

For **each** `FILE_DELETE` comment, use `AskUserQuestion`:

> "Comment [C-X] by <author> requests deleting: `<file path>`
>
> **Comment:** "<full comment text>"
>
> Are you sure you want to delete this file? This cannot be undone."

Options:
1. "Yes, delete `<file>`"
2. "Skip — do not delete"

**Only delete if the user explicitly confirms.** If confirmed, stage the deletion (do not `git rm` — just note it as a pending action, apply at the end in Step 7).

---

## Step 7: Apply Fixes

Apply fixes in file order (group changes to the same file together to avoid conflicts).

For each fix:

1. **Read the current file** before editing — never edit based on diff alone
2. Apply the minimal change needed to address the comment
3. Do NOT refactor surrounding code, add comments, or make "improvements" not requested
4. After editing, verify the change looks correct with a quick re-read of the affected lines

**For individual review mode** (option 2 from Step 4): after showing the proposed diff for each fix, use `AskUserQuestion`:
> "Apply this fix for [C-X]?"
> Options: "Yes", "Skip", "Edit (describe the change you want)"

**If a fix touches a build/config file** (`build.gradle`, `pom.xml`, `application.yml`, etc.), note it explicitly and confirm with user before applying.

---

## Step 8: NITPICK Comments

After all ACTIONABLE fixes are applied, present NITPICK comments together:

> "The following comments are style/preference nitpicks. Do you want to address any of these?"

List them with checkboxes (use `AskUserQuestion` multiSelect). Apply only those the user selects.

---

## Step 9: Summary Report

Print a final report:

```
PR Review Fix Summary — PR #<NUMBER>
=====================================
Fixed:    N comments
  [C-1] <file>:<line> — <one-line description>
  ...

Skipped:  N comments
  [C-2] AMBIGUOUS — user skipped
  [C-5] INVALID — <reason>
  ...

Pending:  N (awaiting your action)
  [C-3] FILE_DELETE — user declined

Resolved without changes: N
  [C-4] QUESTION — no code change needed
```

**Do NOT commit or push.** Inform the user:
> "Changes have been applied locally. Use `/gh-cmt-pr` or `/task-review` to commit, push, and update the PR."

---

## Error Handling

- **File not found at referenced path**: classify as INVALID, note "file may have been moved or deleted"
- **Line number out of range**: read the full file, attempt to locate the referenced code by context; if not found, classify as INVALID
- **GitHub API error fetching comments**: retry once; if still failing, ask user to paste comments manually
- **Conflicting comments on same line**: surface both to the user and ask which to apply
