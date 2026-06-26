#!/bin/sh
set -e
set -u

cd /app 2>/dev/null || cd "$(dirname "$0")"

if [ -f STAGE3_DEPLOY_VERSION.json ]; then
  python -c "import json; d=json.load(open('STAGE3_DEPLOY_VERSION.json', encoding='utf-8')); print('STAGE3_DEPLOY_VERSION'); print('commit=%s' % d.get('commit', 'unknown')); print('contains_24h_runner=%s' % str(d.get('contains_24h_runner', False)).lower()); print('contains_web_ui=%s' % str(d.get('contains_web_ui', False)).lower())"
fi

python tools/research/check_bybit_demo_learning_env.py --strict-env --no-check-package --no-load-local-env

MODE="${STAGE3_STARTUP_MODE:-idle}"
echo "stage3 strict-env passed; STAGE3_STARTUP_MODE=${MODE}"

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
  echo "24h demo learning runner spawned; starting read-only web UI"
fi

if [ "$MODE" = "idle" ]; then
  echo "Stage 3 idle web mode: starting read-only UI"
fi

if [ "$MODE" != "idle" ] && [ "$MODE" != "runner" ]; then
  echo "unknown STAGE3_STARTUP_MODE=${MODE}"
  exit 1
fi

exec python tools/research/stage3_readonly_web_app.py
