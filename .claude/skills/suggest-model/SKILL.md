---
name: suggest-model
description: Preview the routing matrix and cost estimate for a story description, or show current routing system status
argument-hint: "[optional] \"story description or feature summary\""
allowed-tools: Read, Glob, Bash, Agent
---

You are previewing the intelligent model routing system — either for a specific story description or showing overall system status.

Arguments: `$ARGUMENTS`

---

## Mode Detection

- **If `$ARGUMENTS` is non-empty**: run in **PREVIEW mode** — assess complexity, build routing table, estimate cost
- **If `$ARGUMENTS` is empty**: run in **STATUS mode** — show current routing system health and stats

---

## PREVIEW Mode

### Step 1: Assess Story Complexity

Read the story description from `$ARGUMENTS` and reason through these questions:

1. **Scope** — How many distinct services, modules, or layers does this touch? (3+ → HIGH signal)
2. **Volume** — How many distinct acceptance criteria are stated? (5+ → HIGH, 3–4 → MEDIUM signal)
3. **Nature** — Is this implementing a security/auth/payment *flow*, architectural change, or data migration? (yes → HIGH signal)
4. **Size** — Does this feel like more than 500 lines across more than 8 files? (yes → HIGH signal)
5. **Containment** — Is this clearly one file or component, 1–2 ACs, no architectural impact? (yes → LOW)

Classify as:
- **HIGH** — any signal from questions 1, 3, or 4, or 5+ ACs
- **MEDIUM** — none of HIGH but 3–4 ACs or touches 2 layers
- **LOW** — contained, 1–2 ACs, single component

Output:
```
Complexity assessment: LOW / MEDIUM / HIGH
Reasoning: <1-2 sentences>
```

### Step 2: Load Routing Configuration

For each file, check project-local first, then global fallback:

| File | Project-local | Global fallback |
|---|---|---|
| Routing rules | `.claude/config/model-routing.json` | `~/.claude/config/model-routing.json` |
| Floor constraints | `.claude/config/phase-floors.json` | `~/.claude/config/phase-floors.json` |
| Run history | `.claude/data/routing-log.jsonl` | `~/.claude/data/routing-log.jsonl` |
| Aggregated stats | `.claude/data/stats-cache.json` | `~/.claude/data/stats-cache.json` |
| Overrides | `.claude/settings.json` | `~/.claude/settings.json` |

Project-local takes precedence. Global fallback means `/suggest-model` works in any repo after `setup.sh` — no per-project setup needed.

If config files do not exist, use these built-in defaults:
```
Floors: planner=sonnet, executor=sonnet(MED/HIGH)/haiku(LOW), tests=sonnet, security=sonnet, build=haiku, review=sonnet
Cold-start defaults: planner=sonnet(LOW/MED)/opus(HIGH), executor=haiku(LOW)/sonnet(MED)/opus(HIGH), build=haiku(LOW/MED)/sonnet(HIGH), review=sonnet(LOW/MED)/opus(HIGH)
```

### Step 3: Determine Routing Stage Per Phase

For each cognitive phase, look up `{phase}_{complexity}` entry count in `stats-cache.json`:
- Missing or count < 20: **COLD_START** → use `model-routing.json` defaults
- Count 20–99: **LEARNING** → compute score = avg_confidence × success_rate, pick cheapest passing model
- Count ≥ 100: **MATURE** → use semantic similarity (show as MATURE in table)

Mechanical phases always show **MECHANICAL / haiku**.

Apply floor constraints (never go below floor). Apply `model_overrides` from `settings.json` if present.

### Step 4: Estimate Tokens and Cost Per Phase

For each phase, estimate tokens using:

```
input_tokens = (description_chars ÷ 4) + 800 + prior_phase_output_tokens
output_tokens = token_defaults[phase][complexity]   (from model-routing.json, or historical avg if 10+ runs)
```

Prior phase context accumulation:
- Planner: no prior
- Executor: +1,200 (plan output)
- Tests: +4,700 (plan + implementation)
- Security: same as Tests
- Build: +5,300 (plan + impl + tests)
- Review: +5,700 (plan + impl + tests + build)

Cost per phase:
```
phase_cost = (input_tokens/1,000,000 × input_price) + (output_tokens/1,000,000 × output_price)
```

Evaluator cost per cognitive phase (Haiku):
```
eval_input = output_tokens + 400
eval_cost = (eval_input/1,000,000 × 0.80) + (150/1,000,000 × 4.00)
```

Escalation expected cost (per phase):
```
escalation_cost = escalation_rate × (output_tokens × next_tier_output_price/1,000,000)
```
Use `escalation_rate_default` from config (default 15%) if no historical data.

### Step 5: Display Routing Matrix

```
┌─────────────────────────────────────────────────────────────────────┐
│          ROUTING PREVIEW — "<story description (truncated)>"         │
│          Complexity: <LOW / MEDIUM / HIGH>                           │
└─────────────────────────────────────────────────────────────────────┘

Phase                    Model     Stage         Floor      Est. Cost
───────────────────────────────────────────────────────────────────────
Phase 3: Preflight       haiku     MECHANICAL    haiku      $0.001
Phase 4: Planning        <model>   <stage>       <floor>    $<cost>
Phase 5: Implementation  <model>   <stage>       <floor>    $<cost>
Phase 6: Secret Scan     haiku     MECHANICAL    haiku      $0.001
Phase 7a: Tests          <model>   <stage>       <floor>    $<cost>
Phase 7b: Security       <model>   <stage>       <floor>    $<cost>
Phase 8: Build Verify    <model>   <stage>       <floor>    $<cost>
Phase 9: Code Review     <model>   <stage>       <floor>    $<cost>
Phase 10: Commit/PR      haiku     MECHANICAL    haiku      $0.001
───────────────────────────────────────────────────────────────────────
Evaluator calls (×6)                                        $<total>
Escalation risk (15%)                                       $<total>
───────────────────────────────────────────────────────────────────────
TOTAL (intelligent routing)                                 $<total>
vs. all-Opus                                                $<total>
Estimated savings                                           <N>%
```

Also show:
```
Confidence threshold:  70/100 (escalate if below)
Escalation path:       haiku → sonnet → opus
```

### Step 6: Offer Override

Output:
```
To run with a different model tier, use:
  /task <story-number>   — then choose "Override: all Opus/Sonnet/Haiku" when prompted
```

---

## STATUS Mode

When called with no arguments, show current routing system health.

### Step 1: Load Data Files

Read in parallel:
- `.claude/data/routing-log.jsonl`
- `.claude/data/stats-cache.json`
- `.claude/config/model-routing.json`
- `.claude/settings.json`

If `routing-log.jsonl` does not exist or is empty:
```
Routing system status: NO DATA YET
Total runs logged: 0
All phases are in COLD_START stage.
Run /task to start accumulating routing history.
```
Then stop.

### Step 2: Compute Summary Stats

From `routing-log.jsonl`, aggregate:
- Total runs logged
- Total escalations (where `escalated: true`)
- Overall escalation rate
- Overall average confidence score
- Runs with `downstream_build_failed: true`

From `stats-cache.json`, for each `phase_COMPLEXITY` key, determine routing stage:
- entry_count < 20: COLD_START
- 20-99: LEARNING
- ≥ 100: MATURE

### Step 3: Display Status

```
┌─────────────────────────────────────────────────────────────┐
│              ROUTING SYSTEM STATUS                           │
└─────────────────────────────────────────────────────────────┘

Total runs logged:     <N>
Overall escalation:    <N>% (<X> of <Y> phases escalated)
Avg confidence:        <N>/100
Build failures:        <N>% of runs

Phase Performance:
──────────────────────────────────────────────────────────────
Phase / Complexity     Stage        Runs  Avg Conf  Esc Rate  Avg Tokens
──────────────────────────────────────────────────────────────
planner / LOW          COLD_START   <n>   —         —         —
planner / MEDIUM       COLD_START   <n>   —         —         —
planner / HIGH         COLD_START   <n>   —         —         —
executor / MEDIUM      LEARNING     <n>   <c>       <e>%      <t>
...
──────────────────────────────────────────────────────────────

Active model_overrides (from settings.json):
  <phase>: <model>  — or "None"

Cost efficiency vs. all-Opus baseline:
  Historical avg per run: $<actual>  vs. all-Opus: $<baseline>  (savings: <N>%)

Recommendation: Run /routing-review after every 20-30 tasks to apply data-driven improvements.
```

---

## Rules

- Do NOT spawn sub-agents — all computation is done inline in this skill
- If a config file is missing, use built-in defaults and note the missing file
- Round all costs to 4 decimal places ($0.0012 not $0.001234567)
- Do NOT modify any files
