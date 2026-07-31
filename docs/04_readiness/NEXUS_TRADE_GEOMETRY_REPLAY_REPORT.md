# NEXUS Trade Geometry Replay Report

**Session:** `NEXUS-DEMO-6H-8124394e67`  
**Fee for replay:** `REPLAY_CONFIGURED_CONSERVATIVE` taker=`0.00055` (not LIVE claim)  
**Gate unchanged:** `MIN_NET_REWARD_RISK_RATIO=1.2` (not lowered)

## Formal finding

`FIXED_SYMMETRIC_GEOMETRY_INCOMPATIBLE_WITH_NET_RR_GATE=true`

Fixed TP/SL ±0.8% yields Gross R:R ≈ 1.0. After round-trip fee + spread/slip + funding + uncertainty, Net R:R falls below 1.2 for the entire 1221-row set.

This is **not** evidence to lower the gate. It is evidence that Candidate TP/SL must come from market structure / volatility, not a fixed symmetric percent.

## Structure replay (honest)

Original 6H `bounded_candidates` **lack** ATR / swing / support / resistance / liquidity fields.

| Metric | Value |
|--------|-------|
| rows_total | 1221 |
| geometry_input_missing | 1221 |
| geometry_valid | 0 |
| formula_errors | 0 |
| future_data_used | false |
| fixed_symmetric_08_pass | 0 |

## Sensitivity (engineering only — not for live tuning)

Sample n=200:

| TP% | SL% | Gross R:R | pass |
|-----|-----|-----------|------|
| 0.8 | 0.8 | 1.0 | 0 |
| 0.8 | 0.5 | 1.6 | 0 |
| 1.0 | 0.5 | 2.0 | 179 |
| 1.2 | 0.6 | 2.0 | 200 |
| 1.5 | 0.75 | 2.0 | 200 |

Do **not** pick the highest pass-rate combo for trading. Use only to confirm Cost Gate math and required Gross R:R headroom.

## Next

1. Capture structure inputs in Candidate evidence path.
2. Drive geometry via `trade_geometry.compute_structure_geometry`.
3. Then Founder gate for **6H V2** (not 24H).
