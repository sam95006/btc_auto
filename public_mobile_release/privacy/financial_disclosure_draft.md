# Financial-feature disclosure — DRAFT

**Status:** ENGINEERING_DRAFT · NOT_LEGAL_ADVICE · NO_LEGAL_APPROVAL_CLAIMED  
**Submission authorized:** NO

## Product posture (public)

NEXUS Decision is positioned as **research / decision-support / risk-awareness** tooling. It is **not**:

- a brokerage
- a custodial wallet
- an automated trading bot for customers
- investment advice with guaranteed returns
- a copy-trading marketplace

See also: `docs/product_strategy/NEXUS_COMPLIANCE_BOUNDARY_V1.md`.

## Store questionnaire themes (draft)

| Theme | Draft disclosure |
|-------|------------------|
| Does the app provide financial services? | Decision-support research UI only; no order placement on user exchange accounts |
| Trading / investing features | User remains final decision-maker; no automatic customer orders |
| Real-money gambling | No |
| Cryptocurrency trading execution | No public exchange write capability |
| Payments | Future subscription entitlements via Apple/Google IAP only when enabled; currently `live_billing_enabled=false` |

## Required UX labeling (when shipped)

- READ-ONLY relative to user exchange accounts
- NOT INVESTMENT ADVICE
- NO LIVE TRADING / NO AUTOMATIC ORDERS
- Uncertainty and freshness indicators on market/decision data

## Explicit bans in this package

- live billing
- real IAP products
- custodial wallet flows
- copy trading
- automated customer trading
