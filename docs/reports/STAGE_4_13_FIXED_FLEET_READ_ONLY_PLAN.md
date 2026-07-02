# Stage 4.13 — Fixed Fleet Read-only Expansion Plan

**Date:** 2026-07-01  
**Branch:** `stage3-demo-learning`  
**Prerequisite:** Stage 4.12f PASS (36/36 ETHUSDT 180m)

## Goal

Expand read-only Stage 4 dry-run from single-symbol ETHUSDT to fixed four-coin fleet:

```text
BTCUSDT, ETHUSDT, SOLUSDT, PEPEUSDT
```

No strategy changes. No orders. No mock fallback.

## Implementation

| Component | Change |
|-----------|--------|
| `stage4_fleet_symbols.py` | Fixed fleet list, `STAGE4_SYMBOLS` parse, PEPE→1000PEPE alias |
| `stage4_per_symbol_summary.py` | `per_symbol`, `symbols_seen`, `symbols_missing`, context errors |
| `stage4_context_skip.py` | Context-unavailable skip (no LLM, not mock) |
| `bybit_demo_client.py` | `STAGE4_READ_ONLY_SYMBOLS` + SOL/PEPE |
| `stage4_market_context.py` | Alias fetch, `market_context_unavailable()` |
| `run_stage4_ai_decision_dry_run.py` | Per-symbol summary, `--dry-run-once`, phase 4.13 |

## PEPE handling

- Configured symbol: `PEPEUSDT`
- Bybit linear fetch alias: `1000PEPEUSDT`
- If still unavailable → `symbol_unavailable_or_market_context_failed` (run continues)

## 30m probe gate

```text
6 ticks × 4 symbols = 24 max decisions
PASS: effective_decision_count >= 20
BTC + ETH + SOL must produce real LLM decisions
PEPE: decision OR context_unavailable marker
```

## Stage 4.13a — Evidence / Shadow Correctness (pre-413b)

| Fix | Detail |
|-----|--------|
| Per-symbol chain failed | `build_per_symbol_summary(..., system_events=...)` attributes `provider_chain_failed` from system events by symbol |
| Shadow filter | `--symbol BTCUSDT` compares only `decision.symbol == BTCUSDT` |
| PEPE shadow alias | `PEPEUSDT` → `1000PEPEUSDT` for kline fetch; summary records `requested_symbol`, `market_symbol`, `alias_used` |
| Validator | Recomputes per-symbol failed counts; fails if sum ≠ global `provider_chain_failed_count` |

Re-run validator + per-symbol shadow on existing `/data/stage4_ai_decisions_413_fixed_fleet_30m` (no 30m re-probe).

## Not in scope

- Demo order / ARM / radar / auto universe
- Strategy or confidence calibration changes
- 180m soak (Stage 4.13b after 30m PASS)

## Cross-run reference

| Run | Result |
|-----|--------|
| 4.12f | 36/36 ETHUSDT PASS |
| 4.13 | 30m fixed fleet probe |
