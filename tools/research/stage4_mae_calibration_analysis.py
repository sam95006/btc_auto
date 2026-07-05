#!/usr/bin/env python3
"""Stage 4.18-F — analyze LLM MAE distribution from existing decision JSONL (no LLM rerun)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_event_logger import (  # noqa: E402
    MAE_CAPS_PCT,
    apply_paper_guards,
    _normalize_side,
)
from tools.research.stage4_paper_guard_inputs import get_paper_mae_pct  # noqa: E402
from tools.research.stage4_paper_readiness import (  # noqa: E402
    assess_mae_quality,
    build_mae_calibration_metrics,
    infer_decision_quality_incomplete,
    symbol_mae_watch_cap_pct,
    symbol_mae_watch_survival_pct,
)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _distribution(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0}
    return {
        "count": len(values),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
        "avg": round(sum(values) / len(values), 6),
    }


def _would_mae_watch_downgrade(decision: Dict[str, Any]) -> bool:
    intent = str(decision.get("decision_intent") or "").lower()
    if intent != "watch":
        return False
    symbol = str(decision.get("symbol") or "").upper()
    side = _normalize_side(decision.get("candidate_side"))
    guard = apply_paper_guards(decision, intent=intent, side=side)
    return "mae_watch_downgrade" in (guard.reasons or [])


def analyze_mae_distribution(
    decisions: List[Dict[str, Any]],
    *,
    input_dir: str,
) -> Dict[str, Any]:
    by_symbol: Dict[str, List[float]] = defaultdict(list)
    by_intent: Dict[str, List[float]] = defaultdict(list)
    paper_ready_mae: List[float] = []
    downgrade_mae: List[float] = []
    above_survival: Counter[str] = Counter()
    above_cap: Counter[str] = Counter()
    major_symbols = {"BTCUSDT", "ETHUSDT"}

    for decision in decisions:
        if decision.get("parse_error") or decision.get("is_mock_ai"):
            continue

        symbol = str(decision.get("symbol") or "unknown").upper()
        intent = str(decision.get("decision_intent") or "").lower()
        mae = _safe_float(decision.get("mae_risk_estimate_pct"))
        if mae <= 0:
            continue

        by_symbol[symbol].append(mae)
        by_intent[intent].append(mae)

        pr = decision.get("paper_readiness") or {}
        if intent == "watch" and pr.get("eligible_for_watchlist"):
            paper_ready_mae.append(mae)

        if _would_mae_watch_downgrade(decision):
            downgrade_mae.append(mae)

        survival = symbol_mae_watch_survival_pct(symbol)
        cap = symbol_mae_watch_cap_pct(symbol)
        if symbol in major_symbols:
            if mae > survival:
                above_survival[symbol] += 1
            if mae > cap:
                above_cap[symbol] += 1
        elif mae > cap:
            above_cap[symbol] += 1

    major_total = sum(1 for d in decisions if str(d.get("symbol") or "").upper() in major_symbols and _safe_float(d.get("mae_risk_estimate_pct")) > 0)
    major_above_028 = sum(
        1
        for d in decisions
        if str(d.get("symbol") or "").upper() in major_symbols
        and _safe_float(d.get("mae_risk_estimate_pct")) > 0.28
    )
    major_above_035 = sum(
        1
        for d in decisions
        if str(d.get("symbol") or "").upper() in major_symbols
        and _safe_float(d.get("mae_risk_estimate_pct")) > 0.35
    )

    return {
        "record_type": "stage4_18f_mae_distribution",
        "generated_at_utc": utc_now_iso(),
        "input_dir": input_dir,
        "decision_count": len(decisions),
        "mae_present_count": sum(len(v) for v in by_symbol.values()),
        "mae_risk_estimate_pct_by_symbol": {k: _distribution(v) for k, v in sorted(by_symbol.items())},
        "mae_risk_estimate_pct_by_intent": {k: _distribution(v) for k, v in sorted(by_intent.items())},
        "paper_ready_watch_mae_distribution": _distribution(paper_ready_mae),
        "mae_watch_downgrade_mae_distribution": _distribution(downgrade_mae),
        "btc_eth_above_0_28_pct_count": major_above_028,
        "btc_eth_above_0_35_pct_count": major_above_035,
        "btc_eth_mae_present_count": major_total,
        "btc_eth_above_0_28_pct_ratio": round(major_above_028 / major_total, 4) if major_total else 0.0,
        "btc_eth_above_0_35_pct_ratio": round(major_above_035 / major_total, 4) if major_total else 0.0,
        "above_watch_survival_by_symbol": dict(above_survival),
        "above_symbol_cap_by_symbol": dict(above_cap),
        "symbol_mae_caps_pct": dict(MAE_CAPS_PCT),
        "recomputed_incomplete_count": sum(
            1 for d in decisions if infer_decision_quality_incomplete(d)
        ),
        "mae_quality_issue_counts": dict(
            Counter(
                reason
                for d in decisions
                for reason in assess_mae_quality(d)
            )
        ),
        **build_mae_calibration_metrics(decisions),
    }


def run_analysis(*, input_dir: str | Path, output_dir: str | Path) -> Dict[str, Any]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl = input_dir / "ai_decisions.jsonl"
    if not jsonl.is_file():
        raise FileNotFoundError(f"Missing {jsonl}")

    decisions = _read_jsonl(jsonl)
    summary = analyze_mae_distribution(decisions, input_dir=str(input_dir))
    write_json(output_dir / "stage4_18f_mae_distribution.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-F MAE distribution analysis")
    parser.add_argument(
        "--input-dir",
        default="/data/stage4_ai_decisions_418d_schema_regression_30m",
    )
    parser.add_argument(
        "--output-dir",
        default="/data/stage4_18f_mae_calibration_analysis",
    )
    args = parser.parse_args()
    summary = run_analysis(input_dir=args.input_dir, output_dir=args.output_dir)
    print(json.dumps({"output_dir": args.output_dir, "mae_present_count": summary.get("mae_present_count")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
