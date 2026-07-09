#!/usr/bin/env python3
"""Stage 4.18-P1 — BTC shadow provider diagnostics (no paper/calibration writes)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_btc_dual_provider_shadow import _intent_bucket, _safe_float  # noqa: E402
from tools.research.stage4_provider_routing_config import (  # noqa: E402
    PROBE_RESULTS_JSONL,
    SHADOW_JSONL_FILENAME,
)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _avg_delta(rows: List[Dict[str, Any]]) -> Optional[float]:
    deltas: List[float] = []
    for r in rows:
        ac = r.get("actual_confidence")
        sc = r.get("shadow_confidence")
        if ac is not None and sc is not None:
            deltas.append(_safe_float(sc) - _safe_float(ac))
    if not deltas:
        return None
    return round(sum(deltas) / len(deltas), 4)


def _map_probe_row_to_shadow(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map O3 controlled probe row into shadow-like schema for offline diagnostics."""
    provider = str(row.get("provider") or "unknown")
    opposite = "cerebras" if provider == "groq" else "groq"
    return {
        "shadow_decision_id": row.get("probe_id"),
        "source_decision_id": row.get("source_decision_id"),
        "actual_provider": opposite,
        "shadow_provider": provider,
        "actual_decision_intent": "soft_skip",
        "shadow_decision_intent": row.get("decision_intent"),
        "actual_confidence": 0.2,
        "shadow_confidence": row.get("confidence"),
        "shadow_would_be_valid_watch_under_current_rules": row.get(
            "would_be_valid_watch_under_current_rules"
        ),
        "provider_divergence_detected": bool(
            row.get("would_be_valid_watch_under_current_rules")
        ),
        "shadow_diagnostic_only": True,
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "_mapped_from_o3_probe": True,
    }


def load_shadow_rows(input_dir: Path) -> List[Dict[str, Any]]:
    shadow_path = input_dir / SHADOW_JSONL_FILENAME
    if shadow_path.is_file():
        return _read_jsonl(shadow_path)
    probe_path = input_dir / PROBE_RESULTS_JSONL
    if probe_path.is_file():
        return [_map_probe_row_to_shadow(r) for r in _read_jsonl(probe_path)]
    return []


def analyze_btc_shadow_diagnostics(
    *,
    input_dir: str | Path,
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    rows = load_shadow_rows(inp)
    actual_prov = Counter(str(r.get("actual_provider") or "unknown") for r in rows)
    shadow_prov = Counter(str(r.get("shadow_provider") or "unknown") for r in rows)
    intent_delta: Counter[str] = Counter()
    for r in rows:
        key = f"{r.get('actual_decision_intent')}->{r.get('shadow_decision_intent')}"
        intent_delta[key] += 1

    valid_watch = sum(1 for r in rows if r.get("shadow_would_be_valid_watch_under_current_rules"))
    soft_skip = sum(1 for r in rows if _intent_bucket(str(r.get("shadow_decision_intent") or "")) == "soft_skip")
    divergence = sum(1 for r in rows if r.get("provider_divergence_detected"))

    if divergence > 0 and valid_watch > 0:
        recommendation = "provider_routing_may_affect_btc_yield_collect_more_shadow_samples"
    elif divergence > 0:
        recommendation = "provider_intent_divergence_observed_shadow_only"
    elif rows:
        recommendation = "no_shadow_divergence_in_sample"
    else:
        recommendation = "no_shadow_rows_found"

    summary: Dict[str, Any] = {
        "record_type": "stage4_btc_shadow_diagnostics",
        "stage_marker": "4.18-P1",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "shadow_decision_count": len(rows),
        "actual_provider_distribution": dict(actual_prov),
        "shadow_provider_distribution": dict(shadow_prov),
        "shadow_valid_watch_count": valid_watch,
        "shadow_soft_skip_count": soft_skip,
        "provider_divergence_count": divergence,
        "actual_vs_shadow_intent_delta": dict(intent_delta),
        "actual_vs_shadow_confidence_delta_avg": _avg_delta(rows),
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "recommendation": recommendation,
        "offline_only": True,
        "order_sent": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_btc_shadow_diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_btc_shadow_diagnostics_summary.json", summary)
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-P1 BTC shadow diagnostics")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = analyze_btc_shadow_diagnostics(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
