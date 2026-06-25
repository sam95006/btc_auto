# Research Stage 3 — Bybit Demo/Testnet Learning Runner Plan

**Scope:** 24h automated demo/testnet AI trading loop with reflection and patch learning.  
**Service:** `nexus-stage3-bybit-demo-learning` (independent from `btc-auto` and Stage 2 shadow).  
**Not:** production GO · real money GO · Bybit mainnet GO · live capital GO · `btc-auto` production GO.

---

## 1. Goal loop

```
Market scan → Analysis → Bybit demo/testnet order → Close → Record → Reflect on loss → Patch → Block repeat mistake
```

| Stage | Mode |
|-------|------|
| Stage 2 | Public data + paper shadow only (`nexus-stage2-bybit-shadow`) |
| **Stage 3** | **Demo/testnet orders + learning loop** (`nexus-stage3-bybit-demo-learning`) |

---

## 2. Safety invariants

| Flag | Required |
|------|----------|
| `research_only` | `true` |
| `bybit_demo_learning_mode` | `true` |
| `bybit_shadow_mode` | `false` |
| `paper_only` | `false` |
| `bybit_order_allowed` | `true` (demo/testnet scope only) |
| `bybit_order_scope` | `demo_or_testnet_only` |
| `bybit_mainnet_allowed` | `false` |
| `BYBIT_M0_BASE_URL` | `https://api-demo.bybit.com` |
| `exchange_write_allowed` | `true` (demo/testnet scope only) |
| `real_money` | `false` |
| `live_trading` | `false` |
| `production_promotion_allowed` | `false` |
| `arm_allowed` | `false` |

### Hard caps

| Cap | Value |
|-----|-------|
| `MAX_MARGIN_USD` | ≤ 20 |
| `MAX_LEVERAGE` | ≤ 3 |
| `MAX_OPEN_POSITIONS` | ≤ 1 |

### Required governance flags

- `REQUIRE_STOP_LOSS=true`
- `REQUIRE_MAX_HOLD=true`
- `REQUIRE_REFLECTION_ON_LOSS=true`
- `REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP=true`

### Credential policy

- Use **demo/testnet-only** API keys: `BYBIT_DEMO_API_KEY` / `BYBIT_DEMO_API_SECRET`
- Set via Zeabur Variables or local `.env` only — **never** in deploy package
- **Revoke** legacy `BYBIT_M0_API_KEY` / `BYBIT_M0_API_SECRET` (compromised naming)
- Do **not** use `https://api.bybit.com` (mainnet)

---

## 3. Per-trade record schema (required fields)

Every demo/testnet trade must emit:

| Field | Purpose |
|-------|---------|
| `decision_id` | Decision trace join key |
| `signal_id` | Signal lineage |
| `order_id` | Exchange order reference |
| `symbol` | e.g. ETHUSDT |
| `side` | long / short |
| `entry_price` | Fill or intended entry |
| `exit_price` | Close fill |
| `close_pnl` | Realized PnL |
| `exit_reason` | stop_loss / max_hold / signal / manual |
| `confidence_before` | Pre-trade confidence |
| `confidence_after` | Post-reflection confidence |
| `position_size_before` | Size before patch |
| `position_size_after` | Size after patch |
| `reflection_created` | Loss postmortem written |
| `patch_created` | Learning patch artifact |
| `patch_applied_to_next_decision` | Patch consumed on next cycle |
| `repeated_mistake_detected` | Same-setup repeat detected |
| `repeated_mistake_blocked` | Re-entry blocked by patch |

Output path (runtime, on `/data` volume):

- `data/external_alpha/demo_learning/stage3_trades.jsonl`
- `data/external_alpha/demo_learning/stage3_reflections.jsonl`
- `data/external_alpha/demo_learning/stage3_patches.jsonl`

---

## 4. Stop conditions (runner must STOP)

| Condition | Trigger |
|-----------|---------|
| `bybit_mainnet_detected` | Mainnet URL or endpoint used |
| `real_money_detected` | `REAL_MONEY=true` or mainnet credential |
| `margin_usd_exceeds_cap` | > 20 USD margin |
| `leverage_exceeds_cap` | > 3x |
| `open_positions_exceeds_cap` | > 1 position |
| `missing_stop_loss` | Order without SL |
| `missing_max_hold` | No max-hold enforcement |
| `loss_without_reflection` | Loss closed, no reflection |
| `repeated_loss_without_patch` | Repeat loss, no patch |
| `same_setup_reentry_without_patch` | Same setup re-entry blocked failure |
| `production_promotion_allowed` | Without signed operator GO |
| `kill_switch_disabled` | Kill-switch off |
| `btc_auto_production_touched` | Production service modified |

---

## 5. Zeabur deploy profile

| Item | Value |
|------|-------|
| Project | BTC (`69d559b62696d526abde8cd9`) |
| Service name | `nexus-stage3-bybit-demo-learning` |
| Root directory | `deploy/zeabur_stage3_demo_learning` |
| Volume | `/data` → `NEXUS_DATA_DIR=/data` |
| Secrets | Zeabur Variables only (`BYBIT_DEMO_API_KEY`, `BYBIT_DEMO_API_SECRET`) — not `BYBIT_M0_*` |

**Do not** redeploy or modify `btc-auto`.

### Pre-start gate (container only)

```bash
python tools/research/check_bybit_demo_learning_env.py --strict-env --no-check-package
```

### Planned 24h command (not enabled this round)

```bash
# TODO: implement run_bybit_demo_learning_runner.py
python tools/research/run_bybit_demo_learning_runner.py --duration-minutes 1440
```

---

## 6. Boot evidence chain

Runner boot requires (minimal JSON in deploy package):

- `p1_behavior_change_report.json`
- `p2_performance_report.json`
- `oos_walkforward_report.json`
- `phase9_production_promotion_review.json` (`production_promotion_allowed=false`)

---

## 7. Stage 3 vs Stage 2

| | Stage 2 Shadow | Stage 3 Demo Learning |
|--|----------------|----------------------|
| Service | `nexus-stage2-bybit-shadow` | `nexus-stage3-bybit-demo-learning` |
| Orders | Forbidden | Demo/testnet only |
| Exchange write | Forbidden | Allowed (scoped) |
| Base URL | `api.bybit.com` public read | `api-demo.bybit.com` |
| Learning loop | Paper signals only | Trade + reflection + patch |

---

## 8. This round scope

- ✅ Plan, readiness JSON, strict env checker, clean deploy package
- ❌ 24h runner implementation / start
- ❌ Live orders
- ❌ Production promotion
- ❌ `btc-auto` changes

---

## 9. Next steps (after readiness PASS)

1. Implement `run_bybit_demo_learning_runner.py` + `BybitDemoLearningClient` (demo API only).
2. Create Zeabur service with Stage 3 env + `/data` volume.
3. Run container strict-env → short soak → 24h learning run.
4. Export learning bundle; review stop conditions and patch effectiveness.
