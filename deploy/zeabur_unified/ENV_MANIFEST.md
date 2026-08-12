# NEXUS V18.2.30.1 — EXISTING SERVICE unified env (nexus-member-preview-v18-2-1)

## KEEP_ENV (set / keep)

| Name | Value |
|---|---|
| EXCHANGE_WRITE | true |
| MAINNET | false |
| REAL_MONEY | false |
| BYBIT_DEMO_API_KEY | \<secret\> |
| BYBIT_DEMO_API_SECRET | \<secret\> |
| NEXUS_ZEABUR_AUTONOMY_DEPLOYED | true |
| NEXUS_RUNTIME_LOCATION | ZEABUR |
| NEXUS_DATA_ROOT | /data |
| NEXUS_CAMPAIGN_ROOT | /data/campaigns/research_v18_2_30 |
| NEXUS_EVIDENCE_COORDINATOR | /data/evidence_coordinator |
| NEXUS_WEB_ONLY | true |
| NEXUS_EMBEDDED_WORKER | false |
| NEXUS_LEGACY_WORKER_DISABLED | true |
| NEXUS_AUTONOMOUS_DEMO_AUTO_SEND | false |
| PORT | (Zeabur managed) |

## REMOVE_ENV (delete from Zeabur if present)

These can accidentally enable legacy / wrong-lane execution:

- BINANCE_API_KEY / BINANCE_API_SECRET / BINANCE_TESTNET_*
- NEXUS_TRADING_MODE=binance_testnet (or any Binance mode)
- NEXUS_EMBEDDED_WORKER=true
- NEXUS_WEB_ONLY=false (with embedded worker)
- MAINNET=true / REAL_MONEY=true
- BYBIT_API_KEY / BYBIT_API_SECRET (mainnet lane names)
- NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=true (unless Founder explicitly wants old auto-send)
- PURE_AI_* / legacy auto-trader keys
- Stage4 order auto-exec enable flags (if any custom ones were added)
- NEXUS_CAMPAIGN_ROOT pointing to D:\ or local paths
- any EXCHANGE pointing at api.bybit.com (mainnet)

## OPTIONAL_ENV

| Name | Notes |
|---|---|
| BYBIT_DEMO_UID_EXPECTED | fail-closed UID match |
| GROQ_API_KEY_PRIMARY | AI health probe only |
| GROQ_API_KEY_SECONDARY | optional |
| CEREBRAS_API_KEY | optional |
| SAMBANOVA_API_KEY | optional |
| NEXUS_AUTONOMY_REQUIRE_AI_ENTRY | default false |
| NEXUS_CYCLE_SLEEP_SEC | default 120 |

## active_trade_engine

ResearchAutonomyService (only)

## volume

/data

## replicas

1
