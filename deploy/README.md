# Deployments (`deploy/`)

GitHub **`main`** = complete application source-of-truth.  
Folders under `deploy/` = **packaging / entrypoint / Dockerfile definitions** for each Zeabur target.

Do **not** duplicate application source into these folders.

## Catalog

| Folder | Purpose | Environment | Trading allowed | Real money | Health |
|--------|---------|-------------|-----------------|------------|--------|
| `zeabur_bybit_demo_validation/` | Bybit Demo Learning Validation | Bybit **Demo** only | Demo / paper validation only (Founder-gated) | **No** | `/health` |
| `zeabur_unified/` | Unified / main web runtime packaging | Project-configured | Depends on env; default disarmed in docs | **No** (must stay false unless Founder ARM) | `/health` via app |
| `zeabur_member_preview/` | Member UI preview static packaging | Preview | No trading engine | **No** | SPA / static |
| `zeabur_member_preview_v18_2_1/` | Member preview static server | Preview | No | **No** | static server |
| `zeabur_stage3_demo_learning/` | Stage3 demo learning (legacy / suspended caution) | Demo | Historical Stage3 | **No** | service-specific |
| `zeabur_api_staging/` | API staging | Staging | No production | **No** | staging health |
| `zeabur_staging/` | Staging manifests | Staging | No | **No** | n/a |
| `zeabur_runtime_staging/` | Runtime staging | Staging | No | **No** | n/a |
| `zeabur_live_ui_phase1/` | Live UI phase packaging | UI | No exchange writes by default | **No** | UI |
| `zeabur_unified_control_plane/` | Control plane packaging | Control | No | **No** | control health |
| `control_plane_smoke/` | Smoke helpers | CI / smoke | No | **No** | smoke |
| `zeabur_p2_migration_*` | Postgres migration helpers | Staging DB | No trading | **No** | n/a |

## Bybit Demo Learning Validation (primary focus)

- **Source folder:** `deploy/zeabur_bybit_demo_validation/`
- **Application code:** repository root (`backend/`, `app.py`, `run.py`, …) on **`main`**
- **Confirmed service id:** `6a82a79aa21454a2cf6b0015`
- **Build context:** repository root; `ZBPACK_DOCKERFILE_PATH=deploy/zeabur_bybit_demo_validation/Dockerfile.full_engine`
- **Forbidden targets:** Stage3 `6a3b81652fdef84a45a2a553`, member preview IDs, obsolete Validation `6a69ad539949111176cefe63`
- **Secrets:** GitHub Secrets / Zeabur env only — never commit API keys

### Preferred deploy workflow

- Founder `workflow_dispatch` only (no silent main-push deploy to Validation)
- Packaging references `deploy/zeabur_bybit_demo_validation/`
- Checkout **`main`**, never a stale feature branch

### Stale workflow

`founder_approved_demo_validation_deploy.yml` previously checked out `feature/bybit-demo-execution-validation`. Phase A disables its deploy path (fail-closed). Use a current Founder-gated Validation workflow that checks out `main`.

## Rules

1. One Zeabur service ↔ one `deploy/<name>/` definition.
2. `REAL_MONEY=false`, `MAINNET=false` for Demo Validation.
3. Never deploy Validation packaging onto Stage3 or Member Preview service IDs.
4. Local ZIP under `artifacts/deploy/` is optional evidence — not the GitHub source-of-truth path.
