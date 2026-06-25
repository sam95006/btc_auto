#!/bin/sh
set -e
set -u

cd /app 2>/dev/null || cd "$(dirname "$0")"

python tools/research/check_bybit_demo_learning_env.py --strict-env --no-check-package --no-load-local-env

MODE="${STAGE3_STARTUP_MODE:-idle}"
echo "stage3 strict-env passed; STAGE3_STARTUP_MODE=${MODE}"

if [ "$MODE" = "idle" ]; then
  echo "idle keepalive mode; runner not started"
  exec sleep infinity
fi

if [ "$MODE" = "runner" ]; then
  if [ "${OPERATOR_GO_STAGE3_24H_RUNNER:-false}" != "true" ]; then
    echo "OPERATOR_GO_STAGE3_24H_RUNNER required for STAGE3_STARTUP_MODE=runner"
    exit 1
  fi
  if ! python tools/research/preflight_stage3_24h_runner.py --no-load-local-env; then
    echo "preflight_stage3_24h_runner failed"
    exit 1
  fi
  sh /app/run_stage3_24h_demo_learning_background.sh
  echo "24h demo learning runner spawned; container keepalive"
  exec sleep infinity
fi

echo "unknown STAGE3_STARTUP_MODE=${MODE}"
exit 1
