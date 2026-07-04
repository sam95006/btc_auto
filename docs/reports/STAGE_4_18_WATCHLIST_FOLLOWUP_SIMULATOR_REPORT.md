# Stage 4.18 — Watchlist Follow-up Simulator Report

**Generated:** 2026-07-05  
**Mode:** offline simulator — **no execution**  
**Prerequisite:** Stage 4.17-A `cf3c779`

---

## 1. Executive summary

Replayed **718 eligible decisions** and **718 paper events** across three simulation modes. Key outcome:

| Mode | Watchlist created | Confirmed | Graduations |
|------|-------------------|-----------|-------------|
| strict_current | 12 | 0 | **0** |
| confirmed_watchlist_only | 9 | 8 | **0** |
| major_only_calibrated | 7 | 7 | **0** |

**Finding:** Even relaxed modes produce zero graduations on historical fleet data. The primary blockers are **MAE proxy caps** and **low candidate_side assignment** — not watchlist confirmation logic alone.

**recommended_mode_for_419:** `none` (guard calibration required before paper exit evaluation)

---

## 2. Input coverage

- `/data/stage4_ai_decisions_413d_fixed_fleet_180m`
- `/data/stage4_ai_decisions_414b_fixed_fleet_6h`
- `/data/stage4_ai_decisions_414d_fixed_fleet_6h_clean`
- `/data/stage4_ai_decisions_414f_schema_repair_30m_regression`
- `/data/stage4_paper_events/hypothetical_entry_log.jsonl` (718 events)
- `/data/stage4_paper_events/stage4_17_paper_event_summary.json`

Missing datasets: **none**

---

## 3. Why 4.17-A produced zero hypothetical entries

Three compounding factors:

1. **MAE watch guard (80% cap):** 531/531 watch intents downgraded to `hypothetical_skip` before watchlist creation — only 12 watches had low enough MAE proxy to enter watchlist.
2. **Enter candidate MAE guard (60% cap):** All 33 `enter_candidate` intents hit `mae_enter_downgrade` or alt-specific guards (PEPE watchlist required, SOL trend/MAE).
3. **Watch-heavy fleet profile:** 531 watch vs 33 enter_candidate — historical data is structurally biased toward skip/watch, not entry.

This is **intentional under strict 4.16 rules**, not a logger bug.

---

## 4. Watchlist transition analysis

### 4.17-A paper events
- **12 watchlist** paper events recorded (BTC=3, ETH=2, PEPE=7, SOL=0)

### Mode B replay (confirmed_watchlist_only)
- **9 watchlists created** (relaxed MAE-for-watchlist)
- **8 confirmed** (≥2 ticks, confidence non-decreasing)
- **0 graduated** — blocked at graduation by `mae_enter_downgrade` (170 fires) and PEPE/SOL hard guards

**Answer:** Of 12 strict watchlist events, **8 would confirm** under relaxed rules, but **0 would graduate** to hypothetical entry without further MAE/calibration changes.

---

## 5. Enter candidate downgrade analysis

Total eligible enter_candidate: **33**

| Reason (strict 4.17 replay) | Count |
|-------------------------------|-------|
| mae_enter_downgrade | 33 |
| pepe_watchlist_required | 7 |
| sol_trend_mae | (subset of above) |
| pepe_mae_cap | 16 |

All 33 downgraded — none reached `hypothetical_entry` in strict mode.

---

## 6. Mode A — strict_current

```json
{
  "watchlist_created": 12,
  "watchlist_confirmed": 0,
  "watchlist_expired": 0,
  "watchlist_blocked": 0,
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "block_reason_counts": {
    "mae_watch_downgrade": 531,
    "sol_vol_block": 34,
    "pepe_watchlist_only": 140,
    "hard_skip_intent": 74,
    "soft_skip_intent": 80,
    "sol_trend_mae": 118,
    "trend_watchlist_threshold_3": 171,
    "mae_enter_downgrade": 33,
    "pepe_watchlist_required": 7,
    "pepe_mae_cap": 16
  }
}
```

Confirms 4.17-A: **hypothetical_entry=0** reproduced exactly.

---

## 7. Mode B — confirmed_watchlist_only

```json
{
  "watchlist_created": 9,
  "watchlist_confirmed": 8,
  "watchlist_expired": 0,
  "watchlist_blocked": 0,
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "block_reason_counts": {
    "mae_enter_downgrade": 170,
    "pepe_mae_cap": 181,
    "pepe_vol_cap": 97,
    "sol_vol_block": 36,
    "sol_trend_mae": 127
  }
}
```

Watchlist confirmation works (8/9), but **MAE enter guard still blocks all graduations**.

---

## 8. Mode C — major_only_calibrated

```json
{
  "watchlist_created": 7,
  "watchlist_confirmed": 7,
  "watchlist_expired": 0,
  "watchlist_blocked": 0,
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "block_reason_counts": {
    "mae_cap_violation": 138,
    "confidence_below_0.4": 37,
    "confidence_below_0.38": 18,
    "candidate_side_none": 29,
    "volatile_high_regime": 6
  }
}
```

BTC/ETH still blocked by MAE cap violations and missing `candidate_side`. **Not ready for paper exit without threshold calibration.**

---

## 9. Safe calibration candidates

```json
[
  {
    "calibration_id": "major_mae_cap_relaxation",
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "proposal": "Evaluate 100% MAE cap for graduation (vs 60% enter / 80% watch) in paper path only",
    "implement_in_strategy": false
  },
  {
    "calibration_id": "watchlist_graduation_after_confirm",
    "mode": "confirmed_watchlist_only",
    "observed_confirmations": 8,
    "proposal": "8 watchlists confirm; need MAE relaxation to produce graduations",
    "implement_in_strategy": false
  }
]
```

---

## 10. Risk Governor threshold recommendations (candidates only — NOT implemented)

| Guard | Issue | Candidate adjustment |
|-------|-------|---------------------|
| `mae_watch_downgrade` | Blocks 531 watches at 80% cap | Majors: 90% cap; Alts: keep 80% |
| `mae_enter_downgrade` | Blocks all 33 enter + 170 graduation attempts | Majors: 75% cap for paper-only path |
| `pepe_mae_cap` | 181 blocks in relaxed mode | Keep — PEPE stays watchlist-only |
| `candidate_side_none` | 29 majors lack side at graduation tick | Require side on confirmation tick, not graduation tick |

**Do not auto-apply.** Operator approval required for any threshold change.

---

## 11. Stage 4.19 recommendation

**Do not proceed to Stage 4.19 paper exit evaluation yet.**

Prerequisites:
1. Apply **candidate-only** MAE threshold relaxation for BTC/ETH in simulator re-run
2. Re-simulate until `major_only_calibrated` produces >0 graduations
3. Then run offline exit evaluation on graduation events only

**recommended_mode_for_419:** `none`

---

## 12. Safety confirmation

| Check | Value |
|-------|-------|
| mock_ai_used_count | 0 |
| order_sent_count | 0 |
| any_exchange_call_made | false |
| production_touched | false |
| btc_auto_touched | false |

---

## Analysis answers (Stage 4.18 brief)

1. **Why 0 hypothetical_entry in 4.17-A?** MAE watch guard + watch-heavy fleet + enter MAE downgrades.
2. **12 watchlist confirmations?** 8/12 would confirm under Mode B; 0 graduate without MAE relax.
3. **33 enter_candidate downgrades?** 100% hit `mae_enter_downgrade` or alt guards.
4. **MAE too conservative or bad data?** Both — guards are conservative by design; data is 74% watch intent.
5. **BTC/ETH open now?** No — MAE cap violation + candidate_side_none block majors in Mode C.
6. **SOL/PEPE watchlist only?** Yes — maintain; 181+ PEPE MAE blocks confirm.
7. **Stage 4.19 ready?** Not yet — calibrate thresholds in simulator first.
8. **Adjust RG thresholds?** Propose major-only MAE relaxation (paper path); do not implement in live strategy.

**final_verdict:** `STAGE_4_18_WATCHLIST_FOLLOWUP_SIMULATOR_COMPLETE`

**Stopped at gate — Stage 4.19 requires explicit operator approval.**

---

**Prohibitions remain:** no demo order, ARM, radar, real money, production, btc-auto, mock fallback, new long soaks.
