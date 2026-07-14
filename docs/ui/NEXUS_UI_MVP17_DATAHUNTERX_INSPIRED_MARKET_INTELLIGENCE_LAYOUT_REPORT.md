# NEXUS UI MVP-17 — DataHunterX-Inspired Market Intelligence Layout

**Verdict:** `UI_MVP17_PASS`  
**Mode:** Private Operator Market Intelligence redesign (read-only)  
**Date:** 2026-07-14  
**Backend posture:** HOLD (unchanged)  
**Inspiration:** [DataHunterX](https://datahunterx.com/) product structure (not a clone)

---

## 1. MVP-16 recap

MVP-16 delivered static excerpt search/filter, checklist reference links, and unresolved-gate display. Those remain intact.

## 2. Why redesign

MVP-13–16 made the console operable, but the visual language still felt like a “game base / fleet terminal” more than a trading research platform.

## 3. Current UI issue

Too game-like: strong decorative backgrounds, soft card stacks, low scan density. Operators need a denser Market Intelligence dashboard, not another decorative panel layering.

## 4. DataHunterX-inspired structure

Adapted patterns:

- Market dashboard / command center density  
- Signal / candidate partitions  
- Anomaly radar style grouping  
- AI assistant as prompt cards (not live order help)  
- Clear research / learning placeholders  

## 5. What was adapted

- Dark fintech surfaces, flatter cards, weaker background  
- Top gate strip (HOLD / P2H / Stage 4.19 BLOCKED)  
- Fleet intelligence grid + candidate board + signal feed  
- Anomaly radar + AI Commander mini panel  
- Risk Center invariant grid · Provider Intelligence · Validation Lab  

## 6. What was intentionally not copied

- No public marketplace / membership upsell UX as core product  
- No live long/short recommendation chasing  
- No quick order / buy-sell actions  
- No billing, accounts, or API key collection  
- NEXUS Evidence / Gate / Runbook / HOLD remain first-class  

## 7. Retained MVP-16 features

- `docSummaries.ts` · DocSummaryCard/List · DocSummaryFilterBar  
- ChecklistReferenceLinks · UnresolvedGateCard  
- Evidence search/filter · deep links · runbook/report/checkpoint  

## 8. Components added

| Component | Role |
|-----------|------|
| `designTokens.css` | Fintech token system |
| `MarketCommandCenter` | Gate strip + fleet grid + AI mini |
| `CandidateBoard` | Long/Short/Waiting tables |
| `SignalFeedPanel` | Dense signal rows |
| `AnomalyRadarPanel` | Gate / risk / provider anomalies |
| `AICopilotPanel` | Static prompt cards only |
| `SafetyInvariantGrid` | Risk Center badges |
| `ProviderIntelligencePanel` | Routing facts (no editor) |
| `ValidationStatusBoard` | Paper Lab validation facts |
| `ReadOnlyNavChip` | View Evidence / Gate / Risk / Ask AI |

## 9. Pages updated

Overview (Market Command), Evidence (zones + filter retained), Risk Center, Provider Intelligence, Paper Lab / Validation Lab, App layout / sidebar / top bar.

## 10. Responsive result

- Candidate/Signal tables horizontal-scroll on narrow viewports  
- Signal feed cardizes on mobile  
- AI copilot docks to bottom on mobile; desktop rail retained  
- Sidebar remains horizontal-scroll at small widths  

## 11. Safety checks

```bash
python tools/research/check_nexus_ui_mvp17_safety.py
```

## 12. Build / typecheck

```bash
cd frontend && npm run typecheck && npm run build
```

## 13. Backend HOLD unchanged

No 30m / 60m / Stage 4.19 / routing / prompt / MAE / RG edits.

## 14. Trading backend untouched

Frontend + docs + safety only.

## 15. Future public SaaS still not implemented

Future nav items remain placeholders.

## 16. Next UI step

Optional polish: URL-persisted Evidence filters, tighter Provider history charts (still sanitized / read-only).

---

**Stop:** Backend HOLD · UI read-only · do not start Stage 4.19.
