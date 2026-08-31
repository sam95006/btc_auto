# Corporate site — deploy artifact contract (CORPORATE-1)

Code/config only. **No Corporate Zeabur service exists yet → `CORPORATE_DEPLOY_TARGET_REQUIRED`.**
This stage does NOT deploy, and MUST NOT deploy Corporate onto the Personal
(`btc-auto`) or private trading (`nexus-bybit-demo-learning-validation`) services.

## Artifact
- Build: `npm run build:corporate` → **artifact ROOT** `frontend/dist/corporate`
  (contains `index.html` + `assets/`). Serve THIS root (SPA fallback via
  [`server.py`](server.py); fails closed on the wrong parent root).
- [`Dockerfile`](Dockerfile) builds `dist/corporate` and serves it via a tiny
  Python static server. No backend, no trading runtime, no secrets.

## Architecture
```
Corporate frontend service (static, no secrets)
        -> Core / Corporate API (nexus-api-staging, public /api/corporate/v1/*)
             -> PostgreSQL (private network only)
```
The static build carries only a **public** API origin (`VITE_NEXUS_API_ORIGIN`,
default `https://nexus-api-staging.zeabur.app`). No DB DSN / Bybit / AI / Founder
secret is present in the Corporate bundle (enforced by the surface-boundary and
`check_corporate_no_fake_data` checks + `tests/corporate`).

## To deploy later (a dedicated Corporate service must be provisioned first)
1. Create a NEW Zeabur static service (e.g. `nexus-corporate-staging`) in the BTC project.
2. GitHub-link it to `sam95006/btc_auto` main, set `ZBPACK_DOCKERFILE_PATH=deploy/zeabur_corporate_v1/Dockerfile`.
3. Optionally set `VITE_NEXUS_API_ORIGIN` to the Corporate API origin (build var; non-secret).
4. Ensure the Core API (`nexus-api-staging`) CORS allowlist includes the Corporate domain.
