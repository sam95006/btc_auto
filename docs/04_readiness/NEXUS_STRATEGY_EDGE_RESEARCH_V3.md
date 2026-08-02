# Edge Research V3 — Economic Edge Redesign

**Status:** COMPLETE (offline)  
**No 6H/12H/24H/Shadow/Canary/Mainnet/Real Money. Final OOS reserved but NOT executed.**

## Wave freeze

`research_wave_v2_status = CONSUMED_NO_VALIDATED_COHORT`  
Cost floors unchanged: `1.2` / `1.5`

## Microstructure

| Source | Status |
|---|---|
| Funding | **AVAILABLE** (5 symbols) |
| Open interest | **AVAILABLE** (5 symbols) |
| Trade flow / CVD | `INSUFFICIENT_HISTORY` |
| Liquidation | `DATA_UNAVAILABLE` |

No missing series replaced with zero.

## Cost Gate starvation (H1/H3 baseline scan)

Dominant cause: **`TARGET_TOO_CLOSE` (546)**  
Also: ENTRY_TOO_LATE 15, STOP_TOO_WIDE 4, VALID_COST_GATE_BLOCK 4

→ Gate is mostly blocking economically weak geometry, not “randomly starving” valid edges.

## Results

| Family | Best | Status | Trades | Net exp | Base PF | Adverse PF | Median hold |
|---|---|---|---:|---:|---:|---:|---:|
| H1 | H1D | `INSUFFICIENT_SAMPLE` | 0 | — | — | — | — |
| H2 | H2D | `REJECTED` | 250 | −0.78 | 0.66 | 0.59 | **17** (was ~5) |
| H3 | H3E | **`WALK_FORWARD_VALIDATED`** | 109 | +0.24 | 1.16 | 1.05 | 27 |

Also WF: **H3D**; Replay: **H3G** (OI-enriched).

H2 redesign lengthened holds and raised gross_move/cost (~5.3 median) but still **no usable gross edge**.

## Recommendation

**`NEXUS_NEW_OOS_PLAN_READY`**

OOS reservation written (`downloaded=false`, `executed=false`). Do **not** auto-run OOS until Founder explicitly authorizes.

Wallet delta remains `UNKNOWN` / `-0.97052039`.
