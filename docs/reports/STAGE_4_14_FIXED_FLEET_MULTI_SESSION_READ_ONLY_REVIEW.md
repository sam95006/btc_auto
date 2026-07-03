# Stage 4.14 — Fixed Fleet Multi-session Read-only Stability Review

**Date:** 2026-07-03  
**Phase:** 4.14a (evidence / quality review only — no long soak)  
**Prior gate:** Stage 4.13d Fixed Fleet 180m — **PASS**  
**Output reviewed:** `/data/stage4_ai_decisions_413d_fixed_fleet_180m`

---

## 1. Stage 4.13d PASS summary

| Metric | Value |
|--------|-------|
| duration_minutes | 180 |
| tick_count / expected_tick_count | **36 / 36** |
| tick_drift_seconds_max | **0.0** |
| effective_decision_count | **138** (target 120) |
| real_successful_llm_decision_count | 138 |
| dataset_target_met | true |
| dry_run_completed | true |
| partial_completion | false |
| parse_error_count | 0 |
| validator_passed / technical_valid | true / true |
| provider_chain_failed_count | 6 (≤24) |
| mock_ai_used_count / order_sent_count | 0 / 0 |
| debug_log_has_api_key | false |
| bundle_exported | true |

**Symbols (fixed fleet):**

| Symbol | Effective decisions | Chain failed |
|--------|---------------------|--------------|
| BTCUSDT | 36 | 0 |
| ETHUSDT | 34 | 2 |
| SOLUSDT | 33 | 3 |
| PEPEUSDT | 35 | 1 |

**Verdict:** Single-session 180m fixed-fleet read-only architecture is stable. **Not the order / ARM / trading stage.**

---

## 2. Provider stability review

### Observed distribution (4.13d)

| Metric | Value |
|--------|-------|
| provider_success_distribution | groq=34, cerebras=104 |
| groq_share | 24.6% |
| cerebras_share | **75.4%** |
| fallback_attempt_count | 110 |
| fallback_success_count | 110 |
| groq_cooldown_skip_count | 75 |
| groq_429_count | 3 |
| groq_tpm_cooldown_triggered | true |
| cerebras_parse_error_count | 0 |
| cerebras_429_count | 6 |

### Analysis

1. **Cerebras dependency:** **High.** ~75% of successful LLM decisions came from Cerebras after Groq TPM governor cooldown. Fallback path is reliable (110/110) but Groq primary yield is low under sustained fleet load.

2. **Groq local rate gate / TPM governor:** **Conservative under 180m fleet load.** 75 cooldown skips indicate Groq was unavailable for primary attempts most of the session after early TPM 429. Fleet min-interval (6s) is appropriate; the bottleneck is **Groq TPM quota**, not tick scheduler.

3. **Cerebras outage scenario:** If Cerebras failed mid-session, estimated ceiling drops from 138 effective to ~34–40 (Groq-only successes + partial skips). **Fixed fleet would degrade severely** without secondary provider — not collapse to zero, but would miss 6h targets.

4. **6h provider budget guard:** **Recommended.** Monitor `groq_cooldown_skip_count`, `cerebras_429_count`, `provider_chain_failed_count` per hour. Alert thresholds for 4.14b:
   - `provider_chain_failed_count` > 12/hour
   - `parse_error_count` > 0 (hard stop)
   - `cerebras_share` > 85% with rising `cerebras_429_count`

5. **provider_success_minimum_by_session (recommended floors):**

   | Session | Groq min | Cerebras min | Effective min |
   |---------|----------|--------------|---------------|
   | 180m (observed) | 34 | 104 | 138 |
   | 360m (4.14b target) | 40 | 80 | 240 |

### Fallback dependency risk

| Field | Assessment |
|-------|------------|
| fallback_dependency_risk | **high** |
| needs_provider_budget_guard | **true** |
| cerebras_outage_would_degrade | **true** |
| readiness_for_longer_run | **true** (parse=0, chain_failed within scale, effective ≥ target) |

**Conclusion:** Provider stack is **operationally stable** for read-only but **structurally dependent on Cerebras fallback**. Acceptable for 4.14b with monitoring; not acceptable for trading stage without redundancy review.

---

## 3. Per-symbol yield review

| Symbol | Effective | Chain failed | Skipped ticks (symbol) | Notes |
|--------|-----------|--------------|------------------------|-------|
| BTCUSDT | 36/36 | 0 | 0 | Full yield; Groq+Cerebras mix |
| ETHUSDT | 34/36 | 2 | 2 | Minor chain failures |
| SOLUSDT | 33/36 | 3 | 3 | Lowest yield; chain failures |
| PEPEUSDT | 35/36 | 1 | 1 | Alias `1000PEPEUSDT` OK |

All symbols ≥25 effective (180m PASS bar). ETH/SOL bear most chain failures — consistent with 4.13b pattern under Groq cooldown + Cerebras load.

---

## 4. Per-symbol shadow quality review

| Symbol | Compared | neutral | bad_watch | missed_opp | reasonable_watch | good_skip |
|--------|----------|---------|-----------|------------|------------------|-----------|
| BTCUSDT | 36 | 15 | **12** | 4 | 3 | 2 |
| ETHUSDT | 34 | 17 | 3 | 2 | 0 | **12** |
| SOLUSDT | 33 | 12 | 4 | 4 | **11** | 2 |
| PEPEUSDT | 35 | 15 | **9** | 3 | 7 | 1 |

Fleet totals: bad_watch=28, missed_opportunity=13, neutral=59, reasonable_watch=21, good_skip=17.

**Intent distribution (decisions):**

- BTC: watch=32, soft_skip=4 → watch-heavy
- ETH: hard_skip=18, watch=12 → skip-heavy, highest good_skip
- SOL: watch=30 → watch-heavy
- PEPE: watch=31 → watch-heavy

---

## 5. bad_watch / missed_opportunity analysis

### bad_watch

Shadow rule: `watch` intent + MAE dominates MFE over 60m → `bad_watch`.

1. **Concentration in watch intent:** **Yes.** BTC (32 watch / 12 bad_watch), SOL (30 watch / 4 bad_watch), PEPE (31 watch / 9 bad_watch). High bad_watch rates align with watch-heavy fleets, not parse or provider errors.

2. **BTC / PEPE elevated bad_watch:** BTC had largest watch cohort + volatile 60m windows (avg MAE 0.26%). PEPE alias klines (`1000PEPEUSDT`) add volatility; 9 bad_watch with 31 watch decisions (~29% of watch cohort) — review-only signal, not strategy defect.

3. **ETH stable:** bad_watch=3 with mixed skip/watch intents; good_skip=12 indicates skip decisions validated well in shadow.

### missed_opportunity

Shadow rule: directional 60m move despite skip/watch intent.

1. **Skip concentration:** ETH missed=2 mostly from hard_skip cohort (18 skips) — low rate (~11% of skips if directional).
2. **Watch concentration:** BTC/SOL missed=4 each — watch decisions facing directional 60m moves without entry (read-only by design).
3. **Not execution misses:** All decisions `order_sent=false`; labels are observational only.

### SOL reasonable_watch

SOL reasonable_watch=11 (33% of compared) — highest fleet-wide. Indicates watch decisions in volatile but non-directional 60m windows; **observation quality acceptable** for read-only review.

---

## 6. Provider fallback dependency risk (summary)

```text
Risk level: HIGH dependency, MEDIUM operational risk
Groq primary: 24.6% success share
Cerebras fallback: 75.4% success share
Fallback reliability: 110/110 (100%)
Parse/truncation: 0 (4.13c/4.13d repairs effective)
Scheduler: 0.0s drift (absolute tick schedule validated)
```

**If Cerebras unavailable:** expect ~75% decision loss vs observed session; chain_failed would rise. **6h run requires live monitoring**, not strategy changes.

---

## 7. Readiness for longer read-only run

### Multi-session readiness schema

```json
{
  "session_id": "stage4_413d_fixed_fleet_180m",
  "session_type": "fixed_fleet_read_only",
  "duration_minutes": 180,
  "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
  "effective_decision_count": 138,
  "per_symbol_decision_counts": {
    "BTCUSDT": 36,
    "ETHUSDT": 34,
    "SOLUSDT": 33,
    "PEPEUSDT": 35
  },
  "provider_success_distribution": {"groq": 34, "cerebras": 104},
  "provider_chain_failed_count": 6,
  "parse_error_count": 0,
  "tick_count": 36,
  "expected_tick_count": 36,
  "tick_drift_seconds_max": 0.0,
  "shadow_quality_summary": {
    "fleet_bad_watch_count": 28,
    "fleet_missed_opportunity_count": 13,
    "eth_relative_stability": true
  },
  "readiness_for_next_session": true
}
```

**4.14a readiness gate:** **PASS** — proceed to 4.14b with provider budget guard.

Modules: `stage4_multi_session_review.py`, `stage4_provider_stability_review.py`, `stage4_shadow_quality_summary.py`

---

## 8. Stage 4.14b run plan

**Do not run 24h first.** Start with 6h fixed fleet read-only soak.

| Parameter | Value |
|-----------|-------|
| STAGE4_OUTPUT_DIR | `/data/stage4_ai_decisions_414b_fixed_fleet_360m` |
| STAGE4_CLOUD_DRY_RUN_MINUTES | 360 |
| STAGE4_POLL_INTERVAL_SECONDS | 300 |
| expected_tick_count | 72 |
| max_decisions | 288 (72 × 4) |
| STAGE4_TARGET_EFFECTIVE_DECISION_COUNT | 240 |
| STAGE4_SYMBOLS | BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT |
| STAGE4_CEREBRAS_MAX_TOKENS | 1100 |

### 4.14b PASS criteria (draft)

| Criterion | Target |
|-----------|--------|
| duration_minutes | 360 |
| tick_count / expected_tick_count | 72 / 72 |
| effective_decision_count | ≥ 240 |
| dataset_target_met | true |
| per_symbol_decision_counts each | ≥ 50 |
| provider_chain_failed_count | ≤ 48 |
| parse_error_count | 0 |
| validator_passed / technical_valid | true |
| mock / order / api key leak | 0 / 0 / false |
| STAGE4_CLOUD_DRY_RUN_MINUTES reset | 0 after finalize |

### Execution notes

1. Preflight: `check_stage4_provider_capacity.py` + stage3 context (same as 4.13d).
2. Early sanity at 8–12 min (4 symbols, decisions updating).
3. Finalize at ~370 min; do not redeploy mid-soak.
4. Per-symbol shadow compare after finalize.
5. Reset `STAGE4_CLOUD_DRY_RUN_MINUTES=0` before any other stage.

---

## Safety reaffirmation

- No orders, demo order, ARM, Stage 3 runner, production, btc-auto, radar.
- `STAGE4_ALLOW_MOCK_FALLBACK=false`, `STAGE4_ORDER_ALLOWED=false`.
- Shadow labels are **not** backtests; no strategy changes from this review.

---

## Verdict

| Item | Result |
|------|--------|
| **Stage 4.14a** | **PASS** |
| **Readiness for 4.14b 6h** | **GO** (with provider budget guard) |
| **Trading / order stage** | **NOT READY** |

**Next step:** Stage 4.14b — fixed fleet 6h (360m) read-only soak on Zeabur, same env pattern as 4.13d with scaled targets.
