# NEXUS First Bybit Demo Smoke Order Report

**Date:** 2026-07-30  
**Service:** `nexus-bybit-demo-learning-validation`  
**URL:** https://nexus-bybit-demo-val.zeabur.app  
**PR #6 Head (execution):** `758af93`  
**Deploy run:** `30505228019`  
**Recommendation:** `FIRST_DEMO_SMOKE_ORDER_PASS_AWAITING_AUTONOMOUS_6H_APPROVAL`

## Fixed flags after completion

```text
first_demo_smoke_order_approved=false (window closed)
demo_autonomous_enabled=false
exchange_write=false (new orders blocked)
mainnet=false
real_money=false
pr6_draft=true
pr6_merged=false
```

## Result summary

| Field | Value |
|-------|-------|
| Symbol | BTCUSDT |
| Direction | Sell |
| Strategy | SMOKE_MOMENTUM_15M |
| Margin | 20 USDT |
| Leverage | 25 |
| Margin mode | ISOLATED |
| Entry | 63735.5 |
| Exit | 63730 |
| Fee | 0.24538168 |
| Funding | UNAVAILABLE |
| Realized PnL | -0.45224218 |
| Outcome | GOOD_PROCESS_LOSS |
| Reconciliation | MATCH |
| Final positions / orders | 0 / 0 |
| Exchange write calls | 2 |
| Kill switch | false |
| Sample sufficiency | INSUFFICIENT_SAMPLE |
| Learning | PROPOSED only |

## Next Founder Gate

`FOUNDER_GATE=DEMO_AUTONOMOUS_6H_BOUNDED_VALIDATION`

Evidence artifact (local): `artifacts/demo_validation_smoke/smoke_final.json`
