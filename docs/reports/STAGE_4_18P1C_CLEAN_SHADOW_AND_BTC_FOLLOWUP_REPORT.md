# Stage 4.18-P1C — Clean Shadow Sample + BTC Follow-up Gate

**Date:** 2026-07-11 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** 30m read-only clean shadow sample — **no P2, no 60m, no Stage 4.19**  
**Output:** `/data/stage4_ai_decisions_418p1c_clean_shadow_30m`

---

## 1. Executive summary

**Verdict: `STAGE_4_18P1C_PASS`**

| Layer | Result |
|-------|--------|
| Runtime P1B quota-aware code present | **PASS** |
| 30m technical soak | **PASS** (6/6 ticks, 23 effective, parse=0) |
| Shadow JSONL isolation | **PASS** (6 rows, Cerebras opposite) |
| Clean-sample improvement vs P1B | **PASS** (comparable 1→5; uncomparable no longer Groq tokens) |
| Shadow excluded from paper/calibration/graduation/4.19 | **PASS** |
| Flags reset (DRY=0, shadow off) | **PASS** |
| Safety | **PASS** (order=0, mock=0) |
| Auto P2 / 60m / Stage 4.19 | **NOT STARTED** (stop at gate) |

---

## 2. Runtime gate (pre-run)

| Check | Result |
|-------|--------|
| `/health` | 200 |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` | 0 |
| Shadow flags | false |
| `build_skipped_shadow_row` present | true |
| `shadow_groq_call_blocked_reason` present | true |
| `SHADOW_RESPECTS_GROQ_TPM_GOVERNOR` | true |
| `app_file_stale_suspected` | false |

P1B files re-synced into `/app` + `/data/stage4_418f_runtime_patch/` before soak.

---

## 3. 30m technical result

| Metric | Value |
|--------|-------|
| `cloud_dry_run_completed` | true |
| `tick_count` / expected | 6 / 6 |
| `effective_decision_count` | 23 (target 20) |
| `parse_error_count` | 0 |
| `validator_passed` | true |
| `technical_valid` | true |
| `mock_ai_used_count` | 0 |
| `order_sent_count` | 0 |
| `provider_success_distribution` | groq=18, cerebras=5 |
| `fallback_reason_distribution` | groq_rate_limited=5 |
| `paper_ready_watch_count` (actual) | 0 |

BTC actual intents: **6/6 soft_skip** (all Groq).

---

## 4. Shadow clean-sample result

| Metric | P1B (dirty) | P1C (this run) |
|--------|-------------|----------------|
| shadow rows | 6 | 6 |
| `shadow_call_skipped_count` | n/a (pre-fix hard calls) | **0** (correct: opposite was Cerebras) |
| `shadow_comparable_pair_count` | 1 | **5** |
| `shadow_uncomparable_pair_count` | 5 | **1** |
| uncomparable reasons | tokens×4, truncated×1 | **truncated×1 only** |
| `provider_skill_comparison_valid` | false | **true** |
| `shadow_valid_watch_count` | 0 | **5** |
| `actual_valid_watch_count` | 1 | **0** |
| actual BTC provider | mixed / Cerebras-heavy | **Groq×6** |
| shadow BTC provider | Groq-heavy (quota collision) | **Cerebras×6** |

### Why skipped_count=0 is correct

Actual BTC stayed on **Groq**. Opposite shadow provider is therefore **Cerebras**.  
Quota-aware Groq skip only applies when shadow would hard-call Groq (actual already on Cerebras / cooldown). That path was not entered — and Cerebras shadow calls succeeded for 5/6 ticks.

### Skill signal (diagnostic only)

- 5 comparable pairs: actual `soft_skip` → shadow Cerebras `watch` (valid_watch under current rules)
- 1 uncomparable: Cerebras truncation
- Offline tools therefore set `p2_routing_experiment_design_may_be_justified=true`

**Operator gate:** evidence may justify a **future P2 design review**, but P1C **does not** enable routing, does not run 60m, and does not start Stage 4.19.

---

## 5. BTC follow-up gate

| Field | Value |
|-------|-------|
| `btc_actual_valid_watch_count` | **0** |
| `btc_graduation_count` | 0 |
| `followup_tick_available` | false |
| `reason_no_graduation` | `no_btc_valid_watch` |
| `recommendation` | `no_btc_valid_watch_to_diagnose` |

This sample did **not** produce an actual BTC valid_watch, so the P1B “last-tick follow-up” issue could not be re-tested here. Shadow watches remain excluded from paper/calibration and cannot create graduations.

---

## 6. Paper / calibration / Stage 4.19 exclusions

| Path | Result |
|------|--------|
| Paper logger events | 23 (actual only); watchlist_count=0 |
| Calibration graduations | 0 all modes |
| `stage_419_readiness` | false |
| Shadow in paper/calibration/graduation | excluded |

---

## 7. Post-run reset

| Variable | After reset |
|----------|-------------|
| `STAGE4_CLOUD_DRY_RUN_MINUTES` | **0** |
| `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED` | **false** |
| `STAGE4_BTC_DUAL_PROVIDER_SHADOW` | **false** |
| `/health` | 200 |

---

## 8. Safety confirmation

| Guard | Status |
|-------|--------|
| Orders / demo / paper execution | none |
| ARM / radar / production / btc-auto | untouched |
| Actual provider routing | unchanged |
| RG thresholds / MAE cap / confidence floor | unchanged |
| Shadow into 4.19 readiness | false |

---

## 9. Final verdict

**`STAGE_4_18P1C_PASS`**

Clean 30m sample confirms:

1. P1B quota-aware runtime is live.
2. When actual stays on Groq, Cerebras shadow can produce **comparable** pairs (5/6) without Groq token collision.
3. Shadow still isolated from paper/calibration/graduation/4.19.
4. Data **may** support a later P2 **design** discussion — **not** auto-implementation.

**Stop at gate.** No P2. No 60m. No Stage 4.19.

### Next-step recommendation (operator only)

- Option A: Stage 4.18-P2 **design gate only** (no routing enable) using P1C comparable evidence.
- Option B: Another short sample focused on actual BTC valid_watch + follow-up ticks (not shadow routing).
- Do **not** start Stage 4.19 until actual BTC+ETH graduations > 0 from non-shadow decisions.
