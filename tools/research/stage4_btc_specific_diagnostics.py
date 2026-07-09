#!/usr/bin/env python3
"""Stage 4.18-O — offline BTC-specific schema/sample diagnostics (no orders, no soak)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _bias_without_side,
    _has_entry_trigger,
    _has_invalidation,
    _is_valid_watch_candidate,
    _missing_entry_trigger,
    _normalize_side,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    assess_decision_quality,
    apply_schema_level_enforcement,
    parse_entry_trigger,
    parse_invalidation,
    symbol_mae_watch_cap_pct,
)

BTC_SYMBOL = "BTCUSDT"
ETH_SYMBOL = "ETHUSDT"
NEAR_WATCH_MAE_CAP = 0.35
NEAR_WATCH_CONF_FLOOR = 0.40
MINOR_BLOCK_REASONS = frozenset(
    {
        "ok",
        "watch_missing_confirmation_reason",
        "missing_paper_fields",
        "decision_quality_incomplete",
    }
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


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _regime(raw: Dict[str, Any]) -> str:
    mc = raw.get("market_context") or {}
    if isinstance(mc, dict) and mc.get("regime"):
        return str(mc.get("regime") or "unknown")
    return str(raw.get("regime") or "unknown")


def _provider(raw: Dict[str, Any]) -> str:
    p = str(raw.get("provider") or raw.get("llm_provider") or "unknown").strip().lower()
    if p == "unknown" and raw.get("fallback_provider"):
        return str(raw.get("fallback_provider")).strip().lower()
    return p or "unknown"


def _intent_bucket(intent: str) -> str:
    i = intent.lower()
    if i == "watch":
        return "watch"
    if i == "enter_candidate":
        return "enter_candidate"
    if i in {"soft_skip", "soft-skip"}:
        return "soft_skip"
    if i in {"hard_skip", "hard-skip"}:
        return "hard_skip"
    return i or "unknown"


def _near_watch_condition_scores(raw: Dict[str, Any]) -> Tuple[int, int, Dict[str, bool]]:
    intent = str(raw.get("decision_intent") or "").lower()
    bias = _normalize_side(raw.get("directional_bias"))
    if bias == "NONE" and str(raw.get("directional_bias") or "").upper() in {"LONG", "SHORT"}:
        bias = str(raw.get("directional_bias")).upper()
    side_raw = str(raw.get("candidate_side") or "NONE").upper()
    conf = _safe_float(raw.get("confidence"))
    trigger = parse_entry_trigger(raw.get("entry_trigger"))
    inv = parse_invalidation(raw.get("invalidation"))
    mae = _safe_float(raw.get("mae_risk_estimate_pct"))
    _, paper_readiness, reasons = assess_decision_quality(raw)
    block = str(paper_readiness.get("block_reason") or "ok")

    minor_block = block in MINOR_BLOCK_REASONS or (
        block != "ok" and intent in {"soft_skip", "watch"} and not reasons
    )

    checks = {
        "directional_bias_long_short": bias in {"LONG", "SHORT"},
        "candidate_side_buy_sell": side_raw in {"BUY", "SELL"},
        "confidence_ge_040": conf >= NEAR_WATCH_CONF_FLOOR,
        "entry_trigger_present": _has_entry_trigger(trigger),
        "invalidation_present": _has_invalidation(inv),
        "mae_le_cap": 0 < mae <= NEAR_WATCH_MAE_CAP,
        "intent_soft_skip_or_watch": intent in {"soft_skip", "watch"},
        "minor_block_only": minor_block,
    }
    met = sum(1 for v in checks.values() if v)
    return met, len(checks), checks


def _is_near_watch_candidate(raw: Dict[str, Any]) -> bool:
    if _is_valid_watch_candidate(raw):
        return False
    met, total, _ = _near_watch_condition_scores(raw)
    return met >= (total // 2 + 1)


def _why_not_valid_watch(raw: Dict[str, Any]) -> List[str]:
    if _is_valid_watch_candidate(raw):
        return []
    reasons: List[str] = []
    intent = str(raw.get("decision_intent") or "").lower()
    if intent != "watch":
        reasons.append(f"intent_not_watch:{intent or 'unknown'}")
    if _normalize_side(raw.get("candidate_side")) == "NONE":
        reasons.append("candidate_side_none")
    if _bias_without_side(raw) or raw.get("directional_bias_without_candidate_side"):
        reasons.append("directional_bias_without_candidate_side")
    if intent == "watch" and _missing_entry_trigger(raw):
        reasons.append("missing_entry_trigger")
    inv = parse_invalidation(raw.get("invalidation"))
    if intent in {"watch", "enter_candidate"} and not _has_invalidation(inv):
        reasons.append("missing_invalidation")
    mae = _safe_float(raw.get("mae_risk_estimate_pct"))
    if intent == "watch" and mae <= 0:
        reasons.append("missing_mae")
    cap = symbol_mae_watch_cap_pct(str(raw.get("symbol") or ""))
    if intent == "watch" and mae > cap:
        reasons.append("mae_above_symbol_cap")
    incomplete, paper_readiness, enforcement = assess_decision_quality(raw)
    block = str(paper_readiness.get("block_reason") or "ok")
    if block and block != "ok":
        reasons.append(f"paper_block:{block}")
    if incomplete and "decision_quality_incomplete" not in reasons:
        reasons.append("decision_quality_incomplete")
    conf = _safe_float(raw.get("confidence"))
    if conf < NEAR_WATCH_CONF_FLOOR and intent == "watch":
        reasons.append("confidence_below_floor")
    if not reasons:
        reasons.append("unknown")
    return reasons


def _distribution(values: List[Any]) -> Dict[str, int]:
    return dict(Counter(str(v) for v in values))


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _analyze_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    intent = str(raw.get("decision_intent") or "").lower()
    incomplete, paper_readiness, enforcement = assess_decision_quality(raw)
    trigger = parse_entry_trigger(raw.get("entry_trigger"))
    inv = parse_invalidation(raw.get("invalidation"))
    near_met, near_total, near_checks = _near_watch_condition_scores(raw)
    return {
        "decision_id": raw.get("decision_id"),
        "tick_index": raw.get("tick_index"),
        "symbol": raw.get("symbol"),
        "decision_intent": intent,
        "provider": _provider(raw),
        "regime": _regime(raw),
        "confidence": _safe_float(raw.get("confidence")),
        "directional_bias": raw.get("directional_bias"),
        "candidate_side": raw.get("candidate_side"),
        "entry_trigger_exists": _has_entry_trigger(trigger),
        "entry_trigger_type": trigger.get("type"),
        "invalidation_exists": _has_invalidation(inv),
        "mae_risk_estimate_pct": raw.get("mae_risk_estimate_pct"),
        "paper_readiness": paper_readiness,
        "block_reason": str(paper_readiness.get("block_reason") or "ok"),
        "missing_data": raw.get("missing_data") or [],
        "edge_factors": raw.get("edge_factors") or [],
        "risk_factors": raw.get("risk_factors") or [],
        "valid_watch_candidate": _is_valid_watch_candidate(raw),
        "near_watch_candidate": _is_near_watch_candidate(raw),
        "near_watch_conditions_met": near_met,
        "near_watch_conditions_total": near_total,
        "near_watch_condition_checks": near_checks,
        "why_not_valid_watch": _why_not_valid_watch(raw),
        "decision_quality_incomplete": incomplete,
        "paper_enforcement_reasons": enforcement,
    }


def _eth_valid_watch_reference(eth_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    valid = [r for r in eth_rows if _is_valid_watch_candidate(r)]
    if not valid:
        return {"count": 0, "common_conditions": {}}
    providers = _distribution([_provider(r) for r in valid])
    regimes = _distribution([_regime(r) for r in valid])
    biases = _distribution([str(r.get("directional_bias") or "NONE") for r in valid])
    sides = _distribution([str(r.get("candidate_side") or "NONE") for r in valid])
    triggers = _distribution(
        [str(parse_entry_trigger(r.get("entry_trigger")).get("type") or "none") for r in valid]
    )
    return {
        "count": len(valid),
        "common_conditions": {
            "provider_distribution": providers,
            "regime_distribution": regimes,
            "directional_bias_distribution": biases,
            "candidate_side_distribution": sides,
            "entry_trigger_type_distribution": triggers,
            "confidence_avg": _avg([_safe_float(r.get("confidence")) for r in valid]),
            "mae_avg": _avg([_safe_float(r.get("mae_risk_estimate_pct")) for r in valid]),
        },
    }


def _btc_vs_eth_delta(btc_rows: List[Dict[str, Any]], eth_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    btc_valid = [r for r in btc_rows if _is_valid_watch_candidate(r)]
    eth_valid = [r for r in eth_rows if _is_valid_watch_candidate(r)]
    btc_paper = [r for r in btc_rows if _intent_bucket(str(r.get("decision_intent") or "")) in {"watch", "enter_candidate"}]
    eth_paper = [r for r in eth_rows if _intent_bucket(str(r.get("decision_intent") or "")) in {"watch", "enter_candidate"}]

    def _gap(btc_vals: List[float], eth_vals: List[float]) -> Optional[float]:
        ba, ea = _avg(btc_vals), _avg(eth_vals)
        if ba is None or ea is None:
            return None
        return round(ba - ea, 4)

    btc_conf = [_safe_float(r.get("confidence")) for r in btc_rows]
    eth_conf = [_safe_float(r.get("confidence")) for r in eth_rows]
    btc_mae = [_safe_float(r.get("mae_risk_estimate_pct")) for r in btc_rows if _safe_float(r.get("mae_risk_estimate_pct")) > 0]
    eth_mae = [_safe_float(r.get("mae_risk_estimate_pct")) for r in eth_rows if _safe_float(r.get("mae_risk_estimate_pct")) > 0]

    btc_prov = _distribution([_provider(r) for r in btc_rows])
    eth_prov = _distribution([_provider(r) for r in eth_rows])
    btc_reg = _distribution([_regime(r) for r in btc_rows])
    eth_reg = _distribution([_regime(r) for r in eth_rows])
    btc_bias = _distribution([str(r.get("directional_bias") or "NONE") for r in btc_rows])
    eth_bias = _distribution([str(r.get("directional_bias") or "NONE") for r in eth_rows])

    btc_trigger_rate = (
        sum(1 for r in btc_paper if not _missing_entry_trigger(r)) / len(btc_paper) if btc_paper else None
    )
    eth_trigger_rate = (
        sum(1 for r in eth_paper if not _missing_entry_trigger(r)) / len(eth_paper) if eth_paper else None
    )

    return {
        "confidence_gap": _gap(btc_conf, eth_conf),
        "regime_gap": {"btc": btc_reg, "eth": eth_reg},
        "bias_gap": {"btc": btc_bias, "eth": eth_bias},
        "provider_gap": {"btc": btc_prov, "eth": eth_prov},
        "mae_gap": _gap(btc_mae, eth_mae),
        "trigger_gap": (
            round(btc_trigger_rate - eth_trigger_rate, 4)
            if btc_trigger_rate is not None and eth_trigger_rate is not None
            else None
        ),
        "valid_watch_count_gap": len(btc_valid) - len(eth_valid),
        "paper_intent_count_gap": len(btc_paper) - len(eth_paper),
    }


def _infer_primary_cause(
    btc_rows: List[Dict[str, Any]],
    why_counts: Counter[str],
    near_failures: Counter[str],
) -> str:
    if not btc_rows:
        return "no_btc_decisions"
    intent_counts = Counter(_intent_bucket(str(r.get("decision_intent") or "")) for r in btc_rows)
    if intent_counts.get("watch", 0) == 0:
        if intent_counts.get("soft_skip", 0) + intent_counts.get("hard_skip", 0) == len(btc_rows):
            return "btc_consistently_skip_intent_no_watch_signal"
    if why_counts.get("candidate_side_none", 0) >= len(btc_rows) // 2:
        return "btc_candidate_side_missing_or_none"
    if why_counts.get("directional_bias_without_candidate_side", 0) >= 2:
        return "btc_directional_bias_without_candidate_side"
    if why_counts.get("missing_entry_trigger", 0) >= 2:
        return "btc_missing_entry_trigger_on_watch_intent"
    prov = _distribution([_provider(r) for r in btc_rows])
    if prov.get("groq", 0) == len(btc_rows) and len(btc_rows) > 0:
        return "btc_all_groq_no_cerebras_paper_intent_path"
    if near_failures:
        top = near_failures.most_common(1)[0][0]
        return f"btc_near_watch_blocked_by:{top}"
    top = why_counts.most_common(1)[0][0] if why_counts else "unknown"
    return f"btc_primary:{top}"


def _btc_recommendation(
    primary_cause: str,
    btc_rows: List[Dict[str, Any]],
    eth_ref: Dict[str, Any],
    near_count: int,
) -> str:
    if primary_cause == "btc_consistently_skip_intent_no_watch_signal":
        return (
            "market_condition_or_no_edge: BTC decisions are soft/hard skip with no watch intent. "
            "Do not force BTC watch; skip is likely correct. No 60m extension until BTC shows watch intent."
        )
    if "candidate_side" in primary_cause or "directional_bias_without" in primary_cause:
        return (
            "prompt_schema_iteration_recommended: Stage 4.18-O2 BTC-specific examples for side+trigger "
            "only when clear trend; do not copy ETH behavior."
        )
    if "groq" in primary_cause:
        return (
            "provider_or_prompt_gap: BTC path may need Cerebras json_schema watch examples or "
            "BTC-specific Groq strict output; offline probe only — no soak until plan approved."
        )
    if near_count > 0:
        return (
            "sample_or_confirmation_gap: near-watch BTC candidates exist but did not graduate. "
            "Review confirmation window / consecutive ticks before another 60m."
        )
    eth_count = eth_ref.get("count", 0)
    if eth_count >= 3 and len(btc_rows) >= 6:
        return (
            "btc_eth_asymmetry: ETH produces valid_watch via Cerebras; BTC lacks equivalent path. "
            "Recommend 4.18-O2 BTC prompt iteration — not RG threshold change."
        )
    return "insufficient_btc_signal: remain idle; do not extend soak or start Stage 4.19."


def analyze_btc_specific_diagnostics(
    *,
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    paper_events_dir: Optional[str | Path] = None,
    calibration_dir: Optional[str | Path] = None,
    failure_analysis_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    decisions = _read_jsonl(inp / "ai_decisions.jsonl")
    enforced = [apply_schema_level_enforcement(d) for d in decisions if not d.get("parse_error")]

    btc_rows = [r for r in enforced if str(r.get("symbol") or "").upper() == BTC_SYMBOL]
    eth_rows = [r for r in enforced if str(r.get("symbol") or "").upper() == ETH_SYMBOL]

    analyzed: List[Dict[str, Any]] = []
    block_reason_counts: Counter[str] = Counter()
    near_failure_reasons: Counter[str] = Counter()
    why_not_valid_counts: Counter[str] = Counter()
    near_count = 0

    for raw in btc_rows:
        row = _analyze_row(raw)
        analyzed.append(row)
        block_reason_counts[row["block_reason"]] += 1
        for w in row["why_not_valid_watch"]:
            why_not_valid_counts[w.split(":")[0] if ":" in w else w] += 1
        if row["near_watch_candidate"]:
            near_count += 1
            for w in row["why_not_valid_watch"]:
                near_failure_reasons[w] += 1

    intent_counts = Counter(_intent_bucket(str(r.get("decision_intent") or "")) for r in btc_rows)
    valid_watch_count = sum(1 for r in btc_rows if _is_valid_watch_candidate(r))

    eth_ref = _eth_valid_watch_reference(eth_rows)
    delta = _btc_vs_eth_delta(btc_rows, eth_rows)
    primary = _infer_primary_cause(btc_rows, why_not_valid_counts, near_failure_reasons)
    recommendation = _btc_recommendation(primary, btc_rows, eth_ref, near_count)

    failure_summary = _read_json(Path(failure_analysis_dir) / "stage4_paper_entry_failure_summary.json") if failure_analysis_dir else {}

    summary: Dict[str, Any] = {
        "record_type": "stage4_btc_specific_diagnostics",
        "stage_marker": "4.18-O",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "paper_events_dir": str(paper_events_dir) if paper_events_dir else None,
        "calibration_dir": str(calibration_dir) if calibration_dir else None,
        "failure_analysis_dir": str(failure_analysis_dir) if failure_analysis_dir else None,
        "btc_decision_count": len(btc_rows),
        "btc_valid_watch_count": valid_watch_count,
        "btc_watch_intent_count": intent_counts.get("watch", 0),
        "btc_soft_skip_count": intent_counts.get("soft_skip", 0),
        "btc_hard_skip_count": intent_counts.get("hard_skip", 0),
        "btc_provider_distribution": _distribution([_provider(r) for r in btc_rows]),
        "btc_regime_distribution": _distribution([_regime(r) for r in btc_rows]),
        "btc_confidence_distribution": _distribution(
            [f"{_safe_float(r.get('confidence')):.2f}" for r in btc_rows]
        ),
        "btc_directional_bias_distribution": _distribution(
            [str(r.get("directional_bias") or "NONE") for r in btc_rows]
        ),
        "btc_candidate_side_distribution": _distribution(
            [str(r.get("candidate_side") or "NONE") for r in btc_rows]
        ),
        "btc_block_reason_counts": dict(block_reason_counts),
        "btc_near_watch_candidate_count": near_count,
        "btc_near_watch_failure_reasons": dict(near_failure_reasons),
        "btc_no_watch_primary_cause": primary,
        "btc_recommendation": recommendation,
        "eth_valid_watch_reference": eth_ref,
        "btc_vs_eth_delta": delta,
        "failure_analysis_valid_watch_by_symbol": (
            failure_summary.get("valid_watch_candidate_count_by_symbol") or {}
        ),
        "offline_only": True,
        "order_sent": False,
        "exchange_private_api_called": False,
        "production_touched": False,
        "btc_auto_touched": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_18o_btc_specific_diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_btc_specific_diagnostics_summary.json", summary)
    with (out / "stage4_btc_decision_rows.jsonl").open("w", encoding="utf-8") as fh:
        for row in analyzed:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-O BTC-specific diagnostics (offline)")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--paper-events-dir", default="")
    parser.add_argument("--calibration-dir", default="")
    parser.add_argument("--failure-analysis-dir", default="")
    args = parser.parse_args()
    summary = analyze_btc_specific_diagnostics(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
        paper_events_dir=args.paper_events_dir or None,
        calibration_dir=args.calibration_dir or None,
        failure_analysis_dir=args.failure_analysis_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
