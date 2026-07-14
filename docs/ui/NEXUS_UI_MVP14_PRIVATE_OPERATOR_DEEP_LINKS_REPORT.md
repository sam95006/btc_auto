# NEXUS UI MVP-14 — Private Operator Deep Links / Cross Navigation

**Verdict:** `UI_MVP14_PASS`  
**Mode:** Private Operator documentation deep links (read-only)  
**Date:** 2026-07-14  
**Backend posture:** HOLD (unchanged)

---

## 1. MVP-13 recap

MVP-13 polished navigation, Operator Console hero, Evidence Center, and consistent HOLD/BLOCKED/PASS badges.

## 2. Deep link metadata added

`frontend/src/demo/reportIndex.ts` now includes per-artifact:

- `relatedReports` · `relatedRunbooks` · `relatedCheckpoint`
- `nextActionAnchor` · `uiTargetPage`
- `PRIVATE_OPERATOR_CHECKPOINTS` (P2H-REL)
- `OVERVIEW_QUICK_LINKS` + helpers `artifactHref` / `stageAnchorId`

Coverage: P2D → P2D-R1 → P2E → P2F → P2G → P2H → P2H-OPS → P2H-QA → P2H-REL.

## 3. Components added

| Component | Role |
|-----------|------|
| `DeepLinkActionCard` | Read-only quick links |
| `RelatedArtifactLinks` | Related report/runbook/checkpoint chips |
| `OperatorBreadcrumbs` | Console path crumbs |
| `useHashScroll` | Hash target scroll |

## 4. Pages updated

- **Overview** — quick links to Evidence / Runbook / Gate Checklist / Release Checkpoint  
- **Evidence** — related links on reports + runbooks + checkpoint section; index jump P2D→P2H-REL  
- **Paper Lab** — related P2D / P2D-R1 / P2E / P2F  
- **Risk** — related P2H-QA / P2H-REL  
- **Provider Shadow** — related P2G / P2H / P2H-REL  

## 5. Report / runbook / checkpoint navigation

Deep links are in-console `Link` + hash anchors to sanitized metadata. They do not open `/data` raw files and do not perform control actions.

## 6. Safety checks

```bash
python tools/research/check_nexus_ui_mvp14_safety.py
```

## 7. Build / typecheck

```bash
cd frontend && npm run typecheck && npm run build
```

## 8. Backend HOLD unchanged

No runtime soak. No 30m / 60m. No Stage 4.19 start.

## 9. Trading backend untouched

No trading / routing / RG / ARM edits.

## 10. Future public SaaS still not implemented

## 11. Next UI step

Optional: surface sanitized one-line excerpts from docs markdown via static import map (still no `/data`).
