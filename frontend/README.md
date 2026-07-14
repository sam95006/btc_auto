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
python ../tools/research/check_nexus_ui_mvp16_safety.py
```

## Static excerpt search / filter + checklist links (MVP-16)

Evidence Center can **search and filter** sanitized doc summaries locally, and summary cards link to checklist anchors.

### Static search / filter usage

On Evidence → Static Doc Summary Viewer:

- Search text (e.g. `P2D`, `P2E`, `HOLD`, `Stage 4.19`, `no 60m`, `ETH watch`, `prompt repair`, `release checkpoint`)
- Filter by **category** / **gateStatus**
- Toggle **Show unresolved only**
- **Clear filters**

Search/filter is **local sanitized metadata only** (`src/demo/docSummaries.ts`).

- **No backend calls**
- **No /data** raw reads
- **No control actions**

### Checklist link usage

Summary cards may show checklist chips (documentation anchors only):

| From | Links to |
|------|----------|
| P2F | ETH watch reappearance checklist |
| P2H-OPS | Short regression approval checklist |
| P2H-REL | Stage 4.19 dossier checklist |
| P2H-QA | Safety invariants checklist |

URLs e.g. `/overview#checklist-eth-watch-reappearance`, `/risk#checklist-safety-invariants`.

Overview also shows **Top Unresolved Gate**: ETH watch conditions not reappeared · next = wait.

## Static doc summary viewer (MVP-15)

Operators can read **sanitized one-line excerpts** without opening full reports or raw `/data`.

| Surface | What you see |
|---------|----------------|
| Overview `CurrentGateSummaryCard` | Backend HOLD · ETH not reappeared · Stage 4.19 blocked · next = wait |
| Overview `UnresolvedGateCard` | Top unresolved gate under HOLD |
| Evidence `DocSummaryList` + filter | Per-report excerpts · search / category / gate |
| Paper Lab | Validation summary |
| Risk & Safety | Safety summary + invariants checklist |
| Provider Shadow | Routing summary |

### Sanitized excerpt policy

- Metadata only: `src/demo/docSummaries.ts`
- **No raw reports** embedded as full bodies from `/data`
- **No raw data** paths, jsonl, logs, or secrets
- **No control action** buttons (no Start Stage 4.19 / Run 30m / Run 60m)
- Next action language is **wait / hold**, not run

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
- Doc summaries / excerpts / filter tags: `src/demo/docSummaries.ts`
- Release health: `src/demo/releaseHealth.ts`
- Do **not** commit raw `/data`, jsonl, logs, bundles, or secrets

## Explicitly not implemented

- Customer accounts / billing / API key collection  
- Copy trading / managed accounts  
- Trade / orders / ARM / routing-edit / Stage 4.19 start  

## Safety scanners

```bash
python tools/research/check_nexus_ui_mvp14_safety.py
python tools/research/check_nexus_ui_mvp15_safety.py
python tools/research/check_nexus_ui_mvp16_safety.py
```
