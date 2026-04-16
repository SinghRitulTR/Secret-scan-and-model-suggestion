---
name: routing-review
description: Analyzes the routing history log, applies 5 rule-based checks, surfaces model routing recommendations, and writes approved changes to settings.json model_overrides. Run this periodically (every 20–30 runs) to improve routing defaults.
argument-hint: ""
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion, mcp__github__pull_request_read
---

You are the routing review assistant. You analyze past run data to find patterns and recommend routing improvements.

---

## Step 1 — Load Data

Read `.claude/data/routing-log.jsonl` — load all entries.
Read `.claude/config/model-routing.json` — current routing config.
Read `.claude/settings.json` — current model_overrides if any.

If routing-log.jsonl has fewer than 10 entries:
Output: "Not enough data yet for meaningful analysis. Run /adaptive-query or /task at least 10 times first."
Stop.

---

## Step 2 — Fetch PR Comments (for entries with pr_number set)

For any log entry where `pr_number` is not null and `pr_review_comments` is null:
Use `mcp__github__pull_request_read` to get the PR details and count review comments.
Update that entry in memory with the comment count.
(Note: do not write back to log file — just use in analysis)

---

## Step 3 — Apply 5 Rules

Group log entries by `phase` + `complexity`.

**Rule 1 — Escalation Rate Too High:**
For each (phase, complexity) group with ≥ 10 entries:
escalation_rate = entries_where_escalated / total_entries
If escalation_rate > 0.30:
→ Flag: recommend upgrading default model for this phase+complexity

**Rule 2 — Downstream Build Failure Correlation:**
For each entry in implementation-executor or implementation-planner groups:
downstream_fail_rate = entries_where_downstream_build_failed / total_entries
If downstream_fail_rate > 0.30:
→ Flag: recommend upgrading that phase's model

**Rule 3 — Token Count Too Low (Downgrade Opportunity):**
For each (phase, complexity) group with ≥ 10 entries:
avg_tokens = average of token_count across entries (exclude 0 values)
If avg_tokens > 0 AND avg_tokens < 400 AND current_floor != "haiku":
→ Flag: recommend downgrading (phase is consistently trivial)

**Rule 4 — User Revision Rate High:**
For each phase group:
revision_rate = entries_where_user_revision_requested / total_entries
If revision_rate > 0.20:
→ Flag: recommend upgrading that phase's model

**Rule 5 — PR Review Comment Rate High:**
For entries where pr_review_comments is not null, group by complexity:
avg_comments = average pr_review_comments for HIGH complexity entries
If avg_comments > 5:
→ Flag: recommend upgrading code-reviewer model for HIGH complexity

---

## Step 4 — Display Recommendations

If no rules triggered:
Output: "✓ No routing improvements needed based on current data. Routing is performing well."
Stop.

Otherwise display:

```
┌──────────────────────────────────────────────────────────────────┐
│  ROUTING REVIEW — <entry_count> runs analyzed                   │
│  Period: <earliest timestamp> to <latest timestamp>             │
├──────────────────────────────────────────────────────────────────┤
│  <For each recommendation:>                                      │
│                                                                  │
│  [N] ⚠ <phase> (<complexity>): <metric> = <value>              │
│      Rule triggered: <rule name>                                 │
│      Current default: <current model>                           │
│      Recommend: upgrade/downgrade to <model>                     │
│      Data: <specific numbers that triggered the rule>            │
└──────────────────────────────────────────────────────────────────┘
```

Use AskUserQuestion to ask: "Which recommendations would you like to apply?"
Show each recommendation as an option. Include "Apply all" and "Skip all" options.

---

## Step 5 — Apply Approved Recommendations

For each approved recommendation:

1. Read `.claude/settings.json`
2. Add or update `model_overrides` key:
   `model_overrides["<agent-name>"] = "<recommended-model>"`
3. Write updated settings.json

Output confirmation:
```
✓ Applied: <agent-name> → <model>
  Written to .claude/settings.json model_overrides
```

Display final summary of all changes made.
