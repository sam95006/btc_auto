# Stage 4.18-P2D-R1 — ETH Follow-up Prompt Runtime Regression

**Verdict:** `STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH`  
**Mode:** operator-approved 30m read-only cloud dry-run (BTC Cerebras-first experiment, not permanent)  
**Date:** 2026-07-13  
**Output:** `/data/stage4_ai_decisions_418p2d_r1_eth_followup_prompt_30m`  
**Analysis:** `/data/stage4_18p2d_r1_runtime_regression_analysis`

---

## 1. P2D recap

P2D code-only repair added:

- `previous_watch_context` injection into `build_decision_prompt`
- entry_trigger / invalidation / MAE / context continuity recheck requirements
- direction collapse guard
- confidence collapse reason requirement
- static expected behavior: `continuation_watch_or_confirmation_pending`

P2D-R1 purpose: prove that repair in **runtime** prevents unexplained ETH LONG/BUY → NONE/NONE collapse.

---

## 2. Runtime gate

| Check | Result |
|-------|--------|
| Health | 200 |
| Pre-run DRY | 0 |
| P2D prompt markers in runtime | **PASS** (`previous_watch_rechecked`, `direction_collapse_allowed`, `collapse_reason`) |
| `previous_watch_context` injection callable | **PASS** |
| Safety: ORDER/MOCK/ARM/RADAR/PRODUCTION | false / off |
| Stage 4.19 | not started |

Runtime env during run:

- `STAGE4_OUTPUT_DIR=/data/stage4_ai_decisions_418p2d_r1_eth_followup_prompt_30m`
- `STAGE4_CLOUD_DRY_RUN_MINUTES=30`
- `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED=true`
- `STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED=true`
- `STAGE4_BTC_PROVIDER_CHAIN=cerebras,groq`

---

## 3. 30m technical result

| Metric | Value |
|--------|-------|
| tick_count | **6** |
| effective_decision_count | **18** (target 20; short of target) |
| parse_error_count | **0** |
| mock_ai_used_count | **0** |
| order_sent_count | **0** |
| validator | **PASS** |
| technical_valid (ops) | **true** (6 ticks, parse=0, mock=0, order=0) |
| dry_run_completed flag | false (likely hung on effective-target shortfall after ticks finished) |

Note: run produced full tick budget; completion flag stayed false — reset still applied.

---

## 4. P2D prompt repair runtime confirmation

| Check | Result |
|-------|--------|
| prompt_repair_runtime_present | **true** (preflight + post-restart assert) |
| previous_watch_context_seen on decisions | **false** (no prior-watch cases to inject) |
| direction_collapse_guard_seen on decisions | **false** (no follow-up collapse path exercised) |
| confidence_collapse_reason_seen on decisions | **false** |

Repair code was live; this sample simply never reached an ETH watch→follow-up pair.

---

## 5. BTC graduation status

| Item | Value |
|------|--------|
| BTC provider distribution | cerebras×3 / groq×3 |
| BTC chain | cerebras,groq (override active during run) |
| BTC actual valid_watch | **1** (last-tick `watch` / SELL / conf=0.45 / Cerebras) |
| BTC actual graduation | **0** |

Last-tick BTC watch had **no follow-up tick**, so graduation path could not confirm.

---

## 6. ETH valid_watch / follow-up / graduation

| Item | Value |
|------|--------|
| ETH providers | groq×3 / cerebras×2 |
| ETH routing override | unchanged (not BTC override) |
| ETH decisions | soft_skip×3 / hard_skip×2 — all NONE |
| ETH actual valid_watch | **0** |
| ETH follow-up cases | **0** |
| ETH actual graduation | **0** |

---

## 7. ETH direction collapse check

| Item | Value |
|------|--------|
| eth_unexplained_direction_collapse_count | **0** |
| eth_confirmation_prompt_repair_effective | **false** (no ETH watch/follow-up sample to evaluate) |

Cannot claim repair effective or ineffective on collapse — **no ETH watch occurred**.

---

## 8. Actual non-shadow BTC+ETH graduation gate

| Gate | Result |
|------|--------|
| BTC graduation > 0 | false |
| ETH graduation > 0 | false |
| actual_non_shadow_btc_eth_graduation_met | **false** |
| stage_419_readiness | **false** |
| should_start_419 | **false** |

---

## 9. Why Stage 4.19 remains blocked

- ETH graduation = 0
- BTC graduation = 0 this sample
- ETH follow-up repair not exercised (no ETH watch)
- Permanent routing still unsupported

---

## 10. Flags reset confirmation

| Flag after reset | Value |
|------------------|--------|
| STAGE4_CLOUD_DRY_RUN_MINUTES | **0** |
| STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED | **false** |
| STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED | **false** |
| STAGE4_BTC_PROVIDER_CHAIN | empty |
| Health after reset | **200** |
| provider_override_reset | **true** |

---

## 11. Safety confirmation

| Check | Result |
|-------|--------|
| mock | 0 |
| orders | 0 |
| demo / paper execution | off |
| ARM / radar / production / btc-auto | untouched / off |
| MAE cap / confidence floor / RG | unchanged |
| Permanent routing | not applied |
| Stage 4.19 | not started |
| 60m | not run |

---

## 12. Final verdict

**`STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH`**

Technical soak succeeded (6 ticks, parse=0, mock=0, order=0). BTC Cerebras-first experiment produced 1 late BTC watch without graduation. ETH produced **no valid_watch**, so P2D follow-up confirmation repair could not be runtime-validated on this sample.

---

## 13. Next step recommendation

`no 60m yet; inspect sample / market context`

Suggested next (operator-gated, not auto):

1. Inspect why ETH soft/hard-skipped for the full 30m (market vs provider yield).
2. Only after an ETH valid_watch appears, re-run a **short** regression focused on follow-up confirmation — still no 60m / no Stage 4.19 / no permanent routing by default.
