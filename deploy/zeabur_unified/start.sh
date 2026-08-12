#!/bin/sh
# NEXUS V18.2.30.1 Unified Zeabur Runtime
# Supervises: Gunicorn (Web) + ResearchAutonomyService (24/7 Demo)
# One container / one /data / one trading engine.
#
# Process-scoped EXCHANGE_WRITE:
#   - Autonomy child may receive EXCHANGE_WRITE=true (Demo only)
#   - Web/Gunicorn always receives EXCHANGE_WRITE=false (public auth hard-ban safe)
set -eu

PORT="${PORT:-8080}"
CAMPAIGN_ROOT="${NEXUS_CAMPAIGN_ROOT:-/data/campaigns/research_v18_2_30}"
CYCLE_SLEEP="${NEXUS_CYCLE_SLEEP_SEC:-120}"
WEB_PID=""
AUTO_PID=""
SHUTTING_DOWN=0

log() { echo "[unified $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

mkdir -p \
  "${CAMPAIGN_ROOT}/autonomy" \
  "${CAMPAIGN_ROOT}/checkpoints" \
  /data/evidence_coordinator \
  /data/autonomy/locks

# Cloud identity + single-engine defaults (never enable legacy embedded Binance worker)
export NEXUS_RUNTIME_LOCATION="${NEXUS_RUNTIME_LOCATION:-ZEABUR}"
export NEXUS_DATA_ROOT="${NEXUS_DATA_ROOT:-/data}"
export NEXUS_CAMPAIGN_ROOT="${CAMPAIGN_ROOT}"
export NEXUS_EVIDENCE_COORDINATOR="${NEXUS_EVIDENCE_COORDINATOR:-/data/evidence_coordinator}"
export NEXUS_ZEABUR_AUTONOMY_DEPLOYED="${NEXUS_ZEABUR_AUTONOMY_DEPLOYED:-true}"
export NEXUS_WEB_ONLY="${NEXUS_WEB_ONLY:-true}"
export NEXUS_EMBEDDED_WORKER="${NEXUS_EMBEDDED_WORKER:-false}"
export NEXUS_LEGACY_WORKER_DISABLED="${NEXUS_LEGACY_WORKER_DISABLED:-true}"
export NEXUS_AUTONOMOUS_DEMO_AUTO_SEND="${NEXUS_AUTONOMOUS_DEMO_AUTO_SEND:-false}"
export NEXUS_MEMBER_EXECUTION="${NEXUS_MEMBER_EXECUTION:-false}"
export NEXUS_PRODUCTION_BILLING="${NEXUS_PRODUCTION_BILLING:-false}"
# Legacy bounded-demo auto-trader flag — must stay false; V30 ResearchAutonomyService is authoritative
export DEMO_AUTONOMOUS_ENABLED="${DEMO_AUTONOMOUS_ENABLED:-false}"
export MAINNET=false
export REAL_MONEY=false

# Resolve autonomy write permission from supervisor input (do NOT leave true on global export)
_RAW_AUTO_WRITE="${NEXUS_AUTONOMY_EXCHANGE_WRITE:-}"
if [ -z "${_RAW_AUTO_WRITE}" ]; then
  # Backward-compat: if Founder still set global EXCHANGE_WRITE=true in Zeabur, use it for autonomy only
  _RAW_AUTO_WRITE="${EXCHANGE_WRITE:-false}"
fi
case "$(printf '%s' "${_RAW_AUTO_WRITE}" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on) AUTO_EXCHANGE_WRITE=true ;;
  *) AUTO_EXCHANGE_WRITE=false ;;
esac

# CRITICAL: supervisor + Web default is write-disabled. Autonomy gets an override below.
export EXCHANGE_WRITE=false

cleanup() {
  if [ "$SHUTTING_DOWN" -eq 1 ]; then
    return
  fi
  SHUTTING_DOWN=1
  log "SIGTERM/SIGINT — stopping autonomy then web"
  if [ -n "$AUTO_PID" ] && kill -0 "$AUTO_PID" 2>/dev/null; then
    # Prefer graceful STOP file for ResearchAutonomyService
    touch "${CAMPAIGN_ROOT}/autonomy/STOP" 2>/dev/null || true
    kill -TERM "$AUTO_PID" 2>/dev/null || true
  fi
  if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill -TERM "$WEB_PID" 2>/dev/null || true
  fi
  # Wait up to ~25s
  i=0
  while [ "$i" -lt 25 ]; do
    alive=0
    if [ -n "$AUTO_PID" ] && kill -0 "$AUTO_PID" 2>/dev/null; then alive=1; fi
    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then alive=1; fi
    if [ "$alive" -eq 0 ]; then
      break
    fi
    i=$((i + 1))
    sleep 1
  done
  if [ -n "$AUTO_PID" ] && kill -0 "$AUTO_PID" 2>/dev/null; then
    log "autonomy still alive — SIGKILL"
    kill -KILL "$AUTO_PID" 2>/dev/null || true
  fi
  if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
    log "web still alive — SIGKILL"
    kill -KILL "$WEB_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  log "shutdown complete"
}

trap cleanup INT TERM

log "env_isolation auto_exchange_write=${AUTO_EXCHANGE_WRITE} web_exchange_write=false mainnet=false real_money=false"
log "starting ResearchAutonomyService campaign_root=${CAMPAIGN_ROOT}"
# Process-scoped: Demo write only for autonomy child
EXCHANGE_WRITE="${AUTO_EXCHANGE_WRITE}" \
MAINNET=false \
REAL_MONEY=false \
python -m backend.nexus_research_ai_autonomy.research_autonomy_service \
  --run \
  --campaign-root "${CAMPAIGN_ROOT}" \
  --cycle-sleep-sec "${CYCLE_SLEEP}" &
AUTO_PID=$!

log "starting Gunicorn PORT=${PORT} (EXCHANGE_WRITE=false)"
# Process-scoped: Web never inherits execution-enabled state
EXCHANGE_WRITE=false \
MAINNET=false \
REAL_MONEY=false \
NEXUS_MEMBER_EXECUTION=false \
NEXUS_PRODUCTION_BILLING=false \
DEMO_AUTONOMOUS_ENABLED=false \
gunicorn -c gunicorn.conf.py "app:app" &
WEB_PID=$!

# Write unified health once at boot
python - <<'PY' || true
import json, os, time
from pathlib import Path
from datetime import datetime, timezone
root = Path(os.environ.get("NEXUS_EVIDENCE_COORDINATOR", "/data/evidence_coordinator"))
root.mkdir(parents=True, exist_ok=True)
payload = {
  "schema": "v18_2_30_1_unified_runtime_health_v1",
  "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "runtime_location": os.environ.get("NEXUS_RUNTIME_LOCATION", "ZEABUR"),
  "web_process_alive": True,
  "autonomy_process_alive": True,
  "active_trade_engine": "ResearchAutonomyService",
  "legacy_worker_disabled": True,
  "web_exchange_write": os.environ.get("EXCHANGE_WRITE", "false"),
  "exchange_domain": "api-demo.bybit.com",
}
(root / "unified_runtime_health.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

log "supervisor watching web_pid=${WEB_PID} auto_pid=${AUTO_PID}"

# Supervise: if either dies unexpectedly, tear down and exit non-zero for Zeabur restart
while true; do
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    log "CRITICAL: web process died"
    cleanup
    exit 1
  fi
  if ! kill -0 "$AUTO_PID" 2>/dev/null; then
    log "CRITICAL: autonomy process died"
    cleanup
    exit 1
  fi
  # Refresh lightweight unified health (best-effort)
  python - <<'PY' || true
import json, os
from pathlib import Path
from datetime import datetime, timezone
root = Path(os.environ.get("NEXUS_EVIDENCE_COORDINATOR", "/data/evidence_coordinator"))
camp = Path(os.environ.get("NEXUS_CAMPAIGN_ROOT", "/data/campaigns/research_v18_2_30"))
hb = {}
p = camp / "autonomy" / "service_heartbeat.json"
if p.is_file():
    try:
        hb = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        hb = {}
payload = {
  "schema": "v18_2_30_1_unified_runtime_health_v1",
  "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "runtime_location": os.environ.get("NEXUS_RUNTIME_LOCATION", "ZEABUR"),
  "web_process_alive": True,
  "autonomy_process_alive": True,
  "overall": "RUNNING",
  "active_trade_engine": "ResearchAutonomyService",
  "legacy_worker_disabled": True,
  "web_exchange_write": os.environ.get("EXCHANGE_WRITE", "false"),
  "exchange_domain": "api-demo.bybit.com",
  "last_autonomy_heartbeat": hb.get("last_heartbeat_at"),
  "last_cycle": hb.get("last_cycle_completed") or hb.get("last_cycle_started"),
  "next_cycle": hb.get("next_cycle_due"),
  "service_status": hb.get("service_status"),
  "open_position": (hb.get("health") or {}).get("open_position") if isinstance(hb.get("health"), dict) else None,
  "ai": hb.get("ai"),
}
root.mkdir(parents=True, exist_ok=True)
(root / "unified_runtime_health.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
  sleep 5
done
