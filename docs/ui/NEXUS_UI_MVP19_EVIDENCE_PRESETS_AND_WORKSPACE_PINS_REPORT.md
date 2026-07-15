# NEXUS UI MVP-19 — Evidence Share Presets + Operator Workspace Pins

**Verdict:** `UI_MVP19_PASS`  
**Mode:** Private Operator URL-only workspace shortcuts (read-only)  
**Date:** 2026-07-15  
**Backend posture:** HOLD (unchanged)

---

## 1. MVP-18 recap

MVP-18 added Evidence filter URL state, Provider Intelligence static charts, and Candidate/Signal/Anomaly drilldowns.

## 2. Evidence presets metadata

`frontend/src/demo/evidencePresets.ts` defines six static presets:

| Preset | Focus |
|--------|--------|
| ETH Watch Gate | unresolved ETH backend-gate |
| Stage 4.19 Blocker | dossier / blocked status |
| Safety Invariants | Risk Center checklist |
| Provider Routing | Cerebras-first / routing posture |
| P2H Release Checkpoint | HOLD archive |
| Prompt Repair History | P2D prompt-repair chain |

## 3. Workspace pins

`OperatorWorkspacePins` on Overview pins: ETH Watch Gate · Stage 4.19 Blocker · Safety Invariants · Provider Routing.

## 4. URL query / hash behavior

Presets navigate with `targetPage?query#hash` only. Evidence filters sync via MVP-18 `useEvidenceFilterQueryState`. Hash scroll retries briefly for late DOM.

## 5. Copy link behavior

`EvidencePresetCard` copies absolute preset URL via Clipboard API; fallback shows manual text if unavailable. No server write.

## 6. Read-only navigation policy

Allowed: Open preset · Copy link · View Evidence / Gate / Runbook / Provider / Risk.  
Forbidden: Buy/Sell/Execute · Run 30m/60m · Start Stage 4.19 · routing/ARM editors.

## 7. Safety checks

```bash
python tools/research/check_nexus_ui_mvp19_safety.py
```

## 8. Build / typecheck

```bash
cd frontend && npm run typecheck && npm run build
```

## 9. Backend HOLD unchanged

No 30m / 60m / Stage 4.19 / routing / prompt / MAE / RG edits.

## 10. Trading backend untouched

## 11. Future public SaaS still not implemented

## 12. Next UI step

Optional: user-named pin labels still static-only (no account sync) under HOLD.

---

**Stop:** Backend HOLD · UI read-only · do not start Stage 4.19.  
**Note:** MVP-18 shares filter state; MVP-19 adds fixed private research workspace shortcuts.
