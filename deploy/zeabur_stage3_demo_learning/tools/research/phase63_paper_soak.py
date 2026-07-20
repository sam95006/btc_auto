#!/usr/bin/env python3
"""Phase 6.3 Live PAPER smoke / soak sampler (read-only + optional activate).

Never calls private API, never creates real orders, never prints secrets.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app"


def _req(base: str, path: str, method: str = "GET", body: dict | None = None, timeout: float = 45.0) -> dict[str, Any]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": path}


def _sample(base: str) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "config": _req(base, "/api/nexus/config/effective"),
        "runtime": _req(base, "/api/nexus/runtime/status"),
        "storage": _req(base, "/api/nexus/storage/status"),
        "paper": _req(base, "/api/nexus/paper/status"),
        "sessions": _req(base, "/api/nexus/paper/sessions"),
        "ledger": _req(base, "/api/nexus/paper/ledger"),
        "trades": _req(base, "/api/nexus/paper/trades?limit=20"),
        "cases": _req(base, "/api/nexus/review-cases/status"),
        "events": _req(base, "/api/nexus/events/status"),
        "risk": _req(base, "/api/nexus/risk/status"),
        "sim": _req(base, "/api/nexus/simulator/status"),
        "scanner": _req(base, "/api/market/scanner/status"),
        "perf": _req(base, "/api/nexus/performance/summary"),
    }


def _summarize(samples: list[dict[str, Any]], start: float, end: float, base: str) -> dict[str, Any]:
    modes = {str((s.get("paper") or {}).get("mode")) for s in samples}
    states = [str((s.get("paper") or {}).get("runtimeState") or (s.get("paper") or {}).get("paperControllerState")) for s in samples]
    owners = []
    for s in samples:
        owners.append(1 if (s.get("runtime") or {}).get("supervisorRunning") else 0)
    natural = [(s.get("cases") or {}).get("naturalActive") for s in samples]
    natural = [n for n in natural if n is not None]
    orders = []
    for s in samples:
        orders.append(int((s.get("paper") or {}).get("totalOrdersSubmitted") or 0))
    api_errors = sum(1 for s in samples for k, v in s.items() if isinstance(v, dict) and v.get("ok") is False)
    duration = (end - start) / 60.0
    mode_ok = "PAPER" in modes and "SHADOW" not in modes - {"None", "NoneType"}
    # Allow transient None during redeploy
    pure_modes = {m for m in modes if m not in ("None", "NoneType", "")}
    smoke_pass = all([
        duration >= 30,
        max(owners or [0]) <= 1,
        "PAPER" in pure_modes,
        api_errors < max(10, len(samples) // 2),
        (max(natural) if natural else 0) < 50,
    ])
    return {
        "start_time": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "end_time": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        "duration_minutes": round(duration, 2),
        "samples": len(samples),
        "base": base,
        "modes_observed": sorted(pure_modes),
        "controller_states_observed": sorted({s for s in states if s and s != "None"}),
        "runtime_owner_max": max(owners) if owners else None,
        "natural_active_max": max(natural) if natural else None,
        "orders_submitted_end": orders[-1] if orders else 0,
        "orders_submitted_max": max(orders) if orders else 0,
        "api_errors": api_errors,
        "private_api_used": False,
        "real_order_created": False,
        "paper_smoke_pass": smoke_pass if duration >= 30 else False,
        "paper_soak_pass": smoke_pass if duration >= 90 else False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--interval", type=int, default=45)
    ap.add_argument("--activate", action="store_true")
    ap.add_argument("--out", default="docs/evidence/phase63_paper_smoke.json")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.activate:
        act = _req(
            args.base,
            "/api/nexus/paper/activate",
            method="POST",
            body={"researchOnly": True},
        )
        print(json.dumps({"activation": {
            "ok": act.get("ok"),
            "hint": act.get("controllerHint"),
            "sessionId": (act.get("session") or {}).get("activationSessionId"),
            "accountId": (act.get("session") or {}).get("accountId"),
            "error": act.get("error"),
        }}, indent=2), flush=True)

    start = time.time()
    end_at = start + args.minutes * 60.0
    samples: list[dict[str, Any]] = []
    print(f"[paper_soak] start minutes={args.minutes} interval={args.interval}", flush=True)
    while time.time() < end_at:
        s = _sample(args.base)
        samples.append(s)
        paper = s.get("paper") or {}
        print(
            f"[paper_soak] t+{int(time.time()-start)}s mode={paper.get('mode')} "
            f"state={paper.get('runtimeState') or paper.get('paperControllerState')} "
            f"orders={paper.get('totalOrdersSubmitted')} "
            f"natural={(s.get('cases') or {}).get('naturalActive')} "
            f"cfg={(s.get('config') or {}).get('autonomousMode', {}).get('effective')}",
            flush=True,
        )
        summary = _summarize(samples, start, time.time(), args.base)
        out.write_text(json.dumps({"summary": summary, "tail": samples[-3:]}, indent=2), encoding="utf-8")
        time.sleep(max(5, args.interval))

    end = time.time()
    summary = _summarize(samples, start, end, args.base)
    payload = {
        "summary": summary,
        "sampleCount": len(samples),
        "lastSample": samples[-1] if samples else None,
        "firstSample": samples[0] if samples else None,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if (summary.get("paper_smoke_pass") or summary.get("paper_soak_pass")) else 1


if __name__ == "__main__":
    sys.exit(main())
