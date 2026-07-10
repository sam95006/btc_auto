#!/usr/bin/env python3
"""Stage 4.18-P1A — BTC actual vs shadow paired comparison (offline, no LLM)."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_btc_dual_provider_shadow import (  # noqa: E402
    _intent_bucket,
    _safe_float,
    classify_shadow_outcome,
    is_shadow_comparable,
)
from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
    _has_entry_trigger,
    _has_invalidation,
    _is_valid_watch_candidate,
    _normalize_side,
)
from tools.research.stage4_paper_readiness import (  # noqa: E402
    assess_decision_quality,
    parse_entry_trigger,
    parse_invalidation,
    symbol_mae_watch_cap_pct,
)
from tools.research.stage4_provider_routing_config import (  # noqa: E402
    BTC_SYMBOL,
    SHADOW_JSONL_FILENAME,
    is_shadow_decision_row,
)

PAIRED_JSONL = "paired_comparison.jsonl"
PAIRED_SUMMARY = "paired_comparison_summary.json"
PAIRED_REPORT = "paired_comparison_report.md"


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


def load_actual_btc_decisions(input_dir: Path) -> List[Dict[str, Any]]:
    rows = _read_jsonl(input_dir / "ai_decisions.jsonl")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if is_shadow_decision_row(row):
            continue
        if str(row.get("symbol") or "").upper() != BTC_SYMBOL:
            continue
        out.append(row)
    return out


def load_shadow_btc_decisions(input_dir: Path) -> List[Dict[str, Any]]:
    return _read_jsonl(input_dir / SHADOW_JSONL_FILENAME)


def _field_present_trigger(raw: Dict[str, Any]) -> bool:
    return _has_entry_trigger(parse_entry_trigger(raw.get("entry_trigger")))


def _field_present_invalidation(raw: Dict[str, Any]) -> bool:
    return _has_invalidation(parse_invalidation(raw.get("invalidation")))


def _block_reason_for_decision(raw: Dict[str, Any]) -> str:
    intent = _intent_bucket(str(raw.get("decision_intent") or ""))
    if intent in {"unknown", ""}:
        return "unknown_intent"
    if intent not in {"watch", "enter_candidate"}:
        return f"intent_{intent}"
    if raw.get("parse_error"):
        return "parse_error"
    incomplete, paper_readiness, reasons = assess_decision_quality(raw)
    block = str(paper_readiness.get("block_reason") or "")
    if block and block != "ok":
        return block
    if incomplete and reasons:
        return str(reasons[0])
    if _normalize_side(raw.get("candidate_side")) == "NONE":
        return "side_missing"
    if not _field_present_trigger(raw):
        return "trigger_missing"
    if not _field_present_invalidation(raw):
        return "invalidation_missing"
    try:
        mae = float(raw.get("mae_risk_estimate_pct") or 0)
    except (TypeError, ValueError):
        return "mae_missing"
    if mae <= 0:
        return "mae_missing"
    cap = symbol_mae_watch_cap_pct(str(raw.get("symbol") or BTC_SYMBOL))
    if mae > cap:
        return "mae_above_symbol_cap"
    if _is_valid_watch_candidate(raw):
        return "ok"
    return "not_valid_watch_other"


def _why_shadow_not_valid_watch(shadow: Dict[str, Any]) -> str:
    outcome = classify_shadow_outcome(shadow)
    if outcome == "shadow_valid_watch":
        return "n/a_shadow_valid_watch"
    if shadow.get("shadow_call_skipped") or outcome == "shadow_call_skipped":
        return f"shadow_call_skipped:{shadow.get('shadow_skip_reason') or 'unknown'}"
    if outcome == "shadow_provider_token_limited":
        return "shadow_provider_token_limited"
    if outcome == "shadow_provider_rate_limited":
        return "shadow_provider_rate_limited"
    if outcome == "shadow_provider_response_truncated":
        return "shadow_provider_response_truncated"
    if outcome == "shadow_provider_unavailable":
        return "shadow_provider_unavailable"
    if outcome == "shadow_parse_unknown_intent":
        return "shadow_parse_unknown_intent"
    if shadow.get("parse_error") or shadow.get("llm_error"):
        err = str(shadow.get("llm_error") or "parse_error")
        return f"shadow_provider_error:{err}"
    intent = _intent_bucket(str(shadow.get("shadow_decision_intent") or ""))
    if intent in {"unknown", ""}:
        return "shadow_parse_unknown_intent"
    if intent not in {"watch", "enter_candidate"}:
        return f"shadow_intent_{intent}"
    if _normalize_side(shadow.get("shadow_candidate_side")) == "NONE":
        return "shadow_side_missing"
    if not shadow.get("shadow_entry_trigger_present"):
        return "shadow_trigger_missing"
    if not shadow.get("shadow_invalidation_present"):
        return "shadow_invalidation_missing"
    try:
        mae = float(shadow.get("shadow_mae_risk_estimate_pct") or 0)
    except (TypeError, ValueError):
        mae = 0.0
    if mae <= 0:
        return "shadow_mae_missing"
    cap = symbol_mae_watch_cap_pct(BTC_SYMBOL)
    if mae > cap:
        return "shadow_mae_above_cap"
    conf = shadow.get("shadow_confidence")
    if conf is not None and _safe_float(conf) < 0.45:
        return "shadow_confidence_below_soft_floor"
    if shadow.get("shadow_paper_readiness_eligible") is False:
        return "shadow_paper_readiness_ineligible"
    return "shadow_valid_decision_but_not_watch"


def _why_actual_not_graduated(
    *,
    actual: Dict[str, Any],
    actual_valid_watch: bool,
    graduated_ids: set[str],
) -> str:
    did = str(actual.get("decision_id") or "")
    if did and did in graduated_ids:
        return "n/a_graduated"
    if not actual_valid_watch:
        return "n/a_not_valid_watch"
    # Valid watch but no graduation in calibration / follow-up evidence.
    return "watchlist_followup_no_graduation"


def _divergence_type(actual_intent: str, shadow_intent: str, divergence: bool) -> str:
    if not divergence:
        return "none"
    if shadow_intent in {"unknown", ""}:
        return "shadow_unknown_vs_actual"
    if actual_intent != shadow_intent:
        return f"intent_{actual_intent}_vs_{shadow_intent}"
    return "bias_or_side_divergence"


def _load_graduated_decision_ids(input_dir: Path, calibration_dir: Optional[Path]) -> set[str]:
    ids: set[str] = set()
    candidates: List[Path] = []
    if calibration_dir:
        candidates.append(Path(calibration_dir))
    candidates.extend(
        [
            input_dir / "stage4_18p1_r1_actual_only_calibration",
            Path("/data/stage4_18p1_r1_actual_only_calibration"),
        ]
    )
    for base in candidates:
        if not base.is_dir():
            continue
        for path in base.rglob("*.jsonl"):
            for row in _read_jsonl(path):
                if str(row.get("event_type") or row.get("record_type") or "").lower() in {
                    "hypothetical_graduation",
                    "graduation",
                    "watchlist_graduated",
                } or row.get("graduated") is True:
                    sid = str(row.get("source_decision_id") or row.get("decision_id") or "")
                    if sid:
                        ids.add(sid)
        summary = base / "calibration_replay_summary.json"
        if summary.is_file():
            try:
                data = json.loads(summary.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            for mode in (data.get("mode_results") or {}).values():
                if not isinstance(mode, dict):
                    continue
                for g in mode.get("graduations") or mode.get("hypothetical_graduations") or []:
                    if isinstance(g, dict):
                        sid = str(g.get("source_decision_id") or g.get("decision_id") or "")
                        if sid:
                            ids.add(sid)
    return ids


def pair_actual_and_shadow(
    actuals: List[Dict[str, Any]],
    shadows: List[Dict[str, Any]],
) -> List[Tuple[int, Dict[str, Any], Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_tick: Dict[int, Dict[str, Any]] = {}
    for s in shadows:
        sid = str(s.get("source_decision_id") or "")
        if sid:
            by_id[sid] = s
        tick = s.get("source_tick_index")
        if tick is not None:
            try:
                by_tick[int(tick)] = s
            except (TypeError, ValueError):
                pass

    pairs: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    used_shadow_ids: set[str] = set()
    for idx, actual in enumerate(actuals):
        did = str(actual.get("decision_id") or "")
        shadow = by_id.get(did)
        if shadow is None:
            tick = actual.get("tick_index")
            if tick is None:
                tick = idx
            try:
                shadow = by_tick.get(int(tick))
            except (TypeError, ValueError):
                shadow = None
        if shadow is None:
            continue
        shadow_id = str(shadow.get("shadow_decision_id") or id(shadow))
        if shadow_id in used_shadow_ids:
            continue
        used_shadow_ids.add(shadow_id)
        tick_index = shadow.get("source_tick_index")
        if tick_index is None:
            tick_index = actual.get("tick_index", idx)
        try:
            tick_i = int(tick_index)
        except (TypeError, ValueError):
            tick_i = idx
        pairs.append((tick_i, actual, shadow))
    pairs.sort(key=lambda t: t[0])
    return pairs


def build_pair_row(
    *,
    tick_index: int,
    actual: Dict[str, Any],
    shadow: Dict[str, Any],
    graduated_ids: set[str],
) -> Dict[str, Any]:
    actual_intent = _intent_bucket(str(actual.get("decision_intent") or ""))
    shadow_intent = _intent_bucket(str(shadow.get("shadow_decision_intent") or ""))
    actual_valid = _is_valid_watch_candidate(actual)
    outcome = classify_shadow_outcome(shadow)
    comparable = is_shadow_comparable(shadow)
    # Uncomparable rows never count as skill valid_watch.
    shadow_valid = bool(
        comparable and shadow.get("shadow_would_be_valid_watch_under_current_rules")
    )
    divergence = bool(comparable and shadow.get("provider_divergence_detected"))
    if comparable and not divergence:
        divergence = actual_intent != shadow_intent or str(
            actual.get("directional_bias") or "NONE"
        ) != str(shadow.get("shadow_directional_bias") or "NONE")

    why_shadow = _why_shadow_not_valid_watch(shadow)
    why_actual_grad = _why_actual_not_graduated(
        actual=actual,
        actual_valid_watch=actual_valid,
        graduated_ids=graduated_ids,
    )
    routing_justified = bool(comparable and shadow_valid and not actual_valid)

    return {
        "pair_id": str(uuid.uuid4()),
        "tick_index": tick_index,
        "symbol": BTC_SYMBOL,
        "actual_provider": str(
            shadow.get("actual_provider") or actual.get("provider") or "unknown"
        ).lower(),
        "shadow_provider": str(shadow.get("shadow_provider") or "unknown").lower(),
        "actual_decision_intent": actual_intent,
        "shadow_decision_intent": shadow_intent,
        "actual_confidence": actual.get("confidence"),
        "shadow_confidence": shadow.get("shadow_confidence"),
        "actual_directional_bias": actual.get("directional_bias"),
        "shadow_directional_bias": shadow.get("shadow_directional_bias"),
        "actual_candidate_side": actual.get("candidate_side"),
        "shadow_candidate_side": shadow.get("shadow_candidate_side"),
        "actual_entry_trigger_present": _field_present_trigger(actual),
        "shadow_entry_trigger_present": bool(shadow.get("shadow_entry_trigger_present")),
        "actual_invalidation_present": _field_present_invalidation(actual),
        "shadow_invalidation_present": bool(shadow.get("shadow_invalidation_present")),
        "actual_mae_risk_estimate_pct": actual.get("mae_risk_estimate_pct"),
        "shadow_mae_risk_estimate_pct": shadow.get("shadow_mae_risk_estimate_pct"),
        "actual_valid_watch": actual_valid,
        "shadow_valid_watch": shadow_valid,
        "actual_block_reason": _block_reason_for_decision(actual),
        "shadow_block_reason": why_shadow if not shadow_valid else "ok",
        "shadow_outcome_class": outcome,
        "shadow_comparable": comparable,
        "shadow_call_skipped": bool(shadow.get("shadow_call_skipped")),
        "shadow_skip_reason": shadow.get("shadow_skip_reason"),
        "divergence_detected": divergence,
        "divergence_type": _divergence_type(actual_intent, shadow_intent, divergence),
        "why_shadow_not_valid_watch": why_shadow,
        "why_actual_not_graduated": why_actual_grad,
        "routing_change_justified_by_pair": routing_justified,
        "source_decision_id": actual.get("decision_id"),
        "shadow_decision_id": shadow.get("shadow_decision_id"),
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "order_sent": False,
    }


def _recommendation(
    *,
    pair_count: int,
    comparable: int,
    uncomparable: int,
    uncomparable_reasons: Dict[str, int],
    actual_valid: int,
    shadow_valid: int,
    actual_grad: int,
) -> Tuple[str, bool, bool, bool, bool]:
    """Returns recommendation, routing_supported, p2_recommended, should_60m, should_419."""
    if pair_count <= 0:
        return "no_pairs_found", False, False, False, False
    quotaish = sum(
        uncomparable_reasons.get(k, 0)
        for k in (
            "shadow_call_skipped",
            "shadow_provider_token_limited",
            "shadow_provider_rate_limited",
            "shadow_provider_unavailable",
            "shadow_provider_response_truncated",
            "shadow_parse_unknown_intent",
        )
    )
    if comparable < 3:
        if uncomparable > 0 and quotaish >= max(1, uncomparable // 2):
            return (
                "fix_shadow_quota_handling_before_provider_routing",
                False,
                False,
                False,
                False,
            )
        return (
            "collect_more_clean_shadow_samples_after_quota_aware_fix",
            False,
            False,
            False,
            False,
        )
    if shadow_valid > actual_valid and shadow_valid >= 2:
        return (
            "p2_routing_experiment_design_may_be_justified",
            True,
            True,
            False,
            False,
        )
    if actual_valid > shadow_valid:
        if actual_grad == 0 and actual_valid > 0:
            return (
                "analyze_btc_watchlist_followup_failure",
                False,
                False,
                False,
                False,
            )
        return (
            "do_not_change_routing_actual_path_currently_better",
            False,
            False,
            False,
            False,
        )
    if actual_valid > 0 and actual_grad == 0:
        return (
            "analyze_btc_watchlist_followup_failure",
            False,
            False,
            False,
            False,
        )
    return (
        "do_not_change_routing_actual_path_currently_better",
        False,
        False,
        False,
        False,
    )


def build_summary(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
    actual_valid = sum(1 for p in pairs if p.get("actual_valid_watch"))
    # Only comparable shadow valid watches count toward skill comparison.
    shadow_valid = sum(
        1 for p in pairs if p.get("shadow_comparable") and p.get("shadow_valid_watch")
    )
    actual_grad = sum(1 for p in pairs if p.get("why_actual_not_graduated") == "n/a_graduated")
    shadow_grad = 0
    comparable_pairs = [p for p in pairs if p.get("shadow_comparable")]
    uncomparable_pairs = [p for p in pairs if not p.get("shadow_comparable")]
    divergence = sum(1 for p in comparable_pairs if p.get("divergence_detected"))
    shadow_unknown = sum(
        1
        for p in pairs
        if _intent_bucket(str(p.get("shadow_decision_intent") or "")) in {"unknown", ""}
        or p.get("shadow_outcome_class") == "shadow_parse_unknown_intent"
    )
    actual_watch_shadow_not = sum(
        1
        for p in comparable_pairs
        if p.get("actual_valid_watch") and not p.get("shadow_valid_watch")
    )
    shadow_watch_actual_not = sum(
        1
        for p in comparable_pairs
        if p.get("shadow_valid_watch") and not p.get("actual_valid_watch")
    )
    why_shadow = Counter(str(p.get("why_shadow_not_valid_watch") or "") for p in pairs)
    why_shadow.pop("n/a_shadow_valid_watch", None)
    why_actual = Counter(str(p.get("why_actual_not_graduated") or "") for p in pairs)
    why_actual.pop("n/a_graduated", None)
    uncomp_reasons = Counter(
        str(p.get("shadow_outcome_class") or "unknown") for p in uncomparable_pairs
    )
    skipped = sum(1 for p in pairs if p.get("shadow_call_skipped"))
    called = len(pairs) - skipped
    skill_valid = len(comparable_pairs) >= 3

    rec, routing_ok, p2, should_60m, should_419 = _recommendation(
        pair_count=len(pairs),
        comparable=len(comparable_pairs),
        uncomparable=len(uncomparable_pairs),
        uncomparable_reasons=dict(uncomp_reasons),
        actual_valid=actual_valid,
        shadow_valid=shadow_valid,
        actual_grad=actual_grad,
    )
    # Never recommend P2 when skill comparison invalid.
    if not skill_valid:
        routing_ok = False
        p2 = False

    return {
        "record_type": "stage4_btc_shadow_pair_compare",
        "stage_marker": "4.18-P1B",
        "generated_at_utc": utc_now_iso(),
        "pair_count": len(pairs),
        "shadow_total_rows": len(pairs),
        "shadow_called_count": called,
        "shadow_call_skipped_count": skipped,
        "shadow_comparable_pair_count": len(comparable_pairs),
        "shadow_uncomparable_pair_count": len(uncomparable_pairs),
        "shadow_uncomparable_reason_counts": dict(uncomp_reasons),
        "provider_skill_comparison_valid": skill_valid,
        "actual_valid_watch_count": actual_valid,
        "shadow_valid_watch_count": shadow_valid,
        "actual_graduation_count": actual_grad,
        "shadow_graduation_count": shadow_grad,
        "divergence_count": divergence,
        "shadow_unknown_intent_count": shadow_unknown,
        "actual_watch_shadow_not_watch_count": actual_watch_shadow_not,
        "shadow_watch_actual_not_watch_count": shadow_watch_actual_not,
        "actual_provider_distribution": dict(
            Counter(str(p.get("actual_provider") or "unknown") for p in pairs)
        ),
        "shadow_provider_distribution": dict(
            Counter(str(p.get("shadow_provider") or "unknown") for p in pairs)
        ),
        "why_shadow_not_valid_watch_counts": dict(why_shadow),
        "why_actual_not_graduated_counts": dict(why_actual),
        "routing_change_supported": routing_ok,
        "p2_routing_experiment_recommended": p2,
        "should_run_another_60m": should_60m,
        "should_start_419": should_419,
        "stage_419_readiness": False,
        "recommendation": rec,
        "next_recommendation": rec,
        "shadow_excluded_from_paper_logger": True,
        "shadow_excluded_from_calibration": True,
        "shadow_excluded_from_graduation": True,
        "shadow_excluded_from_stage_419_readiness": True,
        "offline_only": True,
        "order_sent": False,
        "llm_called": False,
        "exchange_private_api_called": False,
    }


def _write_report_md(path: Path, summary: Dict[str, Any], pairs: List[Dict[str, Any]]) -> None:
    lines = [
        "# BTC Shadow Paired Comparison",
        "",
        f"- generated_at_utc: `{summary.get('generated_at_utc')}`",
        f"- pair_count: **{summary.get('pair_count')}**",
        f"- shadow_comparable_pair_count: **{summary.get('shadow_comparable_pair_count')}**",
        f"- shadow_uncomparable_pair_count: **{summary.get('shadow_uncomparable_pair_count')}**",
        f"- provider_skill_comparison_valid: **{summary.get('provider_skill_comparison_valid')}**",
        f"- actual_valid_watch_count: **{summary.get('actual_valid_watch_count')}**",
        f"- shadow_valid_watch_count: **{summary.get('shadow_valid_watch_count')}**",
        f"- divergence_count: **{summary.get('divergence_count')}**",
        f"- shadow_unknown_intent_count: **{summary.get('shadow_unknown_intent_count')}**",
        f"- recommendation: `{summary.get('recommendation')}`",
        f"- stage_419_readiness: `{summary.get('stage_419_readiness')}`",
        "",
        "## shadow_uncomparable_reason_counts",
        "",
        "```json",
        json.dumps(summary.get("shadow_uncomparable_reason_counts") or {}, indent=2),
        "```",
        "",
        "## why_shadow_not_valid_watch_counts",
        "",
        "```json",
        json.dumps(summary.get("why_shadow_not_valid_watch_counts") or {}, indent=2),
        "```",
        "",
        "## why_actual_not_graduated_counts",
        "",
        "```json",
        json.dumps(summary.get("why_actual_not_graduated_counts") or {}, indent=2),
        "```",
        "",
        "## Pairs",
        "",
    ]
    for p in pairs:
        lines.append(
            f"- tick={p.get('tick_index')} actual={p.get('actual_provider')}/"
            f"{p.get('actual_decision_intent')} shadow={p.get('shadow_provider')}/"
            f"{p.get('shadow_decision_intent')} "
            f"comparable={p.get('shadow_comparable')} "
            f"class=`{p.get('shadow_outcome_class')}` "
            f"valid(a/s)={p.get('actual_valid_watch')}/{p.get('shadow_valid_watch')} "
            f"why_shadow=`{p.get('why_shadow_not_valid_watch')}` "
            f"why_grad=`{p.get('why_actual_not_graduated')}`"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_pair_compare(
    *,
    input_dir: str | Path,
    output_dir: Optional[str | Path] = None,
    calibration_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir) if output_dir else inp / "stage4_18p1a_btc_shadow_pair_compare"
    out.mkdir(parents=True, exist_ok=True)

    actuals = load_actual_btc_decisions(inp)
    shadows = load_shadow_btc_decisions(inp)
    graduated_ids = _load_graduated_decision_ids(
        inp, Path(calibration_dir) if calibration_dir else None
    )
    paired = pair_actual_and_shadow(actuals, shadows)
    pair_rows = [
        build_pair_row(
            tick_index=tick,
            actual=actual,
            shadow=shadow,
            graduated_ids=graduated_ids,
        )
        for tick, actual, shadow in paired
    ]

    jsonl_path = out / PAIRED_JSONL
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for row in pair_rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = build_summary(pair_rows)
    summary["input_dir"] = str(inp)
    summary["output_dir"] = str(out)
    write_json(out / PAIRED_SUMMARY, summary)
    _write_report_md(out / PAIRED_REPORT, summary, pair_rows)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-P1A BTC shadow paired comparison")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--calibration-dir", default="")
    args = parser.parse_args()
    summary = run_pair_compare(
        input_dir=args.input_dir,
        output_dir=args.output_dir or None,
        calibration_dir=args.calibration_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
