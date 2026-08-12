# NEXUS Zeabur Autonomy Worker (V18.2.30.1)

## Architecture

```
Zeabur Project
├── nexus-web          → existing Dockerfile / Gunicorn
└── nexus-autonomy-worker → Dockerfile.autonomy / ResearchAutonomyService
```

Do **not** run 24/7 autonomy inside the web Gunicorn process.

## Create service (Founder)

1. New Zeabur service in the same project: `nexus-autonomy-worker`
2. Same repo / root as campaign worktree (or monorepo path that contains `backend/nexus_research_ai_autonomy`)
3. Dockerfile: `Dockerfile.autonomy` (repo root) **or** `deploy/zeabur_autonomy_worker/Dockerfile`
4. Persistent Volume mount: `/data`
5. Replicas: **1** (duplicate guard + single-flight also enforced)

## Start command

```bash
python -m backend.nexus_research_ai_autonomy.research_autonomy_service \
  --run \
  --campaign-root /data/campaigns/research_v18_2_30 \
  --cycle-sleep-sec 120
```

## Required env / secrets

| Key | Value |
|---|---|
| `EXCHANGE_WRITE` | `true` |
| `MAINNET` | `false` |
| `REAL_MONEY` | `false` |
| `BYBIT_DEMO_API_KEY` | secret |
| `BYBIT_DEMO_API_SECRET` | secret |
| `BYBIT_DEMO_UID_EXPECTED` | optional UID match |
| `NEXUS_RUNTIME_LOCATION` | `ZEABUR` |
| `NEXUS_DATA_ROOT` | `/data` |
| `GROQ_API_KEY_PRIMARY` | optional AI probe |
| `GROQ_API_KEY_SECONDARY` | optional |
| `CEREBRAS_API_KEY` | optional |
| `SAMBANOVA_API_KEY` | optional |

Never commit secrets. Never expose keys via Founder API.

## Persistence

| Path | Purpose |
|---|---|
| `/data/campaigns/research_v18_2_30/autonomy/` | scheduler state, heartbeat, AI health, locks metadata |
| `/data/campaigns/research_v18_2_30/checkpoints/` | position checkpoints |
| `/data/autonomy/locks/` | single-instance lock |

## Safety

- Demo only (`api-demo.bybit.com`)
- Leverage 1x · notional ≤500 · wallet risk ≤0.10% · max concurrent Research = 1
- Boot fails closed on domain/UID/credential/storage failure
- AI failure ≠ `WAITING_MARKET` (reports `DEGRADED` + AI state)
- Partner Intelligence remains frozen

## Verify after deploy

Heartbeat file should advance across cadence:

`/data/campaigns/research_v18_2_30/autonomy/service_heartbeat.json`

Expect `runtime_location=ZEABUR`, rising `cycles_24h`, and distinct `last_cycle_*` timestamps ~120s apart.
