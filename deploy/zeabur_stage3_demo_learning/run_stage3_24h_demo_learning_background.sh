#!/bin/sh
# Stage 3 Phase D — 24h Bybit demo/testnet learning runner (research only, not production).
set -eu

OUT="${STAGE3_OUTPUT_DIR:-${NEXUS_DATA_DIR:-/data}/stage3_demo_learning}"
mkdir -p "$OUT/bundle"

if [ "${STAGE3_24H_FORKED:-}" != "1" ]; then
  export STAGE3_24H_FORKED=1
  export OPERATOR_GO_STAGE3_24H_RUNNER="${OPERATOR_GO_STAGE3_24H_RUNNER:-true}"
  export OPERATOR_GO_STAGE3_C1_DEMO_ORDER="${OPERATOR_GO_STAGE3_C1_DEMO_ORDER:-false}"
  nohup env STAGE3_24H_FORKED=1 \
    OPERATOR_GO_STAGE3_24H_RUNNER="$OPERATOR_GO_STAGE3_24H_RUNNER" \
    OPERATOR_GO_STAGE3_C1_DEMO_ORDER="$OPERATOR_GO_STAGE3_C1_DEMO_ORDER" \
    STAGE3_RUN_DURATION_MINUTES="${STAGE3_RUN_DURATION_MINUTES:-1440}" \
    STAGE3_POLL_INTERVAL_SECONDS="${STAGE3_POLL_INTERVAL_SECONDS:-15}" \
    STAGE3_MAX_ORDERS_PER_DAY="${STAGE3_MAX_ORDERS_PER_DAY:-6}" \
    sh "$0" >>"$OUT/stage3_24h_runner.log" 2>&1 &
  BG_PID=$!
  echo "$BG_PID" >"$OUT/stage3_24h_runner.pid"
  cd /app 2>/dev/null || cd "$(dirname "$0")"
  python tools/research/read_stage3_24h_status.py --write status=spawned pid="$BG_PID" run_started=true || true
  echo "STARTED_24H background_pid=$BG_PID"
  exit 0
fi

cd /app 2>/dev/null || cd "$(dirname "$0")"

DURATION="${STAGE3_RUN_DURATION_MINUTES:-1440}"
POLL="${STAGE3_POLL_INTERVAL_SECONDS:-15}"
MAX_ORDERS="${STAGE3_MAX_ORDERS_PER_DAY:-6}"

echo "$$" >"$OUT/stage3_24h_runner.pid"
exec >>"$OUT/stage3_24h_runner.log" 2>&1

echo "=== 24h runner start $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ duration=${DURATION}m max_orders=${MAX_ORDERS} ==="

python tools/research/read_stage3_24h_status.py --write \
  status=running \
  pid="$$" \
  run_started=true \
  run_completed=false \
  duration_minutes_target="$DURATION" \
  max_orders_per_day="$MAX_ORDERS" \
  started_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python tools/research/run_bybit_demo_learning_runner.py \
  --mode demo-order \
  --duration-minutes "$DURATION" \
  --poll-interval-seconds "$POLL" \
  --max-orders "$MAX_ORDERS" \
  --no-fresh-output
RUNNER_RC=$?

python tools/research/read_stage3_24h_status.py --write runner_exit_code="$RUNNER_RC" status=validating

VALIDATOR_RC=0
if python tools/research/validate_stage3_demo_learning_outputs.py --require-balance --require-24h-run; then
  VALIDATOR_RC=0
else
  VALIDATOR_RC=$?
fi

if [ "${STAGE3_EXPORT_BUNDLE_ON_EXIT:-true}" = "true" ]; then
  python tools/research/export_stage3_24h_learning_bundle.py || true
fi

python tools/research/read_stage3_24h_status.py --finalize-summary \
  validator_passed="$([ "$VALIDATOR_RC" -eq 0 ] && echo true || echo false)" \
  run_completed=true \
  status="$([ "$VALIDATOR_RC" -eq 0 ] && echo completed || echo validator_failed)"

echo "=== 24h runner end $(date -u +%Y-%m-%dT%H:%M:%SZ) rc=$RUNNER_RC validator=$VALIDATOR_RC ==="
exit "$VALIDATOR_RC"
