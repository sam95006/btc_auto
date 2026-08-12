# Zeabur Bybit Demo Validation Deploy

Independent DEMO-only validation service — **no exchange writes**.

## Service

- Name: `nexus-bybit-demo-learning-validation`
- Branch: `feature/bybit-demo-execution-validation`

## Required Env

```
BYBIT_DEMO=true
MAINNET=false
REAL_MONEY=false
DEMO_AUTONOMOUS_ENABLED=false
AUTONOMOUS_SEND=false
EXCHANGE_WRITE=false
NEXUS_ZEABUR_CLEAN_OBSERVER=false
FIXED_LEVERAGE=25
```

Optional (set via GitHub secrets, never log):

- `BYBIT_DEMO_API_KEY`
- `BYBIT_DEMO_API_SECRET`

## Deploy

Use workflow dispatch:

```
.github/workflows/founder_approved_demo_validation_deploy.yml
confirm=DEPLOY_DEMO_VALIDATION
```

## Post-deploy smoke

```bash
curl -sf "$BASE_URL/health"
curl -sf "$BASE_URL/api/nexus/demo-execution/status"
```

## Blockers

- Do **NOT** use Stage3 SERVICE_ID `6a3b81652fdef84a45a2a553`
- Requires `ZEABUR_TOKEN` + `ZEABUR_PROJECT_ID` secrets
- New service must be created separately (not overwrite live Stage3)
