#!/usr/bin/env python3
"""Stage 4.18-P1/P1B — BTC shadow provider diagnostics (no paper/calibration writes)."""
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
from tools.research.stage4_btc_dual_provider_shadow import (  # noqa: E402
    UNCOMPARABLE_CLASSES,
    _intent_bucket,
    _safe_float,
    aggregate_shadow_rows,
    classify_shadow_outcome,
    is_shadow_comparable,
)
from tools.research.stage4_paper_entry_failure_analyzer import _is_valid_watch_candidate  # noqa: E402
from tools.research.stage4_provider_routing_config import (  # noqa: E402
    BTC_SYMBOL,
    PROBE_RESULTS_JSONL,
    SHADOW_JSONL_FILENAME,
    is_shadow_decision_row,
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
        if not is_shadow_comparable(r):
            continue
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
    mapped = {
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
        "shadow_call_skipped": False,
        "shadow_diagnostic_only": True,
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "_mapped_from_o3_probe": True,
    }
    mapped["shadow_outcome_class"] = classify_shadow_outcome(mapped)
    mapped["shadow_comparable"] = is_shadow_comparable(mapped)
    return mapped


def load_shadow_rows(input_dir: Path) -> List[Dict[str, Any]]:
    shadow_path = input_dir / SHADOW_JSONL_FILENAME
    if shadow_path.is_file():
        return _read_jsonl(shadow_path)
    probe_path = input_dir / PROBE_RESULTS_JSONL
    if probe_path.is_file():
        return [_map_probe_row_to_shadow(r) for r in _read_jsonl(probe_path)]
    return []


def load_actual_btc(input_dir: Path) -> List[Dict[str, Any]]:
    rows = _read_jsonl(input_dir / "ai_decisions.jsonl")
    return [
        r
        for r in rows
        if not is_shadow_decision_row(r) and str(r.get("symbol") or "").upper() == BTC_SYMBOL
    ]


def _next_recommendation(
    *,
    comparable: int,
    uncomparable: int,
    uncomparable_reasons: Dict[str, int],
    actual_valid: int,
    shadow_valid: int,
) -> str:
    quotaish = sum(
        uncomparable_reasons.get(k, 0)
        for k in (
            "shadow_call_skipped",
            "shadow_provider_token_limited",
            "shadow_provider_rate_limited",
            "shadow_provider_unavailable",
            "shadow_provider_response_truncated",
        )
    )
    if comparable < 3:
        if uncomparable > 0 and quotaish >= max(1, uncomparable // 2):
            return "fix_shadow_quota_handling_before_provider_routing"
        return "collect_more_clean_shadow_samples_after_quota_aware_fix"
    if actual_valid > shadow_valid:
        return "do_not_change_routing_actual_path_currently_better"
    if shadow_valid > actual_valid:
        return "p2_routing_experiment_design_may_be_justified"
    return "no_shadow_divergence_in_comparable_sample"


def analyze_btc_shadow_diagnostics(
    *,
    input_dir: str | Path,
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    rows = load_shadow_rows(inp)
    actuals = load_actual_btc(inp)
    agg = aggregate_shadow_rows(rows) if rows else {
        "shadow_total_rows": 0,
        "shadow_called_count": 0,
        "shadow_call_skipped_count": 0,
        "shadow_comparable_pair_count": 0,
        "shadow_uncomparable_pair_count": 0,
        "shadow_uncomparable_reason_counts": {},
        "btc_shadow_valid_watch_count": 0,
        "provider_skill_comparison_valid": False,
        "shadow_provider_skill_result": {},
        "shadow_provider_unavailable_result": {},
        "btc_shadow_provider_distribution": {},
        "btc_shadow_divergence_count": 0,
        "btc_shadow_soft_skip_count": 0,
    }

    actual_prov = Counter(str(r.get("actual_provider") or "unknown") for r in rows)
    intent_delta: Counter[str] = Counter()
    for r in rows:
        if not is_shadow_comparable(r):
            continue
        key = f"{r.get('actual_decision_intent')}->{r.get('shadow_decision_intent')}"
        intent_delta[key] += 1

    actual_valid = sum(1 for a in actuals if _is_valid_watch_candidate(a))
    shadow_valid = int(agg.get("btc_shadow_valid_watch_count") or 0)
    comparable = int(agg.get("shadow_comparable_pair_count") or 0)
    uncomparable = int(agg.get("shadow_uncomparable_pair_count") or 0)
    uncomp_reasons = dict(agg.get("shadow_uncomparable_reason_counts") or {})
    skill_valid = bool(agg.get("provider_skill_comparison_valid"))
    rec = _next_recommendation(
        comparable=comparable,
        uncomparable=uncomparable,
        uncomparable_reasons=uncomp_reasons,
        actual_valid=actual_valid,
        shadow_valid=shadow_valid,
    )
    routing_ok = skill_valid and shadow_valid > actual_valid and shadow_valid >= 2
    p2 = routing_ok

    summary: Dict[str, Any] = {
        "record_type": "stage4_btc_shadow_diagnostics",
        "stage_marker": "4.18-P1B",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "shadow_decision_count": len(rows),
        "shadow_total_rows": len(rows),
        "shadow_called_count": int(agg.get("shadow_called_count") or 0),
        "shadow_call_skipped_count": int(agg.get("shadow_call_skipped_count") or 0),
        "shadow_comparable_pair_count": comparable,
        "shadow_uncomparable_pair_count": uncomparable,
        "shadow_uncomparable_reason_counts": uncomp_reasons,
        "shadow_outcome_class_counts": dict(
            Counter(classify_shadow_outcome(r) for r in rows)
        ),
        "actual_provider_distribution": dict(actual_prov),
        "shadow_provider_distribution": dict(agg.get("btc_shadow_provider_distribution") or {}),
        "shadow_valid_watch_count": shadow_valid,
        "actual_valid_watch_count": actual_valid,
        "shadow_soft_skip_count": int(agg.get("btc_shadow_soft_skip_count") or 0),
        "provider_divergence_count": int(agg.get("btc_shadow_divergence_count") or 0),
        "actual_vs_shadow_intent_delta": dict(intent_delta),
        "actual_vs_shadow_confidence_delta_avg": _avg_delta(rows),
        "shadow_provider_skill_result": agg.get("shadow_provider_skill_result") or {},
        "shadow_provider_unavailable_result": agg.get("shadow_provider_unavailable_result") or {},
        "provider_skill_comparison_valid": skill_valid,
        "routing_change_supported": routing_ok,
        "p2_routing_experiment_recommended": p2,
        "next_recommendation": rec,
        "recommendation": rec,
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "uncomparable_classes": sorted(UNCOMPARABLE_CLASSES),
        "offline_only": True,
        "order_sent": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_btc_shadow_diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_btc_shadow_diagnostics_summary.json", summary)
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-P1B BTC shadow diagnostics")
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
