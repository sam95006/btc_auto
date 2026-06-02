"""
Cloud maintainer for Zeabur NEXUS.

Designed for GitHub Actions:
- Poll /api/nexus/state and /api/nexus/pure-ai-status.
- Decide whether to redeploy (or just alert) based on simple, auditable rules.
- Never prints secrets.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import requests


DEFAULT_BASE_URL = os.getenv("NEXUS_BASE_URL", "https://btc-auto-bot-2026.zeabur.app").rstrip("/")

# Latency guard: if state takes too long repeatedly, redeploy to clear stuck workers.
MAX_STATE_MS = int(float(os.getenv("NEXUS_MAINT_MAX_STATE_MS", "12000")))

# If worker reports ERROR or last_tick_error exists, redeploy.
REDEPLOY_ON_TICK_ERROR = str(os.getenv("NEXUS_MAINT_REDEPLOY_ON_TICK_ERROR", "1")).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


@dataclass
class Fetch:
    ok: bool
    ms: int
    status: int
    payload: Dict[str, Any]
    error: str = ""


def _get_json(url: str, timeout: float = 15.0) -> Fetch:
    started = time.time()
    try:
        res = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-store"})
        ms = int((time.time() - started) * 1000)
        if not res.ok:
            return Fetch(False, ms, int(res.status_code), {}, f"http_{res.status_code}")
        try:
            payload = res.json()
        except Exception as exc:
            return Fetch(False, ms, int(res.status_code), {}, f"json_parse_failed:{exc}")
        if not isinstance(payload, dict):
            return Fetch(False, ms, int(res.status_code), {}, "json_not_object")
        return Fetch(True, ms, int(res.status_code), payload)
    except Exception as exc:
        ms = int((time.time() - started) * 1000)
        return Fetch(False, ms, 0, {}, f"request_failed:{exc}")


def _pick(obj: Dict[str, Any], *keys, default=None):
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def evaluate(base_url: str) -> Tuple[Dict[str, Any], bool]:
    base_url = (base_url or "").rstrip("/")
    state = _get_json(f"{base_url}/api/nexus/state", timeout=20.0)
    pure = _get_json(f"{base_url}/api/nexus/pure-ai-status", timeout=15.0)

    alerts: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    want_redeploy = False

    if not state.ok:
        alerts.append({"level": "critical", "id": "state_unavailable", "detail": state.error})
        want_redeploy = True
    else:
        snap = state.payload
        system = snap.get("system") or {}
        decision = snap.get("decision_summary") or {}
        capital = snap.get("capital") or {}

        worker = str(_pick(system, "module_health", "worker", default="") or "")
        last_tick_error = str(decision.get("last_tick_error") or "")
        capital_source = str(capital.get("source") or "")

        if "ERROR" in worker.upper():
            alerts.append({"level": "critical", "id": "worker_error", "detail": worker[:220]})
            want_redeploy = True

        if REDEPLOY_ON_TICK_ERROR and last_tick_error:
            alerts.append({"level": "high", "id": "last_tick_error", "detail": last_tick_error[:220]})
            want_redeploy = True

        if capital_source != "binance_rest":
            alerts.append({"level": "high", "id": "capital_not_synced", "detail": f"capital.source={capital_source}"})

        if state.ms >= MAX_STATE_MS:
            alerts.append({"level": "high", "id": "state_latency", "detail": f"{state.ms}ms"})
            want_redeploy = True

    if not pure.ok:
        alerts.append({"level": "medium", "id": "pure_ai_status_unavailable", "detail": pure.error})
    else:
        if not bool(pure.payload.get("active")):
            alerts.append({"level": "high", "id": "pure_ai_inactive"})
        if not bool(pure.payload.get("operational")):
            alerts.append({"level": "high", "id": "pure_ai_not_operational"})

    if want_redeploy:
        actions.append({"type": "redeploy", "reason": "alerts_triggered"})

    report = {
        "base_url": base_url,
        "fetched": {
            "state": {"ok": state.ok, "ms": state.ms, "status": state.status, "error": state.error},
            "pure_ai": {"ok": pure.ok, "ms": pure.ms, "status": pure.status, "error": pure.error},
        },
        "alerts": alerts,
        "actions": actions,
    }
    return report, want_redeploy


def main(argv: list[str]) -> int:
    base = DEFAULT_BASE_URL
    if len(argv) >= 2 and argv[1].strip():
        base = argv[1].strip()
    report, want_redeploy = evaluate(base)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # GitHub Actions outputs
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        try:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"want_redeploy={'true' if want_redeploy else 'false'}\n")
        except Exception:
            pass

    return 2 if any(a["level"] == "critical" for a in report["alerts"]) else 1 if report["alerts"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

