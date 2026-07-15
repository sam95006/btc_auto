# NEXUS UI-LIVE-SIGNOFF-1 — Operator Visual Sign-off Checklist

**Purpose:** Human visual sign-off of Zeabur live MVP-20 before any MVP-21 work.  
**Scope:** Checklist only — no UI code changes, no backend changes, no runtime, no Stage 4.19.  
**Date ready:** 2026-07-15  

---

## 1. Live URL

`https://nexus-stage3-bybit-demo-learning.zeabur.app`

Optional legacy:

`https://nexus-stage3-bybit-demo-learning.zeabur.app/nexus`

Tip: use **Ctrl+F5** or a private window for the first pass.

---

## 2. Current deployed commit

| Item | Value |
|------|--------|
| UI polish commit (verified) | `4687fb0` |
| Verification report commit | `de73962` |
| Live verification | UI-DEPLOY-3 **PASS** |
| Expected service root | `operator_ui` (Market Intelligence SPA) |

Confirm (optional, 30s):

- `GET /health` → `operator_ui_ready=true`, `root_serves=operator_ui`
- `GET /api/nexus/ui-build` → `buildMarker=NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60`
- Top bar shows: `UI Build: MVP-19 · live`

---

## 3. Backend state HOLD

| Gate | Required |
|------|----------|
| Backend | **HOLD** |
| Runtime 30m / 60m | **Do not run** |
| Stage 4.19 | **BLOCKED** — do not start |
| Orders / ARM / routing edit | **Absent** |

This sign-off does **not** change backend state.

---

## 4. UI read-only

| Expectation | OK? |
|-------------|-----|
| Private Operator Mode only | ☐ |
| All actions are navigation (Evidence / Gate / Risk / Provider / Ask AI) | ☐ |
| No trading controls | ☐ |
| NOT INVESTMENT ADVICE visible (banner / footer / secondary) | ☐ |

---

## 5. Visual checklist

Mark each after browsing live (desktop first, then narrow width).

### Top bar

| Check | Pass? | Notes |
|-------|-------|-------|
| No horizontal scrollbar on top bar | ☐ | |
| Primary chips only: Backend HOLD · Stage 4.19 BLOCKED · Mode READ ONLY · UI Build MVP-19 · live | ☐ | |
| Secondary / footer carries lower-priority text (not crowding chips) | ☐ | |

### Sidebar

| Check | Pass? | Notes |
|-------|-------|-------|
| Groups clear: Operator Console / Research / Future | ☐ | |
| Labels feel product-like (not raw engineering dump) | ☐ | |
| Evidence / Risk / Validation Lab / Provider / Reports / Runbooks reachable | ☐ | |

### Overview / Market Intelligence

| Check | Pass? | Notes |
|-------|-------|-------|
| Overview looks like a Market Intelligence dashboard (not debug console) | ☐ | |
| System gate strip readable | ☐ | |
| Fleet cards readable (BTC / ETH / SOL / PEPE) | ☐ | |
| Fleet shows status / stance / intent / graduation / next without raw debug tone | ☐ | |
| CandidateBoard readable as a table | ☐ | |
| SignalFeed rows clear | ☐ | |
| AnomalyRadar compact and scannable | ☐ | |
| AI Commander **not duplicated** (desktop: full rail; main: compact chips only) | ☐ | |
| Badge noise acceptable (not DEMO DATA on every card) | ☐ | |

### Evidence / Provider

| Check | Pass? | Notes |
|-------|-------|-------|
| Evidence filter usable (search / presets / pins) | ☐ | |
| Provider Intelligence charts usable (read-only) | ☐ | |
| Deep links to runbook / gate / checkpoint still work | ☐ | |

### SPA routes

| Route | Looks OK? | Notes |
|-------|-----------|-------|
| `/` | ☐ | |
| `/overview` | ☐ | |
| `/evidence` | ☐ | |
| `/risk-evidence` | ☐ | |
| `/provider-shadow` | ☐ | |
| `/paper-lab` | ☐ | |
| `/nexus` still legacy Stage 3 (intentional) | ☐ | |

### Mobile / narrow

| Check | Pass? | Notes |
|-------|-------|-------|
| Layout acceptable at ~390px width (or phone) | ☐ | |
| No broken horizontal page overflow | ☐ | |
| AI Commander available via mobile dock / bottom area | ☐ | |
| Tables scroll locally without breaking the shell | ☐ | |

---

## 6. Safety checklist

| Check | Pass? |
|-------|-------|
| No Buy / Sell / Execute controls | ☐ |
| No Quick Order / 快速下單 | ☐ |
| No Run 30m / Run 60m buttons | ☐ |
| No Start Stage 4.19 button | ☐ |
| No API key collection UI | ☐ |
| No billing / checkout / customer accounts UI | ☐ |
| No `/trade` `/orders` `/arm` `/routing-edit` as product routes | ☐ |

---

## 7. Operator decision

Pick **one**:

| Decision | Meaning |
|----------|---------|
| ☐ **APPROVE_MVP20_VISUAL** | Live MVP-20 looks product-ready enough; MVP-21 may be considered next |
| ☐ **NEED_POLISH_FIXES** | Keep HOLD; list visual issues below; fix before MVP-21 |
| ☐ **HOLD_UI** | Pause UI track; no MVP-21; backend stays HOLD |

**Operator name / date:** __________________  
**Decision:** __________________  

---

## 8. If approved (`APPROVE_MVP20_VISUAL`)

Next allowed step (only after this checkbox is signed):

- UI **MVP-21** may be scoped (still read-only; still no Stage 4.19 / 30m / 60m unless separately approved)
- Backend remains HOLD unless an explicit backend gate is opened

Not automatically authorized:

- Live trading, orders, ARM, billing, customer SaaS, provider routing editors, Risk Governor editors

---

## 9. If not approved

List **specific visual issues only** (no trading/backend requests):

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________
4. _______________________________________________
5. _______________________________________________

Then prefer a small **polish-fix** pass (UI-only) before any MVP-21 feature work.

---

## Gate (do not clear until sign-off)

| Gate | Status |
|------|--------|
| Backend | HOLD |
| UI | read-only |
| 30m / 60m | blocked |
| Stage 4.19 | blocked |
| MVP-21 | **blocked until visual sign-off** |

**One-liner:** Deploy and live polish already passed — next is your browser pass to approve MVP-20 visually, not more feature work.
