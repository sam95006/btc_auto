#!/bin/sh
# Demo Validation entrypoint — Flask/Gunicorn only; no Bybit calls at boot.
set -eu

cd /app 2>/dev/null || cd "$(dirname "$0")/../.."

DATA_DIR="${NEXUS_DATA_DIR:-/tmp/nexus_demo_validation}"
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

# Optional baked Founder gate file (CI deploy context).
if [ -f ./demo_founder_gate.env ]; then
  # shellcheck disable=SC1091
  set -a
  . ./demo_founder_gate.env
  set +a
  echo "founder_gate_file=loaded"
fi

echo "founder_gate=${FOUNDER_GATE:-MISSING}"
echo "founder_6h_approved=${FOUNDER_6H_APPROVED:-MISSING}"
echo "demo_autonomous_enabled=${DEMO_AUTONOMOUS_ENABLED:-false}"
echo "exchange_write=${EXCHANGE_WRITE:-false}"
echo "mainnet=${MAINNET:-false}"
echo "real_money=${REAL_MONEY:-false}"

# Fail-closed: never enable unbounded autonomous send from this entrypoint.
# Bounded 6H session uses FOUNDER_6H_APPROVED + in-process write window, not this flag.
export DEMO_AUTONOMOUS_ENABLED=false
export AUTONOMOUS_SEND=false
export EXCHANGE_WRITE=false
export NEXUS_AUTONOMOUS_DEMO_AUTO_SEND=false
export NEXUS_WEB_ONLY="${NEXUS_WEB_ONLY:-true}"
export NEXUS_EMBEDDED_WORKER="${NEXUS_EMBEDDED_WORKER:-false}"

exec gunicorn -c gunicorn.conf.py -b "0.0.0.0:${PORT}" app:app
