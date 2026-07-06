# Stage 4.18-I — ETH MAE Alignment + Watchlist Confirmation Recovery

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Prior soak:** 4.18-H-R1 PARTIAL (`bd0155b`)  
**Mode:** code-only analysis + prompt iteration — **no 30m soak**

---

## 1. H-R1 result summary

| Metric | H-R1 |
|--------|------|
| Runtime gate | PASS |
| Technical soak | PASS (6/6, 21 effective, parse=0) |
| ETH watches | **4** (G-R1: 0) |
| ETH avg MAE | **0.454%** (cap 0.35%) |
| BTC avg MAE | **1.420%** (G-R1: 2.485%) |
| `within_cap` / `above_cap` | **2 / 17** |
| Graduations | **0** (G-R1: 1 BTC) |
| `recommended_mode_for_419` | **none** |

---

## 2. Why Stage 4.19 is still blocked

- `within_cap (2) < above_cap (17)` — MAE cap alignment not met
- `calibration_total_graduations = 0` — no BTC or ETH graduation
- ETH watches exist but most MAE still **> 0.35%**
- Watchlist confirmation dropped (G-R1: 1 confirmed → H-R1: 0)
- Formal Risk Governor thresholds **unchanged**

---

## 3. G-R1 vs H-R1 comparison (analysis)

New tool: `tools/research/stage4_mae_regression_compare.py`

| Dimension | G-R1 | H-R1 | Delta |
|-----------|------|------|-------|
| ETH watch intents | 0 | **4** | +4 |
| ETH avg MAE | N/A | 0.454% | new yield |
| BTC avg MAE | 2.485% | 1.420% | improved |
| PEPE avg MAE | 0.916% | 2.000% | worsened |
| SOL avg MAE | 2.800% | 2.217% | slightly better |
| `within_cap` | 7 | 2 | -5 |
| `above_cap` | 22 | 17 | -5 |
| BTC graduation (`major_mae_100_llm_mae`) | **1** | **0** | -1 |
| Watchlist confirmed (calibration) | 1 | 0 | -1 |

---

## 4. BTC graduation regression analysis

**Root cause (418-I compare tool):**

1. **MAE above cap on confirming ticks** — H-R1 BTC watches improved avg MAE but most ticks still > 0.35%; calibration mode `major_mae_100_llm_mae` blocks graduation at `mae_cap_violation_100pct`.
2. **Watchlist confirmation regression** — G-R1 had fewer watches (4) but one consecutive confirming pair; H-R1 had 6 BTC watches spread across ticks without a confirmed pair meeting side + MAE + confidence gates.
3. **418-H over-conservative skip bias** — more paper-ready watches emitted (19 summary) but many marked `decision_quality_incomplete` on MAE recompute → excluded from paper logger eligibility → fewer watchlist confirmations.
4. **`candidate_side_none`** — some BTC watches carry `directional_bias` but `candidate_side=NONE`, blocking graduation even when bias is clear.

**418-I fix:** BTC graduation recovery guidance — allow paper-ready watch when bias clear, side set, MAE ≤ 0.35%, confidence ≥ 0.40; do not over-skip qualifying watches.

---

## 5. ETH watch yield / MAE cap analysis

| Metric | H-R1 |
|--------|------|
| `eth_watch_count` | 4 |
| `eth_watch_mae_within_cap_count` | ~1 |
| `eth_watch_mae_above_cap_count` | ~3 |
| ETH graduation | 0 |

**ETH no-graduation cause:** watches produced with MAE **0.454% avg** — above 0.35% cap → `decision_quality_incomplete` → no watchlist confirmation → no graduation.

**418-I fix:**

- MAE = **invalidation distance** (reference_price → invalidation_price), not 15m volatility
- If ETH MAE > 0.35% → soft_skip/hard_skip (not paper-ready watch)
- If ETH MAE 0.28–0.35% → watch with `watch_followup_required=true`, `entry_trigger`, `invalidation`, `block_reason=null`
- No forced `enter_candidate` on ETH

---

## 6. Prompt changes (`stage4_prompt_builder.py`)

### ETH (418-I)
- Invalidation-distance MAE for watch intents
- Hard skip when MAE > 0.35%
- 0.28–0.35% band with follow-up fields
- Direction-only paper-ready watch (no forced enter_candidate)

### BTC graduation recovery
- Do not over-skip qualifying watches
- Paper-ready when bias + side + MAE ≤ 0.35% + confidence ≥ 0.40

### SOL / PEPE conservative
- No MAE deflation for graduation
- SOL > 0.25% / PEPE > 0.20% → skip or watchlist-only
- PEPE high volatility → soft_skip

### Runtime gate
- `check_stage4_runtime_version.py` updated with 418-I prompt hints
- Compare tool added to deploy package allowlist

---

## 7. Next 30m regression plan (4.18-I-R1)

**After code pass — not run in this step:**

1. Sync runtime patch (include `stage4_mae_regression_compare.py`)
2. `check_stage4_runtime_version.py --gate` must PASS (418-I hints)
3. 30m read-only soak with same env as H-R1
4. Run compare tool: G-R1 baseline vs I-R1 candidate
5. PASS criteria: `within_cap > above_cap`, BTC + ETH graduation > 0, `recommended_mode_for_419 != none`

---

## 8. Safety confirmation

| Check | Value |
|-------|-------|
| 30m soak run | **NO** |
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| Exchange private API | not called |
| RG thresholds | unchanged |
| Stage 4.19 | **NOT started** |

---

**`final_verdict`:** `STAGE_4_18I_CODE_PASS`

**`next_step_recommendation`:** Run **4.18-I-R1** 30m runtime-gated regression after deploy sync.

**Stopped at gate.**
