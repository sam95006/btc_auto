# NEXUS V18.2.30.1 — Zeabur nexus-autonomy-worker env manifest (names only)

## Required (must set)

| Name | Value |
|---|---|
| EXCHANGE_WRITE | true |
| MAINNET | false |
| REAL_MONEY | false |
| BYBIT_DEMO_API_KEY | \<Zeabur secret\> |
| BYBIT_DEMO_API_SECRET | \<Zeabur secret\> |
| NEXUS_ZEABUR_AUTONOMY_DEPLOYED | true |
| NEXUS_RUNTIME_LOCATION | ZEABUR |
| NEXUS_DATA_ROOT | /data |
| NEXUS_CAMPAIGN_ROOT | /data/campaigns/research_v18_2_30 |

## Strongly recommended

| Name | Value |
|---|---|
| BYBIT_DEMO_UID_EXPECTED | \<your Demo UID\> |
| NEXUS_EVIDENCE_COORDINATOR | /data/evidence_coordinator |

## Optional AI probe (observability only; NOT required for V30 entry)

| Name | Notes |
|---|---|
| GROQ_API_KEY_PRIMARY | probe / future LLM |
| GROQ_API_KEY_SECONDARY | optional |
| CEREBRAS_API_KEY | optional |
| SAMBANOVA_API_KEY | optional |

## Do NOT set

| Name | Why |
|---|---|
| MAINNET=true | forbidden |
| REAL_MONEY=true | forbidden |
| BYBIT_API_KEY (mainnet) | wrong lane |
| BINANCE_* | wrong exchange |

## Service

- name: nexus-autonomy-worker
- Dockerfile: Dockerfile.autonomy
- volume: /data
- replicas: 1
- start: baked into Dockerfile.autonomy CMD
