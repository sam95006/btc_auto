# NEXUS UI MVP-18 — Evidence Filter URL State + Provider Intelligence Charts

**Verdict:** `UI_MVP18_PASS`  
**Mode:** Private Operator interaction polish (read-only)  
**Date:** 2026-07-14  
**Backend posture:** HOLD (unchanged)

---

## 1. MVP-17 recap

MVP-17 delivered the Market Intelligence visual shell (tokens, Market Command Center, Candidate / Signal / Anomaly, Risk / Provider / Validation surfaces) while retaining MVP-16 search/filter/checklist.

## 2. Evidence URL filter state

`useEvidenceFilterQueryState` syncs filters to URL query:

| Param | Meaning |
|-------|---------|
| `q` | search text |
| `category` | doc category |
| `gateStatus` | HOLD / WAIT / … |
| `unresolved` | `true` when unresolved-only |
| `tag` | tag substring |

Example: `/evidence?q=ETH&category=backend-gate&gateStatus=HOLD&unresolved=true`

Clear filters clears these query keys. No backend · no `/data` · no secret localStorage.

## 3. Provider Intelligence static chart metadata

`frontend/src/demo/providerHistory.ts` — sanitized static bars + timeline + routing posture (Groq vs Cerebras, Cerebras-first experiment-only, shadow ≠ graduation, permanent routing=false).

## 4. Provider chart components

| Component | Role |
|-----------|------|
| `ProviderHistoryChart` | CSS bars Groq vs Cerebras valid_watch |
| `ProviderDivergenceTimeline` | Stage timeline (+ `#btc-cerebras-first`) |
| `ProviderRoutingPostureCard` | Routing posture facts · no editor |

## 5. Candidate / Signal / Anomaly cross links

Each row links Evidence / Gate / Provider / Risk (navigation only).

## 6. Overview drilldown links

Market Command gate strip + fleet cards jump to P2H-REL / Stage 4.19 dossier / ETH watch gate / Provider history.

## 7. Sanitized static-only policy

All charts and filter state are frontend TypeScript metadata. No live market API, no raw logs, no trading controls.

## 8. Safety checks

```bash
python tools/research/check_nexus_ui_mvp18_safety.py
```

## 9. Build / typecheck

```bash
cd frontend && npm run typecheck && npm run build
```

## 10. Backend HOLD unchanged

No 30m / 60m / Stage 4.19 / routing runtime / prompt / MAE / RG edits.

## 11. Trading backend untouched

Frontend + docs + safety scanner only.

## 12. Future public SaaS still not implemented

## 13. Next UI step

Optional: preserve Evidence hash + query together more aggressively; still read-only under HOLD.

---

**Stop:** Backend HOLD · UI read-only · do not start Stage 4.19.  
**Note:** MVP-17 = looks like a trading platform; MVP-18 = research ops are queryable/shareable — still not trade execution.
