# Research Stage 3 Phase C — Controlled Bybit Demo Order Micro Session Plan

**Scope:** First controlled Bybit demo/testnet micro order session with full learning loop.  
**Service:** `nexus-stage3-bybit-demo-learning` (independent from `btc-auto`).  
**Not:** production · real money · mainnet · 24h runner · `btc-auto` GO.

---

## 1. Phase progression

| Phase | Mode | Orders |
|-------|------|--------|
| A | `mock` / `dry-run` | Simulated only |
| B | `dry-run` | Balance read + would_order simulation |
| **C** | **preflight + design** | **No orders this round** |
| C+1 (operator GO) | `demo-order` | Single controlled micro order |

---

## 2. Phase C micro session flow

```
Market scan (ETHUSDT linear ticker)
  → Balance snapshot (private read wallet-balance)
  → Preflight / order safety contract
  → Decision (one side, one position max)
  → Demo order (operator GO only)
  → Position tracking (private read position/list)
  → Close / max-hold / stop-loss exit
  → Trade result record
  → Reflection (if loss)
  → Patch (if loss)
  → Next decision adjustment (block repeat setup)
```

---

## 3. Session parameters (defaults)

| Parameter | Value |
|-----------|-------|
| `symbol` | `ETHUSDT` |
| `category` | `linear` |
| `side` | Runner decision; **one order per session** |
| `max_margin_usd` | ≤ 20 |
| `max_leverage` | ≤ 3 |
| `max_open_positions` | 1 |
| `max_hold_minutes` | 10 |
| `require_stop_loss` | true |
| `stop_loss_max_usd` | 2 |
| `take_profit_optional` | true |
| `force_close_on_timeout` | true |
| `reflection_required_on_close` | true (mandatory on loss) |
| `patch_required_if_loss` | true |

---

## 4. Order safety contract

Before any `demo-order`, all must be true:

| Check | Requirement |
|-------|-------------|
| `balance_snapshot_id` | Exists from current tick |
| `account_available_balance` | ≥ `max_margin_usd` (20) |
| `existing_open_positions` | 0 |
| Stop loss | Attached or protective exit defined |
| Max hold | Attached |
| `order_scope` | `demo_or_testnet_only` |
| `mainnet` | false |
| `real_money` | false |

Tool: `python tools/research/preflight_stage3_demo_order.py`  
Report: `data/external_alpha/reports/stage3_demo_order_preflight.json`

---

## 5. Preflight checklist

| Check | Required |
|-------|----------|
| `strict_env_passed` | true |
| `BYBIT_M0_BASE_URL` | `https://api-demo.bybit.com` |
| `BYBIT_ORDER_SCOPE` | `demo_or_testnet_only` |
| `BYBIT_MAINNET_ALLOWED` | false |
| `REAL_MONEY` | false |
| `LIVE_TRADING` | false |
| `PRODUCTION_PROMOTION_ALLOWED` | false |
| `ARM_ALLOWED` | false |
| `MAX_MARGIN_USD` | ≤ 20 |
| `MAX_LEVERAGE` | ≤ 3 |
| `MAX_OPEN_POSITIONS` | 1 |
| `REQUIRE_STOP_LOSS` | true |
| `REQUIRE_MAX_HOLD` | true |
| `REQUIRE_REFLECTION_ON_LOSS` | true |
| `REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP` | true |
| `account_balance_read_ok` | true |
| `account_coin` | USDT |
| `account_available_balance` | > 20 |
| `wallet_coin_missing` | false |
| `existing_open_positions` | 0 |
| `no_mainnet_endpoint` | true |
| `no_production_service_touched` | true |

---

## 6. Allowed private read endpoints (Phase C)

- `GET /v5/account/wallet-balance`
- `GET /v5/position/list`
- `GET /v5/market/tickers` (public)

**Forbidden:** order create/cancel, transfer, withdraw, mainnet (`api.bybit.com`).

---

## 7. Output paths

| Environment | Path |
|-------------|------|
| Local | `data/external_alpha/stage3_demo_learning/` |
| Zeabur | `/data/stage3_demo_learning/` |

Phase C adds no new files until operator GO; preflight report only:

- `data/external_alpha/reports/stage3_demo_order_preflight.json`

---

## 8. Hard prohibitions (Phase C)

- No `--mode demo-order` without operator GO
- No multi-position
- No margin > 20 USD
- No leverage > 3
- No order without stop loss / max hold
- No mainnet / real money / production promotion
- No ARM / OPEN / CLOSE via production paths
- No `btc-auto` modification
- No Zeabur 24h runner / entrypoint change this round

---

## 9. Operator GO gate (Phase C+1)

When preflight passes and operator explicitly approves:

```bash
# NOT enabled in Phase C — requires signed GO
python tools/research/run_bybit_demo_learning_runner.py \
  --mode demo-order \
  --duration-minutes 15 \
  --poll-interval-seconds 30 \
  --micro-session
```

Until GO: run preflight only.

```bash
python tools/research/preflight_stage3_demo_order.py
```

---

## 10. Success criteria (Phase C)

- [x] Plan documented
- [x] Preflight tool implemented
- [x] Order safety contract defined
- [x] Balance + position read verified
- [ ] Demo order placed — **deferred to operator GO**
