#!/bin/sh
# Stage 3 C+3 — Zeabur background demo-order micro session (not 24h runner).
set -eu

OUT="${NEXUS_DATA_DIR:-/data}/stage3_demo_learning"
mkdir -p "$OUT"

if [ "${STAGE3_BACKGROUND_FORKED:-}" != "1" ]; then
  export STAGE3_BACKGROUND_FORKED=1
  GO="${OPERATOR_GO_STAGE3_C1_DEMO_ORDER:-}"
  nohup env OPERATOR_GO_STAGE3_C1_DEMO_ORDER="$GO" STAGE3_BACKGROUND_FORKED=1 \
    sh "$0" >>"$OUT/nohup.out" 2>&1 &
  BG_PID=$!
  echo "$BG_PID" >"$OUT/background_session.pid"
  cd /app 2>/dev/null || cd "$(dirname "$0")"
  python tools/research/read_stage3_background_status.py --write \
    phase=C+3 \
    status=spawned \
    pid="$BG_PID" \
    background_session_started=true \
    operator_go_present="$([ "$GO" = "true" ] && echo true || echo false)" || true
  echo "STARTED background_pid=$BG_PID"
  exit 0
fi

cd /app 2>/dev/null || cd "$(dirname "$0")"

LOG="$OUT/background_session.log"
PIDFILE="$OUT/background_session.pid"

echo "$$" >"$PIDFILE"
exec >>"$LOG" 2>&1

echo "=== background session start $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ ==="

python tools/research/read_stage3_background_status.py --write \
  phase=C+3 \
  status=starting \
  pid="$$" \
  operator_go_checked=false \
  strict_env_passed=false \
  preflight_passed=false \
  session_completed=false \
  validator_passed=false

if ! python -c "from tools.research.stage3_operator_go import operator_go_present; import sys; sys.exit(0 if operator_go_present() else 1)"; then
  python tools/research/read_stage3_background_status.py --write status=failed error=operator_go_missing
  exit 1
fi

python tools/research/read_stage3_background_status.py --write operator_go_present=true operator_go_checked=true status=strict_env

if ! python tools/research/check_bybit_demo_learning_env.py --strict-env --no-check-package --no-load-local-env; then
  python tools/research/read_stage3_background_status.py --write status=failed error=strict_env_failed
  exit 1
fi

python tools/research/read_stage3_background_status.py --write strict_env_passed=true status=preflight

if ! python tools/research/preflight_stage3_demo_order.py; then
  python tools/research/read_stage3_background_status.py --write status=failed error=preflight_failed
  exit 1
fi

python tools/research/read_stage3_background_status.py --write \
  preflight_passed=true \
  status=running \
  background_session_started=true \
  started_at_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python tools/research/run_bybit_demo_learning_runner.py \
  --mode demo-order \
  --duration-minutes 10 \
  --poll-interval-seconds 15 \
  --max-orders 1
RUNNER_RC=$?

python tools/research/read_stage3_background_status.py --write runner_exit_code="$RUNNER_RC"

if [ "$RUNNER_RC" -ne 0 ]; then
  python tools/research/read_stage3_background_status.py --write status=failed error=runner_exit_nonzero
  exit "$RUNNER_RC"
fi

python tools/research/read_stage3_background_status.py --write status=validating session_completed=true

if python tools/research/validate_stage3_demo_learning_outputs.py --require-balance --require-demo-order; then
  VALIDATOR_RC=0
else
  VALIDATOR_RC=$?
fi

python tools/research/read_stage3_background_status.py --write \
  validator_exit_code="$VALIDATOR_RC" \
  validator_passed="$([ "$VALIDATOR_RC" -eq 0 ] && echo true || echo false)" \
  status="$([ "$VALIDATOR_RC" -eq 0 ] && echo completed || echo validator_failed)"

python tools/research/read_stage3_background_status.py --finalize-report

echo "=== background session end $(date -u +%Y-%m-%dT%H:%M:%SZ) rc=$VALIDATOR_RC ==="
exit "$VALIDATOR_RC"
