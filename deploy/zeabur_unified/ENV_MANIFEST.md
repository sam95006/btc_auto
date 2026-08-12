# NEXUS V18.2.30.1 — EXISTING SERVICE unified env (nexus-member-preview-v18-2-1)

## KEEP_ENV (set / keep)

| Name | Value | Scope |
|---|---|---|
| NEXUS_AUTONOMY_EXCHANGE_WRITE | true | Supervisor → autonomy child only |
| EXCHANGE_WRITE | false (or unset) | Web-safe global default |
| MAINNET | false | both |
| REAL_MONEY | false | both |
| BYBIT_DEMO_API_KEY | \<secret\> | autonomy (Demo) |
| BYBIT_DEMO_API_SECRET | \<secret\> | autonomy (Demo) |
| NEXUS_ZEABUR_AUTONOMY_DEPLOYED | true | both |
| NEXUS_RUNTIME_LOCATION | ZEABUR | both |
| NEXUS_DATA_ROOT | /data | both |
| NEXUS_CAMPAIGN_ROOT | /data/campaigns/research_v18_2_30 | both |
| NEXUS_EVIDENCE_COORDINATOR | /data/evidence_coordinator | both |
| NEXUS_WEB_ONLY | true | web |
| NEXUS_EMBEDDED_WORKER | false | web |
| NEXUS_LEGACY_WORKER_DISABLED | true | web |
| NEXUS_AUTONOMOUS_DEMO_AUTO_SEND | false | both |
| NEXUS_MEMBER_EXECUTION | false | web |
| NEXUS_PRODUCTION_BILLING | false | web |
| DEMO_AUTONOMOUS_ENABLED | false | legacy flag only — does NOT gate V30 |
| PORT | (Zeabur managed) | web |

## Process isolation (`deploy/zeabur_unified/start.sh`)

- **ResearchAutonomyService** child: `EXCHANGE_WRITE=true` (from `NEXUS_AUTONOMY_EXCHANGE_WRITE`), `MAINNET=false`, `REAL_MONEY=false`
- **Gunicorn Web** child: `EXCHANGE_WRITE=false`, `MAINNET=false`, `REAL_MONEY=false`, member/billing false
- Do **not** set global Zeabur `EXCHANGE_WRITE=true` — that caused public auth HARD BAN on Web.

Backward-compat: if only legacy `EXCHANGE_WRITE=true` is set in Zeabur, start.sh still maps it to the autonomy child and forces Web to false.

## REMOVE_ENV (delete from Zeabur if present)

These can accidentally enable legacy / wrong-lane execution:

- Global `EXCHANGE_WRITE=true` (prefer `NEXUS_AUTONOMY_EXCHANGE_WRITE=true` instead)
- BINANCE_API_KEY / BINANCE_API_SECRET / BINANCE_TESTNET_*
- NEXUS_TRADING_MODE=binance_testnet (or any Binance mode)
- NEXUS_EMBEDDED_WORKER=true
- NEXUS_WEB_ONLY=false (with embedded worker)
- MAINNET=true / REAL_MONEY=true
- BYBIT_API_KEY / BYBIT_API_SECRET (mainnet lane names)
- NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=true (unless Founder explicitly wants old auto-send)
- DEMO_AUTONOMOUS_ENABLED=true (legacy 6H/12H auto-trader — keep false)
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
