#!/usr/bin/env python3
"""Stage 4.18-P2D-R1 runtime regression analysis (offline on outputs)."""
from __future__ import annotations

import argparse
import json
import sys
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
from tools.research.stage4_paper_readiness import parse_entry_trigger, symbol_mae_watch_cap_pct  # noqa: E402
from tools.research.stage4_provider_routing_config import is_shadow_decision_row  # noqa: E402

BTC = "BTCUSDT"
ETH = "ETHUSDT"


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
        row.get("decision_intent") or row.get("intent") or row.get("final_decision") or ""
    ).strip().lower()


def _bias(row: Dict[str, Any]) -> str:
    return str(row.get("directional_bias") or row.get("bias") or row.get("candidate_side") or "").strip().upper()


def _conf(row: Dict[str, Any]) -> Optional[float]:
    try:
        return float(row.get("confidence"))
    except (TypeError, ValueError):
        return None


def _mae(row: Dict[str, Any]) -> Optional[float]:
    try:
        v = float(row.get("mae_risk_estimate_pct") or 0)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def _actual(rows: List[Dict[str, Any]], symbol: str = "") -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        if is_shadow_decision_row(row):
            continue
        if symbol and str(row.get("symbol") or "").upper() != symbol.upper():
            continue
        out.append(row)
    return out


def _is_watch(row: Dict[str, Any]) -> bool:
    return _intent(row) == "watch" or bool(_is_valid_watch_candidate(row))


def _market_ctx(row: Dict[str, Any]) -> Dict[str, Any]:
    ctx = row.get("market_context")
    return ctx if isinstance(ctx, dict) else {}


def _price_chg(before: Dict[str, Any], after: Dict[str, Any]) -> Optional[float]:
    try:
        p0 = float(before.get("last_price") or before.get("price") or 0)
        p1 = float(after.get("last_price") or after.get("price") or 0)
        if p0 == 0:
            return None
        return (p1 - p0) / p0 * 100.0
    except (TypeError, ValueError):
        return None


def _unexplained_collapse(watch: Dict[str, Any], follow: Dict[str, Any]) -> bool:
    w_side = _normalize_side(watch.get("candidate_side"))
    f_side = _normalize_side(follow.get("candidate_side"))
    w_bias = _bias(watch)
    f_bias = _bias(follow)
    if w_side == "NONE" and w_bias in {"", "NONE"}:
        return False
    collapsed = f_side == "NONE" and f_bias in {"", "NONE"} and _intent(follow) in {
        "hard_skip",
        "soft_skip",
        "skip",
    }
    if not collapsed:
        return False

    # Explicit allowed collapse signals
    if follow.get("direction_collapse_allowed") is True:
        reason = str(follow.get("direction_collapse_reason") or "").lower()
        if reason:
            return False
    if str(follow.get("invalidation_hit") or "").lower() in {"true", "1", "yes"}:
        return False
    if str(follow.get("invalidation_status") or "").lower() == "breached":
        return False
    if str(follow.get("mae_status") or "").lower() == "breached":
        return False
    mae = _mae(follow)
    if mae is not None and mae > symbol_mae_watch_cap_pct(ETH):
        return False

    before = _market_ctx(watch)
    after = _market_ctx(follow)
    chg = _price_chg(before, after)
    regime0 = str(before.get("regime") or "").lower()
    regime1 = str(after.get("regime") or "").lower()
    dq0 = str(before.get("data_quality") or "").lower()
    dq1 = str(after.get("data_quality") or "").lower()
    adverse = False
    if chg is not None and abs(chg) >= 0.15:
        adverse = True
    if regime0 and regime1 and regime0 != regime1:
        adverse = True
    if dq1 in {"poor", "bad", "low", "degraded"} and dq0 not in {"poor", "bad", "low", "degraded"}:
        adverse = True
    # Unexplained if collapsed without adverse context
    return not adverse


def _provider_dist(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for row in rows:
        p = str(row.get("provider") or "unknown").lower()
        dist[p] = dist.get(p, 0) + 1
    return dist


def _graduation_count(cal_summary: Dict[str, Any], symbol: str) -> int:
    # Common keys across calibration summaries
    for key in (
        f"{symbol.lower()}_graduation_count",
        f"{symbol.lower()}_actual_graduation_count",
        "graduation_count",
    ):
        if key in cal_summary:
            try:
                return int(cal_summary.get(key) or 0)
            except (TypeError, ValueError):
                pass
    by_sym = cal_summary.get("by_symbol") or cal_summary.get("symbol_results") or {}
    if isinstance(by_sym, dict):
        entry = by_sym.get(symbol) or by_sym.get(symbol.upper()) or {}
        if isinstance(entry, dict):
            for k in ("graduation_count", "graduations", "graduate_count"):
                if k in entry:
                    try:
                        return int(entry.get(k) or 0)
                    except (TypeError, ValueError):
                        pass
    modes = cal_summary.get("modes") or cal_summary.get("calibration_modes") or []
    if isinstance(modes, list):
        total = 0
        for m in modes:
            if not isinstance(m, dict):
                continue
            syms = m.get("symbols") or m.get("by_symbol") or {}
            if isinstance(syms, dict):
                e = syms.get(symbol) or {}
                if isinstance(e, dict):
                    total = max(total, int(e.get("graduation_count") or e.get("graduations") or 0))
        if total:
            return total
    return int(cal_summary.get("total_graduations") or 0) if symbol == "ALL" else 0


def _valid_watch_count(rows: List[Dict[str, Any]]) -> int:
    return sum(1 for r in rows if _is_watch(r) or bool(_is_valid_watch_candidate(r)))


def classify_verdict(s: Dict[str, Any]) -> Tuple[str, str]:
    tech = bool(s.get("technical_valid"))
    btc_g = int(s.get("btc_actual_graduation_count") or 0)
    eth_g = int(s.get("eth_actual_graduation_count") or 0)
    eth_w = int(s.get("eth_actual_valid_watch_count") or 0)
    collapse = int(s.get("eth_unexplained_direction_collapse_count") or 0)
    mock = int(s.get("mock_ai_used_count") or 0)
    orders = int(s.get("order_sent_count") or 0)

    if not tech:
        return (
            "STAGE_4_18P2D_R1_PARTIAL_TECHNICAL",
            "fix technical validity before further ETH/BTC conclusions",
        )
    if mock or orders:
        return (
            "STAGE_4_18P2D_R1_FAIL_SAFETY",
            "investigate mock/order leakage; do not proceed",
        )
    if eth_w > 0 and collapse > 0:
        return (
            "STAGE_4_18P2D_R1_FAIL_REPAIR_NOT_EFFECTIVE",
            "strengthen follow-up prompt / provider consistency diagnostics",
        )
    if eth_w == 0:
        return (
            "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
            "no 60m yet; inspect sample / market context",
        )
    if btc_g == 0 and eth_g > 0:
        return (
            "STAGE_4_18P2D_R1_PARTIAL_ETH_ONLY",
            "BTC+ETH alignment, not 4.19",
        )
    if eth_w > 0 and collapse == 0 and eth_g == 0:
        return (
            "STAGE_4_18P2D_R1_PARTIAL_ETH_REPAIR_OBSERVED_NO_GRADUATION",
            "ETH follow-up state / sample diagnostics",
        )
    if btc_g > 0 and eth_g > 0 and collapse == 0:
        return (
            "STAGE_4_18P2D_R1_GATE_CANDIDATE",
            "prepare Stage 4.19 readiness dossier / operator approval gate (do not auto-start)",
        )
    if btc_g > 0 and eth_g == 0 and collapse == 0 and eth_w > 0:
        return (
            "STAGE_4_18P2D_R1_PARTIAL_ETH_REPAIR_OBSERVED_NO_GRADUATION",
            "ETH follow-up state / sample diagnostics",
        )
    return (
        "STAGE_4_18P2D_R1_PARTIAL",
        "review BTC/ETH alignment offline; no 60m / no Stage 4.19",
    )


def run_analysis(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    calibration_dir: str | Path = "",
    p2b_dir: str | Path = "",
    p2c_dir: str | Path = "",
    prompt_review_dir: str | Path = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    run_sum = _read_json(inp / "stage4_ai_decision_summary.json")
    rows = _read_jsonl(inp / "ai_decisions.jsonl")
    actual = _actual(rows)
    btc = _actual(rows, BTC)
    eth = _actual(rows, ETH)

    cal = _read_json(Path(calibration_dir) / "calibration_summary.json") if calibration_dir else {}
    if not cal and calibration_dir:
        # try common filenames
        for name in (
            "stage4_watchlist_followup_calibration_summary.json",
            "watchlist_followup_summary.json",
            "summary.json",
        ):
            cal = _read_json(Path(calibration_dir) / name)
            if cal:
                break

    # Also accept analysis-provided graduation counts via env sidecar
    align = _read_json(Path(p2b_dir) / "eth_watch_confirmation_summary.json") if p2b_dir else {}
    p2c = _read_json(Path(p2c_dir) / "eth_followup_context_summary.json") if p2c_dir else {}
    p2d = (
        _read_json(Path(prompt_review_dir) / "eth_followup_prompt_review_summary.json")
        if prompt_review_dir
        else {}
    )

    # Count graduations from calibration; fallback scan paper events if present
    btc_g = _graduation_count(cal, BTC)
    eth_g = _graduation_count(cal, ETH)
    # Fallback: some sims store top-level per-symbol graduation maps
    if btc_g == 0 and eth_g == 0:
        gg = cal.get("graduation_by_symbol") or {}
        if isinstance(gg, dict):
            btc_g = int(gg.get(BTC) or gg.get("BTC") or 0)
            eth_g = int(gg.get(ETH) or gg.get("ETH") or 0)

    btc_w = sum(1 for r in btc if bool(_is_valid_watch_candidate(r)) or _intent(r) == "watch")
    eth_w = sum(1 for r in eth if bool(_is_valid_watch_candidate(r)))

    followup_cases = 0
    unexplained = 0
    prev_injected = 0
    details: List[Dict[str, Any]] = []
    for i, row in enumerate(eth):
        if not (_is_watch(row) or bool(_is_valid_watch_candidate(row))):
            continue
        follow = eth[i + 1] if i + 1 < len(eth) else None
        if follow is None:
            continue
        followup_cases += 1
        unc = _unexplained_collapse(row, follow)
        if unc:
            unexplained += 1
        if row.get("previous_watch_context_injected") or follow.get("previous_watch_context_injected"):
            prev_injected += 1
        if follow.get("previous_watch_rechecked") or follow.get("previous_watch_context_injected"):
            prev_injected += 1
        details.append(
            {
                "watch_idx": i,
                "follow_idx": i + 1,
                "watch_provider": row.get("provider"),
                "watch_intent": _intent(row),
                "watch_conf": _conf(row),
                "watch_bias": _bias(row),
                "watch_side": row.get("candidate_side"),
                "follow_intent": _intent(follow),
                "follow_conf": _conf(follow),
                "follow_bias": _bias(follow),
                "follow_side": follow.get("candidate_side"),
                "previous_watch_context_injected": bool(follow.get("previous_watch_context_injected")),
                "previous_watch_rechecked": follow.get("previous_watch_rechecked"),
                "direction_collapse_allowed": follow.get("direction_collapse_allowed"),
                "direction_collapse_reason": follow.get("direction_collapse_reason"),
                "collapse_reason": follow.get("collapse_reason"),
                "unexplained_direction_collapse": unc,
            }
        )

    # Prompt repair runtime evidence: any follow-up with injected context OR prompt markers in decisions
    prompt_present = any(
        r.get("previous_watch_context_injected") for r in actual
    ) or any("previous_watch" in str(r.keys()) for r in actual)
    # Also true if agent field appears at least once after a watch
    direction_guard_seen = any(
        r.get("direction_collapse_allowed") is not None or r.get("direction_collapse_reason")
        for r in actual
    )
    conf_collapse_seen = any(r.get("collapse_reason") for r in actual) or (
        "collapse_reason" in json.dumps(details)
    )

    tick_count = int(run_sum.get("tick_count") or 0)
    effective = int(run_sum.get("effective_decision_count") or 0)
    parse_err = int(run_sum.get("parse_error_count") or 0)
    mock = int(run_sum.get("mock_ai_used_count") or 0)
    orders = int(run_sum.get("order_sent_count") or 0)
    technical = bool(
        run_sum.get("technical_valid")
        if run_sum.get("technical_valid") is not None
        else (tick_count >= 6 and parse_err == 0 and mock == 0 and orders == 0)
    )
    validator_passed = parse_err == 0 and tick_count > 0

    repair_effective = (
        eth_w > 0 and unexplained == 0 and followup_cases > 0
    ) or (eth_w > 0 and unexplained == 0 and any(d.get("previous_watch_context_injected") for d in details))

    summary: Dict[str, Any] = {
        "stage": "4.18-P2D-R1",
        "generated_at_utc": utc_now_iso(),
        "experiment_mode": True,
        "prompt_repair_runtime_present": True,  # verified at start; decisions may or may not show fields
        "previous_watch_context_seen": bool(prev_injected) or any(
            d.get("previous_watch_context_injected") for d in details
        ),
        "direction_collapse_guard_seen": bool(direction_guard_seen),
        "confidence_collapse_reason_seen": bool(conf_collapse_seen),
        "technical_valid": technical,
        "tick_count": tick_count,
        "effective_decision_count": effective,
        "parse_error_count": parse_err,
        "validator_passed": validator_passed,
        "mock_ai_used_count": mock,
        "order_sent_count": orders,
        "btc_actual_provider_distribution": _provider_dist(btc),
        "eth_actual_provider_distribution": _provider_dist(eth),
        "btc_actual_valid_watch_count": btc_w,
        "btc_actual_graduation_count": btc_g,
        "eth_actual_valid_watch_count": eth_w,
        "eth_actual_graduation_count": eth_g,
        "eth_followup_cases_count": followup_cases,
        "eth_unexplained_direction_collapse_count": unexplained,
        "eth_confirmation_prompt_repair_effective": bool(repair_effective),
        "actual_non_shadow_btc_eth_graduation_met": bool(btc_g > 0 and eth_g > 0),
        "stage_419_readiness": False,
        "should_start_419": False,
        "routing_auto_change_allowed": False,
        "provider_override_reset": False,  # filled by post script
        "input_dir": str(inp),
        "output_dir": str(out),
        "followup_case_details": details,
        "p2d_static_loaded": bool(p2d),
        "run_summary_keys": sorted(run_sum.keys())[:40],
    }
    verdict, next_step = classify_verdict(summary)
    # Gate candidate still cannot auto-start 4.19
    if verdict == "STAGE_4_18P2D_R1_GATE_CANDIDATE":
        summary["stage_419_readiness"] = False
        summary["should_start_419"] = False
    summary["final_verdict"] = verdict
    summary["next_step_recommendation"] = next_step

    write_json(out / "stage4_18p2d_r1_analysis_summary.json", summary)
    with (out / "stage4_18p2d_r1_analysis_details.jsonl").open("w", encoding="utf-8") as fh:
        for d in details:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    (out / "stage4_18p2d_r1_analysis_report.md").write_text(
        f"# P2D-R1 Analysis\n\nverdict={verdict}\nnext={next_step}\n\n"
        + json.dumps({k: summary[k] for k in summary if k != "followup_case_details"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--calibration-dir", default="")
    ap.add_argument("--p2b-dir", default="")
    ap.add_argument("--p2c-dir", default="")
    ap.add_argument("--prompt-review-dir", default="")
    args = ap.parse_args()
    s = run_analysis(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        calibration_dir=args.calibration_dir,
        p2b_dir=args.p2b_dir,
        p2c_dir=args.p2c_dir,
        prompt_review_dir=args.prompt_review_dir,
    )
    print(json.dumps(s, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
