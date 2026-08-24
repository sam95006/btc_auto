# Zeabur Service ID Map (non-secret)

IDs below are **public routing identifiers**, not credentials.

## Confirmed Validation (live)

| Field | Value |
|-------|-------|
| `VALIDATION_SERVICE_NAME` | `nexus-bybit-demo-learning-validation` |
| `VALIDATION_SERVICE_ID` | `6a82a79aa21454a2cf6b0015` |
| `VALIDATION_SERVICE_ID_CONFIRMED` | **yes** |

Live post-deploy evidence (disarmed health boundary): `persistence_probe=ok`, `MAINNET=false`, `REAL_MONEY=false`, `EXCHANGE_WRITE=false`, `DEMO_AUTONOMOUS_ENABLED=false`.

**This is the only current Validation deploy target.**

## Confirmed-forbidden (never overwrite)

| Role | Service ID | Rule |
|------|------------|------|
| Stage3 | `6a3b81652fdef84a45a2a553` | Never overwrite |
| Member / Preview | `69d559cb2696d526abde8cda` | Never overwrite |
| Member Preview static | `6a744ba3472e2c91a9e728a8` | Never overwrite |

## Obsolete / historical Validation candidate

| Service ID | Status |
|------------|--------|
| `6a69ad539949111176cefe63` | **OBSOLETE** — former repo candidate; **NOT** the live `nexus-bybit-demo-learning-validation` service. Do **not** deploy Validation workloads to it. Treat as forbidden for Validation targeting. |

## Packaging

- Source-of-truth: GitHub `main`
- Deploy definition: `deploy/zeabur_bybit_demo_validation/`
- Full engine Dockerfile (repo-root build context): `deploy/zeabur_bybit_demo_validation/Dockerfile.full_engine`
- Pin via Zeabur env: `ZBPACK_DOCKERFILE_PATH=deploy/zeabur_bybit_demo_validation/Dockerfile.full_engine` (or minimal `Dockerfile` for health-only)
