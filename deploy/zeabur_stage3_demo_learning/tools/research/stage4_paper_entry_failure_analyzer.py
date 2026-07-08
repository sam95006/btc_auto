#!/usr/bin/env python3
"""Stage 4.18-K/L — offline paper entry failure analyzer (no orders, no LLM)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_readiness import (  # noqa: E402
    BLOCK_REASON_MAE_ABOVE_CAP,
    BLOCK_REASON_MAE_SCALE_DRIFT,
    BLOCK_REASON_MISSING_FIELDS,
    BLOCK_REASON_SIDE_MISSING,
    apply_schema_level_enforcement,
    assess_decision_quality,
    build_enforcement_metrics,
    detect_mae_scale_drift,
    derive_candidate_side_suggestion,
    parse_entry_trigger,
    parse_invalidation,
    symbol_mae_watch_cap_pct,
)
from tools.research.stage4_schema_repair import build_schema_repair_aggregate_metrics  # noqa: E402


def _provider_label(raw: Dict[str, Any]) -> str:
    provider = str(raw.get("provider") or raw.get("llm_provider") or "unknown").strip().lower()
    if not provider or provider == "unknown":
        fb = str(raw.get("fallback_provider") or "").strip().lower()
        if fb:
            return fb
    return provider or "unknown"


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


def _normalize_side(raw: Any) -> str:
    side = str(raw or "NONE").upper()
    if side in {"BUY", "LONG"}:
        return "LONG"
    if side in {"SELL", "SHORT"}:
        return "SHORT"
    return "NONE"


def _has_entry_trigger(entry_trigger: Dict[str, Any]) -> bool:
    return entry_trigger.get("type") != "none" and bool(
        str(entry_trigger.get("trigger_condition") or "").strip()
    )


def _has_invalidation(invalidation: Dict[str, Any]) -> bool:
    try:
        max_adv = float(invalidation.get("max_adverse_move_pct") or 0)
    except (TypeError, ValueError):
        max_adv = 0.0
    return invalidation.get("invalidation_price", 0) > 0 or max_adv > 0


def _bias_without_side(raw: Dict[str, Any]) -> bool:
    bias = str(raw.get("directional_bias") or "NONE").upper()
    if bias in {"BUY"}:
        bias = "LONG"
    if bias in {"SELL"}:
        bias = "SHORT"
    return bias in {"LONG", "SHORT"} and _normalize_side(raw.get("candidate_side")) == "NONE"


def _missing_entry_trigger(raw: Dict[str, Any]) -> bool:
    intent = str(raw.get("decision_intent") or "").lower()
    if intent not in {"watch", "enter_candidate"}:
        return False
    return not _has_entry_trigger(parse_entry_trigger(raw.get("entry_trigger")))


def _is_valid_watch_candidate(raw: Dict[str, Any]) -> bool:
    intent = str(raw.get("decision_intent") or "").lower()
    if intent != "watch":
        return False
    incomplete, paper_readiness, _ = assess_decision_quality(raw)
    if incomplete:
        return False
    block = str(paper_readiness.get("block_reason") or "")
    if block and block != "ok":
        return False
    if _normalize_side(raw.get("candidate_side")) == "NONE":
        return False
    if not _has_entry_trigger(parse_entry_trigger(raw.get("entry_trigger"))):
        return False
    try:
        mae = float(raw.get("mae_risk_estimate_pct") or 0)
    except (TypeError, ValueError):
        return False
    cap = symbol_mae_watch_cap_pct(str(raw.get("symbol") or ""))
    return 0 < mae <= cap


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _field_contract_failures(raw: Dict[str, Any]) -> Dict[str, int]:
    intent = str(raw.get("decision_intent") or "").lower()
    if intent not in {"watch", "enter_candidate"}:
        return {}
    out = {
        "side_missing": 0,
        "trigger_missing": 0,
        "invalidation_missing": 0,
        "mae_missing": 0,
        "mae_scale_drift_suspected": 0,
        "mae_above_cap": 0,
    }
    if _bias_without_side(raw) or str(raw.get("candidate_side") or "NONE").upper() == "NONE":
        out["side_missing"] = 1
    trigger = parse_entry_trigger(raw.get("entry_trigger"))
    if not _has_entry_trigger(trigger):
        out["trigger_missing"] = 1
    inv = parse_invalidation(raw.get("invalidation"))
    if not _has_invalidation(inv):
        out["invalidation_missing"] = 1
    try:
        mae = float(raw.get("mae_risk_estimate_pct") or 0)
    except (TypeError, ValueError):
        mae = 0.0
    if mae <= 0:
        out["mae_missing"] = 1
    if detect_mae_scale_drift(raw):
        out["mae_scale_drift_suspected"] = 1
    _, _, reasons = assess_decision_quality(raw)
    if BLOCK_REASON_MAE_ABOVE_CAP in reasons:
        out["mae_above_cap"] = 1
    return out


def _build_recommendations(
    *,
    side_missing_rate: Dict[str, float],
    trigger_missing_rate: Dict[str, float],
    valid_watch_by_symbol: Dict[str, int],
    paper_intent_by_symbol: Dict[str, int],
    mae_drift_count: int,
    no_valid_watch_count: int,
    paper_intent_count: int,
) -> List[str]:
    recs: List[str] = []
    high_side = [s for s, r in side_missing_rate.items() if r >= 0.5 and paper_intent_by_symbol.get(s, 0) > 0]
    high_trigger = [s for s, r in trigger_missing_rate.items() if r >= 0.5 and paper_intent_by_symbol.get(s, 0) > 0]
    low_valid = [s for s, c in valid_watch_by_symbol.items() if c == 0 and paper_intent_by_symbol.get(s, 0) >= 2]

    if high_side:
        recs.append(
            "side_missing high for "
            + ", ".join(high_side)
            + " → recommend=structured_schema_side_required"
        )
    if high_trigger:
        recs.append(
            "trigger_missing high for "
            + ", ".join(high_trigger)
            + " → recommend=structured_schema_trigger_required"
        )
    if mae_drift_count > 0:
        recs.append(
            f"mae_scale_drift_suspected_count={mae_drift_count}"
            + " → recommend=mae_scale_contract_or_provider_specific_prompt"
        )
    if no_valid_watch_count >= paper_intent_count and paper_intent_count > 0:
        recs.append(
            "no_valid_watch_candidate_count high"
            + " → recommend=do_not_extend_sample_until_field_contract_passes"
        )
    elif low_valid:
        recs.append(
            "valid_watch_candidate_count=0 for "
            + ", ".join(low_valid)
            + " → recommend=do_not_extend_sample_until_field_contract_passes"
        )
    if not recs:
        recs.append("field contract moderate — run 418-M-R1 30m regression after code pass")
    return recs


def analyze_paper_entry_failures(
    *,
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    paper_events_dir: Optional[str | Path] = None,
    calibration_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    decisions = _read_jsonl(inp / "ai_decisions.jsonl")
    enforced = [apply_schema_level_enforcement(d) for d in decisions if not d.get("parse_error")]
    enforcement = build_enforcement_metrics(enforced)

    by_symbol: Counter[str] = Counter()
    by_block: Counter[str] = Counter()
    by_intent: Counter[str] = Counter()

    side_missing_num: Counter[str] = Counter()
    side_missing_den: Counter[str] = Counter()
    trigger_missing_num: Counter[str] = Counter()
    trigger_missing_den: Counter[str] = Counter()
    valid_watch: Counter[str] = Counter()

    top_side_missing: List[Dict[str, Any]] = []
    top_missing_fields: List[Dict[str, Any]] = []
    top_mae_above: List[Dict[str, Any]] = []
    rows_out: List[Dict[str, Any]] = []

    derived_side_suggestion_count = 0
    mae_scale_drift_count = 0
    no_valid_watch_count = 0
    field_contract_by_symbol: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "side_missing": 0,
            "trigger_missing": 0,
            "invalidation_missing": 0,
            "mae_missing": 0,
            "mae_scale_drift_suspected": 0,
            "mae_above_cap": 0,
        }
    )

    for raw in enforced:
        intent = str(raw.get("decision_intent") or "").lower()
        if intent not in {"watch", "enter_candidate"}:
            continue
        symbol = str(raw.get("symbol") or "").upper()
        incomplete, paper_readiness, reasons = assess_decision_quality(raw)
        block = str(paper_readiness.get("block_reason") or "ok")
        by_symbol[symbol] += 1
        by_intent[intent] += 1
        if block != "ok":
            by_block[block] += 1

        if _bias_without_side(raw) or raw.get("directional_bias_without_candidate_side"):
            side_missing_num[symbol] += 1
            derived_side_suggestion_count += 1
        if detect_mae_scale_drift(raw) or raw.get("mae_scale_drift_suspected"):
            mae_scale_drift_count += 1

        contract = _field_contract_failures(raw)
        for key, val in contract.items():
            field_contract_by_symbol[symbol][key] += val

        if _normalize_side(raw.get("directional_bias")) in {"LONG", "SHORT"} or str(
            raw.get("directional_bias") or ""
        ).upper() in {"LONG", "SHORT", "BUY", "SELL"}:
            side_missing_den[symbol] += 1

        if intent == "watch":
            trigger_missing_den[symbol] += 1
            if _missing_entry_trigger(raw):
                trigger_missing_num[symbol] += 1
            if _is_valid_watch_candidate(raw):
                valid_watch[symbol] += 1
            else:
                no_valid_watch_count += 1

        row = {
            "decision_id": raw.get("decision_id"),
            "tick_index": raw.get("tick_index"),
            "symbol": symbol,
            "decision_intent": intent,
            "candidate_side": raw.get("candidate_side"),
            "directional_bias": raw.get("directional_bias"),
            "derived_candidate_side_suggestion": raw.get("derived_candidate_side_suggestion")
            or derive_candidate_side_suggestion(raw),
            "mae_risk_estimate_pct": raw.get("mae_risk_estimate_pct"),
            "mae_scale_drift_suspected": bool(
                raw.get("mae_scale_drift_suspected") or detect_mae_scale_drift(raw)
            ),
            "block_reason": block,
            "decision_quality_incomplete": incomplete,
            "directional_bias_without_candidate_side": raw.get("directional_bias_without_candidate_side")
            or _bias_without_side(raw),
            "missing_entry_trigger": _missing_entry_trigger(raw),
            "valid_watch_candidate": _is_valid_watch_candidate(raw),
            "field_contract_failures": contract,
            "paper_enforcement_reasons": reasons,
        }
        rows_out.append(row)

        if row["directional_bias_without_candidate_side"] and len(top_side_missing) < 5:
            top_side_missing.append(row)
        if BLOCK_REASON_MISSING_FIELDS in reasons and len(top_missing_fields) < 5:
            top_missing_fields.append(row)
        if len(top_mae_above) < 5 and (
            BLOCK_REASON_MAE_ABOVE_CAP in reasons or BLOCK_REASON_MAE_SCALE_DRIFT in reasons
        ):
            top_mae_above.append(row)

    paper_intent_by_symbol = dict(by_symbol)
    candidate_side_missing_rate = {
        s: _rate(side_missing_num[s], side_missing_den[s]) for s in paper_intent_by_symbol
    }
    missing_entry_trigger_rate = {
        s: _rate(trigger_missing_num[s], trigger_missing_den[s]) for s in paper_intent_by_symbol
    }
    valid_watch_candidate_count_by_symbol = {s: valid_watch.get(s, 0) for s in paper_intent_by_symbol}

    recommendations = _build_recommendations(
        side_missing_rate=candidate_side_missing_rate,
        trigger_missing_rate=missing_entry_trigger_rate,
        valid_watch_by_symbol=valid_watch_candidate_count_by_symbol,
        paper_intent_by_symbol=paper_intent_by_symbol,
        mae_drift_count=mae_scale_drift_count,
        no_valid_watch_count=no_valid_watch_count,
        paper_intent_count=len(rows_out),
    )

    by_provider_side: Dict[str, List[float]] = defaultdict(list)
    by_provider_trigger: Dict[str, List[float]] = defaultdict(list)
    provider_valid_watch: Counter[str] = Counter()
    for raw in enforced:
        intent = str(raw.get("decision_intent") or "").lower()
        if intent not in {"watch", "enter_candidate"}:
            continue
        prov = _provider_label(raw)
        if _bias_without_side(raw) or str(raw.get("candidate_side") or "NONE").upper() == "NONE":
            by_provider_side[prov].append(1.0)
        else:
            by_provider_side[prov].append(0.0)
        if intent == "watch":
            by_provider_trigger[prov].append(1.0 if _missing_entry_trigger(raw) else 0.0)
            if _is_valid_watch_candidate(raw):
                provider_valid_watch[prov] += 1

    provider_side_missing_rate = {
        p: _rate(int(sum(v)), len(v)) for p, v in by_provider_side.items() if v
    }
    provider_trigger_missing_rate = {
        p: _rate(int(sum(v)), len(v)) for p, v in by_provider_trigger.items() if v
    }
    schema_repair_metrics = build_schema_repair_aggregate_metrics(enforced)

    summary: Dict[str, Any] = {
        "record_type": "stage4_paper_entry_failure_analysis",
        "stage_marker": "4.18-N",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "paper_events_dir": str(paper_events_dir) if paper_events_dir else None,
        "calibration_dir": str(calibration_dir) if calibration_dir else None,
        "decision_count": len(decisions),
        "paper_intent_count": len(rows_out),
        "derived_candidate_side_suggestion_count": derived_side_suggestion_count,
        "mae_scale_drift_suspected_count": mae_scale_drift_count,
        "no_valid_watch_candidate_count": no_valid_watch_count,
        "field_contract_failure_by_symbol": {
            sym: dict(counts) for sym, counts in sorted(field_contract_by_symbol.items())
        },
        "failure_by_block_reason": dict(by_block),
        "failure_by_symbol": dict(by_symbol),
        "failure_by_intent": dict(by_intent),
        "candidate_side_missing_rate_by_symbol": candidate_side_missing_rate,
        "missing_entry_trigger_rate_by_symbol": missing_entry_trigger_rate,
        "valid_watch_candidate_count_by_symbol": valid_watch_candidate_count_by_symbol,
        "top_examples": {
            "directional_bias_without_candidate_side": top_side_missing,
            "missing_paper_fields": top_missing_fields,
            "mae_above_symbol_cap": top_mae_above,
        },
        "recommendations": recommendations,
        "provider_side_missing_rate": provider_side_missing_rate,
        "provider_trigger_missing_rate": provider_trigger_missing_rate,
        "provider_valid_watch_candidate_count": dict(provider_valid_watch),
        **schema_repair_metrics,
        **enforcement,
        "offline_only": True,
        "order_sent": False,
        "exchange_private_api_called": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_paper_entry_failure_analysis"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "stage4_paper_entry_failure_summary.json", summary)
    with (out / "stage4_paper_entry_failure_rows.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows_out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-K/L/M paper entry failure analyzer")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--paper-events-dir", default="")
    parser.add_argument("--calibration-dir", default="")
    args = parser.parse_args()
    summary = analyze_paper_entry_failures(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
        paper_events_dir=args.paper_events_dir or None,
        calibration_dir=args.calibration_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
