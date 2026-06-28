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

_start_stage4_cloud_dry_run() {
  STAGE4_OUT="${STAGE4_OUTPUT_DIR:-/data/stage4_ai_decisions_42_10m}"
  STAGE3_DIR="${STAGE3_OUTPUT_DIR:-/data/stage3_demo_learning}"
  STAGE4_SYMBOLS_VAL="${STAGE4_SYMBOLS:-ETHUSDT,BTCUSDT}"
  STAGE4_POLL="${STAGE4_POLL_INTERVAL_SECONDS:-120}"
  mkdir -p "$STAGE4_OUT"

  if [ "${STAGE4_REQUIRE_STAGE3_CONTEXT:-false}" = "true" ]; then
    if ! python tools/research/check_stage3_context_seed.py --target-dir "$STAGE3_DIR"; then
      echo "Stage 4 cloud dry-run blocked: missing required stage3 context"
      python tools/research/run_stage4_ai_decision_dry_run.py \
        --fail-summary-only \
        --failed-reason missing_required_stage3_context \
        --duration-minutes "${STAGE4_CLOUD_DRY_RUN_MINUTES}" \
        --poll-interval-seconds "$STAGE4_POLL" \
        --symbols "$STAGE4_SYMBOLS_VAL" \
        --mode dry-run \
        --use-real-llm \
        --output-dir "$STAGE4_OUT" \
        >> "$STAGE4_OUT/stage4_cloud_dry_run.log" 2>&1 || true
      return 0
    fi
  fi

  if [ "${STAGE4_REQUIRE_REAL_LLM:-false}" = "true" ]; then
    if ! python tools/research/run_stage4_ai_decision_dry_run.py \
      --preflight-only \
      --use-real-llm \
      --output-dir "$STAGE4_OUT" \
      >> "$STAGE4_OUT/stage4_cloud_dry_run.log" 2>&1; then
      echo "Stage 4 cloud dry-run blocked: real LLM required but Groq key missing or provider unavailable"
      return 0
    fi
  fi

  echo "Stage 4 cloud dry-run: ${STAGE4_CLOUD_DRY_RUN_MINUTES}m -> $STAGE4_OUT (background, no orders)"
  python tools/research/run_stage4_ai_decision_dry_run.py \
    --duration-minutes "${STAGE4_CLOUD_DRY_RUN_MINUTES}" \
    --poll-interval-seconds "$STAGE4_POLL" \
    --symbols "$STAGE4_SYMBOLS_VAL" \
    --mode dry-run \
    --use-real-llm \
    --output-dir "$STAGE4_OUT" \
    >> "$STAGE4_OUT/stage4_cloud_dry_run.log" 2>&1 &
}

if [ "$MODE" = "idle" ]; then
  echo "Stage 3 idle web mode: starting read-only UI"
  if [ "${STAGE4_DRY_RUN_ONLY:-false}" = "true" ] && [ "${STAGE4_CLOUD_DRY_RUN_MINUTES:-0}" != "0" ]; then
    _start_stage4_cloud_dry_run
  fi
fi

if [ "$MODE" != "idle" ] && [ "$MODE" != "runner" ]; then
  echo "unknown STAGE3_STARTUP_MODE=${MODE}"
  exit 1
fi

exec python tools/research/stage3_readonly_web_app.py
