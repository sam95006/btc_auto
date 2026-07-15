# NEXUS UI-DEPLOY-3 — Live MVP-20 Polish Verification

**Date:** 2026-07-15  
**Branch:** `stage3-demo-learning`  
**Service:** `nexus-stage3-bybit-demo-learning`  
**URL:** `https://nexus-stage3-bybit-demo-learning.zeabur.app`  
**Backend:** HOLD · no 30m/60m · Stage 4.19 not started · UI read-only  

---

## 1. MVP-20 recap

Commit `4687fb0` polished live Market Intelligence:

- Compact top bar (no horizontal scroll)
- AI Commander de-dup (rail vs chip strip)
- Fleet trading-summary copy
- Badge noise reduction
- Sidebar product groups
- Marker preserved: `NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60` (display: `MVP-19 · live`)

## 2. Deployed commit

| Field | Value |
|-------|-------|
| Deployment ID | `6a57078cf9e67eefe065f59a` |
| Status | `RUNNING` |
| Ref | `refs/heads/stage3-demo-learning` |
| commitSHA | `4687fb0d08ccb14a436052d9478a92998a3c993f` |
| ≥ 4687fb0? | **YES** |
| finishedAt | `2026-07-15T04:09:01.479Z` |

## 3. `/health` result

```json
{
  "operator_ui_ready": true,
  "root_serves": "operator_ui",
  "build_marker": "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60",
  "service": "nexus-web",
  "status": "ok"
}
```

## 4. `/api/nexus/ui-build` result

```json
{
  "operator_ui_ready": true,
  "buildMarker": "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60",
  "ui_version": "MVP-19",
  "ui_style": "Market Intelligence Layout",
  "served_by": "nexus-web",
  "legacy_nexus_path": "/nexus"
}
```

## 5. Root route result

| Check | Result |
|-------|--------|
| `/` SPA | **PASS** (`id=root`, assets `index-DlxPnL8V.js` / `index-DSDINYht.css`) |
| Legacy Stage 3 title | **absent** |
| Old MVP-19 asset hashes | **absent** |

## 6. SPA routes result

| Route | Result |
|-------|--------|
| `/overview` | SPA |
| `/evidence` | SPA |
| `/risk-evidence` | SPA |
| `/provider-shadow` | SPA |
| `/paper-lab` | SPA |
| `/nexus` | Legacy Stage 3 (`Stage 3 Demo Learning`) |

## 7. Top bar polish result

| Check | Evidence |
|-------|----------|
| No horizontal scroll styling | CSS `overflow-x: hidden` + `top-status-primary` layout |
| Primary chips structure | JS contains `top-status-primary`, Backend/HOLD, BLOCKED, READ ONLY, `MVP-19` + `live` |
| Full marker not crowded in top bar | Full marker in `/health` + footer (`app-footer` / sync meta) |

**Verdict:** `top_bar_no_horizontal_scroll=true`, `top_bar_primary_chips_ok=true`

## 8. AI Commander de-dup result

| Check | Evidence |
|-------|----------|
| Compact main chips | JS: `see right rail` / chip-strip path |
| Full rail AI Commander | App shell still mounts desktop rail + mobile dock (from MVP-20 App.tsx) |
| No raw dual MCC embed | MCC no longer ships full panel string path; chip strip present |

**Verdict:** `ai_commander_deduplicated_live=true`

## 9. Fleet card polish result

| Check | Evidence |
|-------|----------|
| Polished BTC copy | `Prior evidence only` present |
| Polished ETH copy | `Watch condition not reappeared` present |
| Raw debug gone | `NONE (latest regen)` **absent** |
| 4-col fleet grid | CSS `repeat(4, …)` present |

**Verdict:** `fleet_cards_polished_live=true`

## 10. Badge noise result

Polish commit reduces per-card DEMO DATA / disclaimer spam; top/secondary + footer carry lower-priority text. Live bundle matches MVP-20 build hashes.

**Verdict:** `badge_noise_reduced_live=true` (bundle-level)

## 11. Sidebar result

JS contains `Operator Console`, `Validation Lab`, `Public SaaS` grouping labels from polished sidebar.

**Verdict:** `sidebar_polished_live=true`

## 12. Cache / hard refresh note

- Index `Cache-Control: no-cache, must-revalidate`
- Re-fetch with `Cache-Control: no-cache` still returns `index-DlxPnL8V` SPA (not legacy)
- Operator tip: Ctrl+F5 or private window if a browser still shows old JS chunk

**hard_refresh_tested:** true (API/header-level no-cache re-fetch)

## 13. Final verdict

**PASS — Live serves MVP-20 polish (`4687fb0`).**

Root cause if failed: N/A (`root_cause_if_failed=null`)

## 14. Next recommendation

- Backend remains **HOLD**
- Do **not** start Stage 4.19 / 30m / 60m
- Optional next UI: MVP-21 only after operator visual sign-off in browser
- Prefer hard refresh once after each deploy
