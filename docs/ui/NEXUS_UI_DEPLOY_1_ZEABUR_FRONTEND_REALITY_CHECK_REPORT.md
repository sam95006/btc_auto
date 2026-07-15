# NEXUS UI-DEPLOY-1 — Zeabur Frontend Deployment Reality Check

**Date:** 2026-07-15  
**Branch:** `stage3-demo-learning`  
**Backend:** HOLD · Stage 4.19 BLOCKED · no 30m/60m  
**Scope:** Diagnose why Zeabur still showed Stage 3 space-fleet UI despite MVP-17~19 commits; wire Market Intelligence SPA into deploy package.

---

## 1. Problem recap

UI MVP-17 (`631e45f`), MVP-18 (`00faa01`), MVP-19 (`76e8b60`) were committed and pushed under `frontend/`. Zeabur still rendered the legacy Stage 3 “太空艦隊” command UI (`nexus_command.html` + `/static/nexus`), with none of the Market Intelligence panels visible.

## 2. Expected UI commit

| Field | Value |
|-------|-------|
| Expected latest UI commit | `76e8b60` |
| Full SHA (local/remote at check) | `76e8b602e432c9952fa432d587432983225d73e7` |
| UI style | Market Intelligence Layout (DataHunterX-inspired) |

## 3. Actual Zeabur deployed commit

| Field | Value |
|-------|-------|
| Zeabur current deployed commit | **Not readable from this environment** (no Zeabur CLI / authenticated dashboard API in session) |
| Package metadata pre-fix (`STAGE3_DEPLOY_VERSION.json`) | `8230f73d623e0b55005ad88b182c450e40cb5e71` (2026-07-08) — **stale vs MVP-17~19** |
| Git branch (Zeabur docs) | `stage3-demo-learning` |
| local HEAD (pre UI-DEPLOY-1 commit) | `76e8b60` |
| remote `origin/stage3-demo-learning` HEAD | `76e8b60` (matched) |
| Zeabur deployment id | Unknown (no live API) |
| Zeabur build time | Unknown (no live API) |
| Using `76e8b60` assets at runtime? | **No evidence** — package previously lacked `static/operator_ui` and served legacy `/` |

**Note:** Even if Zeabur auto-redeployed git HEAD `76e8b60`, the Dockerfile root is `deploy/zeabur_stage3_demo_learning` and never built `frontend/`, so the SPA would still be absent until this wire-up.

## 4. Build root

| Item | Value |
|------|-------|
| Zeabur service | `nexus-stage3-bybit-demo-learning` (docs) |
| **build_root** | `deploy/zeabur_stage3_demo_learning` (**B/C hybrid: package root, not repo root, not `frontend/`**) |
| Classification | Not case A (repo root). Not B (`frontend/`). Closest to **D + package Python app**. |

## 5. Build command

| Item | Value |
|------|-------|
| **build_command** | Docker: `pip install -r requirements.txt` only |
| `frontend/package.json` executed on Zeabur? | **No** |
| `npm run build` on Zeabur? | **No** |
| **frontend_build_executed** (on Zeabur) | `false` |
| Local UI-DEPLOY-1 | `cd frontend && npm run typecheck && npm run build` → sync into package |

## 6. Start command

| Item | Value |
|------|-------|
| **start_command** | `./entrypoint.sh` → `python tools/research/stage3_readonly_web_app.py` |
| Server | Flask read-only Stage 3 web |

## 7. Runtime served UI path (pre-fix)

| Item | Value |
|------|-------|
| **runtime_served_index_path** | `templates/nexus_command.html` via `/` |
| **runtime_served_static_path** | `/static/nexus/` |
| Operator SPA | Missing |

## 8. Whether frontend/dist is used

| Item | Value |
|------|-------|
| Zeabur historically used `frontend/dist`? | **No** → `FRONTEND_BUILD_NOT_USED` + `STATIC_DIST_NOT_COPIED` |
| After UI-DEPLOY-1 | Pre-built `frontend/dist` synced to `deploy/.../static/operator_ui/` and committed with package |
| **frontend_dist_created** (local) | `true` |
| Marker in dist | `NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60` found |

## 9. Whether multiple UI sources exist

**all_ui_directories_found:**

| Path | Role |
|------|------|
| `frontend/` | Cursor MVP-0~19 React/Vite Market Intelligence (**canonical new UI**) |
| `deploy/zeabur_stage3_demo_learning/static/nexus` + `templates/nexus_command.html` | Legacy Stage 3 space-fleet UI (what Zeabur served) |
| `deploy/zeabur_stage3_demo_learning/static/operator_ui` | **New** synced SPA for Zeabur (UI-DEPLOY-1) |
| `static/nexus` / `static/operator_ui` | Repo-root mirrors for local Flask ROOT |
| No `backend/frontend` customer app for this service | — |

| Question | Answer |
|----------|--------|
| Zeabur previously served which? | Legacy `nexus_command` |
| Cursor modified which? | `frontend/` |
| Mismatch? | **Yes** — `MULTIPLE_UI_SOURCE_MISMATCH` |

## 10. Whether new UI markers exist in runtime

| Check | Pre-fix Zeabur image (inferred) | Post-fix package (local) |
|-------|----------------------------------|---------------------------|
| MarketCommandCenter / CandidateBoard / … | Absent (not copied) | Present in minified JS under `static/operator_ui/assets/` |
| Build marker | Absent | Present: `NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60` |
| `/health` → `operator_ui_ready` | N/A / false | `true` when `index.html` present |
| `/api/nexus/ui-build` | N/A | Exposes marker + sync meta |

Live Zeabur runtime marker: **pending redeploy** after this commit is pushed and Zeabur rebuilds.

## 11. Root route / overview route result

| Route | Pre-fix | Post-fix (intended) |
|-------|----------|----------------------|
| `/` | Legacy space-fleet → `ROOT_ROUTE_OLD_UI` | Market Intelligence SPA `index.html` |
| `/overview` | 404 / not SPA | SPA fallback → Market Intelligence |
| `/evidence`, `/risk-evidence`, `/provider-shadow`, `/paper-lab` | Not served as SPA | SPA fallback |
| `/nexus` | (was `/`) | **Legacy** space-fleet kept for rollback |

## 12. Root cause classification

Primary (AND):

1. **FRONTEND_BUILD_NOT_USED** — Zeabur Docker never runs `frontend` npm build  
2. **MULTIPLE_UI_SOURCE_MISMATCH** — Cursor ships `frontend/`; Zeabur package served `nexus_command`  
3. **STATIC_DIST_NOT_COPIED** — `frontend/dist` never landed in deploy image  
4. **RUNTIME_SERVING_OLD_UI** / **BACKEND_SERVES_OLD_STATIC** — Flask `/` → legacy template  
5. **ROOT_ROUTE_OLD_UI** — root path was old UI  
6. **DEPLOY_STALE_COMMIT** (package metadata) — `STAGE3_DEPLOY_VERSION.json` still referenced `8230f73` era packaging  

Secondary / not confirmed live:

- **ZEEBUR_CACHE_OR_BUILD_CACHE** — possible but not required to explain symptoms  
- **BROWSER_CACHE_OR_ROUTE_ISSUE** — only if post-redeploy marker appears in `/api/nexus/ui-build` but browser still shows fleet UI  

## 13. Fix applied

1. Added `frontend/src/demo/buildInfo.ts` + TopStatusBar line:  
   `UI Build: MVP-19 · 76e8b60 · Market Intelligence · HOLD`  
2. Rewrote `tools/research/stage3_readonly_web_app.py` (and deploy package copy) to:  
   - serve `static/operator_ui` at `/` when present  
   - SPA fallback for MI routes  
   - keep legacy at `/nexus`  
   - expose `/health` + `/api/nexus/ui-build` markers  
3. Added `tools/deploy/sync_operator_ui_into_zeabur_stage3.py` to copy `frontend/dist` → deploy + repo `static/operator_ui`  
4. Ran local typecheck/build; synced assets; verified marker in dist and package  
5. Updated `STAGE3_DEPLOY_VERSION.json` for operator UI fields  

**Operator action after push:** Redeploy Zeabur service `nexus-stage3-bybit-demo-learning` (root still `deploy/zeabur_stage3_demo_learning`). Confirm:

- UI footer/chip shows MVP-19 · 76e8b60  
- `GET /api/nexus/ui-build` → `operator_ui_ready: true` + marker  
- `GET /health` → `root_serves: operator_ui`  
- `/nexus` still loads legacy if needed  

## 14. Safety confirmation

| Check | Result |
|-------|--------|
| Trading logic | Untouched |
| Provider routing | Untouched |
| Risk Governor | Untouched |
| Prompt / MAE / confidence floor | Untouched |
| Stage 4.19 | Not started |
| 30m / 60m | Not run |
| Order / ARM / billing / accounts / API keys UI | Not added |
| `/data`, jsonl, logs, secrets | Not committed |

## 15. Final verdict

**Root cause:** Zeabur was never serving Cursor’s `frontend/` Market Intelligence SPA. It served the Stage 3 Flask legacy template from the deploy package. MVP-17~19 were successful in-repo; deployment plumbing was missing.

**Status after this change:** Package and Flask serve path fixed, committed, and pushed as `c840401`. **Live Zeabur confirmation still requires a redeploy/rebuild**, then verify the build marker. Backend remains **HOLD**. Do not start Stage 4.19. Do not start MVP-20 until marker is visible on Zeabur.

**git_commit_hash:** `c840401` · **git_push_done:** yes (`origin/stage3-demo-learning`)

---

## Verification commands

```bash
cd frontend && npm run typecheck && npm run build
python tools/deploy/sync_operator_ui_into_zeabur_stage3.py
# Windows: findstr /s /i NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60 frontend\dist\*
rg "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60" frontend/dist deploy/zeabur_stage3_demo_learning/static/operator_ui
```

## Files touched (UI-DEPLOY-1)

- `frontend/src/demo/buildInfo.ts` (add)
- `frontend/src/components/TopStatusBar.tsx` (marker chip)
- `tools/research/stage3_readonly_web_app.py`
- `tools/deploy/sync_operator_ui_into_zeabur_stage3.py` (add)
- `deploy/zeabur_stage3_demo_learning/tools/research/stage3_readonly_web_app.py`
- `deploy/zeabur_stage3_demo_learning/static/operator_ui/**` (synced dist)
- `deploy/zeabur_stage3_demo_learning/STAGE3_DEPLOY_VERSION.json`
- `static/operator_ui/**` (repo-root sync)
- `docs/ui/NEXUS_UI_DEPLOY_1_ZEABUR_FRONTEND_REALITY_CHECK_REPORT.md`
