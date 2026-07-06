# Stage 4.18-J — Schema-Level MAE Cap Enforcement + Confirmation Diagnostics

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** code + offline replay only — **no new 30m soak**, no orders, no RG changes  
**I-R1 input:** `/data/stage4_ai_decisions_418i_r1_eth_mae_recovery_30m`  
**Offline outputs:**
- `/data/stage4_paper_events_418j_enforced_i_r1`
- `/data/stage4_18j_enforced_i_r1_calibration`
- `/data/stage4_18j_compare_g_r1_vs_i_r1`

---

## 1. I-R1 failure summary

| Layer | I-R1 result |
|-------|-------------|
| Runtime / technical | **PASS** (6/6 ticks, 22 effective, parse=0, order=0) |
| `within_cap` vs `above_cap` | **FAIL** (2 vs 15) |
| ETH avg MAE | **1.150%** (regression vs H-R1 **0.454%**) |
| ETH within-cap watches | **0** |
| BTC / ETH graduations | **0** |
| `recommended_mode_for_419` | **none** |
| Stage 4.19 | **blocked** |

418-I prompt tuning alone did not align ETH MAE to the 0.35% cap and did not recover BTC graduation.

---

## 2. Why prompt-only tuning is insufficient

- LLM continues to emit `mae_risk_estimate_pct` far above symbol caps (15/17 paper-ready watches above cap on I-R1).
- ETH watches used adverse distances ~0.8–1.5% while invalidation math implied tighter stops.
- Many BTC watches had `directional_bias` but `candidate_side=NONE`, blocking confirmation graduation.
- G-R1’s lone BTC graduation relied on fields that fail **418-J** enforcement (`entry_trigger.type=none`) — prompt compliance alone is not a reliable gate.

**418-J adds deterministic post-parse enforcement** so paper logger / simulator / compare classify failures without loosening formal RG thresholds.

---

## 3. Schema-level enforcement changes

**Files:** `stage4_paper_readiness.py`, `stage4_decision_schema.py`

For `decision_intent in {watch, enter_candidate}`:

| Rule | Effect |
|------|--------|
| `mae_risk_estimate_pct > symbol cap` | `decision_quality_incomplete=true`, `block_reason=mae_above_symbol_cap`, not `parse_error` |
| `mae > invalidation.max_adverse_move_pct` | `block_reason=mae_invalidation_inconsistent` |
| Missing `entry_trigger` or `invalidation` on watch | `block_reason=missing_paper_fields` |
| `directional_bias` LONG/SHORT + `candidate_side=NONE` | flag `directional_bias_without_candidate_side` (watch may still log; graduation blocked in simulator) |

Caps unchanged: BTC/ETH **0.35%**, SOL **0.25%**, PEPE **0.20%**.

Enforcement affects **paper readiness only** — no order path.

---

## 4. ETH acceptable / too-risky examples (418-J prompt)

Added worked examples in `stage4_prompt_builder.py`:

| Example | Reference | Invalidation | MAE | Intent |
|---------|-----------|--------------|-----|--------|
| ETH acceptable watch | 3000 | 2991 (0.30%) | **0.30%** | `watch`, eligible watchlist |
| ETH too-risky | 3000 | 2960 (1.33%) | **1.33%** | `soft_skip` / `hard_skip`, `mae_risk_too_high` |
| BTC acceptable watch | 100000 | 99700 (0.30%) | ≤0.35% | `watch` with side + conf ≥0.40 |
| SOL / PEPE | — | — | >0.25 / >0.20 | skip — do not deflate MAE for graduation |

---

## 5. BTC G-R1 graduation diagnostic

**Historical G-R1 graduation (pre-418-J replay rules):**

| Field | Value |
|-------|-------|
| `decision_id` | `beb61bde-19f9-4f8b-a0bc-05e8f7d2b07f` |
| Symbol | BTCUSDT |
| Side | **SHORT** (`candidate_side=SELL`) |
| Confidence | **0.62** |
| MAE | **0.30%** (within 0.35% cap) |
| Regime | **trend** (high vol) |
| Mode | `major_mae_100_llm_mae` |
| Confirmation | 2 consecutive watch ticks |

**418-J re-enforcement on G-R1 dataset:** `graduation_found=false` — same row now fails `missing_paper_fields` (`entry_trigger.type=none`). Historical graduation depended on lenient paper-field checks.

---

## 6. Watchlist confirmation regression diagnostic

**G-R1 vs I-R1 compare** (`/data/stage4_18j_compare_g_r1_vs_i_r1`):

| Breakdown bucket | Count (I-R1 candidate) |
|------------------|------------------------|
| `mae_above_cap` | **15** |
| `quality_incomplete` | **17** |
| `side_missing_on_confirmation` | **7** |
| `confidence_decreasing` | **2** |
| `no_consecutive_tick` | 0 |
| `provider_diff` | (folded into per-tick analysis) |

**Why H/I-R1 lost G-R1 BTC graduation:**

1. **MAE / quality:** Most BTC watches exceed cap or lack complete paper fields under 418-J rules.
2. **Side:** Frequent `candidate_side=NONE` with directional bias — confirmation cannot graduate without side memory.
3. **Confirmation window:** `watchlist_confirmed=0` on I-R1 (and H-R1) vs G-R1 `=1`.
4. **Provider mix:** Cerebras-heavy ticks; Groq TPM cooldown on tick 0 in both soaks.

---

## 7. Offline replay on I-R1 (418-J enforcement)

| Metric | I-R1 raw logger | **418-J enforced replay** |
|--------|-----------------|---------------------------|
| `total_events_written` | 22 | **22** |
| `watchlist_count` | 2 | **0** |
| `hypothetical_entry_count` | 0 | **0** |
| `paper_ready_watch_count` | 2 | **0** |
| `recommended_mode_for_419` | none | **none** |
| `calibration_total_graduations` | 0 | **0** |

**Enforcement counters (I-R1 decisions re-assessed):**

| Counter | Value |
|---------|-------|
| `mae_above_symbol_cap_count` | **15** |
| `mae_invalidation_inconsistent_count` | **4** |
| `missing_paper_fields_count` | **12** |
| `directional_bias_without_candidate_side_count` | **7** |
| `paper_readiness_block_reason_counts` | `mae_above_symbol_cap=15`, `missing_paper_fields=2` (primary block only) |

Replay **correctly reclassifies** prior watchlist-eligible rows as blocked — not expected to increase graduations.

---

## 8. ETH no-graduation diagnostic

| Metric | Value |
|--------|-------|
| ETH watch count | **2** |
| ETH MAE within cap | **0** |
| ETH MAE above cap | **2** |
| ETH avg MAE | **1.15%** |
| Cause | `eth_watch_mae_above_0_35pct_cap` |

Both ETH watches report MAE ~0.8–1.5% vs 0.35% cap — enforcement + prompt examples target this on next soak.

---

## 9. Why Stage 4.19 remains blocked

- `calibration_total_graduations=0` (BTC and ETH)
- `within_cap (2) < above_cap (15)` on I-R1
- Operator gate requires **both** BTC and ETH graduation > 0
- Formal RG thresholds **unchanged**

**Do not auto-start Stage 4.19.**

---

## 10. Next 30m regression plan (4.18-J-R1)

1. Sync 418-J runtime patch to container (`sync_418f_runtime_to_zeabur.py`).
2. Runtime gate PASS (`check_stage4_runtime_version.py --gate`).
3. Run **30m** dry-run soak with 418-J prompt + enforcement in parse path.
4. Offline replay: logger → simulator → compare (G-R1 / H-R1 / J-R1).
5. Success criteria (indicative): ETH watch MAE within cap ↑, `watchlist_confirmed` > 0, enforcement counters explain residual blocks, still **no orders**.

---

## 11. Safety confirmation

| Check | Value |
|-------|-------|
| `mock_ai_used_count` | 0 |
| `order_sent_count` | 0 |
| `any_exchange_call_made` | false |
| `demo_order_enabled` | false |
| `paper_order_execution_enabled` | false |
| `arm_enabled` | false |
| `radar_enabled` | false |
| `production_touched` | false |
| `btc_auto_touched` | false |
| RG thresholds changed | **NO** |
| 30m soak in this step | **NO** |
| Stage 4.19 auto-started | **NO** |

---

## 12. Verdict

**`STAGE_4_18J_CODE_PASS`** — schema enforcement, diagnostics, tests (281/281), offline replay complete.

**`final_verdict`:** **CODE PASS** — stopped at gate.  
**`next_step_recommendation`:** **4.18-J-R1** 30m runtime-gated regression with 418-J enforcement + ETH examples; do not start Stage 4.19 until BTC **and** ETH graduation > 0 with `within_cap > above_cap`.
