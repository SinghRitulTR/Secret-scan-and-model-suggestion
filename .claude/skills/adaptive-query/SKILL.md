---
name: adaptive-query
description: Standalone test skill for the intelligent model routing system. Routes any query through the full adaptive routing pipeline — router decides model, executor answers, evaluator scores, escalation if needed, result logged. Use this to test and validate routing behavior before /task integration.
argument-hint: "<your query here>"
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, AskUserQuestion
---

You are testing the intelligent model routing system in isolation. Route the following query through the full pipeline.

**QUERY:** $ARGUMENTS

If $ARGUMENTS is empty, use AskUserQuestion to ask: "What query would you like to route through the adaptive model system?"

---

## Step 1 — Classify Query Type

Classify the query into one of:
- PLANNING — architecture, design, system integration
- IMPLEMENTATION — write code, implement feature, add function
- CODE_REVIEW — review diff, find bugs, check quality
- TEST_GENERATION — write tests, generate test cases
- BUILD_DIAGNOSIS — why is build failing, fix compilation error
- SECURITY_SCAN — find vulnerabilities, check for issues
- SUMMARIZATION — summarize, explain, describe
- GIT_OPS — branch, commit, merge, PR operations

Also assess story complexity:
- HIGH: multiple systems, security implications, > 5 requirements
- MEDIUM: standard feature, 2–5 requirements, 1–3 components
- LOW: single file, 1–2 requirements, config/doc/simple change

---

## Step 2 — Get Routing Decision

Spawn sub-agent (subagent_type: `adaptive-router`):

> PHASE: <query_type>
> COMPLEXITY: <assessed_complexity>
> QUERY_SUMMARY: <first 150 chars of query>

Store returned JSON as ROUTING_DECISION.

---

## Step 3 — Execute Query

Spawn sub-agent (subagent_type: `query-executor`, model: ROUTING_DECISION.decided_model_id):

> Query: <full query>
> Context: This is a <query_type> task at <complexity> complexity.

Store returned answer as EXECUTOR_ANSWER.

---

## Step 4 — Evaluate Confidence

Spawn sub-agent (subagent_type: `confidence-evaluator`, model: `haiku`):

> QUERY: <full query>
> ANSWER: <EXECUTOR_ANSWER>

Store returned JSON as EVAL_RESULT.

---

## Step 5 — Escalate If Needed

If EVAL_RESULT.score < 70:

Determine escalation model:
- If current model is haiku → escalate to sonnet
- If current model is sonnet → escalate to opus
- If current model is opus → accept result with LOW_CONFIDENCE flag, no further escalation

Re-spawn executor at escalation model. Re-run evaluator. Store new results.
Track number of escalations.

---

## Step 6 — Log Result

Append one line to `.claude/data/routing-log.jsonl`:

```json
{"timestamp":"<ISO timestamp>","run_id":"adaptive-query-test","phase":"<query_type>","complexity":"<complexity>","routing_stage":"<ROUTING_DECISION.routing_stage>","model_decided":"<ROUTING_DECISION.decided_model>","final_model":"<final model used>","escalated":<true/false>,"escalation_count":<n>,"confidence_score":<final score>,"token_count":0,"retry_count":<escalation_count>,"downstream_build_failed":false,"user_revision_requested":false,"pr_number":null,"pr_review_comments":null}
```

Also rebuild stats-cache.json: read all lines from routing-log.jsonl, group by "phase_COMPLEXITY" key, compute avg_confidence, success_rate (entries where escalated=false / total entries), entry_count per group. Write updated stats-cache.json.

---

## Step 7 — Display Result

```
┌──────────────────────────────────────────────────────────────┐
│  ADAPTIVE QUERY RESULT                                       │
├──────────────────────────────────────────────────────────────┤
│  Query type:      <type>                                     │
│  Complexity:      <LOW/MEDIUM/HIGH>                          │
│  Routing stage:   <COLD_START/LEARNING/MATURE>               │
│  Model decided:   <model>  (<reasoning>)                     │
│  Final model:     <model>  (escalated: <yes/no>)             │
│  Confidence:      <score>/100  <flags if any>                │
├──────────────────────────────────────────────────────────────┤
│  ANSWER:                                                     │
│  <executor answer>                                           │
└──────────────────────────────────────────────────────────────┘
  ✓ Result logged to routing-log.jsonl
```
