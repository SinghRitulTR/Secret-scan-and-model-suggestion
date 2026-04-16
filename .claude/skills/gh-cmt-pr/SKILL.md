---
name: gh-cmt-pr
description: Generate change summary, commit, push, and create a draft PR with Copilot reviewer
argument-hint: "[optional] AB#XXXXXX description"
allowed-tools: Bash, mcp__github__create_pull_request, mcp__github__request_copilot_review, mcp__github__get_me, mcp__github__get_label, mcp__github__list_pull_requests, AskUserQuestion
---

You are performing a commit-and-PR workflow. Follow these steps precisely and interactively.

## Step 0: Branch Safety Check + Repo Detection

Run in parallel:
- `git branch --show-current` — detect current branch
- `git remote get-url origin` — detect repo URL
- `git status --porcelain` — check for changes

**Branch check**: If the current branch is `main` or `master`, stop immediately and warn:
> "You are on the `main` branch. Create a feature branch before committing."

**Repo detection**: Parse `owner` and `repo` from the remote URL. Handles both SSH and HTTPS formats:
- SSH: `git@github.com:owner/repo.git`
- HTTPS: `https://github.com/owner/repo.git`

**No changes check**: If `git status --porcelain` output is empty, stop with:
> "No changes detected. Nothing to commit."

---

## Step 1: Determine Story Number

Priority order (silent — do not announce the source to the user):
1. Extract `AB#XXXXXX` from `$ARGUMENTS` if present
2. Extract `AB#XXXXXX` from the current branch name if it matches that pattern
3. Ask the user via `AskUserQuestion`

If `$ARGUMENTS` contains a description beyond the story number, use it as the commit description.

---

## Step 2: Review Changes

Run in parallel:
- `git status` — all modified, added, deleted, untracked files
- `git diff` + `git diff --cached` — unstaged and staged changes
- `git log --oneline -5` — recent commits for style reference

**Safety checks — always exclude these paths from staging:**
- `.env`, `credentials.*`, `secrets.*` — sensitive files
- Build output directories (`build/`, `target/`, `dist/`, `node_modules/`) — build output
- IDE/tool directories (`.gradle/`, `.idea/`, `.vscode/`) — IDE files
- `.claude/` — agent files (not for version control)
- Files > 10MB

**Project-specific exclusions**: Read CLAUDE.md for additional exclusions (look for 'Critical Warnings' or 'NEVER commit' instructions). Add any documented exclusions to the list above.

Present a summary of files to be staged and the proposed commit message.

---

## Step 3: Present Summary and Ask for Confirmation

Use `AskUserQuestion` to present:
- Files to be staged
- Proposed commit message: `AB#{STORY_NUMBER}: {DESCRIPTION}`
  - If no description was provided, generate a concise one from the staged changes (under 72 chars)
- Branch and remote
- Intent to push and create a draft PR

Options:
1. "Proceed" — stage, commit, push, and create draft PR
2. "Edit message" — prompt user for a different commit message then proceed
3. "Cancel" — abort

**STOP and WAIT** for user response before continuing.

---

## Step 4: Stage and Commit

1. Stage files **explicitly by name** — NEVER `git add .` or `git add -A`. Exclude any files from the safety list.
2. Commit message format: `AB#{STORY_NUMBER}: {DESCRIPTION}`
3. Commit and verify with `git status` after.

---

## Step 5: Push to Remote

```bash
git push -u origin HEAD
```

If the push fails due to upstream divergence:
```bash
git fetch origin && git rebase origin/<branch-name>
```
Then retry the push once. If it still fails, ask the user before attempting a force push.

---

## Step 6: Check for Existing PR

Before creating a PR, check if one already exists for the current branch:

Use `mcp__github__list_pull_requests` with:
- **owner**: detected in Step 0
- **repo**: detected in Step 0
- **head**: `<owner>:<branch-name>`
- **state**: `"all"`

- If a PR **already exists** (any state):
  - Capture the existing PR number and URL
  - Skip Steps 6a, 7, 8, and 9 entirely
  - Note in the final report: "PR already exists — skipped PR creation, reviewer, assignee, and label steps"
- If **no PR exists**, proceed with Steps 6a-9 below

---

## Step 6a: Create Draft Pull Request

Use `mcp__github__create_pull_request` with:
- **owner**: detected in Step 0
- **repo**: detected in Step 0
- **title**: `AB#{STORY_NUMBER}: {SHORT_DESCRIPTION}` — under 70 chars
- **body**:
  ```
  ## Summary
  <2-3 bullet points summarizing the changes>
  ```
  **Do NOT add a Test Plan, Checklist, Notes, or any other section.**
- **base**: `main`
- **head**: current branch name
- **draft**: `true`

Capture the returned PR number and PR URL.

---

## Step 7: Add Copilot as Reviewer

Use `mcp__github__request_copilot_review` with:
- **owner**: detected in Step 0
- **repo**: detected in Step 0
- **pullNumber**: the PR number captured in Step 6a

If this fails, inform the user to add the reviewer manually via the GitHub UI. Do not abort.

---

## Step 8: Assign PR to Current User

1. Get the authenticated user's login using `mcp__github__get_me`
2. Assign the PR:
   ```bash
   gh pr edit <PR_NUMBER> --repo <owner>/<repo> --add-assignee <login>
   ```

If this fails, inform the user without aborting.

---

## Step 9: Assign 'AI Generated' Label

1. Check label exists via `mcp__github__get_label` with `name: "AI Generated"`
2. If not found, create it:
   ```bash
   gh label create "AI Generated" --repo <owner>/<repo> --color 5319e7 --description "Created by AI"
   ```
3. Assign to the PR:
   ```bash
   gh pr edit <PR_NUMBER> --repo <owner>/<repo> --add-label "AI Generated"
   ```

If any label step fails, inform the user without aborting.

---

## Step 10: Report Results

Print a final summary table:

| Item | Result |
|---|---|
| Commit | `<hash>` — `<message>` |
| Branch | `<branch-name>` |
| Files committed | `<list>` |
| Push | Success / Failed |
| Pull Request | `<PR URL>` (draft) / `<PR URL>` (already existed — skipped) |
| Copilot reviewer | Added / Failed (add manually) / Skipped (PR existed) |
| Assignee | `<login>` assigned / Failed / Skipped (PR existed) |
| AI Generated label | Assigned / Created + Assigned / Failed / Skipped (PR existed) |
