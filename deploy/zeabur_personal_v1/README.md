# Personal Market Intelligence — deploy artifact contract (PERSONAL-2)

This package formalizes how the **Personal** product frontend is packaged and
served. It is code/config + documentation only. **No Zeabur deployment is
performed by this stage, and no Zeabur environment or secret is read or
written.**

## 1. Artifact contract

- The Personal frontend is a static React Router SPA built by
  `npm run build:personal` (in `frontend/`).
- The build output — the **artifact ROOT** — is:

  ```
  frontend/dist/personal/
    index.html
    assets/...
  ```

- **The artifact root is `dist/personal` itself**, the directory that directly
  contains `index.html` and `assets/`. Deployment must serve **this** root.
  Serving the parent `frontend/dist/` is wrong: `dist/` has no `index.html`, so
  `GET /` returns 404. This is the known root-404 failure.

## 2. Runtime

- [`server.py`](server.py) — a tiny static SPA server. It serves the artifact
  root with **SPA fallback**: any non-file path resolves to `index.html`, so a
  direct browser refresh of `/`, `/app`, `/app/intelligence`,
  `/app/membership`, … returns the SPA (200), never a 404. It fails closed at
  startup if `NEXUS_PERSONAL_DIST` does not point at a valid artifact root.
- [`Dockerfile`](Dockerfile) — builds `dist/personal` and serves it via
  `server.py`. It **does not** run Gunicorn, `ResearchAutonomyService`, the
  Bybit runner, a trading worker, or any Founder/private runtime.

Config: `NEXUS_PERSONAL_DIST` (artifact root, default `/app/dist/personal`),
`PORT` (default `8080`).

## 3. Frontend / API are separable surfaces

The Personal static web artifact and the Personal API are **different
deployment surfaces** and need not share a process or container. The frontend
targets the API via `VITE_NEXUS_API_ORIGIN` (an explicit HTTPS origin); it must
not assume same-process co-hosting, and no final production domain is
hard-coded here.

## 4. Legacy root Dockerfile — ownership correction

The repository root [`Dockerfile`](../../Dockerfile) is the **PRIVATE unified
trading + web runtime** (Gunicorn + `ResearchAutonomyService`). Its historical
header called it "canonical deploy path for nexus-member-preview-v18-2-1".
Under the PLATFORM-1 four-surface separation that is **no longer the Personal
frontend's canonical deployment**:

- Personal frontend → **this** package (`deploy/zeabur_personal_v1`, static
  `dist/personal`).
- The root `Dockerfile` remains the private trading/research runtime and is
  **out of scope** for Personal closed-beta serving.

The trading runtime and its logic are unchanged; only the deployment ownership
is clarified so no future engineer treats the unified trading container as the
Personal frontend runtime.

## 5. Four-surface deployment contracts

Each surface is an independent artifact with its own document root. There is no
shared public document root.

| Surface    | Build            | Artifact root          | Serving                         |
|------------|------------------|------------------------|---------------------------------|
| Personal   | `build:personal` | `dist/personal`        | this package (static SPA)       |
| Corporate  | `build:corporate`| `dist/corporate`       | own static artifact (separate)  |
| Enterprise | `build:enterprise`| `dist/enterprise`     | own static artifact (separate)  |
| Founder    | `build:founder`  | `dist/founder`         | own PRIVATE artifact (separate) |

`dist/founder` and any private trading runtime must never be packaged into the
Personal image.

## 6. Zeabur watch-path / release-trigger ownership (documentation only)

To stop the Personal service from redeploying on every unrelated `main` commit,
the intended (future, not applied here) release-trigger ownership is:

- Personal service watch paths: `frontend/**`, `deploy/zeabur_personal_v1/**`.
- It should **not** rebuild for changes confined to `backend/nexus_strategy_*`,
  `backend/nexus_research_*`, private trading runtime, or the other surfaces.

This is guidance only. **This stage does not mutate Zeabur, does not deploy, and
inserts no Zeabur token or secret.** `ZEABUR DEPLOY / RUNTIME RECOVERY` remains
DEFERRED to a separate stage.
