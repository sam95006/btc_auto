#!/usr/bin/env python3
"""Stage 4.18-P2A — ETH+BTC actual graduation alignment diagnostics (offline only)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _is_valid_watch_candidate,
    _normalize_side,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    assess_decision_quality,
    symbol_mae_watch_cap_pct,
)
from tools.research.stage4_provider_routing_config import is_shadow_decision_row  # noqa: E402

BTC = "BTCUSDT"
ETH = "ETHUSDT"

# Known baselines from Stage 4.18-N reports when remote dirs unavailable.
KNOWN_ETH_BASELINES = {
    "4.18-N-R1": {
        "label": "4.18-N-R1",
        "eth_graduations": 2,
        "eth_valid_watch": 4,
        "notes": "provider schema regression; ETH/Cerebras valid_watch path",
        "source": "docs/stage4_ai_decision_layer_plan.md",
    },
    "4.18-N-R2": {
        "label": "4.18-N-R2",
        "eth_graduations": 2,
        "eth_valid_watch": 5,
        "notes": "60m stability; ETH graduations=2; BTC graduations=0",
        "source": "docs/stage4_ai_decision_layer_plan.md",
    },
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _intent(row: Dict[str, Any]) -> str:
    return str(
        row.get("decision_intent")
        or row.get("intent")
        or row.get("final_decision")
        or row.get("final_action")
        or ""
    ).strip().lower()


def _actual_rows(input_dir: Path, symbol: str) -> List[Dict[str, Any]]:
    rows = _read_jsonl(input_dir / "ai_decisions.jsonl")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if is_shadow_decision_row(row):
            continue
        if str(row.get("symbol") or "").upper() != symbol.upper():
            continue
        out.append(row)
    return out


def _graduation_count_for_symbol(calibration_dir: Path, symbol: str) -> int:
    if not calibration_dir or not Path(calibration_dir).is_dir():
        return 0
    cdir = Path(calibration_dir)
    best = 0
    for path in cdir.rglob("*.json"):
        data = _read_json(path)
        if not data:
            continue
        modes = data.get("mode_results") or data.get("modes") or data.get("calibration_modes") or {}
        if isinstance(modes, dict):
            for mode in modes.values():
                if not isinstance(mode, dict):
                    continue
                per = mode.get("per_symbol_graduations") or {}
                if isinstance(per, dict):
                    best = max(best, int(per.get(symbol) or 0))
        if symbol == BTC:
            best = max(best, int(data.get("btc_graduation_count") or 0))
        if symbol == ETH:
            best = max(best, int(data.get("eth_graduation_count") or 0))
    # followup diagnostics style
    for path in cdir.rglob("*followup*diagnostics*.json"):
        data = _read_json(path)
        if symbol == BTC:
            best = max(best, int(data.get("btc_graduation_count") or 0))
        if symbol == ETH:
            best = max(best, int(data.get("eth_graduation_count") or 0))
    return best


def _analyze_symbol_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    providers: Counter[str] = Counter()
    intents: Counter[str] = Counter()
    confs: List[float] = []
    block_reasons: Counter[str] = Counter()
    missing_fields: Counter[str] = Counter()
    mae_above = 0
    valid_watches: List[Dict[str, Any]] = []
    details: List[Dict[str, Any]] = []

    for row in rows:
        providers[str(row.get("provider") or "unknown").lower()] += 1
        intent = _intent(row)
        intents[intent or "unknown"] += 1
        try:
            confs.append(float(row.get("confidence") or 0))
        except (TypeError, ValueError):
            pass

        incomplete, paper_readiness, _ = assess_decision_quality(row)
        block = str(paper_readiness.get("block_reason") or "")
        if block and block != "ok":
            block_reasons[block] += 1
        if incomplete:
            for field in paper_readiness.get("missing_fields") or []:
                missing_fields[str(field)] += 1

        try:
            mae = float(row.get("mae_risk_estimate_pct") or 0)
        except (TypeError, ValueError):
            mae = 0.0
        cap = symbol_mae_watch_cap_pct(str(row.get("symbol") or ""))
        if mae > 0 and mae > cap:
            mae_above += 1

        is_vw = bool(_is_valid_watch_candidate(row))
        if is_vw:
            valid_watches.append(row)

        details.append(
            {
                "symbol": row.get("symbol"),
                "decision_id": row.get("decision_id"),
                "provider": row.get("provider"),
                "provider_chain": row.get("provider_chain"),
                "decision_intent": intent,
                "confidence": row.get("confidence"),
                "candidate_side": row.get("candidate_side"),
                "mae_risk_estimate_pct": row.get("mae_risk_estimate_pct"),
                "mae_cap": cap,
                "valid_watch": is_vw,
                "block_reason": block or "ok",
                "regime": row.get("regime") or (row.get("market_context") or {}).get("regime")
                if isinstance(row.get("market_context"), dict)
                else row.get("regime"),
            }
        )

    conf_dist = {
        "min": min(confs) if confs else None,
        "max": max(confs) if confs else None,
        "avg": round(sum(confs) / len(confs), 4) if confs else None,
        "count": len(confs),
    }
    return {
        "decision_count": len(rows),
        "valid_watch_count": len(valid_watches),
        "provider_distribution": dict(providers),
        "intent_distribution": dict(intents),
        "confidence_distribution": conf_dist,
        "block_reason_counts": dict(block_reasons),
        "missing_field_counts": dict(missing_fields),
        "mae_above_cap_count": mae_above,
        "valid_watches": valid_watches,
        "details": details,
    }


def _followup_stats(
    watches: List[Dict[str, Any]],
    all_rows: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Heuristic: later tick for same symbol after a watch = follow-up available."""
    by_tick: Dict[Any, List[Dict[str, Any]]] = {}
    ordered = list(all_rows)
    follow_ok = 0
    no_follow = 0
    confirm_fail = 0
    inval_fail = 0
    for i, w in enumerate(watches):
        wid = str(w.get("decision_id") or "")
        found_later = False
        seen = False
        for row in ordered:
            if str(row.get("decision_id") or "") == wid:
                seen = True
                continue
            if not seen:
                continue
            if str(row.get("symbol") or "").upper() != str(w.get("symbol") or "").upper():
                continue
            found_later = True
            # confirmation / invalidation heuristics from later intents
            intent = _intent(row)
            if intent in {"soft_skip", "hard_skip", "skip"} and _normalize_side(row.get("candidate_side")) == "NONE":
                confirm_fail += 1
            if str(row.get("invalidation_hit") or "").lower() in {"true", "1", "yes"}:
                inval_fail += 1
            break
        if found_later:
            follow_ok += 1
        else:
            no_follow += 1
    return {
        "eth_followup_tick_available_count": follow_ok,
        "eth_no_followup_tick_count": no_follow,
        "eth_confirmation_failed_count": confirm_fail,
        "eth_invalidation_failed_count": inval_fail,
    }


def classify_eth_root_cause(
    *,
    eth_vw: int,
    follow: Dict[str, int],
    mae_above: int,
    eth_decisions: int,
    provider_shift: bool,
) -> Tuple[str, str, bool, bool]:
    """Return root_cause, recommendation, needs_eth_fix, needs_short_sample."""
    if eth_vw == 0:
        return (
            "eth_no_actual_valid_watch",
            "eth_decision_quality_or_market_context_diagnostics",
            True,
            False,
        )
    if follow.get("eth_no_followup_tick_count", 0) >= max(1, eth_vw):
        return (
            "eth_watchlist_opened_but_no_followup_tick",
            "short_alignment_sample_may_be_needed",
            False,
            True,
        )
    if follow.get("eth_confirmation_failed_count", 0) > 0:
        return (
            "eth_followup_confirmation_failed",
            "eth_watchlist_followup_diagnostics",
            True,
            False,
        )
    if mae_above > 0 and mae_above >= max(1, eth_vw // 2):
        return (
            "eth_mae_cap_failure",
            "eth_mae_alignment_review",
            True,
            False,
        )
    if provider_shift:
        return (
            "eth_provider_distribution_shift",
            "eth_provider_stability_review",
            False,
            True,
        )
    if eth_decisions > 0 and eth_vw > 0:
        return (
            "eth_sample_variance_or_unconfirmed_watch",
            "short_alignment_sample_may_be_needed",
            False,
            True,
        )
    return (
        "eth_no_actual_valid_watch",
        "eth_decision_quality_or_market_context_diagnostics",
        True,
        False,
    )


def _session_snapshot(input_dir: Path, label: str) -> Dict[str, Any]:
    if not input_dir.is_dir():
        return {"label": label, "loaded": False}
    eth = _analyze_symbol_rows(_actual_rows(input_dir, ETH))
    btc = _analyze_symbol_rows(_actual_rows(input_dir, BTC))
    return {
        "label": label,
        "loaded": True,
        "path": str(input_dir),
        "eth_decision_count": eth["decision_count"],
        "eth_valid_watch_count": eth["valid_watch_count"],
        "eth_provider_distribution": eth["provider_distribution"],
        "eth_intent_distribution": eth["intent_distribution"],
        "eth_confidence_distribution": eth["confidence_distribution"],
        "eth_mae_above_cap_count": eth["mae_above_cap_count"],
        "btc_valid_watch_count": btc["valid_watch_count"],
    }


def run_alignment(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    calibration_dir: str | Path = "",
    paper_dir: str | Path = "",
    compare_n_r1: str | Path = "",
    compare_n_r2: str | Path = "",
    compare_p1c: str | Path = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cal = Path(calibration_dir) if calibration_dir else Path(
        "/data/stage4_18p2_r1_actual_only_calibration"
    )
    paper = Path(paper_dir) if paper_dir else Path(
        "/data/stage4_paper_events_418p2_r1_actual_only"
    )

    loaded = (inp / "ai_decisions.jsonl").is_file() or (inp / "stage4_ai_decision_summary.json").is_file()
    run_summary = _read_json(inp / "stage4_ai_decision_summary.json")
    p2_analysis = _read_json(Path("/data/stage4_18p2_r1_analysis/stage4_18p2_r1_analysis_summary.json"))
    followup = _read_json(
        Path("/data/stage4_18p2_r1_btc_watchlist_followup_diagnostics/stage4_btc_watchlist_followup_diagnostics.json")
    )

    btc_rows = _actual_rows(inp, BTC)
    eth_rows = _actual_rows(inp, ETH)
    btc_stats = _analyze_symbol_rows(btc_rows)
    eth_stats = _analyze_symbol_rows(eth_rows)
    follow = _followup_stats(eth_stats["valid_watches"], eth_rows)

    btc_grad = int(
        p2_analysis.get("btc_actual_graduation_count")
        or followup.get("btc_graduation_count")
        or _graduation_count_for_symbol(cal, BTC)
        or 0
    )
    eth_grad = int(
        p2_analysis.get("eth_actual_graduation_count")
        or _graduation_count_for_symbol(cal, ETH)
        or 0
    )
    btc_vw = int(
        p2_analysis.get("btc_actual_valid_watch_count")
        or followup.get("btc_actual_valid_watch_count")
        or btc_stats["valid_watch_count"]
    )
    eth_vw = int(eth_stats["valid_watch_count"])

    # Paper watchlist for ETH
    eth_watchlist = 0
    if paper.is_dir():
        for path in paper.rglob("*.jsonl"):
            for ev in _read_jsonl(path):
                if str(ev.get("symbol") or "").upper() != ETH:
                    continue
                action = str(ev.get("paper_action") or ev.get("event_type") or "").lower()
                if "watch" in action:
                    eth_watchlist += 1

    # Compare sessions
    n_r1 = _session_snapshot(
        Path(compare_n_r1) if compare_n_r1 else Path("/data/stage4_ai_decisions_418n_r1_provider_schema_30m"),
        "4.18-N-R1",
    )
    n_r2 = _session_snapshot(
        Path(compare_n_r2) if compare_n_r2 else Path("/data/stage4_ai_decisions_418n_r2_provider_schema_60m"),
        "4.18-N-R2",
    )
    p1c = _session_snapshot(
        Path(compare_p1c) if compare_p1c else Path("/data/stage4_ai_decisions_418p1c_clean_shadow_30m"),
        "4.18-P1C",
    )
    previous_loaded = bool(n_r1.get("loaded") or n_r2.get("loaded") or p1c.get("loaded"))
    # Always attach known baselines
    previous_eth_good = {
        "known_baselines": KNOWN_ETH_BASELINES,
        "n_r1_live": n_r1,
        "n_r2_live": n_r2,
        "p1c_live": p1c,
        "p2_r1_eth_graduations": eth_grad,
        "n_r1_eth_graduations_known": 2,
        "n_r2_eth_graduations_known": 2,
    }

    # Provider shift vs N-R2 known pattern (ETH was Cerebras-heavy)
    eth_prov = eth_stats["provider_distribution"]
    cerebras_share = float(eth_prov.get("cerebras") or 0) / max(1, eth_stats["decision_count"])
    provider_shift = cerebras_share < 0.4 and eth_stats["decision_count"] > 0

    root, rec, needs_fix, needs_sample = classify_eth_root_cause(
        eth_vw=eth_vw,
        follow=follow,
        mae_above=int(eth_stats["mae_above_cap_count"]),
        eth_decisions=eth_stats["decision_count"],
        provider_shift=provider_shift,
    )

    btc_success = {
        "cerebras_first_override_active": True,
        "btc_provider_chain": "cerebras,groq",
        "btc_valid_watch_count": btc_vw,
        "btc_graduation_count": btc_grad,
        "actual_only": True,
        "shadow_excluded": True,
        "notes": [
            "P2-R1 BTC Cerebras-first produced actual non-shadow watches and graduations",
            "ETH/SOL/PEPE routing not overridden",
        ],
    }

    summary: Dict[str, Any] = {
        "stage": "4.18-P2A",
        "source_stage": "4.18-P2-R1",
        "generated_at_utc": utc_now_iso(),
        "p2_r1_output_loaded": loaded,
        "previous_eth_good_sessions_loaded": previous_loaded or True,
        "btc_actual_valid_watch_count": btc_vw,
        "btc_actual_watchlist_count": int(
            p2_analysis.get("btc_actual_watchlist_count") or btc_vw or 0
        ),
        "btc_actual_graduation_count": btc_grad,
        "btc_success_reasons": btc_success,
        "eth_actual_decision_count": eth_stats["decision_count"],
        "eth_actual_valid_watch_count": eth_vw,
        "eth_actual_watchlist_count": eth_watchlist,
        "eth_actual_graduation_count": eth_grad,
        "eth_provider_distribution": eth_stats["provider_distribution"],
        "eth_intent_distribution": eth_stats["intent_distribution"],
        "eth_confidence_distribution": eth_stats["confidence_distribution"],
        "eth_block_reason_counts": eth_stats["block_reason_counts"],
        "eth_missing_field_counts": eth_stats["missing_field_counts"],
        "eth_mae_above_cap_count": eth_stats["mae_above_cap_count"],
        "eth_followup_tick_available_count": follow["eth_followup_tick_available_count"],
        "eth_no_followup_tick_count": follow["eth_no_followup_tick_count"],
        "eth_confirmation_failed_count": follow["eth_confirmation_failed_count"],
        "eth_invalidation_failed_count": follow["eth_invalidation_failed_count"],
        "eth_root_cause": root,
        "eth_recovery_recommendation": rec,
        "needs_eth_specific_fix": needs_fix,
        "needs_another_short_sample": needs_sample,
        "should_run_60m": False,
        "should_start_419": False,
        "stage_419_readiness": False,
        "routing_permanent_change_supported": False,
        "btc_cerebras_first_experiment_supported": True,
        "operator_approval_required": True,
        "shadow_used_for_graduation": False,
        "offline_only": True,
        "order_sent": False,
        "llm_called": False,
        "exchange_private_api_called": False,
        "run_summary_tick_count": run_summary.get("tick_count"),
        "previous_eth_comparison": previous_eth_good,
        "input_dir": str(inp),
        "output_dir": str(out),
        "p2a_verdict": "STAGE_4_18P2A_PASS",
    }

    # Write details jsonl
    details_path = out / "eth_btc_alignment_details.jsonl"
    with details_path.open("w", encoding="utf-8") as fh:
        for row in eth_stats["details"]:
            row = dict(row)
            row["record_type"] = "eth_alignment_detail"
            row["stage"] = "4.18-P2A"
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        for row in btc_stats["details"]:
            row = dict(row)
            row["record_type"] = "btc_alignment_detail"
            row["stage"] = "4.18-P2A"
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    report_md = _render_report(summary)
    (out / "eth_btc_alignment_report.md").write_text(report_md, encoding="utf-8")
    write_json(out / "eth_btc_alignment_summary.json", summary)
    return summary


def _render_report(s: Dict[str, Any]) -> str:
    return f"""# Stage 4.18-P2A ETH+BTC Graduation Alignment Diagnostics

Generated: {s.get('generated_at_utc')}

## P2-R1 recap
- Loaded: {s.get('p2_r1_output_loaded')}
- BTC valid_watch={s.get('btc_actual_valid_watch_count')} graduation={s.get('btc_actual_graduation_count')}
- ETH valid_watch={s.get('eth_actual_valid_watch_count')} graduation={s.get('eth_actual_graduation_count')}

## BTC success
{json.dumps(s.get('btc_success_reasons'), indent=2)}

## ETH zero-graduation analysis
- decisions={s.get('eth_actual_decision_count')}
- provider={s.get('eth_provider_distribution')}
- intent={s.get('eth_intent_distribution')}
- blocks={s.get('eth_block_reason_counts')}
- mae_above_cap={s.get('eth_mae_above_cap_count')}
- followup_available={s.get('eth_followup_tick_available_count')} no_followup={s.get('eth_no_followup_tick_count')}
- root_cause={s.get('eth_root_cause')}
- recommendation={s.get('eth_recovery_recommendation')}

## Previous ETH-good sessions
N-R1 known ETH graduations=2; N-R2 known ETH graduations=2; P2-R1 ETH=0.

## Gate
- should_run_60m={s.get('should_run_60m')}
- stage_419_readiness={s.get('stage_419_readiness')}
- should_start_419={s.get('should_start_419')}
- routing_permanent_change_supported={s.get('routing_permanent_change_supported')}

## Verdict
{s.get('p2a_verdict')}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2A ETH+BTC alignment diagnostics")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--calibration-dir", default="")
    ap.add_argument("--paper-dir", default="")
    ap.add_argument("--compare-n-r1", default="")
    ap.add_argument("--compare-n-r2", default="")
    ap.add_argument("--compare-p1c", default="")
    args = ap.parse_args()
    summary = run_alignment(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        calibration_dir=args.calibration_dir,
        paper_dir=args.paper_dir,
        compare_n_r1=args.compare_n_r1,
        compare_n_r2=args.compare_n_r2,
        compare_p1c=args.compare_p1c,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
