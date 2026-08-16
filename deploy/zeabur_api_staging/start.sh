#!/bin/sh
# API-only staging entrypoint. Never launches a trading or Shadow runtime.
set -eu

export NEXUS_ENV=STAGING
export EXCHANGE_WRITE=false
export MAINNET=false
export REAL_MONEY=false
export NEXUS_MEMBER_EXECUTION=false
export NEXUS_PRODUCTION_BILLING=false
export NEXUS_RUNTIME_BINDING=UNAVAILABLE
export NEXUS_PG_RUNTIME_ENABLED=true
export NEXUS_PG_EVIDENCE_MIRROR_ENABLED=false

# DATABASE_URL is Zeabur secret-only and resolved through its private network.
# The migration CLI fails closed on connectivity, drift, or unsafe SQL.
python -m backend.nexus_persistence_pg.cli migrate apply

exec gunicorn -c gunicorn.conf.py "api_staging_app:app"
