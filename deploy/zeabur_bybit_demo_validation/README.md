# Zeabur Bybit Demo Learning Validation

Independent **Bybit Demo** learning / validation packaging.

Application source = GitHub **`main`** repository root.  
This folder = Docker / entrypoint / health / gate templates only.

## Allowed

- Bybit Demo
- Learning validation / evidence / reflection / behavior-change checks
- Paper / demo validation sessions (Founder-gated)

## Forbidden

- Real Money
- Production ARM
- Stage3 production promotion
- Overwriting member preview or Stage3 services
- Treating Bybit Demo as a Binance Testnet replacement

## Files

| File | Role |
|------|------|
| `Dockerfile` | Minimal validation image (repo-root build context) |
| `Dockerfile.full_engine` | Full-engine packaging variant |
| `entrypoint.sh` | Boot boundary; keeps write flags disarmed |
| `validation_health_server.py` | Minimal `/health` server |
| `Procfile` | Process declaration if needed |
| `demo_founder_gate.env` | Non-secret Founder gate flags only |
| `.env.example` | Secret **names** / placeholders |
| `.zeaburignore` | Upload exclusions |
| `README.md` | This file |

## Build context

```bash
# From repository root on main:
docker build -f deploy/zeabur_bybit_demo_validation/Dockerfile -t nexus-demo-val .
```

Dockerfile may `COPY` from repository root (`backend/`, `config/`, …). Do not duplicate those trees into this folder.

## Required env (Zeabur / GitHub Secrets — never commit values)

```
BYBIT_DEMO=true
MAINNET=false
REAL_MONEY=false
DEMO_AUTONOMOUS_ENABLED=false
AUTONOMOUS_SEND=false
EXCHANGE_WRITE=false
FIXED_LEVERAGE=25
NEXUS_DATA_ROOT=/app/data/nexus_demo_validation
NEXUS_DATA_DIR=/app/data/nexus_demo_validation
```

Optional secrets (GitHub / Zeabur only):

- `BYBIT_DEMO_API_KEY`
- `BYBIT_DEMO_API_SECRET`
- `NEXUS_BOUNDED_SESSION_CONTROL_SECRET`
- `NEXUS_POSTGRES_URL`

## Service mapping

See [docs/validation/SERVICE_ID_MAP.md](../../docs/validation/SERVICE_ID_MAP.md).

Repo-documented Validation candidate: `6a69ad539949111176cefe63`.  
Live confirmation required before deploy. Never use Stage3 / member preview IDs.

## Deploy

1. Checkout **`main`**
2. Use Founder `workflow_dispatch` (not silent push to Validation)
3. Target packaging: `deploy/zeabur_bybit_demo_validation/`
4. Deploy only the dedicated Validation Zeabur service

Stale path (disabled): `.github/workflows/founder_approved_demo_validation_deploy.yml` (formerly checked out a feature branch).

## Health

```bash
curl -sf "$BASE_URL/health"
```

## Blockers

- Do **NOT** use Stage3 SERVICE_ID `6a3b81652fdef84a45a2a553`
- Do **NOT** use Member Preview IDs listed in the service map
- Requires `ZEABUR_TOKEN` + `ZEABUR_PROJECT_ID` (+ Validation service id secret)
