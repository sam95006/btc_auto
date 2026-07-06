#!/usr/bin/env python3
"""Stage 4.18-I — compare two Stage4 MAE regression soak outputs (offline, no orders)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_event_logger import (  # noqa: E402
    MAE_CAPS_PCT,
    WatchlistState,
    classify_paper_event,
    is_eligible_decision,
)
from tools.research.stage4_paper_guard_inputs import get_paper_mae_pct  # noqa: E402
from tools.research.stage4_paper_readiness import (  # noqa: E402
    assess_mae_quality,
    build_mae_calibration_metrics,
    infer_decision_quality_incomplete,
    symbol_mae_watch_cap_pct,
)
from tools.research.stage4_watchlist_followup_simulator import (  # noqa: E402
    simulate_major_mae_calibration_mode,
    simulate_mode,
)

DEFAULT_BASELINE_DIR = "/data/stage4_ai_decisions_418g_r1_llm_mae_schema_regression_30m"
DEFAULT_CANDIDATE_DIR = "/data/stage4_ai_decisions_418h_r1_mae_prompt_regression_30m"
DEFAULT_OUTPUT_DIR = "/data/stage4_18i_mae_regression_compare"
CALIBRATION_MODE = "major_mae_100_llm_mae"


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _analyzable_decisions(decisions: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        d
        for d in decisions
        if not d.get("parse_error") and not d.get("is_mock_ai") and not d.get("order_sent")
    ]


def _load_session(input_dir: Path) -> Dict[str, Any]:
    summary_path = input_dir / "stage4_ai_decision_summary.json"
    summary: Dict[str, Any] = {}
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}
    decisions = _read_jsonl(input_dir / "ai_decisions.jsonl")
    effective = [d for d in decisions if is_eligible_decision(d)]
    analyzable = _analyzable_decisions(decisions)
    return {
        "input_dir": str(input_dir),
        "summary": summary,
        "decisions_all": decisions,
        "decisions_effective": effective,
        "decisions_analyzable": analyzable,
    }


def _eth_watch_metrics(decisions: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    within = 0
    above = 0
    watch_count = 0
    for decision in decisions:
        if str(decision.get("symbol") or "").upper() != "ETHUSDT":
            continue
        if str(decision.get("decision_intent") or "").lower() != "watch":
            continue
        watch_count += 1
        mae, _ = get_paper_mae_pct(decision, mae_source_mode="llm_mae_primary")
        cap = symbol_mae_watch_cap_pct("ETHUSDT")
        if mae <= 0:
            continue
        if mae <= cap:
            within += 1
        else:
            above += 1
    return {
        "eth_watch_count": watch_count,
        "eth_watch_mae_within_cap_count": within,
        "eth_watch_mae_above_cap_count": above,
    }


def _btc_graduation_candidates(decisions: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """BTC watches that could confirm/graduate if MAE and side are aligned."""
    confirmation = 0
    graduation = 0
    for decision in decisions:
        if str(decision.get("symbol") or "").upper() != "BTCUSDT":
            continue
        intent = str(decision.get("decision_intent") or "").lower()
        if intent not in {"watch", "enter_candidate"}:
            continue
        mae, _ = get_paper_mae_pct(decision, mae_source_mode="llm_mae_primary")
        cap = symbol_mae_watch_cap_pct("BTCUSDT")
        confidence = _safe_float(decision.get("confidence"))
        side = str(decision.get("candidate_side") or "NONE").upper()
        bias = str(decision.get("directional_bias") or "NONE").upper()
        has_side = side != "NONE" or bias in {"LONG", "SHORT"}
        if mae > 0 and mae <= cap and confidence >= 0.40 and has_side:
            confirmation += 1
            if not infer_decision_quality_incomplete(decision):
                graduation += 1
    return {
        "btc_watch_confirmation_candidate_count": confirmation,
        "btc_graduation_candidate_count": graduation,
    }


def _watchlist_confirmation_block_reasons(
    decisions: Sequence[Dict[str, Any]],
    *,
    dataset: str,
) -> Dict[str, int]:
    reasons: Counter[str] = Counter()
    watchlists: Dict[str, WatchlistState] = {}
    for decision in decisions:
        if not is_eligible_decision(decision):
            continue
        event = classify_paper_event(decision, source_dataset=dataset, watchlists=watchlists)
        if not event:
            continue
        for r in event.get("risk_governor_reasons") or []:
            reasons[str(r)] += 1
        action = str(event.get("paper_action") or "")
        if action == "watchlist":
            wl = event.get("watchlist_follow_up") or {}
            conf = _safe_float(wl.get("confirmation_count"))
            thresh = _safe_float(wl.get("confirmation_threshold"))
            if conf < thresh:
                reasons["watchlist_pending_confirmation"] += 1
        elif action == "hypothetical_skip":
            reasons["hypothetical_skip"] += 1
    return dict(reasons)


def _symbol_mae_averages(decisions: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    by_symbol: Dict[str, List[float]] = defaultdict(list)
    for decision in decisions:
        if not is_eligible_decision(decision):
            continue
        symbol = str(decision.get("symbol") or "").upper()
        mae = _safe_float(decision.get("mae_risk_estimate_pct"))
        if mae > 0:
            by_symbol[symbol].append(mae)
    return {
        sym: round(sum(vals) / len(vals), 6)
        for sym, vals in sorted(by_symbol.items())
        if vals
    }


def _calibration_summary(
    decisions: Sequence[Dict[str, Any]],
    *,
    dataset: str,
) -> Dict[str, Any]:
    rows = [(dataset, d) for d in decisions if is_eligible_decision(d)]
    acc = simulate_major_mae_calibration_mode(CALIBRATION_MODE, rows)
    return {
        "mode": CALIBRATION_MODE,
        "watchlist_created": acc.watchlist_created,
        "watchlist_confirmed": acc.watchlist_confirmed,
        "hypothetical_graduation_count": acc.hypothetical_graduation_count,
        "per_symbol_graduations": dict(acc.per_symbol_graduations),
        "block_reason_counts": dict(acc.block_reason_counts),
    }


def _strict_mode_summary(
    decisions: Sequence[Dict[str, Any]],
    *,
    dataset: str,
) -> Dict[str, Any]:
    rows = [(dataset, d) for d in decisions if is_eligible_decision(d)]
    acc = simulate_mode("strict_current", rows)
    return {
        "watchlist_created": acc.watchlist_created,
        "watchlist_confirmed": acc.watchlist_confirmed,
        "hypothetical_graduation_count": acc.hypothetical_graduation_count,
        "block_reason_counts": dict(acc.block_reason_counts),
    }


def _analyze_pepe_regression(
    baseline: Sequence[Dict[str, Any]],
    candidate: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    def _pepe_stats(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        maes: List[float] = []
        intents: Counter[str] = Counter()
        vol_high = 0
        for d in rows:
            if str(d.get("symbol") or "").upper() != "PEPEUSDT":
                continue
            if not is_eligible_decision(d):
                continue
            intents[str(d.get("decision_intent") or "").lower()] += 1
            mae = _safe_float(d.get("mae_risk_estimate_pct"))
            if mae > 0:
                maes.append(mae)
            mc = d.get("market_context") or {}
            if str(mc.get("volatility_level") or "").lower() == "high":
                vol_high += 1
        avg = round(sum(maes) / len(maes), 6) if maes else None
        return {
            "avg_mae": avg,
            "intent_counts": dict(intents),
            "high_volatility_ticks": vol_high,
            "watch_with_mae_above_cap": sum(
                1
                for d in rows
                if is_eligible_decision(d)
                and str(d.get("symbol") or "").upper() == "PEPEUSDT"
                and str(d.get("decision_intent") or "").lower() == "watch"
                and _safe_float(d.get("mae_risk_estimate_pct")) > MAE_CAPS_PCT["PEPEUSDT"]
            ),
        }

    b = _pepe_stats(baseline)
    c = _pepe_stats(candidate)
    cause = "unknown"
    if c.get("avg_mae") and b.get("avg_mae") and c["avg_mae"] > b["avg_mae"]:
        if c.get("intent_counts", {}).get("watch", 0) > b.get("intent_counts", {}).get("watch", 0):
            cause = "418h_prompt_increased_pepe_watch_yield_with_high_mae_not_volatility_tied"
        elif c.get("high_volatility_ticks", 0) > b.get("high_volatility_ticks", 0):
            cause = "regime_volatility_variation"
        else:
            cause = "llm_mae_estimate_inflation_vs_418f_conservative_skips"
    return {"baseline": b, "candidate": c, "pepe_mae_worsening_cause": cause}


def _analyze_sol(candidate: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    maes: List[float] = []
    above_cap = 0
    watch = 0
    for d in candidate:
        if str(d.get("symbol") or "").upper() != "SOLUSDT":
            continue
        if not is_eligible_decision(d):
            continue
        if str(d.get("decision_intent") or "").lower() == "watch":
            watch += 1
        mae = _safe_float(d.get("mae_risk_estimate_pct"))
        if mae > 0:
            maes.append(mae)
            if mae > MAE_CAPS_PCT["SOLUSDT"]:
                above_cap += 1
    avg = round(sum(maes) / len(maes), 6) if maes else None
    recommendation = "remain_conservative"
    if avg and avg > MAE_CAPS_PCT["SOLUSDT"]:
        recommendation = "remain_conservative_skip_or_watchlist_only_above_0_25pct"
    return {
        "sol_avg_mae": avg,
        "sol_watch_count": watch,
        "sol_mae_above_cap_count": above_cap,
        "sol_recommendation": recommendation,
    }


def _graduation_regression_analysis(
    baseline_cal: Dict[str, Any],
    candidate_cal: Dict[str, Any],
    baseline_btc: Dict[str, int],
    candidate_btc: Dict[str, int],
) -> Dict[str, Any]:
    b_grad = int(baseline_cal.get("hypothetical_graduation_count") or 0)
    c_grad = int(candidate_cal.get("hypothetical_graduation_count") or 0)
    causes: List[str] = []
    if b_grad > c_grad:
        b_conf = int(baseline_cal.get("watchlist_confirmed") or 0)
        c_conf = int(candidate_cal.get("watchlist_confirmed") or 0)
        if c_conf < b_conf:
            causes.append("watchlist_confirmation_regression")
        if candidate_btc.get("btc_graduation_candidate_count", 0) < baseline_btc.get("btc_graduation_candidate_count", 0):
            causes.append("btc_mae_above_cap_or_incomplete_quality")
        b_blocks = baseline_cal.get("block_reason_counts") or {}
        c_blocks = candidate_cal.get("block_reason_counts") or {}
        for key in ("mae_cap_violation_100pct", "candidate_side_none", "confidence_below_0.38"):
            if int(c_blocks.get(key, 0)) > int(b_blocks.get(key, 0)):
                causes.append(key)
        if not causes:
            causes.append("fewer_consecutive_confirming_ticks_or_side_missing")
    return {
        "baseline_graduations": b_grad,
        "candidate_graduations": c_grad,
        "btc_graduation_regression": b_grad > c_grad,
        "btc_graduation_regression_cause": "; ".join(causes) if causes else "no_regression",
    }


def _eth_no_graduation_cause(
    eth_metrics: Dict[str, int],
    candidate_cal: Dict[str, Any],
) -> str:
    if int(candidate_cal.get("per_symbol_graduations", {}).get("ETHUSDT", 0)) > 0:
        return "eth_graduated"
    if eth_metrics.get("eth_watch_count", 0) == 0:
        return "no_eth_watch_intents"
    if eth_metrics.get("eth_watch_mae_above_cap_count", 0) > 0:
        return "eth_watch_mae_above_0_35pct_cap"
    blocks = candidate_cal.get("block_reason_counts") or {}
    if int(blocks.get("candidate_side_none", 0)) > 0:
        return "candidate_side_none_despite_directional_bias"
    if int(candidate_cal.get("watchlist_confirmed") or 0) == 0:
        return "watchlist_never_confirmed"
    return "confirmation_or_confidence_gate"


def compare_mae_regressions(
    *,
    baseline_dir: str,
    candidate_dir: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    baseline_path = Path(baseline_dir)
    candidate_path = Path(candidate_dir)
    out_path = Path(output_dir or DEFAULT_OUTPUT_DIR)

    baseline = _load_session(baseline_path)
    candidate = _load_session(candidate_path)

    b_eff = baseline["decisions_effective"]
    c_eff = candidate["decisions_effective"]
    b_an = baseline["decisions_analyzable"]
    c_an = candidate["decisions_analyzable"]

    b_mae = build_mae_calibration_metrics(b_an)
    c_mae = build_mae_calibration_metrics(c_an)

    b_eth = _eth_watch_metrics(b_an)
    c_eth = _eth_watch_metrics(c_an)

    b_btc = _btc_graduation_candidates(b_an)
    c_btc = _btc_graduation_candidates(c_an)

    b_cal = _calibration_summary(b_eff, dataset=str(baseline_path))
    c_cal = _calibration_summary(c_eff, dataset=str(candidate_path))

    b_strict = _strict_mode_summary(b_eff, dataset=str(baseline_path))
    c_strict = _strict_mode_summary(c_eff, dataset=str(candidate_path))

    b_blocks = _watchlist_confirmation_block_reasons(b_eff, dataset=str(baseline_path))
    c_blocks = _watchlist_confirmation_block_reasons(c_eff, dataset=str(candidate_path))
    merged_blocks: Dict[str, int] = Counter(b_blocks)
    merged_blocks.update(c_blocks)

    grad_analysis = _graduation_regression_analysis(b_cal, c_cal, b_btc, c_btc)
    pepe_analysis = _analyze_pepe_regression(b_an, c_an)
    sol_analysis = _analyze_sol(c_an)

    watchlist_regression_cause = "none"
    if int(c_cal.get("watchlist_confirmed") or 0) < int(b_cal.get("watchlist_confirmed") or 0):
        top = sorted(c_cal.get("block_reason_counts", {}).items(), key=lambda x: -x[1])[:5]
        watchlist_regression_cause = (
            "mae_above_cap"
            if int(c_mae.get("paper_ready_watch_mae_above_cap_count") or 0)
            > int(b_mae.get("paper_ready_watch_mae_above_cap_count") or 0)
            else "confirmation_window_or_side_missing"
        )
        if top:
            watchlist_regression_cause += f"; top_blocks={dict(top)}"

    summary: Dict[str, Any] = {
        "generated_at_utc": utc_now_iso(),
        "stage": "4.18-I",
        "baseline_dir": str(baseline_path),
        "candidate_dir": str(candidate_path),
        "baseline_label": "418g_r1",
        "candidate_label": "418h_r1",
        "order_sent_count": 0,
        "mock_ai_used_count": 0,
        "any_exchange_call_made": False,
        "demo_order_enabled": False,
        "paper_order_execution_enabled": False,
        "arm_enabled": False,
        "radar_enabled": False,
        "production_touched": False,
        "btc_auto_touched": False,
        "sessions": {
            "baseline": {
                "effective_decision_count": len(b_eff),
                "mae_metrics": b_mae,
                "eth_watch_metrics": b_eth,
                "btc_candidate_metrics": b_btc,
                "calibration": b_cal,
                "strict_mode": b_strict,
                "symbol_mae_avg": _symbol_mae_averages(b_an),
            },
            "candidate": {
                "effective_decision_count": len(c_eff),
                "mae_metrics": c_mae,
                "eth_watch_metrics": c_eth,
                "btc_candidate_metrics": c_btc,
                "calibration": c_cal,
                "strict_mode": c_strict,
                "symbol_mae_avg": _symbol_mae_averages(c_an),
            },
        },
        "comparison": {
            "within_cap_delta": (
                int(c_mae.get("paper_ready_watch_mae_within_cap_count") or 0)
                - int(b_mae.get("paper_ready_watch_mae_above_cap_count") or 0)
            ),
            "above_cap_delta": (
                int(c_mae.get("paper_ready_watch_mae_above_cap_count") or 0)
                - int(b_mae.get("paper_ready_watch_mae_above_cap_count") or 0)
            ),
            "graduation_delta": int(c_cal.get("hypothetical_graduation_count") or 0)
            - int(b_cal.get("hypothetical_graduation_count") or 0),
            "eth_watch_delta": c_eth.get("eth_watch_count", 0) - b_eth.get("eth_watch_count", 0),
        },
        "analysis": {
            "btc_graduation_regression": grad_analysis,
            "btc_graduation_regression_cause": grad_analysis.get("btc_graduation_regression_cause"),
            "eth_no_graduation_cause": _eth_no_graduation_cause(c_eth, c_cal),
            "watchlist_confirmation_regression_cause": watchlist_regression_cause,
            "pepe_mae_worsening": pepe_analysis,
            "pepe_mae_worsening_cause": pepe_analysis.get("pepe_mae_worsening_cause"),
            "sol_analysis": sol_analysis,
            "sol_recommendation": sol_analysis.get("sol_recommendation"),
        },
        "eth_watch_count": c_eth.get("eth_watch_count", 0),
        "eth_watch_mae_within_cap_count": c_eth.get("eth_watch_mae_within_cap_count", 0),
        "eth_watch_mae_above_cap_count": c_eth.get("eth_watch_mae_above_cap_count", 0),
        "btc_watch_confirmation_candidate_count": c_btc.get("btc_watch_confirmation_candidate_count", 0),
        "btc_graduation_candidate_count": c_btc.get("btc_graduation_candidate_count", 0),
        "watchlist_confirmation_block_reasons": dict(merged_blocks),
        "final_verdict": "STAGE_4_18I_COMPARE_COMPLETE",
        "next_step_recommendation": (
            "Apply 418-I prompt alignment; run 4.18-I-R1 30m regression after code pass."
        ),
    }

    out_path.mkdir(parents=True, exist_ok=True)
    write_json(out_path / "stage4_18i_compare_summary.json", summary)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Stage4 MAE regression soak outputs")
    parser.add_argument("--baseline-dir", default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--candidate-dir", default=DEFAULT_CANDIDATE_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    summary = compare_mae_regressions(
        baseline_dir=args.baseline_dir,
        candidate_dir=args.candidate_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
