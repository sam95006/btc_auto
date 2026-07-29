# NEXUS Demo Validation Zeabur 502 Incident Report

## 1. First Observed

- 2026-07-29 — independent service `nexus-bybit-demo-learning-validation` domain `https://nexus-bybit-demo-val.zeabur.app` returned HTTP 502 on `/health` while Deploy Workflow reported success.
- Stage3 `https://nexus-stage3-bybit-demo-learning.zeabur.app/health` remained HTTP 200 (not overwritten).

## 2. Affected Service

| Field | Value |
|-------|-------|
| Name | `nexus-bybit-demo-learning-validation` |
| Service ID | `6a69ad539949111176cefe63` |
| Domain | `https://nexus-bybit-demo-val.zeabur.app` |
| Project | `69d559b62696d526abde8cd9` |
| Environment | `69d559b6474db8a99d6dd6bf` |

## 3. Stage3 Impact

- **None.** Stage3 service ID `6a3b81652fdef84a45a2a553` was never targeted. Stage3 `/health` stayed 200 throughout.

## 4. Build Method (pre-fix)

- Zeabur CLI `zeabur deploy` from **repository root** zip upload.
- Service template: `PREBUILT_V2`.
- Diagnose note: *"This deployment was started from a container image and was not built on Zeabur"* — runtime logs unavailable via CLI during UNKNOWN status.

## 5. Build Context (pre-fix)

- **Actual:** repository root (full monorepo).
- Service `Root Directory` empty.
- **Not used:** `deploy/zeabur_bybit_demo_validation/` as build root (Dockerfile existed but was not the effective deploy package).

## 6. Dockerfile

| Phase | Path / behavior |
|-------|-----------------|
| Pre-fix (effective) | Repo-root `Dockerfile` → `CMD gunicorn -c gunicorn.conf.py app:app` |
| Latent defect | `deploy/zeabur_bybit_demo_validation/Dockerfile` referenced missing `entrypoint.sh` |
| Post-fix package | Slim Stage3-style context assembled in CI (`app.py`, `run.py`, `gunicorn.conf.py`, `backend/`, `requirements.txt`, root `Dockerfile`) |

## 7. Start Command

```text
gunicorn -c gunicorn.conf.py app:app
```

- Flask entry: `app:app` (via `app.py` → `run.create_app()`), **not** `uvicorn backend.api.server:app`.
- `backend/api/server.py` remains a route-registration module only.

## 8. Listening Port

- Gunicorn binds `0.0.0.0:$PORT` (Zeabur injects `PORT`).
- Domain `portName=web`, status `PROVISIONED`.

## 9. Runtime Fatal Error

Primary crash path (local Docker reproduction with `NEXUS_DATA_DIR=/data/nexus_demo_validation` and no writable volume):

```text
PermissionError: [Errno 13] Permission denied: '/data/nexus_demo_validation'
  at backend/core/data_paths.py → resolve_data_dir() mkdir
  imported during RuntimeStateStore / app startup
→ gunicorn worker never binds → Zeabur edge 502
```

Secondary latent defect: Demo Dockerfile `COPY entrypoint.sh` when file was missing (would fail image build if that Dockerfile were used with that context).

## 10. Root Cause

**Hard `mkdir` on `NEXUS_DATA_DIR=/data/nexus_demo_validation` during import/startup without a mounted writable volume**, causing process exit before HTTP listen. Combined with full-monorepo PREBUILT deploy producing `Status=UNKNOWN` and empty runtime logs, the edge surfaced as persistent 502.

## 11. Contributing Factors

1. Workflow set `NEXUS_DATA_DIR=/data/...` without attaching a Zeabur volume.
2. `resolve_data_dir()` treated mkdir failure as fatal.
3. Demo API state also mkdir’d eagerly at import.
4. Root `zeabur deploy` of full monorepo → fragile PREBUILT / UNKNOWN status (hard to diagnose).
5. Demo package Dockerfile/entrypoint inconsistency (not the path Zeabur actually ran, but a landmine).

## 12. Why Deploy Run Showed Success

- Zeabur CLI reported upload/deploy acceptance and domain provision success.
- Edge returned 502 because **no healthy upstream process** was listening — deploy success ≠ process health.
- CLI could not surface runtime logs while service status was UNKNOWN.

## 13. Minimal Fix

1. Soft `resolve_data_dir()` with writable fallbacks (`/tmp/nexus_demo_validation`, etc.).
2. Soft/lazy demo persistence paths; health decoupled from Bybit/SQLite.
3. Safer gunicorn PORT resolution + startup banner (no secrets).
4. Add `deploy/zeabur_bybit_demo_validation/entrypoint.sh`; fix Demo Dockerfile for **repo-root** build context.
5. Workflow: `NEXUS_DATA_DIR=/tmp/nexus_demo_validation`, `NEXUS_WEB_ONLY=true`, `NEXUS_EMBEDDED_WORKER=false`.
6. CI assembles **slim Stage3-style deploy context**, `zeabur deploy --service-id` same service, then `service restart` + sleep before smoke.

Key commits (feature branch / main workflow PRs): runtime soft-path + slim deploy packaging (see git log around `be9229b` / deploy workflow updates on `main`).

## 14. Local Reproduction

```text
docker build -t nexus-demo-val-rc .
docker run -e PORT=8080 -e NEXUS_DATA_DIR=/data/nexus_demo_validation \
  -e DEMO_AUTONOMOUS_ENABLED=false -e EXCHANGE_WRITE=false ...
→ PermissionError / crash (pre-fix)
```

Post-fix: same image with soft paths → process stays up; `/health` 200 without credentials.

## 15. Local Container Result

- Pre-fix: `container_running` fails / process exits; health unreachable.
- Post-fix: `health_200=true`, `exchange_write_call_count=0`, no Bybit required for `/health`.

## 16. Redeploy Run

- Recovering deploy: GitHub Actions run **`30438414655`** (success).
- Same service ID retained (no third duplicate service created for recovery).

## 17. Runtime Logs

- Post-recovery: service serves HTTP; diagnose still limited on PREBUILT log pull, but live probes confirm process up.
- Startup intent: `service_mode=BYBIT_DEMO_VALIDATION`, bind `0.0.0.0:$PORT`, flags false for autonomous/write/mainnet/real_money.

## 18. Health T+0 / 60 / 180

| Probe | Result |
|-------|--------|
| T+0 `/health` | **200** |
| T+60 `/health` | **200** |
| T+180 `/health` | **200** |

(Service health stability only — not account triple snapshot.)

## 19. Account Gate Result

- Live Demo private read: `source=BYBIT_DEMO_PRIVATE_API`.
- Example: wallet/equity ≈ 5023.46 USDT, available ≈ 5029.54 USDT, positions=0, orders=0.
- Readonly cycle: `success=true`, `terminal_stage=FOUNDER_CONFIRMATION_REQUIRED`.
- Reconciliation: `MATCH`; protection: `VERIFIED`; dry-run intent persisted; order payload `VALID`.
- Account T+0/60/180 all HTTP 200, `source=BYBIT_DEMO_PRIVATE_API`, wallet/equity ≈ 5023.46, available ≈ 5029.54, positions=0, orders=0 (evidence: `artifacts/demo_validation_502/account_snapshots.jsonl`).

## 20. Exchange Write Count

- `exchange_write_call_count=0` (cycle + status).

## 21. Mainnet Count

- `mainnet=false`, `real_money=false` on all probed endpoints.

## 22. Remaining Blockers

- **Founder confirmation** required before first Demo smoke order (`first_demo_smoke_order_ready=false`).
- PR #6 remains Draft; must not merge until Founder approves.
- Persistence currently under `/data/nexus_demo_validation` or `/tmp/...` depending on env — durable Volume attach still recommended for long runs (not a 502 blocker).
- No first Demo order, no autonomous enablement in this incident closeout.

## Recommendation

`DEMO_VALIDATION_SERVICE_READY_FOR_FOUNDER_SMOKE_ORDER_APPROVAL`

(Service healthy; offline+online readonly gates at `FOUNDER_CONFIRMATION_REQUIRED`; write/autonomous still off.)

## Fixed flags

```text
first_demo_smoke_order=false
demo_autonomous_enabled=false
exchange_write=false
mainnet=false
real_money=false
```
