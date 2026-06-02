"""
Autodev: strategy parameter optimizer (safe, PR-friendly).

This DOES NOT change trading/execution logic. It only proposes bounded config/env tweaks
to improve win_rate and reduce churn based on recent performance metrics.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import requests


DEFAULT_BASE_URL = os.getenv("NEXUS_BASE_URL", "https://btc-auto-bot-2026.zeabur.app").rstrip("/")

# Target: try to push win_rate towards 0.80, but enforce minimum sample to avoid overfitting.
MIN_SAMPLE = int(float(os.getenv("NEXUS_AUTODEV_MIN_SAMPLE", "30")))
TARGET_WIN_RATE = float(os.getenv("NEXUS_AUTODEV_TARGET_WIN_RATE", "0.80"))


@dataclass
class Fetch:
    ok: bool
    status: int
    payload: Dict[str, Any]
    error: str = ""


def _get_json(url: str, timeout: float = 20.0) -> Fetch:
    try:
        res = requests.get(url, timeout=timeout, headers={"Cache-Control": "no-store"})
        if not res.ok:
            return Fetch(False, int(res.status_code), {}, f"http_{res.status_code}")
        payload = res.json()
        if not isinstance(payload, dict):
            return Fetch(False, int(res.status_code), {}, "json_not_object")
        return Fetch(True, int(res.status_code), payload)
    except Exception as exc:
        return Fetch(False, 0, {}, f"request_failed:{exc}")


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _format_env_line(key: str, value: Any) -> str:
    if isinstance(value, bool):
        value = "1" if value else "0"
    return f"{key}={value}"


def _patch_env_example(text: str, updates: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Update (or append) env keys inside .env.example without touching real .env.
    Returns patched text + list of changed keys.
    """
    changed: List[str] = []
    out_lines: List[str] = []
    lines = text.splitlines()
    seen = set()
    pattern = re.compile(r"^([A-Z0-9_]+)=(.*)$")
    for line in lines:
        m = pattern.match(line.strip())
        if not m:
            out_lines.append(line)
            continue
        key = m.group(1)
        if key in updates:
            out_lines.append(_format_env_line(key, updates[key]))
            changed.append(key)
            seen.add(key)
        else:
            out_lines.append(line)
            seen.add(key)
    # Append missing keys at end (keep file human-readable)
    missing = [k for k in updates.keys() if k not in seen]
    if missing:
        out_lines.append("")
        out_lines.append("# Autodev suggested tuning")
        for key in missing:
            out_lines.append(_format_env_line(key, updates[key]))
            changed.append(key)
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else ""), changed


def propose_tuning(perf: Dict[str, Any], monthly: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bounded knobs:
    - reduce leverage & margin when drawdown / negative pnl
    - raise min confidence to trade less when win_rate is low
    - slow down entry rate to reduce fee churn
    - tighten hard SL and take partial earlier when losses dominate
    """
    sample = int(perf.get("sample_size") or 0)
    win_rate = _safe_float(perf.get("win_rate"))
    profit_factor = _safe_float(perf.get("profit_factor"))
    max_dd = _safe_float(perf.get("max_drawdown"))
    total_pnl = _safe_float(perf.get("total_pnl"))
    fees = _safe_float(perf.get("estimated_fees_usd"))

    net = _safe_float(monthly.get("realized_pnl_net"))
    progress = _safe_float(monthly.get("progress_pct"))

    # Default (no-op) if insufficient sample.
    if sample < MIN_SAMPLE:
        return {}

    updates: Dict[str, Any] = {}

    # If win rate is far from target, trade less aggressively.
    if win_rate < TARGET_WIN_RATE:
        # Increase confidence gate (0.12..0.35)
        cur = _safe_float(os.getenv("NEXUS_PURE_AI_MIN_CONFIDENCE", "0.15"))
        updates["NEXUS_PURE_AI_MIN_CONFIDENCE"] = round(_clamp(cur + 0.03, 0.12, 0.35), 2)

        # Reduce max leverage (10..25)
        cur_lev = _safe_float(os.getenv("NEXUS_PURE_AI_MAX_LEVERAGE", "25"))
        updates["NEXUS_PURE_AI_MAX_LEVERAGE"] = int(_clamp(cur_lev - 2, 10, 25))

        # Slow entries per tick (1..2)
        updates["NEXUS_PURE_AI_MAX_ENTRIES_PER_TICK"] = 1

    # If profit factor poor or net negative, tighten risk and take partial earlier.
    if profit_factor < 1.0 or total_pnl < 0 or net < 0 or progress < 0:
        # Take partial earlier (6..12)
        tp_partial = _safe_float(os.getenv("NEXUS_PURE_AI_TP_PARTIAL_PCT", "12"))
        updates["NEXUS_PURE_AI_TP_PARTIAL_PCT"] = int(_clamp(tp_partial - 2, 6, 12))

        # Tighten SL a bit (10..18) on margin
        sl = _safe_float(os.getenv("NEXUS_PURE_AI_SL_PCT_ON_MARGIN", "16"))
        updates["NEXUS_PURE_AI_SL_PCT_ON_MARGIN"] = int(_clamp(sl - 1, 10, 18))

        # Reduce per-trade margin cap (60..120)
        max_margin = _safe_float(os.getenv("NEXUS_PURE_AI_MAX_MARGIN_USD", "120"))
        updates["NEXUS_PURE_AI_MAX_MARGIN_USD"] = int(_clamp(max_margin - 10, 60, 120))

    # If fees high relative to pnl, reduce churn.
    if fees > 0 and abs(total_pnl) > 0 and abs(fees) / max(abs(total_pnl), 1.0) > 0.5:
        updates["NEXUS_PURE_AI_LLM_REFRESH_SECONDS"] = 5
        updates["NEXUS_PURE_AI_MAX_PROPOSALS"] = 4

    # Always keep learning on when optimizing.
    updates["NEXUS_PURE_AI_RESPECT_LEARNING"] = 1
    updates["NEXUS_LEARNING_AUTO_APPLY"] = 1

    return updates


def main(argv: List[str]) -> int:
    base = DEFAULT_BASE_URL
    if len(argv) >= 2 and argv[1].strip():
        base = argv[1].strip().rstrip("/")

    perf = _get_json(f"{base}/api/nexus/performance-report")
    monthly = _get_json(f"{base}/api/nexus/monthly-revenue")

    if not perf.ok:
        print(json.dumps({"ok": False, "error": "performance_report_failed", "detail": perf.error}, ensure_ascii=False))
        return 2
    if not monthly.ok:
        monthly_payload: Dict[str, Any] = {}
    else:
        monthly_payload = monthly.payload

    updates = propose_tuning(perf.payload, monthly_payload)
    print(json.dumps({"ok": True, "updates": updates, "perf": perf.payload, "monthly": monthly_payload}, ensure_ascii=False, indent=2))

    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"has_updates={'true' if bool(updates) else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

