"""
Auto-dev remote triage for Zeabur NEXUS.

Goals:
- Pull minimal state from the deployed service (no secrets).
- Detect common failure modes: worker offline, stale snapshots, mismatched accounts,
  Pure AI not operational, no exits firing, API latency spikes.
- Print a short, actionable report for Cursor-driven iteration.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import requests


DEFAULT_BASE = "https://btc-auto-bot-2026.zeabur.app"


@dataclass
class FetchResult:
    ok: bool
    ms: int
    status: int
    payload: Dict[str, Any]
    error: str = ""


def _get_json(url: str, timeout: float = 12.0) -> FetchResult:
    started = time.time()
    try:
        res = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-store"})
        ms = int((time.time() - started) * 1000)
        status = int(res.status_code)
        if not res.ok:
            return FetchResult(False, ms, status, {}, f"http_{status}")
        try:
            payload = res.json()
        except Exception as exc:
            return FetchResult(False, ms, status, {}, f"json_parse_failed:{exc}")
        if not isinstance(payload, dict):
            return FetchResult(False, ms, status, {}, "json_not_object")
        return FetchResult(True, ms, status, payload)
    except Exception as exc:
        ms = int((time.time() - started) * 1000)
        return FetchResult(False, ms, 0, {}, f"request_failed:{exc}")


def _pick(obj: Dict[str, Any], *keys, default=None):
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def _fmt_money(x: Any) -> str:
    try:
        return f"{float(x or 0.0):.2f}U"
    except Exception:
        return "0.00U"


def triage(base_url: str) -> Tuple[int, Dict[str, Any]]:
    base_url = (base_url or "").rstrip("/")
    state = _get_json(f"{base_url}/api/nexus/state", timeout=15.0)
    pure = _get_json(f"{base_url}/api/nexus/pure-ai-status", timeout=12.0)

    report: Dict[str, Any] = {
        "base_url": base_url,
        "fetched": {
            "state": {"ok": state.ok, "ms": state.ms, "status": state.status, "error": state.error},
            "pure_ai": {"ok": pure.ok, "ms": pure.ms, "status": pure.status, "error": pure.error},
        },
        "alerts": [],
        "summary": {},
    }

    if not state.ok:
        report["alerts"].append({"level": "critical", "id": "state_unavailable", "detail": state.error})
        return 2, report

    snap = state.payload
    system = snap.get("system") or {}
    decision = snap.get("decision_summary") or {}
    capital = snap.get("capital") or {}
    account = snap.get("account_sync_status") or {}

    worker_mod = _pick(system, "module_health", "worker", default="")
    last_tick_error = decision.get("last_tick_error")
    futures_positions = int(decision.get("live_position_count") or 0)

    report["summary"] = {
        "worker": str(worker_mod),
        "last_tick_error": str(last_tick_error or ""),
        "capital_source": str(capital.get("source") or ""),
        "capital_total": _fmt_money(capital.get("total")),
        "futures_equity": _fmt_money(capital.get("futures_total")),
        "spot_stable_total": _fmt_money(capital.get("spot_stable_total")),
        "futures_positions": futures_positions,
        "rest_snapshot_status": account.get("rest_snapshot_status") or {},
    }

    if "ERROR" in str(worker_mod).upper():
        report["alerts"].append({"level": "critical", "id": "worker_error", "detail": worker_mod})
    if last_tick_error:
        report["alerts"].append({"level": "high", "id": "last_tick_error", "detail": str(last_tick_error)[:240]})
    if str(capital.get("source") or "") != "binance_rest":
        report["alerts"].append(
            {"level": "high", "id": "capital_not_synced", "detail": f"capital.source={capital.get('source')}"}
        )
    if state.ms >= 12000:
        report["alerts"].append({"level": "high", "id": "state_latency", "detail": f"{state.ms}ms"})

    # Pure AI gate checks
    if pure.ok:
        if not bool(pure.payload.get("operational")):
            report["alerts"].append({"level": "high", "id": "pure_ai_not_operational"})
        execd = _pick(pure.payload, "entry_execution", "executed", default=0)
        cand = _pick(pure.payload, "entry_execution", "candidates", default=0)
        report["summary"]["pure_ai"] = {
            "operational": bool(pure.payload.get("operational")),
            "entries": f"{int(execd or 0)}/{int(cand or 0)}",
        }
    else:
        report["alerts"].append({"level": "medium", "id": "pure_ai_status_unavailable", "detail": pure.error})

    # If positions exist but exits never fire, flag it.
    exits = _pick(pure.payload if pure.ok else {}, "last_cycle", "exit_count", default=None)
    if futures_positions > 0 and pure.ok and exits == 0:
        report["alerts"].append(
            {"level": "medium", "id": "positions_no_exits_this_cycle", "detail": "check hard_exit_enabled + exit actions"}
        )

    code = 0
    if any(a["level"] == "critical" for a in report["alerts"]):
        code = 2
    elif report["alerts"]:
        code = 1
    return code, report


def main(argv: list[str]) -> int:
    base = DEFAULT_BASE
    if len(argv) >= 2 and argv[1].strip():
        base = argv[1].strip()
    code, report = triage(base)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

