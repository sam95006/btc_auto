# NEXUS / EATI — Repository Map (Phase A)

**`main` is the only source-of-truth** for `sam95006/btc_auto`.

`deploy/*` is a **deployment definition / packaging layer**, not a second copy of application source.
ZIP bundles under `artifacts/deploy/` are local evidence only — never the primary deploy path.

## Current layout (authoritative today)

| Area | Location today | Notes |
|------|----------------|-------|
| NEXUS Core | `backend/nexus_*`, `backend/core/` | Do not mass-move in Phase A |
| EATI Learning | `backend/learning/`, `backend/nexus_demo_execution/`, `tools/research/` | Gradual migration target: `eati/` |
| Apps | `app.py`, `run.py`, `frontend/`, `apps/` | Operator UI + Flask entry |
| Integrations | `backend/nexus_official_market_adapters/`, Bybit demo clients | Target: `integrations/` |
| Deployments | `deploy/zeabur_*` | One folder per Zeabur service |
| Configs | `config/` | Target alias: `configs/` (Phase B) |
| Docs | `docs/` | Architecture / validation / runbooks |
| Artifacts | `artifacts/` | Evidence, reports, local deploy bundles (ignored/local) |
| CI | `.github/workflows/` | Founder-gated; no silent Real Money |

## Target information architecture (Phase B migration)

See ideal tree in root `README.md`. **Do not relocate import-critical packages until dependency audit proves it is safe.**

## Rules

1. Never reset / force-push / revert `main` to an older architecture.
2. Never commit secrets, API keys, Zeabur tokens, or local `.env` values.
3. Never treat a ZIP upload as source-of-truth.
4. Zeabur deploys must target a **named** `deploy/<service>/` package + GitHub `main` checkout.
5. Bybit Demo Learning Validation is **demo/paper only** — not Stage3, not member preview, not production ARM.
