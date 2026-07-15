# NEXUS UI-DEPLOY-2 — Zeabur Live Runtime Verification

**Date:** 2026-07-15  
**Branch:** `stage3-demo-learning`  
**Prior fix commit:** `c840401`  
**Backend:** HOLD · no MVP-20 · no Stage 4.19 · no 30m/60m  

---

## 1. Live check after c840401

| Check | Result |
|-------|--------|
| Zeabur deployment | `RUNNING` |
| Branch | `refs/heads/stage3-demo-learning` |
| Deployed commit | `c840401d1b6b54a65604d4aa11c9a761e09fab1d` (≥ c840401) |
| Public `/` | Still **legacy** “Stage 3 Demo Learning” space fleet |
| Top bar MVP-19 marker | **missing** |
| `GET /api/nexus/ui-build` | **404** |
| `GET /health` | `service=nexus-web` · **no** `root_serves` / `operator_ui_ready` |
| `/overview` … `/paper-lab` | **404** |
| `/nexus` | Legacy HTML (same template) |

**Verdict after c840401 alone:** commit landed, but **live process still served old UI**.

---

## 2. Runtime inspection (service exec)

Container `/app` is **repo root**, not `deploy/zeabur_stage3_demo_learning`:

- Present: `app.py`, `run.py`, `zbpack.json`, `backend/`, `frontend/`, `static/operator_ui/`
- Start: `gunicorn … app:app` (`zbpack.json` / root `Dockerfile`)
- `STAGE3_DEPLOY_VERSION.json` **not** at `/app`
- `tools/research/` **excluded** by root `.dockerignore` (`tools/research/`)
- `stage3_readonly_web_app.py` only under `/app/deploy/zeabur_stage3_demo_learning/...` and **not** the process that listens on `:8080`
- `static/operator_ui/index.html` **present** + marker in JS asset
- `curl localhost:8080/health` → `nexus-web` (matches public URL)

### Corrected root cause

| Prev assumption (UI-DEPLOY-1) | Live reality (UI-DEPLOY-2) |
|-------------------------------|----------------------------|
| Zeabur root = deploy package Flask | Zeabur root = **monorepo** · **nexus-web** |
| Fixing package Flask `/` is enough | Package Flask is **not** what public domain runs |
| | `run.py` `/` → `templates/nexus_command.html` |

Classification:

- `MULTIPLE_UI_SOURCE_MISMATCH` (confirmed)
- `BACKEND_SERVES_OLD_STATIC` / `ROOT_ROUTE_OLD_UI` on **nexus-web**
- `FRONTEND_BUILD_NOT_USED` on Zeabur (still true; dist is pre-synced)
- Docs/root mismatch: written root directory ≠ live build root

---

## 3. Fix applied (UI-DEPLOY-2)

Static-serve only (no trading / provider / RG / prompt changes):

1. `backend/api/operator_ui_routes.py` — SPA assets, SPA fallback, `/api/nexus/ui-build`
2. `run.py` — `/` prefers `static/operator_ui`; `/health` exposes `operator_ui_ready` + `root_serves`; register operator routes
3. Legacy remains at `/nexus` (existing `server.py` route)

---

## 4. Post-fix verification targets

After this commit deploys `RUNNING`:

1. `/health` → `root_serves=operator_ui`, `operator_ui_ready=true`
2. `/api/nexus/ui-build` → `buildMarker=NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60`
3. `/` HTML loads SPA `index.html` + `/assets/index-*.js` containing marker
4. `/overview` `/evidence` `/risk-evidence` `/provider-shadow` `/paper-lab` → SPA
5. `/nexus` → legacy Stage 3 UI
6. Top bar: `UI Build: MVP-19 · 76e8b60 · Market Intelligence · HOLD`

---

## 5. Safety

Trading logic / provider routing / Risk Governor / Stage 4.19 / 30m / 60m / orders / ARM / billing / secrets: untouched.

## 6. Gate

Backend HOLD. No MVP-20. Await live re-verify after this deploy.
