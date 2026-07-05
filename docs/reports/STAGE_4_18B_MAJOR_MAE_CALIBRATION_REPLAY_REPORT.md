# Stage 4.18-B — Major-only MAE Calibration Replay Report

**Generated:** 2026-07-05T14:01:58Z  
**Mode:** offline calibration replay — **no execution, no RG changes**

## 1. Executive summary

- Modes tested: **5**
- recommended_mode_for_419: **`none`**
- stage_419_readiness: **False**

## 2. Why 4.18 had zero graduations

7 BTC/ETH watchlists confirmed but MAE proxy exceeds cap even at 100%; side_memory and confidence floors cannot help until MAE/yield improves

- **primary_blocker_418b:** `mae_cap_violation`
- **mae_cap_violation_at_100pct:** 228
- **candidate_side_none_impact:** False

Stage 4.18 `major_only_calibrated` had `candidate_side_none=29` but 4.18-B confirms MAE proxy blocks all 7 confirmed BTC/ETH watchlists before side resolution at every tested cap (75–100%).

## 3. Calibration modes tested

- **major_mae_75**: graduations=0, BTC=0, ETH=0
- **major_mae_90**: graduations=0, BTC=0, ETH=0
- **major_mae_100**: graduations=0, BTC=0, ETH=0
- **major_mae_100_side_memory**: graduations=0, BTC=0, ETH=0
- **major_mae_100_side_memory_conf_floor**: graduations=0, BTC=0, ETH=0

## 4. BTC/ETH graduation results

### major_mae_75
```json
{
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "avg_confidence_of_graduations": 0.0,
  "mae_cap_used": {
    "BTCUSDT": 0.2625,
    "ETHUSDT": 0.2625
  }
}
```

### major_mae_90
```json
{
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "avg_confidence_of_graduations": 0.0,
  "mae_cap_used": {
    "BTCUSDT": 0.315,
    "ETHUSDT": 0.315
  }
}
```

### major_mae_100
```json
{
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "avg_confidence_of_graduations": 0.0,
  "mae_cap_used": {
    "BTCUSDT": 0.35,
    "ETHUSDT": 0.35
  }
}
```

### major_mae_100_side_memory
```json
{
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "avg_confidence_of_graduations": 0.0,
  "mae_cap_used": {
    "BTCUSDT": 0.35,
    "ETHUSDT": 0.35
  }
}
```

### major_mae_100_side_memory_conf_floor
```json
{
  "hypothetical_graduation_count": 0,
  "per_symbol_graduations": {},
  "avg_confidence_of_graduations": 0.0,
  "mae_cap_used": {
    "BTCUSDT": 0.35,
    "ETHUSDT": 0.35
  }
}
```

## 5. Candidate-side memory results

- side_memory_impact: **False**

```json
{
  "major_mae_100": {},
  "major_mae_100_side_memory": {}
}
```

## 6. SOL/PEPE block confirmation

- major_mae_75: sol_pepe_blocked_count=361
- major_mae_90: sol_pepe_blocked_count=361
- major_mae_100: sol_pepe_blocked_count=361
- major_mae_100_side_memory: sol_pepe_blocked_count=361
- major_mae_100_side_memory_conf_floor: sol_pepe_blocked_count=361

## 7. Safety confirmation

- order_sent_count: **0**
- mock_ai_used_count: **0**
- any_exchange_call_made: **False**
- production_touched: **False**
- btc_auto_touched: **False**

## 8. Block reason matrix summary

```json
{
  "major_mae_75": {
    "alt_blocked_major_only_calibration": 329,
    "mae_cap_violation_75pct": 228
  },
  "major_mae_90": {
    "alt_blocked_major_only_calibration": 329,
    "mae_cap_violation_90pct": 228
  },
  "major_mae_100": {
    "alt_blocked_major_only_calibration": 329,
    "mae_cap_violation_100pct": 228
  },
  "major_mae_100_side_memory": {
    "alt_blocked_major_only_calibration": 329,
    "mae_cap_violation_100pct": 228
  },
  "major_mae_100_side_memory_conf_floor": {
    "alt_blocked_major_only_calibration": 329,
    "mae_cap_violation_100pct": 132,
    "confidence_below_0.4": 37,
    "confidence_decreasing": 62,
    "confidence_below_0.38": 18
  }
}
```

## 9. Recommendation for Stage 4.19 or prompt/schema repair

Return to Stage 4 AI prompt/decision schema — improve candidate_side yield; do not loosen live risk controls

All five calibration modes produced **0 hypothetical graduations**. Do **not** loosen formal Risk Governor MAE thresholds. Next work: improve AI `candidate_side` yield and reduce MAE proxy on confirmed watchlist ticks (prompt/schema repair + additional read-only soak), then re-run 4.18-B.

## 10. Explicit non-execution statement

This replay compares candidate MAE thresholds offline only. No orders, no demo trading, no formal Risk Governor changes, no strategy modifications.

**final_verdict:** `STAGE_4_18B_MAJOR_MAE_CALIBRATION_REPLAY_COMPLETE`

**Stopped at gate — Stage 4.19 requires explicit operator approval.**
