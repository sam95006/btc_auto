# Stage 4.18-P1-R1 — 30m BTC Dual-Provider Shadow Sample

**Date:** 2026-07-10 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Service:** `nexus-stage3-bybit-demo-learning`  
**Output dir:** `/data/stage4_ai_decisions_418p1_r1_btc_shadow_30m`  
**Mode:** read-only 30m cloud dry-run — shadow diagnostic only, **no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18P1_R1_PASS`**

| Layer | Result |
|-------|--------|
| Runtime gate (post P1 sync) | **PASS** |
| 30m technical soak | **PASS** (6/6 ticks, 20 effective, parse=0) |
| Shadow JSONL isolation | **PASS** (`btc_shadow_provider_decisions.jsonl`, 6 rows) |
| Shadow excluded from paper/calibration/graduation/4.19 | **PASS** |
| Post-run flag reset | **PASS** (DRY=0, shadow flags=false) |
| Safety (orders/mock/ARM/radar/production) | **PASS** |
| BTC shadow watch yield vs actual | **No improvement** (shadow valid_watch=0, actual BTC valid_watch=1) |
| Stage 4.19 | **BLOCKED** (0 graduations) |

**Note:** An earlier invalid attempt (pre-P1 runtime sync, corrupted `/data/stage4_418f_runtime_patch`) produced 19 effective decisions with **no shadow JSONL**. That run is **not** scored. The scored run below used a clean output dir after `sync_418p1_runtime_to_zeabur.py` (including patch-dir fix).

---

## 2. P1 implementation summary (baseline)

From commit `bcd1ea2` (`STAGE_4_18P1_PASS`):

- Shadow requires **both** `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED=true` and `STAGE4_BTC_DUAL_PROVIDER_SHADOW=true`.
- Actual path unchanged; shadow writes only to `btc_shadow_provider_decisions.jsonl`.
- Shadow excluded from `effective_decision_count`, paper logger, calibration, graduation, Stage 4.19 readiness.
- Unit tests: 25/25 related shadow tests at P1 code freeze.

---

## 3. Runtime gate

| Check | Result |
|-------|--------|
| Service RUNNING | yes |
| `/health` | 200 |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` (pre-run) | 0 |
| `runtime_version_check_passed` | true |
| `app_file_stale_suspected` | false |
| P1 shadow modules importable | yes (after sync + patch-dir repair) |
| `stage_marker` (runtime check) | `4.18-N` (P1 files present via runtime patch) |
| `order_allowed` / `mock_allowed` / `arm` / `radar` / `production` | all false/off |

**Runtime sync:** `tools/research/sync_418p1_runtime_to_zeabur.py` uploaded P1 files and refreshed `/data/stage4_418f_runtime_patch/` so entrypoint re-apply does not restore corrupted `stage4_prompt_builder.py`.

---

## 4. 30m technical result

| Metric | Value |
|--------|-------|
| `cloud_dry_run_completed` | true |
| `tick_count` / `expected_tick_count` | 6 / 6 |
| `effective_decision_count` | 20 (target 20) |
| `parse_error_count` | 0 |
| `validator_passed` | true |
| `technical_valid` | true |
| `mock_ai_used_count` | 0 |
| `order_sent_count` | 0 |
| `provider_success_distribution` | groq=2, cerebras=18 |
| `fallback_reason_distribution` | groq_rate_limited=18 |
| `paper_ready_watch_count` (actual) | 3 |

---

## 5. Shadow diagnostics

| Metric | Value |
|--------|-------|
| `shadow_jsonl_exists` | true |
| `btc_shadow_decision_count` | 6 |
| `btc_shadow_valid_watch_count` | **0** |
| `btc_shadow_divergence_count` | 5 |
| `btc_shadow_soft_skip_count` | 1 |
| `btc_shadow_provider_distribution` | cerebras=1, groq=5 |
| `actual_provider_distribution` (BTC ticks) | groq=1, cerebras=5 |
| `intent_delta` | soft_skip→watch: 1; soft_skip→unknown: 3; watch→unknown: 1; soft_skip→soft_skip: 1 |
| `shadow_excluded_from_paper_logger` | true |
| `shadow_excluded_from_calibration` | true |
| `shadow_excluded_from_graduation` | true |
| `shadow_excluded_from_stage_419_readiness` | true |

**Interpretation:** Shadow ran on every BTC tick and detected provider intent divergence (5/6), but **no shadow row qualified as valid_watch** under current rules. One case moved from actual `soft_skip` to shadow `watch`, but it did not pass full paper-readiness gates in shadow diagnostics.

---

## 6. Actual provider result

| Symbol | Intent distribution (actual) | Valid watch (rules) |
|--------|------------------------------|---------------------|
| BTCUSDT | soft_skip=5, watch=1 | **1** |
| ETHUSDT | soft_skip=1, watch=1, hard_skip=4 | 1 |
| SOLUSDT | watch=1, soft_skip=3 | 1 |
| PEPEUSDT | soft_skip=4 | 0 |

Provider field compliance (actual `ai_decisions.jsonl` only): Cerebras 18 decisions, 3 valid_watch candidates; Groq 2 decisions, 0 valid_watch.

---

## 7. Shadow provider result

Opposite-provider shadow calls completed for all 6 BTC ticks. Shadow provider mix: Groq×5 (when actual was Cerebras), Cerebras×1 (when actual was Groq). **Shadow valid_watch=0** — opposite provider did not produce a stable better watch signal in this window.

---

## 8. BTC actual vs shadow divergence

- **5/6** BTC ticks: `provider_divergence_detected=true`
- **1/6**: actual `soft_skip` vs shadow `watch` (divergence without shadow valid_watch promotion)
- **3/6**: shadow returned `unknown` intent (provider/parse edge on opposite path)
- Actual BTC had **1** valid_watch; shadow had **0** → **no evidence** that Cerebras shadow consistently beats Groq actual (or vice versa) in this 30m sample.

---

## 9–11. Shadow exclusion confirmations

| Path | Shadow used? | Evidence |
|------|--------------|----------|
| Paper logger | **no** | 20 events written from actual only; shadow IDs absent |
| Calibration replay | **no** | 0 graduations; shadow not in inputs |
| Graduation | **no** | `hypothetical_graduation_count=0` all modes |
| Stage 4.19 readiness | **no** | `stage_419_readiness=false` |

Validator: `validator_passed=true`, no `shadow_row_in_ai_decisions` errors.

---

## 12. P2 routing experiment recommendation

**Do not design/enable P2 live routing yet.**

Reasons:

1. Shadow safety path validated — isolation works.
2. Shadow **did not** demonstrate higher BTC valid_watch yield than actual in this window.
3. Heavy Groq TPM cooldown (18 Cerebras fallbacks) still dominates actual routing; shadow opposite-provider calls add diagnostic value but not a clear routing win.
4. Stage 4.19 remains blocked (0 BTC/ETH graduations).

**Next design step (offline only):** extend shadow diagnostics with per-tick paired comparison export before any P2 routing experiment proposal.

---

## 13. Safety confirmation

| Guard | Status |
|-------|--------|
| Orders / demo / paper execution | not sent |
| ARM / radar / production / btc-auto | not touched |
| Risk Governor thresholds | unchanged |
| BTC MAE cap / confidence floor | unchanged |
| Actual provider routing | unchanged |
| Post-run DRY + shadow flags | reset to safe defaults |

---

## 14. Final verdict

**`STAGE_4_18P1_R1_PASS`** — technical and safety criteria met; shadow pipeline works in real 30m flow. **Stop at gate.** Do **not** run 60m. Do **not** start Stage 4.19.

**Observation (not a fail):** In this sample, BTC Cerebras shadow did **not** prove more stable/better watch yield than actual Groq/Cerebras mix.

---

## Commands run (operator reference)

```bash
python tools/research/sync_418p1_runtime_to_zeabur.py
# Zeabur env apply + restart (P1-R1 vars, then post-reset vars)
python tools/research/validate_stage4_ai_decision_outputs.py \
  --output-dir /data/stage4_ai_decisions_418p1_r1_btc_shadow_30m --require-real-llm
python tools/research/stage4_btc_shadow_diagnostics.py \
  --input-dir /data/stage4_ai_decisions_418p1_r1_btc_shadow_30m \
  --output-dir /data/stage4_18p1_r1_btc_shadow_diagnostics
python tools/research/stage4_provider_field_compliance_review.py \
  --input-dir /data/stage4_ai_decisions_418p1_r1_btc_shadow_30m \
  --output-dir /data/stage4_18p1_r1_provider_field_compliance_review
python tools/research/stage4_paper_event_logger.py \
  --input-dir /data/stage4_ai_decisions_418p1_r1_btc_shadow_30m \
  --output-dir /data/stage4_paper_events_418p1_r1_actual_only --mode append-only
python tools/research/stage4_watchlist_followup_simulator.py --calibration-replay \
  --input-dir /data/stage4_ai_decisions_418p1_r1_btc_shadow_30m \
  --paper-events-dir /data/stage4_paper_events_418p1_r1_actual_only \
  --output-dir /data/stage4_18p1_r1_actual_only_calibration
```
