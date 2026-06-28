#!/usr/bin/env python3
"""Analyze Stage 4 rate-limit / skip events from a dry-run output directory."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HTTP_429_TYPES = frozenset({"provider_http_429", "provider_rate_limited", "rate_limit"})
LOCAL_GATE_TYPES = frozenset({"local_rate_gate_skip", "rate_limit_gate"})
BACKOFF_TYPES = frozenset({"backoff_active_skip"})
HEALTH_SKIP_TYPES = frozenset({"healthcheck_skipped_by_gate"})


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _delta_seconds(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if not a or not b:
        return None
    return abs((b - a).total_seconds())


def analyze_rate_limit_events(output_dir: Path) -> Dict[str, Any]:
    out = output_dir.expanduser().resolve()
    events = _read_jsonl(out / "stage4_system_events.jsonl")
    debug = _read_jsonl(out / "llm_client_debug.jsonl")
    summary: Dict[str, Any] = {}
    summary_path = out / "stage4_ai_decision_summary.json"
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}

    real_http_429 = 0
    local_gate = 0
    backoff_skip = 0
    health_gate_skip = 0

    for ev in events:
        et = str(ev.get("event_type") or "")
        reason = str(ev.get("reason") or "")
        if et in HTTP_429_TYPES or reason == "rate_limit":
            real_http_429 += 1
        elif et in LOCAL_GATE_TYPES or reason in LOCAL_GATE_TYPES:
            local_gate += 1
        elif et in BACKOFF_TYPES or reason in BACKOFF_TYPES:
            backoff_skip += 1
        elif et in HEALTH_SKIP_TYPES:
            health_gate_skip += 1

    debug_429 = sum(1 for r in debug if int(r.get("http_status") or 0) == 429)
    debug_gate = sum(
        1
        for r in debug
        if str(r.get("error_type") or "") in LOCAL_GATE_TYPES | BACKOFF_TYPES
    )
    health_debug = sum(1 for r in debug if str(r.get("call_kind") or "") == "healthcheck")
    decision_debug = sum(1 for r in debug if str(r.get("call_kind") or "decision") == "decision")

    success_debug = [r for r in debug if r.get("success")]
    http_429_debug = [r for r in debug if int(r.get("http_status") or 0) == 429]

    success_times = [_parse_ts(str(r.get("created_at_utc") or "")) for r in success_debug]
    success_times = [t for t in success_times if t]
    rate_times = [_parse_ts(str(r.get("created_at_utc") or "")) for r in http_429_debug]
    rate_times = [t for t in rate_times if t]

    between_success: List[float] = []
    for i in range(1, len(success_times)):
        d = _delta_seconds(success_times[i - 1], success_times[i])
        if d is not None:
            between_success.append(d)

    between_429: List[float] = []
    for i in range(1, len(rate_times)):
        d = _delta_seconds(rate_times[i - 1], rate_times[i])
        if d is not None:
            between_429.append(d)

    poll = float(summary.get("poll_interval_seconds") or 0)
    suggested_poll = max(poll, 600.0)
    if between_429 and max(between_429) > suggested_poll:
        suggested_poll = max(suggested_poll, min(max(between_429) + 60, 900.0))

    last_429 = max(rate_times) if rate_times else None
    now = datetime.now(timezone.utc)
    cooldown_until = (last_429 + timedelta(minutes=15)) if last_429 else now
    can_rerun = True
    if last_429 and now < cooldown_until:
        can_rerun = False
    if debug_429 >= 3 and len(success_debug) <= 1:
        suggested_poll = max(suggested_poll, 600.0)
        if debug_429 > len(success_debug) * 4:
            can_rerun = last_429 is not None and now >= cooldown_until

    return {
        "record_type": "stage4_rate_limit_diagnosis",
        "output_dir": str(out),
        "provider_rate_limit_count": int(summary.get("provider_rate_limit_count") or 0),
        "skipped_tick_count": int(summary.get("skipped_tick_count") or 0),
        "real_http_429_count": max(real_http_429, debug_429 // 2 if debug_429 else 0),
        "local_rate_gate_skip_count": max(local_gate, debug_gate),
        "backoff_active_skip_count": backoff_skip,
        "healthcheck_skipped_by_gate_count": health_gate_skip,
        "healthcheck_llm_call_count": health_debug,
        "decision_llm_call_count": decision_debug or len(debug) - health_debug,
        "debug_http_429_count": debug_429,
        "debug_success_count": len(success_debug),
        "time_between_successful_llm_calls_seconds": between_success,
        "time_between_rate_limited_events_seconds": between_429,
        "retry_after_seconds_observed": between_429[:5],
        "suggested_poll_interval_seconds": suggested_poll,
        "suggested_symbols": summary.get("symbols") or ["ETHUSDT"],
        "can_rerun_now": can_rerun,
        "cooldown_recommended_until_utc": cooldown_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diagnosis_summary": (
            "real_groq_http_429"
            if debug_429 > local_gate
            else "local_gate_or_backoff"
            if local_gate or backoff_skip
            else "mixed_or_unknown"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Stage 4 rate-limit events")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    report = analyze_rate_limit_events(Path(args.output_dir))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
