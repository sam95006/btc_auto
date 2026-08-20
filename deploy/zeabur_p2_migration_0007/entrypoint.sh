#!/bin/sh
# P2 migration 0007 one-shot entrypoint — health server only; no trading or exchange calls.
set -eu

cd /app 2>/dev/null || cd "$(dirname "$0")/../.."

DATA_DIR="${NEXUS_DATA_DIR:-/tmp/nexus_p2_migration_0007}"
mkdir -p "$DATA_DIR" || DATA_DIR="/tmp/nexus_p2_migration_0007"
mkdir -p "$DATA_DIR" || true
export NEXUS_DATA_DIR="$DATA_DIR"

PORT_RESOLVED="${PORT:-}"
case "$PORT_RESOLVED" in
  ''|\$\{*\} ) PORT_RESOLVED="${WEB_PORT:-8080}" ;;
esac
case "$PORT_RESOLVED" in
  ''|*[!0-9]* ) PORT_RESOLVED=8080 ;;
esac
export PORT="$PORT_RESOLVED"

echo "service_mode=P2_MIGRATION_0007"
echo "bind_host=0.0.0.0"
echo "bind_port=$PORT"

if [ -f ./DEPLOYMENT_COMMIT ]; then
  DEPLOY_SHA=$(tr -d ' \t\r\n' < ./DEPLOYMENT_COMMIT)
  if [ -n "$DEPLOY_SHA" ]; then
    export NEXUS_DEPLOYMENT_COMMIT="$DEPLOY_SHA"
    export NEXUS_SOURCE_COMMIT="$DEPLOY_SHA"
    export NEXUS_DEPLOYMENT_ID="$DEPLOY_SHA"
    export GITHUB_SHA="${GITHUB_SHA:-$DEPLOY_SHA}"
  fi
fi

if [ -f ./SOURCE_COMMIT ]; then
  SOURCE_SHA=$(tr -d ' \t\r\n' < ./SOURCE_COMMIT)
  if [ -n "$SOURCE_SHA" ]; then
    export NEXUS_SOURCE_COMMIT="$SOURCE_SHA"
  fi
fi

echo "deployment_commit=${NEXUS_DEPLOYMENT_COMMIT:-MISSING}"
echo "source_commit=${NEXUS_SOURCE_COMMIT:-MISSING}"
echo "demo_autonomous_enabled=${DEMO_AUTONOMOUS_ENABLED:-false}"
echo "exchange_write=${EXCHANGE_WRITE:-false}"
echo "mainnet=${MAINNET:-false}"
echo "real_money=${REAL_MONEY:-false}"

export DEMO_AUTONOMOUS_ENABLED=false
export AUTONOMOUS_SEND=false
export EXCHANGE_WRITE=false
export NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=false
export NEXUS_WEB_ONLY=true
export NEXUS_EMBEDDED_WORKER=false

exec python ./migration_health_server.py
