---
name: suggest-model
description: Analyze any task description and show projected routing matrix with full token and cost prediction
argument-hint: "<description of what you want to do>"
allowed-tools: AskUserQuestion, Read
---

You are the model routing advisor. The intelligent routing system automatically assigns the right model to each workflow phase — this skill shows you what that routing looks like and projects the token and cost estimate.

If `$ARGUMENTS` is provided, assess the complexity of the described task and show the projected routing matrix with full cost prediction.

If `$ARGUMENTS` is empty, read `.claude/data/routing-log.jsonl` and `.claude/data/stats-cache.json` to show the current routing performance summary.

---

## With task description ($ARGUMENTS provided):

### Step 1 — Assess complexity

Reason holistically about the described task. Do NOT use keyword matching.
Consider: how many systems does this touch? How much ambiguity? How many edge cases?
Output your reasoning in 2–3 sentences before stating complexity: HIGH / MEDIUM / LOW.

### Step 2 — Read routing config

Read `.claude/config/model-routing.json` to get the model presets for the assessed complexity.
Read `.claude/config/phase-floors.json` to get the floor constraints.

### Step 3 — Check routing history

Read `.claude/data/routing-log.jsonl`.
Count total entries for each (phase, complexity) combination.

Determine routing stage per phase:
- 0–19 entries → COLD_START
- 20–99 entries → LEARNING
- 100+ entries → MATURE

For LEARNING phases: read `.claude/data/stats-cache.json` to get the recommended model if available.
For MATURE phases: use the model from stats-cache if available, else fall back to preset.
For COLD_START: use the static floor from phase-floors.json directly.

### Step 4 — Predict token cost per phase

**Token estimation approach:**

For each cognitive phase, compute:

```
INPUT TOKENS (exact):
  - Story/description context passed to agent ≈ len($ARGUMENTS) ÷ 4 tokens
  - System prompt + agent instructions ≈ 800 tokens (fixed overhead per phase)
  - Prior phase output passed as context (cumulative, grows each phase):
      Phase 4: +0 (no prior phase output)
      Phase 5: +plan_tokens (Phase 4 output)
      Phase 7a: +plan_tokens + impl_tokens
      Phase 7b: +plan_tokens + impl_tokens
      Phase 8: +impl_tokens + test_tokens
      Phase 9: +impl_tokens + test_tokens + build_tokens
  - For COLD_START: use these defaults for prior phase output sizes:
      plan_tokens = 1200, impl_tokens = 3500, test_tokens = 1800, build_tokens = 400
  - For LEARNING/MATURE: use avg_token_count from routing-log.jsonl history

OUTPUT TOKENS (history-based or default):
  - If history exists for this (phase, complexity): use avg_token_count from log
  - If no history (COLD_START): use these defaults:
      Phase 4 Planning:        LOW=800,  MEDIUM=1200, HIGH=2000
      Phase 5 Implementation:  LOW=2500, MEDIUM=4000, HIGH=6500
      Phase 7a Tests:          LOW=1200, MEDIUM=2000, HIGH=3000
      Phase 7b Security:       LOW=600,  MEDIUM=900,  HIGH=1200
      Phase 8 Build Verify:    LOW=300,  MEDIUM=400,  HIGH=600
      Phase 9 Code Review:     LOW=700,  MEDIUM=1100, HIGH=1800

CONFIDENCE EVALUATOR TOKENS (added after every cognitive phase):
  - Input: query + phase output ≈ output_tokens + 400 (fixed prompt)
  - Output: always small JSON response ≈ 150 tokens
  - Model: haiku (cheap — runs after every cognitive phase)
  - Count: 6 evaluator calls total (one per cognitive phase)

ESCALATION COST (history-based or default):
  - If history exists: escalation_rate from routing-log for (phase, complexity)
  - If no history: use 15% default escalation probability
  - Escalation adds one full retry at next tier model (same token count, higher price)
  - Expected escalation cost per phase = escalation_rate × (output_tokens × next_tier_price_per_token)
```

### Step 5 — Apply pricing

```
Model pricing (per 1M tokens):
  haiku:  input $0.80,  output $4.00
  sonnet: input $3.00,  output $15.00
  opus:   input $15.00, output $75.00
```

For each phase compute:
```
phase_cost = (input_tokens/1M × input_price) + (output_tokens/1M × output_price) + escalation_cost
```

Evaluator cost per call:
```
eval_cost = ((output_tokens + 400)/1M × 0.80) + (150/1M × 4.00)   [haiku pricing]
```

Mechanical phases (3, 6, 10) use haiku at approximately 200 input + 100 output tokens each.

### Step 6 — Display results

```
Routing Matrix — Token & Cost Prediction
Task: <first 60 chars of description>
Complexity: <HIGH/MEDIUM/LOW>  |  Confidence: <LOW=cold start, MED=some history, HIGH=10+ runs>

Phase                   Model      Stage        Est. Tokens    Est. Cost
────────────────────────────────────────────────────────────────────────
Phase 3: Preflight      haiku      mechanical      ~300         $0.0003
Phase 4: Planning       <model>    <stage>       ~<N>           $<X.XXXX>
  + Evaluator           haiku      evaluator       ~<N>         $<X.XXXX>
Phase 5: Implementation <model>    <stage>       ~<N>           $<X.XXXX>
  + Evaluator           haiku      evaluator       ~<N>         $<X.XXXX>
  + Escalation risk     <tier+1>   15% chance      ~<N>         $<X.XXXX>
Phase 6: Secret Scan    haiku      mechanical      ~300         $0.0003
Phase 7a: Tests         <model>    <stage>       ~<N>           $<X.XXXX>
  + Evaluator           haiku      evaluator       ~<N>         $<X.XXXX>
Phase 7b: Security      <model>    <stage>       ~<N>           $<X.XXXX>
  + Evaluator           haiku      evaluator       ~<N>         $<X.XXXX>
Phase 8: Build Verify   <model>    <stage>       ~<N>           $<X.XXXX>
  + Evaluator           haiku      evaluator       ~<N>         $<X.XXXX>
Phase 9: Code Review    <model>    <stage>       ~<N>           $<X.XXXX>
  + Evaluator           haiku      evaluator       ~<N>         $<X.XXXX>
Phase 10: Commit/PR     haiku      mechanical      ~300         $0.0003
────────────────────────────────────────────────────────────────────────
TOTAL (primary agents):                          ~<N> tokens    $<X.XX>
TOTAL (evaluators):                              ~<N> tokens    $<X.XX>
TOTAL (escalation risk):                         ~<N> tokens    $<X.XX>
────────────────────────────────────────────────────────────────────────
GRAND TOTAL (all sub-agents):                    ~<N> tokens    $<X.XX>

Estimate confidence: <LOW (cold start — no history) / MEDIUM (1–9 runs) / HIGH (10+ runs)>
Data source: <N> historical runs for this complexity level
```

If estimate is LOW confidence, add:
```
Note: These are cold-start defaults. Estimates improve automatically as runs are logged
to .claude/data/routing-log.jsonl. After 10 runs, accuracy typically improves by 40%.
```

---

## Without arguments (routing performance view):

Read `.claude/data/routing-log.jsonl` and `.claude/data/stats-cache.json`. Display:

```
Routing System Status
─────────────────────────────────────────────────────
Total runs logged: <N>
Overall escalation rate: <X>%
Overall avg confidence:  <Y>/100

Per-phase performance:
  Phase 4 Planning:          <avg_conf>/100  escalation <X>%  avg tokens <N>
  Phase 5 Implementation:    <avg_conf>/100  escalation <X>%  avg tokens <N>
  Phase 7a Tests:            <avg_conf>/100  escalation <X>%  avg tokens <N>
  Phase 7b Security:         <avg_conf>/100  escalation <X>%  avg tokens <N>
  Phase 8 Build Verify:      <avg_conf>/100  escalation <X>%  avg tokens <N>
  Phase 9 Code Review:       <avg_conf>/100  escalation <X>%  avg tokens <N>

Routing stages active:
  <list each phase and its current stage: COLD_START / LEARNING / MATURE>

Cost efficiency (if enough data):
  Estimated total cost per run:     $<X.XX>
  vs. all-Opus baseline:            $<Y.YY>
  Savings per run:                  $<Z.ZZ> (<P>%)

Run /routing-review for improvement recommendations.
```

If routing-log.jsonl is empty or has fewer than 5 entries:
```
Routing System Status
No run history yet. System is in COLD_START for all phases.
Run /adaptive-query "<task description>" to log your first entries.
Static floors are active — system is safe to use immediately.
```
