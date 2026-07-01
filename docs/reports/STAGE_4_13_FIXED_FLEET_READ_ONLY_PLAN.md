# Stage 4.13 — Fixed Fleet Read-only Expansion Plan

**Date:** 2026-07-01  
**Branch:** `stage3-demo-learning`  
**Prior:** Stage 4.12f PASS (36/36 ETHUSDT 180m)

## Goal

Expand single-symbol ETHUSDT read-only dry-run to fixed four-symbol fleet:

```text
BTCUSDT, ETHUSDT, SOLUSDT, PEPEUSDT
```

No orders, no ARM, no radar, no strategy changes.

## Scope

| Area | Change |
|------|--------|
| `STAGE4_READ_ONLY_SYMBOLS` | +SOLUSDT, +PEPEUSDT (env override via `STAGE4_READ_ONLY_SYMBOLS`) |
| `stage4_fleet_summary.py` | per-symbol summary, market context error tracking |
| `run_stage4_ai_decision_dry_run.py` | fleet phase 4.13, `--dry-run-once`, per_symbol in summary |
| `validate_stage4_ai_decision_outputs.py` | fleet fields in validation report |

## Per-symbol summary fields

```json
{
  "symbols_configured": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "PEPEUSDT"],
  "symbols_seen": [],
  "per_symbol": { "...": { "effective_decision_count": 0 } },
  "symbols_missing": [],
  "symbols_with_market_context_error": [],
  "all_symbols_read_only": true
}
```

PEPE failure must not crash run; record `symbol_unavailable_or_market_context_failed`.

## 30m fixed fleet probe gate

```text
output_dir=/data/stage4_ai_decisions_413_fixed_fleet_30m
duration=30m, poll=300s, target_effective>=20
max decisions = 6 ticks × 4 symbols = 24
```

**PASS:** effective>=20, BTC/ETH/SOL seen, PEPE produced OR marked unavailable, no mock/orders.

**Next after PASS:** Stage 4.13b 180m fixed fleet soak.

## Prohibited

No demo order, ARM, production, btc-auto, multi-coin radar, mock fallback.
