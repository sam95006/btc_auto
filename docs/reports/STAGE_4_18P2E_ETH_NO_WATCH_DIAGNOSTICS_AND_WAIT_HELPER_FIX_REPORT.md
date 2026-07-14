# Stage 4.18-P2E — ETH No-Watch Diagnostics + Wait Helper Robustness Fix

**Verdict:** `STAGE_4_18P2E_PASS`  
**Mode:** offline diagnostics / code-only  
**Date:** 2026-07-14  
**Source:** Stage 4.18-P2D-R1 actual-only + P2B/P2C/P2D references  
**Output:** `/data/stage4_18p2e_eth_no_watch_diagnostics`

---

## 1. P2D-R1 recap

| Item | Value |
|------|--------|
| Verdict | `STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH` |
| Commit | `8ce1d8d` |
| technical_valid | true |
| tick_count | 6 |
| effective_decision_count | 18 |
| parse_error_count | 0 |
| prompt_repair_runtime_present | true |
| ETH valid_watch | **0** |
| ETH followup_cases | **0** |
| ETH graduation | **0** |
| BTC valid_watch | 1 (last tick, no follow-up) |
| BTC graduation | 0 |
| Stage 4.19 readiness | false |
| Flags | reset |
| 60m | not run |

---

## 2. Why P2D repair could not be validated

P2D repair depends on a **prior ETH watch** so that:

- `previous_watch_context` can inject
- direction-collapse guard can fire on LONG/BUY → NONE/NONE
- confidence-collapse reason can be required

P2D-R1 sample never produced an ETH valid_watch, so repair effectiveness remained `false` due to **sample insufficient**, not because repair was proven wrong.

---

## 3. ETH no-watch analysis (P2D-R1 actual-only)

| Metric | Value |
|--------|--------|
| eth_decision_count | **5** |
| eth_provider_distribution | groq×3 / cerebras×2 |
| eth_intent_distribution | soft_skip×3 / hard_skip×2 |
| eth_confidence_distribution | 0.20–0.35×4 / lt_0.20×1 |
| eth_directional_bias_distribution | NONE×5 |
| eth_candidate_side_distribution | NONE×5 |
| eth_block_reason_counts | skip_intent×5 |
| eth_entry_trigger_present_count | 0 |
| eth_invalidation_present_count | 0 |
| eth_mae_above_cap_count | 0 |
| eth_valid_watch_count | 0 |
| eth_watchlist_count | 0 |
| eth_graduation_count | 0 |

All ETH decisions were skip with NONE direction / side and low confidence. No watch-shaped candidate appeared.

---

## 4. Comparison with P2B/P2C ETH watch case

| Field | P2B watch reference | P2D-R1 ETH |
|-------|---------------------|------------|
| provider | cerebras | mixed groq/cerebras (skips) |
| confidence | 0.55 | mostly 0.20–0.35 |
| directional_bias | LONG | NONE |
| candidate_side | BUY | NONE |
| mae_risk_estimate_pct | 0.3 (within cap) | N/A (skip) |
| outcome | valid_watch=1 then follow-up hard_skip | valid_watch=0 |

P2C classified the historical watch→NONE collapse as `confirmation_prompt_too_strict` (system issue). That path was never re-entered in P2D-R1.

---

## 5. No-watch root cause

**`sample_market_no_edge`**

Evidence:

- majority skip intents
- confidence low
- directional_bias / candidate_side all NONE
- MAE above_cap count = 0
- no evidence that P2D prompt repair over-suppressed a watchable ETH case
- fields missing for triggers are expected on skip intents, not proof of over-conservative repair

| Flag | Value |
|------|--------|
| prompt_repair_over_conservative_suspected | **false** |
| sample_market_no_edge_suspected | **true** |
| needs_prompt_adjustment | **false** |
| needs_another_short_regression | **true** (operator-approved, when ETH watch conditions reappear) |
| should_run_60m | **false** |
| stage_419_readiness | **false** |
| should_start_419 | **false** |

**next_runtime_regression_condition:**  
`wait_for_next_operator_approved_short_regression_when_eth_watch_conditions_reappear`

---

## 6. Wait helper failures and fixes

Known P2D-R1 wait failures:

1. **f-string syntax error** in ad-hoc wait scripting / fragile brace escaping  
2. **tick_count=6 reached** but `dry_run_completed=false` → infinite poll until timeout

Fixes in `tools/research/wait_stage4_cloud_dry_run.py`:

- brace-safe `build_summary_poll_command` (no brittle f-string dict literals)
- `extract_json_object` tolerates npm warn noise
- `evaluate_wait_status`: if expected tick_count reached + summary present + effective_decision_count present, return **`completed_needs_finalize`** / `partial_completion_or_finalize_needed` instead of waiting forever
- timeout only when ticks not reached / no progress
- no trading state mutation; no Stage 4.19 trigger

Tests: `tests/test_stage4_wait_helper_robustness.py` — PASS

---

## 7. Why no 60m yet

- ETH repair validation still blocked by missing ETH watch sample
- Extending duration does not fix sample composition
- Gate remains: diagnose / wait for ETH watch conditions, then short regression — not 60m soak

---

## 8. Why Stage 4.19 remains blocked

- actual_non_shadow BTC graduation = 0 (this sample)
- ETH graduation = 0
- no order / mock / ARM / production / permanent routing

---

## 9. Safety confirmation

| Check | Result |
|-------|--------|
| offline_only | true |
| llm_called | false |
| order_sent | false |
| exchange_private_api_called | false |
| mae_cap_changed | false |
| confidence_floor_changed | false |
| prompt changed | false |
| schema changed | false |
| state machine changed | false |
| RG / MAE floor / routing permanent | untouched |
| Stage 4.19 started | false |
| production / btc-auto | untouched |

---

## 10. Final verdict

**`STAGE_4_18P2E_PASS`**

ETH no-watch is classified as **sample_market_no_edge**. P2D repair is present but still unvalidated at runtime. Wait helper robustness fixed for future short regressions.

---

## 11. Next step recommendation

1. Do **not** run 60m.
2. Do **not** start Stage 4.19.
3. Do **not** permanently change routing.
4. Do **not** change prompt/MAE/confidence floors now.
5. Wait for operator-approved short regression **when ETH watch conditions reappear** (to exercise previous_watch_context / collapse guard).
6. Prefer wait helper `completed_needs_finalize` path if tick budget finishes with `dry_run_completed=false`.

---

## Tools / tests

- `tools/research/stage4_eth_no_watch_diagnostics.py`
- `tools/research/wait_stage4_cloud_dry_run.py`
- `tests/test_stage4_eth_no_watch_diagnostics.py`
- `tests/test_stage4_wait_helper_robustness.py`

```text
python -m unittest tests.test_stage4_eth_no_watch_diagnostics -v
python -m unittest tests.test_stage4_wait_helper_robustness -v
```
