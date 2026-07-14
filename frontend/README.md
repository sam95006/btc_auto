# NEXUS / EATI Private Operator UI

Read-only research dashboard for private operators. **Not** a customer SaaS product.

## Current mode

- **Private Operator** · sanitized snapshot · **READ ONLY**
- Backend posture: **HOLD** / wait-for-condition / **Auto-run: false**
- Stage 4.19: **BLOCKED** · 30m now: false · 60m: false
- Release checkpoint: **P2H** (P2H-QA health PASS)
- **NOT INVESTMENT ADVICE**
- No live trading, order entry, ARM, production toggles, or routing editor

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Checks:

```bash
npm run typecheck
npm run build
python ../tools/research/check_nexus_ui_mvp13_safety.py
```

Open the Vite URL (typically `http://localhost:5173`).

## How to use (MVP-13)

| Nav group | Pages | Purpose |
|-----------|-------|---------|
| Operator Console | Overview, Evidence Center, Risk & Safety, Paper Lab, Provider Shadow | Daily HOLD ops |
| Research | Fleets, Signals, Reflection | Supporting research views |
| Future / Placeholder | Assistant, Academy, Calculator, Membership | Not productized SaaS |

1. Start on **Overview** — Operator Console hero shows HOLD / P2H checkpoint / Stage 4.19 BLOCKED / next action / no 30m·60m·auto-run.
2. Open **Evidence Center** for Report Viewer, Runbook Viewer, Release Checkpoint, and ordered P2D→P2H-QA index.
3. Use **Paper Lab** for validation status (BTC prior evidence, ETH repair pending runtime, short regression=false).
4. Use **Risk & Safety** for safety invariants (`orders/mock/ARM/production/btc_auto/4.19/billing=false`).
5. Use **Provider Shadow** for experiment-only routing history (permanent change=false; operator approval required).

## Snapshot policy

- Sanitized fixtures: `src/demo/snapshots/`
- Report/runbook metadata: `src/demo/reportIndex.ts` (`docs/...` only)
- Release health: `src/demo/releaseHealth.ts`
- Do **not** commit raw `/data`, jsonl, logs, bundles, or secrets

## Explicitly not implemented

- Customer accounts / billing / API key collection  
- Copy trading / managed accounts  
- Trade / orders / ARM / routing-edit / Stage 4.19 start  
- Production or btc-auto arming  

## Safety scanners

```bash
python tools/research/check_nexus_ui_mvp12_safety.py
python tools/research/check_nexus_ui_mvp13_safety.py
```
