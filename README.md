# NEXUS AI Trading System

完整說明請閱讀：**[docs/NEXUS_GUIDE.zh-TW.md](docs/NEXUS_GUIDE.zh-TW.md)**

## Source of truth

- GitHub repository: **`sam95006/btc_auto`**
- Branch: **`main`** is the only source-of-truth
- **`deploy/*`** = deployment packaging for Zeabur targets (not a second source tree)
- Local ZIP under `artifacts/deploy/` = optional evidence only — not the primary deploy path

## Repository Map

| Area | Where (today) | Notes |
|------|---------------|-------|
| **NEXUS Core** | `backend/`, pointer `nexus/` | Core runtime / demo execution / bounded runtime |
| **EATI Learning** | `backend/learning/`, `tools/`, pointer `eati/` | Research, reflection, validation |
| **Apps** | `app.py`, `run.py`, `frontend/`, `apps/` | Web + operator / member UI |
| **Integrations** | market adapters under `backend/`, pointer `integrations/` | Binance / Bybit / external data |
| **Deployments** | `deploy/` — see [deploy/README.md](deploy/README.md) | One folder per Zeabur service |
| **Docs** | `docs/` | Architecture, validation, runbooks |
| **Artifacts** | `artifacts/` | Evidence / reports / local bundles |

Target information architecture and Phase A/B rules: [docs/architecture/REPOSITORY_MAP.md](docs/architecture/REPOSITORY_MAP.md).

## Quick start

- 本機：`python run.py` → http://127.0.0.1:5000/nexus  
- Zeabur：見指南第 5 節與 [deploy/README.md](deploy/README.md)  
- 資金與 Binance testnet 同步：見指南第 2 節  
- 清除舊 DB：`python tools/deploy/purge_runtime.py`（需先停止 `run.py`）

## Safety defaults

- `MAINNET=false` / `REAL_MONEY=false` for Demo Validation
- No production ARM from documentation paths
- Secrets only via GitHub Secrets / Zeabur Environment Variables
