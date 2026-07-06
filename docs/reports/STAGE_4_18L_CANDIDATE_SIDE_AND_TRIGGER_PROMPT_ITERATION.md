# Stage 4.18-L — Candidate Side + Entry Trigger Prompt/Schema Iteration

**Date:** 2026-07-07 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** code + offline analyzer replay only — **no soak**  
**J-R1 input:** `/data/stage4_ai_decisions_418j_r1_schema_enforced_regression_30m`  
**Analyzer output:** `/data/stage4_18l_j_r1_failure_analysis`

---

## 1. J-R1 / K summary

| Stage | Verdict |
|-------|---------|
| 4.18-J-R1 | **PARTIAL** — technical PASS, quality FAIL |
| 4.18-K | **CODE PASS** — failure analyzer v1 |

J-R1 quality failures: `within_cap=2`, `above_cap=13`, `directional_bias_without_candidate_side=14`, `missing_paper_fields=12`, 0 graduations.

---

## 2. Why Stage 4.19 remains blocked

- `calibration_total_graduations=0` (BTC=0, ETH=0)
- `recommended_mode_for_419=none`
- `within_cap (2) < above_cap (13)`
- Operator gate requires BTC **and** ETH graduation with quality PASS

**Stage 4.19 was NOT started.**

---

## 3. candidate_side missing diagnosis

J-R1 offline replay (418-L analyzer):

| Symbol | candidate_side_missing_rate |
|--------|----------------------------|
| BTCUSDT | **1.0** (6/6) |
| ETHUSDT | **1.0** (3/3) |
| SOLUSDT | **1.0** (5/5) |
| PEPEUSDT | **1.0** (1/1) |

**Root cause:** LLM outputs `directional_bias=LONG/SHORT` but leaves `candidate_side=NONE` on nearly all watch intents. Schema enforcement correctly flags `directional_bias_without_candidate_side` but prompt did not require BUY/SELL pairing.

---

## 4. entry_trigger missing diagnosis

| Symbol | missing_entry_trigger_rate |
|--------|---------------------------|
| BTCUSDT | **1.0** |
| ETHUSDT | **1.0** |
| SOLUSDT | **1.0** |
| PEPEUSDT | **1.0** |

**Root cause:** Watch intents treated as vague observation — `entry_trigger.type=none` or missing. 418-J examples showed invalidation distance but did not mandate non-none `entry_trigger` with side.

---

## 5. Prompt changes (418-L)

**File:** `tools/research/stage4_prompt_builder.py`

Added Stage 4.18-L worked examples:

1. **BTC valid watch** — SHORT bias → `candidate_side=SELL`, MAE 0.30%, `entry_trigger.type != none`
2. **ETH valid watch** — LONG bias → `candidate_side=BUY`, MAE 0.30%, full paper fields
3. **Bias without side INVALID** — `directional_bias_without_candidate_side`, LONG→BUY, SHORT→SELL
4. **Missing entry_trigger INVALID** — `missing_paper_fields` for watch without trigger/invalidation
5. **MAE above cap skip** — preserved `mae_risk_too_high`, no MAE deflation

Paper-readiness rules updated: watch MUST include `candidate_side` when bias is directional.

---

## 6. Analyzer changes (418-L)

**File:** `tools/research/stage4_paper_entry_failure_analyzer.py`

New outputs:

- `candidate_side_missing_rate_by_symbol`
- `missing_entry_trigger_rate_by_symbol`
- `valid_watch_candidate_count_by_symbol`
- `top_examples` (side missing, missing fields, MAE above cap)
- `recommendations` (auto-suggests prompt vs 60m sample path)

---

## 7. Schema enforcement (unchanged — verified)

**Files:** `stage4_paper_readiness.py`, `stage4_decision_schema.py`

- Bias without side flagged (enter_candidate blocks; watch logs flag)
- Missing `entry_trigger` / `invalidation` → `missing_paper_fields`
- MAE above cap → `mae_above_symbol_cap`
- Not `parse_error`; paper readiness only

No RG threshold changes.

---

## 8. Offline analyzer replay on J-R1

| Metric | Value |
|--------|-------|
| `valid_watch_candidate_count` (all symbols) | **0** |
| `mae_above_symbol_cap_count` | 13 |
| `directional_bias_without_candidate_side_count` | 14 |
| `missing_paper_fields_count` | 12 |

**Recommendations emitted:**

1. Reinforce LONG→BUY / SHORT→SELL prompt examples (all majors)
2. Reinforce `entry_trigger.type != none` for watch
3. After 418-L-R1 code pass, consider 60m read-only **only with operator approval** if valid_watch still 0

Replay does **not** increase graduations — confirms diagnosis only.

---

## 9. Next regression plan

1. **418-L-R1:** Runtime gate → **30m** dry-run with 418-L prompt (default next step)
2. Success criteria: `candidate_side_missing_rate` drops, `missing_entry_trigger_rate` drops, `valid_watch_candidate_count > 0`, `within_cap > above_cap`
3. **60m sample:** defer until 418-L-R1 evaluated; requires **explicit operator approval** (not auto)

---

## 10. Should 60m be considered?

**Not yet.** 418-L addresses root causes (side + trigger) in prompt. Run **418-L-R1 30m** first. If PARTIAL with improved field compliance but `no_consecutive_tick` only, then propose 60m to operator — do not auto-run.

---

## 11. Safety confirmation

| Check | Value |
|-------|-------|
| 30m / 60m soak in this step | **NO** |
| Stage 4.19 started | **NO** |
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| RG thresholds changed | **NO** |
| Production / btc-auto / ARM / radar | **not touched** |

---

## 12. Verdict

**`STAGE_4_18L_CODE_PASS`** — prompt + analyzer iteration complete; stopped at gate.

**Next:** **418-L-R1** 30m runtime-gated regression (operator-triggered; not auto-started).
