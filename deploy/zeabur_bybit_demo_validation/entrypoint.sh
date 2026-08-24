#!/bin/sh
# Demo Validation entrypoint — packaging boot boundary.
# Modes:
#   NEXUS_VALIDATION_BOOT=health      → minimal /health server (default)
#   NEXUS_VALIDATION_BOOT=full_engine → gunicorn app:app (Full Engine)
# Never enables Real Money / unbounded autonomous send from this script.
set -eu

cd /app 2>/dev/null || cd "$(dirname "$0")/../.."

DATA_DIR="${NEXUS_DATA_DIR:-/app/data/nexus_demo_validation}"
mkdir -p "$DATA_DIR" || DATA_DIR="/tmp/nexus_demo_validation"
mkdir -p "$DATA_DIR" || true
if touch "$DATA_DIR/.write_test" 2>/dev/null; then
  rm -f "$DATA_DIR/.write_test"
  echo "persistence_probe=ok data_dir=$DATA_DIR"
else
  DATA_DIR="/tmp/nexus_demo_validation"
  mkdir -p "$DATA_DIR"
  echo "persistence_probe=fallback data_dir=$DATA_DIR"
  export NEXUS_DATA_DIR="$DATA_DIR"
fi

PORT_RESOLVED="${PORT:-}"
case "$PORT_RESOLVED" in
  ''|\$\{*\} ) PORT_RESOLVED="${WEB_PORT:-8080}" ;;
esac
case "$PORT_RESOLVED" in
  ''|*[!0-9]* ) PORT_RESOLVED=8080 ;;
esac
export PORT="$PORT_RESOLVED"

echo "service_mode=BYBIT_DEMO_VALIDATION"
echo "bind_host=0.0.0.0"
echo "bind_port=$PORT"
echo "validation_boot=${NEXUS_VALIDATION_BOOT:-health}"

# Bake file fills gaps only — never clobber Zeabur/process FOUNDER_GATE already set for 12H.
if [ -f ./demo_founder_gate.env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      ''|\#*) continue ;;
    esac
    case "$line" in
      *=*) ;;
      *) continue ;;
    esac
    k=${line%%=*}
    v=${line#*=}
    k=$(printf '%s' "$k" | tr -d ' \t\r')
    # shellcheck disable=SC2086
    eval "cur=\${$k-}"
    if [ -z "$cur" ]; then
      export "$k=$v"
    fi
  done < ./demo_founder_gate.env
  echo "founder_gate_file=loaded_gaps_only"
fi

# Deployment identity: baked file (build-arg) wins; else Zeabur/GitHub env (no temp CTX).
resolve_commit_identity() {
  if [ -s ./DEPLOYMENT_COMMIT ]; then
    tr -d ' \t\r\n' < ./DEPLOYMENT_COMMIT
    return 0
  fi
  for key in NEXUS_DEPLOYMENT_COMMIT NEXUS_SOURCE_COMMIT GITHUB_SHA; do
    # shellcheck disable=SC2086
    eval "val=\${$key-}"
    val=$(printf '%s' "$val" | tr -d ' \t\r\n')
    if [ -n "$val" ] && [ "$val" != "unknown" ] && [ "$val" != "MISSING" ]; then
      printf '%s' "$val"
      return 0
    fi
  done
  return 1
}

if DEPLOY_SHA=$(resolve_commit_identity); then
  printf '%s' "$DEPLOY_SHA" > ./DEPLOYMENT_COMMIT
  printf '%s' "$DEPLOY_SHA" > ./SOURCE_COMMIT
  export NEXUS_DEPLOYMENT_COMMIT="$DEPLOY_SHA"
  export NEXUS_SOURCE_COMMIT="$DEPLOY_SHA"
  export NEXUS_DEPLOYMENT_ID="$DEPLOY_SHA"
  export GITHUB_SHA="${GITHUB_SHA:-$DEPLOY_SHA}"
  echo "deployment_identity_source=baked_or_env"
else
  echo "deployment_identity_source=missing"
fi

echo "founder_gate=${FOUNDER_GATE:-MISSING}"
echo "founder_6h_approved=${FOUNDER_6H_APPROVED:-MISSING}"
echo "founder_12h_approved=${FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3:-MISSING}"
echo "deployment_commit=${NEXUS_DEPLOYMENT_COMMIT:-MISSING}"
echo "demo_autonomous_enabled=${DEMO_AUTONOMOUS_ENABLED:-false}"
echo "exchange_write=${EXCHANGE_WRITE:-false}"
echo "mainnet=${MAINNET:-false}"
echo "real_money=${REAL_MONEY:-false}"

# Fail-closed: never enable unbounded autonomous send from this entrypoint.
export DEMO_AUTONOMOUS_ENABLED=false
export AUTONOMOUS_SEND=false
export EXCHANGE_WRITE=false
export NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=false
export NEXUS_WEB_ONLY=true
export NEXUS_EMBEDDED_WORKER=false
export MAINNET=false
export REAL_MONEY=false

BOOT="${NEXUS_VALIDATION_BOOT:-health}"
case "$BOOT" in
  full_engine|FULL_ENGINE|full)
    echo "boot_target=gunicorn_app"
    exec gunicorn -c gunicorn.conf.py app:app
    ;;
  *)
    echo "boot_target=validation_health_server"
    exec python ./validation_health_server.py
    ;;
esac
