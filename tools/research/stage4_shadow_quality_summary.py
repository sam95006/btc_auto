"""Stage 4 shadow quality aggregation and intent-label analysis (read-only)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


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


def analyze_label_by_intent(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Count shadow labels grouped by decision_intent."""
    out: Dict[str, Dict[str, int]] = {}
    for row in rows:
        label = str(row.get("shadow_label") or "unknown")
        if label == "insufficient_future_data":
            continue
        intent = str(row.get("decision_intent") or "unknown").lower()
        bucket = out.setdefault(intent, {})
        bucket[label] = int(bucket.get(label) or 0) + 1
    return out


def _label_rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def build_per_symbol_shadow_quality(
    summary: Dict[str, Any],
    *,
    rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    symbol = str(summary.get("requested_symbol") or summary.get("symbol") or "unknown").upper()
    labels = summary.get("shadow_label_distribution") or {}
    intents = summary.get("decision_intent_distribution") or {}
    compared = _safe_int(summary.get("shadow_compared_count") or summary.get("decision_count"))
    bad_watch = _safe_int(summary.get("bad_watch_count") or labels.get("bad_watch"))
    missed = _safe_int(summary.get("missed_opportunity_count") or labels.get("missed_opportunity"))
    watch_count = _safe_int(intents.get("watch"))
    skip_count = _safe_int(intents.get("hard_skip")) + _safe_int(intents.get("soft_skip"))

    label_by_intent = analyze_label_by_intent(rows or [])
    watch_labels = label_by_intent.get("watch") or {}
    skip_labels = label_by_intent.get("hard_skip") or {}
    skip_labels = {**skip_labels, **(label_by_intent.get("soft_skip") or {})}

    bad_watch_in_watch = _safe_int(watch_labels.get("bad_watch"))
    missed_in_skip = _safe_int(skip_labels.get("missed_opportunity"))
    missed_in_watch = _safe_int(watch_labels.get("missed_opportunity"))

    return {
        "symbol": symbol,
        "decision_count": _safe_int(summary.get("decision_count")),
        "shadow_compared_count": compared,
        "shadow_label_distribution": dict(labels),
        "decision_intent_distribution": dict(intents),
        "bad_watch_count": bad_watch,
        "missed_opportunity_count": missed,
        "bad_watch_rate": _label_rate(bad_watch, compared),
        "missed_opportunity_rate": _label_rate(missed, compared),
        "bad_watch_concentrated_in_watch_intent": (
            bad_watch_in_watch >= max(1, bad_watch * 0.8) if bad_watch else False
        ),
        "missed_opportunity_concentrated_in_skip_intent": (
            missed_in_skip >= max(1, missed * 0.5) if missed else False
        ),
        "label_by_intent": label_by_intent,
        "watch_intent_count": watch_count,
        "skip_intent_count": skip_count,
        "bad_watch_in_watch_count": bad_watch_in_watch,
        "missed_in_watch_count": missed_in_watch,
        "missed_in_skip_count": missed_in_skip,
        "reasonable_watch_count": _safe_int(summary.get("reasonable_watch_count") or labels.get("reasonable_watch")),
        "good_skip_count": _safe_int(summary.get("good_skip_count") or labels.get("good_skip")),
        "neutral_count": _safe_int(summary.get("neutral_count") or labels.get("neutral")),
        "alias_used": bool(summary.get("alias_used")),
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_shadow_quality_summary(
    per_symbol_summaries: Dict[str, Dict[str, Any]],
    *,
    shadow_rows_by_symbol: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Fleet-level shadow quality aggregation."""
    shadow_rows_by_symbol = shadow_rows_by_symbol or {}
    per_symbol: Dict[str, Any] = {}
    fleet_labels: Dict[str, int] = {}
    fleet_bad_watch = 0
    fleet_missed = 0
    fleet_compared = 0

    for sym, summary in per_symbol_summaries.items():
        rows = shadow_rows_by_symbol.get(sym)
        quality = build_per_symbol_shadow_quality(summary, rows=rows)
        per_symbol[sym.upper()] = quality
        fleet_compared += quality["shadow_compared_count"]
        fleet_bad_watch += quality["bad_watch_count"]
        fleet_missed += quality["missed_opportunity_count"]
        for label, count in (quality.get("shadow_label_distribution") or {}).items():
            if label == "insufficient_future_data":
                continue
            fleet_labels[label] = int(fleet_labels.get(label) or 0) + _safe_int(count)

    eth = per_symbol.get("ETHUSDT") or {}
    btc = per_symbol.get("BTCUSDT") or {}
    pepe = per_symbol.get("PEPEUSDT") or {}
    sol = per_symbol.get("SOLUSDT") or {}

    return {
        "record_type": "stage4_shadow_quality_summary",
        "per_symbol": per_symbol,
        "fleet_shadow_label_distribution": fleet_labels,
        "fleet_bad_watch_count": fleet_bad_watch,
        "fleet_missed_opportunity_count": fleet_missed,
        "fleet_shadow_compared_count": fleet_compared,
        "fleet_bad_watch_rate": _label_rate(fleet_bad_watch, fleet_compared),
        "fleet_missed_opportunity_rate": _label_rate(fleet_missed, fleet_compared),
        "eth_relative_stability": eth.get("bad_watch_rate", 1.0) <= 0.15 and eth.get("good_skip_count", 0) >= 10,
        "btc_bad_watch_elevated": _safe_int(btc.get("bad_watch_count")) >= 10,
        "pepe_bad_watch_elevated": _safe_int(pepe.get("bad_watch_count")) >= 8,
        "sol_reasonable_watch_strong": _safe_int(sol.get("reasonable_watch_count")) >= 10,
        "bad_watch_analysis_note": (
            "bad_watch labels apply to watch intent when MAE dominates MFE; "
            "high counts often correlate with watch-heavy intent distribution."
        ),
        "missed_opportunity_analysis_note": (
            "missed_opportunity arises from skip/watch intents facing directional 60m moves; "
            "not an execution miss (read-only, no orders)."
        ),
    }


def load_shadow_summary(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_shadow_rows(path: Path) -> List[Dict[str, Any]]:
    return _read_jsonl(path)


__all__ = [
    "analyze_label_by_intent",
    "build_per_symbol_shadow_quality",
    "build_shadow_quality_summary",
    "load_shadow_summary",
    "read_shadow_rows",
]
