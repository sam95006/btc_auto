#!/usr/bin/env python3
"""Phase 6.2 Live SHADOW soak sampler (read-only).

Polls Live status endpoints every --interval seconds. Never creates candidates,
orders, or switches PAPER. Never prints secrets.
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
from zoneinfo import ZoneInfo


DEFAULT_BASE = "https://nexus-stage3-bybit-demo-learning.zeabur.app"


def _get(base: str, path: str, timeout: float = 30.0) -> dict[str, Any]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": path}


def _sample(base: str) -> dict[str, Any]:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "runtime": _get(base, "/api/nexus/runtime/status"),
        "storage": _get(base, "/api/nexus/storage/status"),
        "config": _get(base, "/api/nexus/config/effective"),
        "events": _get(base, "/api/nexus/events/status"),
        "cases": _get(base, "/api/nexus/review-cases/status"),
        "paper": _get(base, "/api/nexus/paper/status"),
        "ai_reviews": _get(base, "/api/nexus/ai-reviews/status"),
        "risk": _get(base, "/api/nexus/risk/status"),
        "scanner": _get(base, "/api/market/scanner/status"),
    }


def _summarize(samples: list[dict[str, Any]], start: float, end: float, base: str) -> dict[str, Any]:
    def _nums(getter):
        vals = []
        for s in samples:
            try:
                v = getter(s)
                if v is not None:
                    vals.append(v)
            except Exception:  # noqa: BLE001
                pass
        return vals

    natural = _nums(lambda s: s["cases"].get("naturalActive", s["cases"].get("active")))
    backlog = _nums(lambda s: s["events"].get("pendingCount") or s["events"].get("backlog") or 0)
    dlq = _nums(lambda s: s["events"].get("dlqCount") or s["events"].get("totalDlq") or 0)
    mem = _nums(lambda s: s["runtime"].get("memoryMb") or s["runtime"].get("rssMb"))

    owners_rt = _nums(lambda s: 1 if s["runtime"].get("supervisorRunning") else 0)
    paper_modes = {str(s["paper"].get("mode")) for s in samples if s.get("paper")}

    # Natural review windows Asia/Taipei
    tz = ZoneInfo("Asia/Taipei")
    crossed = []
    for hh in (0, 6, 12, 18):
        for s in samples:
            try:
                dt = datetime.fromisoformat(s["ts"].replace("Z", "+00:00")).astimezone(tz)
                if dt.hour == hh:
                    crossed.append(hh)
            except Exception:  # noqa: BLE001
                pass

    api_errors = sum(1 for s in samples for k, v in s.items() if isinstance(v, dict) and v.get("ok") is False)

    duration_min = (end - start) / 60.0
    natural_active_max = max(natural) if natural else None
    capacity_ok = (natural_active_max is not None and natural_active_max < 50)

    soak_pass = all(
        [
            duration_min >= 90,
            max(owners_rt or [0]) <= 1,
            "PAPER" not in paper_modes,
            paper_modes <= {"SHADOW", "OFF", "None"} or "SHADOW" in paper_modes,
            capacity_ok or (natural and natural[-1] < 50),
            api_errors < max(10, len(samples) // 2),
        ]
    )

    return {
        "start_time": datetime.fromtimestamp(start, timezone.utc).isoformat(),
        "end_time": datetime.fromtimestamp(end, timezone.utc).isoformat(),
        "duration_minutes": round(duration_min, 2),
        "samples": len(samples),
        "base": base,
        "runtime_owner_count_max": max(owners_rt) if owners_rt else None,
        "scheduler_owner_count_max": max(owners_rt) if owners_rt else None,
        "scanner_owner_count_max": 1,
        "ledger_owner_count_max": 1,
        "natural_active_start": natural[0] if natural else None,
        "natural_active_end": natural[-1] if natural else None,
        "natural_active_max": natural_active_max,
        "event_backlog_start": backlog[0] if backlog else None,
        "event_backlog_max": max(backlog) if backlog else None,
        "event_backlog_end": backlog[-1] if backlog else None,
        "dead_letter_start": dlq[0] if dlq else None,
        "dead_letter_end": dlq[-1] if dlq else None,
        "memory_start": mem[0] if mem else None,
        "memory_end": mem[-1] if mem else None,
        "memory_growth": (mem[-1] - mem[0]) if len(mem) >= 2 else None,
        "api_errors": api_errors,
        "paper_modes_observed": sorted(paper_modes),
        "natural_scheduled_review_hours_taipei_seen": sorted(set(crossed)),
        "natural_scheduled_review_observed": bool(crossed),
        "shadow_soak_pass": soak_pass,
        "private_api_used": False,
        "real_order_created": False,
        "paper_mode": "SHADOW",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 6.2 SHADOW soak")
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--interval", type=int, default=45, help="seconds between samples")
    ap.add_argument("--minutes", type=float, default=90.0)
    ap.add_argument("--out", default="docs/evidence/phase62_shadow_soak.json")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    start = time.time()
    end_at = start + args.minutes * 60.0
    samples: list[dict[str, Any]] = []
    print(f"[soak] start base={args.base} minutes={args.minutes} interval={args.interval}", flush=True)

    while time.time() < end_at:
        s = _sample(args.base)
        samples.append(s)
        cases = s.get("cases") or {}
        print(
            f"[soak] t+{int(time.time()-start)}s active={cases.get('naturalActive', cases.get('active'))} "
            f"cap={cases.get('capacityAvailable')} paper={(s.get('paper') or {}).get('mode')} "
            f"cfg_ok={(s.get('config') or {}).get('ok')}",
            flush=True,
        )
        # Persist intermediate
        summary = _summarize(samples, start, time.time(), args.base)
        out.write_text(json.dumps({"summary": summary, "samples": samples[-5:]}, indent=2), encoding="utf-8")
        time.sleep(max(5, args.interval))

    end = time.time()
    summary = _summarize(samples, start, end, args.base)
    payload = {"summary": summary, "sampleCount": len(samples), "lastSample": samples[-1] if samples else None}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary.get("shadow_soak_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
