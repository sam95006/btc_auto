#!/usr/bin/env bash
# Wave 5.1 browser readiness: backend /health + frontend /overview before Playwright.
# Deterministic / fixture mode — no private Bybit API, no exchange write.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

export PUBLIC_MARKET_DATA_ONLY=true
export BYBIT_PRIVATE_API=false
export EXCHANGE_WRITE=false
export AUTONOMOUS_SEND=false
export MAINNET=false
export REAL_MONEY=false
export ARM=false
export EXPLICIT_FIXTURE_MODE=true
export NEXUS_ZEABUR_CLEAN_OBSERVER=false
export FIXED_LEVERAGE=25
export AI_CAN_CHANGE_LEVERAGE=false
export PORT=8080
export CI=true
export PLAYWRIGHT_REUSE_SERVER=1

BACKEND_LOG="${ROOT}/artifacts/wave5/backend_e2e.log"
FRONTEND_LOG="${ROOT}/artifacts/wave5/frontend_preview.log"
mkdir -p "${ROOT}/artifacts/wave5"

echo "==> frontend npm ci / build / playwright chromium"
cd "${ROOT}/frontend"
npm ci --no-audit --no-fund
npm run build
npx playwright install --with-deps chromium

echo "==> start backend (gunicorn) on :8080"
cd "${ROOT}"
pkill -f 'gunicorn.*app:app' 2>/dev/null || true
nohup gunicorn -b 127.0.0.1:8080 -w 1 --timeout 60 app:app >"${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!
echo "backend_pid=${BACKEND_PID}"

wait_http() {
  local url="$1"
  local name="$2"
  local ok=0
  for i in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "${name}_200=true url=${url} attempt=${i}"
      ok=1
      break
    fi
    sleep 2
  done
  if [ "$ok" != "1" ]; then
    echo "${name}_200=false url=${url}" >&2
    echo "---- backend log ----" >&2
    tail -n 120 "${BACKEND_LOG}" >&2 || true
    echo "---- frontend log ----" >&2
    tail -n 120 "${FRONTEND_LOG}" >&2 || true
    kill "${BACKEND_PID}" 2>/dev/null || true
    exit 1
  fi
}

wait_http "http://127.0.0.1:8080/health" "health"
echo "webserver_started=true (backend)"

echo "==> start vite preview on :4173"
cd "${ROOT}/frontend"
pkill -f 'vite preview.*4173' 2>/dev/null || true
nohup npx vite preview --host 127.0.0.1 --port 4173 --strictPort >"${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID=$!
echo "frontend_pid=${FRONTEND_PID}"

wait_http "http://127.0.0.1:4173/overview" "overview"
echo "overview_200=true"
echo "playwright_started=true"

cd "${ROOT}/frontend"
set +e
npx playwright test --grep-invert "@visual|@a11y" --reporter=line
PW_EXIT=$?
set -e

kill "${FRONTEND_PID}" 2>/dev/null || true
kill "${BACKEND_PID}" 2>/dev/null || true
wait "${FRONTEND_PID}" 2>/dev/null || true
wait "${BACKEND_PID}" 2>/dev/null || true

exit "${PW_EXIT}"
