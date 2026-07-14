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
python ../tools/research/check_nexus_ui_mvp14_safety.py
```

## How to use Private Operator deep links (MVP-14)

Deep links are **documentation-only navigation** between console sections and sanitized report/runbook/checkpoint metadata. They do **not** start soaks, edits, or Stage 4.19.

| From | Jump to |
|------|---------|
| Overview quick links | Evidence Center · HOLD Runbook · Gate Checklist · Release Checkpoint |
| Evidence Report Viewer | Related reports / runbooks / P2H-REL checkpoint |
| Report Index chips | Ordered P2D → P2H-REL anchors |
| Paper Lab | P2D · P2D-R1 · P2E · P2F |
| Risk & Safety | P2H-QA · P2H-REL |
| Provider Shadow | P2G · P2H · P2H-REL |

URLs look like `/evidence#artifact-4-18-p2h-ops` or `/overview#gate-checklist`.

**No control actions** — no Start Stage 4.19 / Run 30m / Run 60m buttons.

## How to use (MVP-13 console)

| Nav group | Pages | Purpose |
|-----------|-------|---------|
| Operator Console | Overview, Evidence Center, Risk & Safety, Paper Lab, Provider Shadow | Daily HOLD ops |
| Research | Fleets, Signals, Reflection | Supporting research views |
| Future / Placeholder | Assistant, Academy, Calculator, Membership | Not productized SaaS |

## Snapshot policy

- Sanitized fixtures: `src/demo/snapshots/`
- Report/runbook/checkpoint metadata: `src/demo/reportIndex.ts` (`docs/...` only)
- Release health: `src/demo/releaseHealth.ts`
- Do **not** commit raw `/data`, jsonl, logs, bundles, or secrets

## Explicitly not implemented

- Customer accounts / billing / API key collection  
- Copy trading / managed accounts  
- Trade / orders / ARM / routing-edit / Stage 4.19 start  

## Safety scanners

```bash
python tools/research/check_nexus_ui_mvp13_safety.py
python tools/research/check_nexus_ui_mvp14_safety.py
```
