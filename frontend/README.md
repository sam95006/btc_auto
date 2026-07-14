# NEXUS / EATI Private Operator UI

Read-only research dashboard for private operators. **Not** a customer SaaS product.

## Current mode

- **Private Operator** · sanitized snapshot · **READ ONLY**
- Backend posture displayed: **HOLD** / wait-for-condition / no auto-run
- Stage 4.19 shown as **blocked**
- **NOT INVESTMENT ADVICE**
- No live trading, order entry, ARM, production toggles, or routing editor

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Optional checks:

```bash
npm run typecheck
npm run build
npm run check:safety
```

Open the Vite URL (typically `http://localhost:5173`).

## Snapshot policy

- UI reads **sanitized** TypeScript fixtures under `src/demo/snapshots/`
- Report / runbook viewers read **sanitized metadata** from `src/demo/reportIndex.ts` (`docs/...` paths only)
- Do **not** commit raw `/data` jsonl, logs, or cloud bundles into `frontend/`
- Do **not** place API keys or secrets in snapshots
- Adapter prefers the latest private-operator snapshot (currently P2G/P2H HOLD)

## Report Viewer / Runbook Viewer (MVP-11)

- **Evidence**: Private Report Viewer + Operator Runbook Viewer (why HOLD, which report/runbook)
- **Overview**: Gate checklist summary for next short regression
- **Paper Lab**: Next short-regression checklist
- **Risk Evidence**: Safety invariants checklist
- **Provider Shadow**: Routing remains experimental / permanent routing false
- Metadata only — **no control buttons**, no Stage 4.19 start, no order/ARM controls

Safety:

```bash
python tools/research/check_nexus_ui_mvp11_safety.py
```

## Explicitly not implemented

- Customer accounts / billing / API key collection  
- Copy trading / managed accounts  
- Trade / orders / ARM / routing-edit / Stage 4.19 start controls  
- Production or btc-auto arming  

Public SaaS remains future-only (see Membership / Academy placeholders).

## Safety scanners

```bash
python tools/research/check_nexus_ui_mvp10_safety.py
```
