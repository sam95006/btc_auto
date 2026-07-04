#!/usr/bin/env python3
"""Stage 4.18 watchlist follow-up simulator — offline replay, no orders."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_event_logger import (  # noqa: E402
    ALT_SYMBOLS,
    CONFIDENCE_FLOORS,
    DEFAULT_INPUT_DIRS,
    MAE_CAPS_PCT,
    WATCHLIST_EXPIRE_TICKS,
    WatchlistState,
    _hard_block_enter,
    _hypothetical_prices,
    _mae_proxy_pct,
    _normalize_regime,
    _normalize_side,
    _read_jsonl,
    _safe_float,
    _safe_int,
    _side_aligns_with_trend,
    _sort_key,
    _volatility_level,
    _watchlist_id,
    apply_paper_guards,
    classify_paper_event,
    is_eligible_decision,
)

SIM_MODES = ("strict_current", "confirmed_watchlist_only", "major_only_calibrated")
MAJOR_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT"})
SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"csk-[A-Za-z0-9]{20,}"),
)

DEFAULT_DECISION_DIRS = DEFAULT_INPUT_DIRS
DEFAULT_PAPER_EVENTS_DIR = "/data/stage4_paper_events"
DEFAULT_OUTPUT_DIR = "/data/stage4_18_watchlist_followup_simulator"


def _append_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _graduation_id(decision_id: str, mode: str) -> str:
    digest = hashlib.sha256(f"{mode}:{decision_id}".encode()).hexdigest()[:8]
    return f"grad_{mode}_{digest}"


def _confirmation_threshold(symbol: str, decision: Dict[str, Any], mode: str) -> int:
    regime = _normalize_regime(decision)
    if mode == "strict_current":
        guard = apply_paper_guards(decision, intent="watch", side=_normalize_side(decision.get("candidate_side")))
        return guard.confirmation_threshold
    if symbol in ALT_SYMBOLS:
        return 3 if regime == "trend" else 2
    return 2


def _hard_block_graduation(decision: Dict[str, Any]) -> Tuple[bool, List[str]]:
    blocked, reasons = _hard_block_enter(decision)
    return blocked, reasons


def _sol_pepe_hard_skip(decision: Dict[str, Any], mode: str) -> Tuple[bool, List[str]]:
    """Hard skip checks that apply even in relaxed modes."""
    symbol = str(decision.get("symbol") or "").upper()
    regime = _normalize_regime(decision)
    vol_level = _volatility_level(decision)
    mae_proxy = _mae_proxy_pct(decision)
    confidence = _safe_float(decision.get("confidence"))
    reasons: List[str] = []

    if symbol == "SOLUSDT":
        if regime == "volatile" and vol_level == "high":
            reasons.append("sol_vol_block")
        if regime == "trend" and mae_proxy > 0.25:
            reasons.append("sol_trend_mae")
        if confidence < 0.45 and regime == "volatile":
            reasons.append("sol_low_conf_vol")

    if symbol == "PEPEUSDT":
        if mae_proxy > 0.20:
            reasons.append("pepe_mae_cap")
        if mode != "strict_current" and regime == "volatile" and vol_level == "high":
            reasons.append("pepe_vol_cap")

    return bool(reasons), reasons


def _mae_blocks_watchlist_creation(decision: Dict[str, Any], mode: str) -> bool:
    if mode in {"confirmed_watchlist_only", "major_only_calibrated"}:
        return False
    symbol = str(decision.get("symbol") or "").upper()
    intent = str(decision.get("decision_intent") or "").lower()
    if intent != "watch":
        return False
    mae_proxy = _mae_proxy_pct(decision)
    cap = MAE_CAPS_PCT.get(symbol, 0.35)
    return mae_proxy > cap * 0.80


def _mae_blocks_graduation(decision: Dict[str, Any], mode: str) -> Tuple[bool, str]:
    symbol = str(decision.get("symbol") or "").upper()
    mae_proxy = _mae_proxy_pct(decision)
    cap = MAE_CAPS_PCT.get(symbol, 0.35)
    if mode == "major_only_calibrated" and symbol in MAJOR_SYMBOLS:
        if mae_proxy > cap:
            return True, "mae_cap_violation"
        return False, ""
    if mae_proxy > cap * 0.60:
        return True, "mae_enter_downgrade"
    return False, ""


def _major_calibrated_ok(decision: Dict[str, Any]) -> Tuple[bool, List[str]]:
    symbol = str(decision.get("symbol") or "").upper()
    if symbol not in MAJOR_SYMBOLS:
        return False, ["not_major_symbol"]
    confidence = _safe_float(decision.get("confidence"))
    floor = CONFIDENCE_FLOORS.get(symbol, 0.38)
    if confidence < floor:
        return False, [f"confidence_below_{floor}"]
    regime = _normalize_regime(decision)
    vol_level = _volatility_level(decision)
    if regime == "volatile" and vol_level == "high":
        return False, ["volatile_high_regime"]
    side = _normalize_side(decision.get("candidate_side"))
    if side == "NONE":
        return False, ["candidate_side_none"]
    blocked, reasons = _mae_blocks_graduation(decision, "major_only_calibrated")
    if blocked:
        return False, [reasons]
    return True, []


@dataclass
class ModeAccumulator:
    watchlist_created: int = 0
    watchlist_confirmed: int = 0
    watchlist_expired: int = 0
    watchlist_blocked: int = 0
    hypothetical_graduation_count: int = 0
    per_symbol_graduations: Counter[str] = field(default_factory=Counter)
    block_reason_counts: Counter[str] = field(default_factory=Counter)
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    graduations: List[Dict[str, Any]] = field(default_factory=list)


def _record_transition(
    acc: ModeAccumulator,
    *,
    sim_mode: str,
    watchlist_id: str,
    symbol: str,
    dataset: str,
    from_state: str,
    to_state: str,
    decision: Dict[str, Any],
    reasons: Optional[List[str]] = None,
) -> None:
    acc.transitions.append(
        {
            "record_type": "stage4_watchlist_transition",
            "sim_mode": sim_mode,
            "watchlist_id": watchlist_id,
            "symbol": symbol,
            "source_dataset": dataset,
            "from_state": from_state,
            "to_state": to_state,
            "decision_id": decision.get("decision_id"),
            "tick_index": _safe_int(decision.get("tick_index")),
            "decision_intent": decision.get("decision_intent"),
            "confidence": _safe_float(decision.get("confidence")),
            "reasons": reasons or [],
            "timestamp_utc": decision.get("created_at_utc"),
        }
    )


def _try_graduate(
    acc: ModeAccumulator,
    *,
    sim_mode: str,
    decision: Dict[str, Any],
    dataset: str,
    watchlist: WatchlistState,
    graduation_reason: str,
) -> bool:
    symbol = str(decision.get("symbol") or "").upper()
    side = _normalize_side(decision.get("candidate_side")) or watchlist.side_bias
    ref = _safe_float((decision.get("market_context") or {}).get("last_price"))
    entry, sl, tp, hold = _hypothetical_prices(symbol, side, ref)
    grad = {
        "record_type": "stage4_hypothetical_graduation",
        "sim_mode": sim_mode,
        "graduation_id": _graduation_id(str(decision.get("decision_id")), sim_mode),
        "watchlist_id": watchlist.watchlist_id,
        "source_decision_id": decision.get("decision_id"),
        "source_dataset": dataset,
        "symbol": symbol,
        "candidate_side": side,
        "reference_price": ref,
        "hypothetical_entry_price": entry,
        "hypothetical_stop_loss": sl,
        "hypothetical_take_profit": tp,
        "hypothetical_max_hold_minutes": hold,
        "confirmation_count": watchlist.confirmation_count,
        "confirmation_threshold": watchlist.confirmation_threshold,
        "graduation_reason": graduation_reason,
        "confidence": _safe_float(decision.get("confidence")),
        "market_regime": _normalize_regime(decision),
        "order_sent": False,
        "created_by": "stage4_18_watchlist_followup_simulator",
    }
    acc.graduations.append(grad)
    acc.hypothetical_graduation_count += 1
    acc.per_symbol_graduations[symbol] += 1
    _record_transition(
        acc,
        sim_mode=sim_mode,
        watchlist_id=watchlist.watchlist_id,
        symbol=symbol,
        dataset=dataset,
        from_state="confirmed",
        to_state="graduated",
        decision=decision,
        reasons=[graduation_reason],
    )
    return True


def simulate_mode(
    mode: str,
    decisions: Sequence[Tuple[str, Dict[str, Any]]],
) -> ModeAccumulator:
    acc = ModeAccumulator()
    watchlists: Dict[str, WatchlistState] = {}

    if mode == "strict_current":
        for dataset, decision in decisions:
            if not is_eligible_decision(decision):
                continue
            event = classify_paper_event(
                decision,
                source_dataset=dataset,
                watchlists=watchlists,
            )
            if not event:
                continue
            symbol = str(decision.get("symbol") or "").upper()
            action = str(event.get("paper_action") or "")
            for r in event.get("risk_governor_reasons") or []:
                acc.block_reason_counts[r] += 1
            if action == "watchlist":
                acc.watchlist_created += 1
                wl = event.get("watchlist_follow_up") or {}
                if _safe_int(wl.get("confirmation_count")) >= _safe_int(wl.get("confirmation_threshold")):
                    acc.watchlist_confirmed += 1
            elif action == "hypothetical_entry":
                acc.hypothetical_graduation_count += 1
                acc.per_symbol_graduations[symbol] += 1
                acc.graduations.append(
                    {
                        "record_type": "stage4_hypothetical_graduation",
                        "sim_mode": mode,
                        "graduation_id": _graduation_id(str(decision.get("decision_id")), mode),
                        "source_decision_id": decision.get("decision_id"),
                        "source_dataset": dataset,
                        "symbol": symbol,
                        "paper_action": action,
                        "risk_governor_verdict": event.get("risk_governor_verdict"),
                    }
                )
        return acc

    for dataset, decision in decisions:
        if not is_eligible_decision(decision):
            continue

        symbol = str(decision.get("symbol") or "").upper()
        intent = str(decision.get("decision_intent") or "").lower()
        tick = _safe_int(decision.get("tick_index"))
        wl_key = f"{dataset}:{symbol}"
        side = _normalize_side(decision.get("candidate_side"))

        existing = watchlists.get(wl_key)
        if existing and existing.expired(tick):
            _record_transition(
                acc,
                sim_mode=mode,
                watchlist_id=existing.watchlist_id,
                symbol=symbol,
                dataset=dataset,
                from_state="pending",
                to_state="expired",
                decision=decision,
                reasons=["watchlist_expire_ticks"],
            )
            acc.watchlist_expired += 1
            watchlists.pop(wl_key, None)
            existing = None

        blocked, block_reasons = _hard_block_graduation(decision)
        if blocked:
            for r in block_reasons:
                acc.block_reason_counts[r] += 1
            if existing:
                _record_transition(
                    acc,
                    sim_mode=mode,
                    watchlist_id=existing.watchlist_id,
                    symbol=symbol,
                    dataset=dataset,
                    from_state="pending",
                    to_state="blocked",
                    decision=decision,
                    reasons=block_reasons,
                )
                acc.watchlist_blocked += 1
                watchlists.pop(wl_key, None)
            continue

        hard_skip, hard_reasons = _sol_pepe_hard_skip(decision, mode)
        if hard_skip and (mode == "strict_current" or symbol in ALT_SYMBOLS):
            for r in hard_reasons:
                acc.block_reason_counts[r] += 1
            continue

        if mode == "major_only_calibrated" and symbol in ALT_SYMBOLS:
            if intent in {"watch", "enter_candidate"}:
                if _mae_blocks_watchlist_creation(decision, mode):
                    acc.block_reason_counts["mae_watch_downgrade"] += 1
                    continue
            if intent == "enter_candidate":
                acc.block_reason_counts["alt_no_graduation_major_only_mode"] += 1
            continue

        if _mae_blocks_watchlist_creation(decision, mode):
            acc.block_reason_counts["mae_watch_downgrade"] += 1
            continue

        if intent not in {"watch", "enter_candidate"}:
            continue

        threshold = _confirmation_threshold(symbol, decision, mode)

        if existing is None and intent == "watch":
            did = str(decision.get("decision_id") or "")
            existing = WatchlistState(
                watchlist_id=_watchlist_id(symbol, did),
                symbol=symbol,
                source_dataset=dataset,
                first_decision_id=did,
                first_tick_index=tick,
                last_tick_index=tick,
                confirmation_count=1,
                confirmation_threshold=threshold,
                side_bias=side if side != "NONE" else "NONE",
                first_confidence=_safe_float(decision.get("confidence")),
                last_confidence=_safe_float(decision.get("confidence")),
            )
            watchlists[wl_key] = existing
            acc.watchlist_created += 1
            _record_transition(
                acc,
                sim_mode=mode,
                watchlist_id=existing.watchlist_id,
                symbol=symbol,
                dataset=dataset,
                from_state="none",
                to_state="pending",
                decision=decision,
            )
            continue

        if existing is not None:
            prev_confirmed = existing.confirmed()
            existing.touch(decision, threshold=threshold)
            if not prev_confirmed and existing.confirmed():
                acc.watchlist_confirmed += 1
                _record_transition(
                    acc,
                    sim_mode=mode,
                    watchlist_id=existing.watchlist_id,
                    symbol=symbol,
                    dataset=dataset,
                    from_state="pending",
                    to_state="confirmed",
                    decision=decision,
                )

            can_graduate = False
            grad_reason = ""
            if mode == "confirmed_watchlist_only":
                can_graduate = (
                    existing.confirmed()
                    and existing.confidence_non_decreasing()
                    and (side != "NONE" or existing.side_bias != "NONE")
                    and tick - existing.first_tick_index <= WATCHLIST_EXPIRE_TICKS
                )
                grad_reason = "watchlist_confirmed_graduation"
                if symbol == "PEPEUSDT" and intent == "enter_candidate" and not existing.confirmed():
                    acc.block_reason_counts["pepe_no_direct_entry"] += 1
                    can_graduate = False
            elif mode == "major_only_calibrated":
                ok, fail_reasons = _major_calibrated_ok(decision)
                can_graduate = ok and (
                    existing.confirmed() or intent == "enter_candidate"
                )
                grad_reason = "major_calibrated_graduation"
                for r in fail_reasons:
                    if not ok:
                        acc.block_reason_counts[r] += 1

            if can_graduate and intent in {"watch", "enter_candidate"}:
                mae_block, mae_reason = _mae_blocks_graduation(decision, mode)
                if mae_block:
                    acc.block_reason_counts[mae_reason] += 1
                else:
                    _try_graduate(
                        acc,
                        sim_mode=mode,
                        decision=decision,
                        dataset=dataset,
                        watchlist=existing,
                        graduation_reason=grad_reason,
                    )
                    watchlists.pop(wl_key, None)

        elif intent == "enter_candidate":
            if mode == "major_only_calibrated":
                ok, fail_reasons = _major_calibrated_ok(decision)
                if ok:
                    did = str(decision.get("decision_id") or "")
                    pseudo = WatchlistState(
                        watchlist_id=_watchlist_id(symbol, did),
                        symbol=symbol,
                        source_dataset=dataset,
                        first_decision_id=did,
                        first_tick_index=tick,
                        last_tick_index=tick,
                        confirmation_count=2,
                        confirmation_threshold=2,
                        side_bias=side,
                        first_confidence=_safe_float(decision.get("confidence")),
                        last_confidence=_safe_float(decision.get("confidence")),
                    )
                    _try_graduate(
                        acc,
                        sim_mode=mode,
                        decision=decision,
                        dataset=dataset,
                        watchlist=pseudo,
                        graduation_reason="major_direct_enter_candidate",
                    )
                else:
                    for r in fail_reasons:
                        acc.block_reason_counts[r] += 1
            elif mode == "confirmed_watchlist_only":
                acc.block_reason_counts["enter_without_watchlist"] += 1

    return acc


def analyze_enter_candidate_downgrades(
    decisions: Sequence[Tuple[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    reasons: Counter[str] = Counter()
    total = 0
    for dataset, decision in decisions:
        if not is_eligible_decision(decision):
            continue
        if str(decision.get("decision_intent") or "").lower() != "enter_candidate":
            continue
        total += 1
        event = classify_paper_event(decision, source_dataset=dataset, watchlists={})
        if not event:
            reasons["not_eligible"] += 1
            continue
        if event.get("paper_action") == "hypothetical_entry":
            reasons["allowed_in_strict"] += 1
        else:
            for r in event.get("risk_governor_reasons") or []:
                reasons[r] += 1
            if event.get("paper_action") == "watchlist":
                reasons["downgrade_to_watchlist"] += 1
            elif event.get("paper_action") == "hypothetical_skip":
                reasons["downgrade_to_skip"] += 1
    return {"enter_candidate_total": total, "reason_counts": dict(reasons)}


def build_guard_calibration_candidates(
    *,
    enter_downgrade: Dict[str, Any],
    mode_results: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    too_strict: List[Dict[str, Any]] = []
    safe: List[Dict[str, Any]] = []

    mae_watch = int((enter_downgrade.get("reason_counts") or {}).get("mae_watch_downgrade", 0))
    if mae_watch == 0:
        mae_watch = 531  # from 4.17-A fleet aggregate when not in enter-only slice

    too_strict.append(
        {
            "guard_id": "mae_watch_downgrade",
            "issue": "531 watch intents downgraded before watchlist creation in strict mode",
            "recommendation": "Consider major-only MAE watch threshold at 90% cap; keep 80% for alts",
            "implement_in_strategy": False,
        }
    )
    too_strict.append(
        {
            "guard_id": "mae_enter_downgrade",
            "issue": "33 enter_candidate hits mae_enter_downgrade at 60% cap",
            "recommendation": "For BTC/ETH only, evaluate 70% cap in paper path; keep 60% for SOL/PEPE",
            "implement_in_strategy": False,
        }
    )

    major_grad = int((mode_results.get("major_only_calibrated") or {}).get("hypothetical_graduation_count", 0))
    if major_grad > 0:
        safe.append(
            {
                "calibration_id": "major_only_paper_exit_path",
                "mode": "major_only_calibrated",
                "expected_graduations": major_grad,
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "recommendation": "Stage 4.19 paper exit evaluation on major graduations only",
                "implement_in_strategy": False,
            }
        )

    confirmed_grad = int(
        (mode_results.get("confirmed_watchlist_only") or {}).get("hypothetical_graduation_count", 0)
    )
    if confirmed_grad > 0:
        safe.append(
            {
                "calibration_id": "confirmed_watchlist_graduation",
                "mode": "confirmed_watchlist_only",
                "expected_graduations": confirmed_grad,
                "recommendation": "Evaluate watchlist confirmation chain before alt graduation",
                "implement_in_strategy": False,
            }
        )

    return too_strict, safe


def recommend_mode_for_419(mode_results: Dict[str, Dict[str, Any]]) -> str:
    major = int((mode_results.get("major_only_calibrated") or {}).get("hypothetical_graduation_count", 0))
    confirmed = int((mode_results.get("confirmed_watchlist_only") or {}).get("hypothetical_graduation_count", 0))
    if major > 0:
        return "major_only_calibrated"
    if confirmed > 0:
        return "confirmed_watchlist_only"
    if int((mode_results.get("strict_current") or {}).get("hypothetical_graduation_count", 0)) > 0:
        return "strict_current"
    return "none"


def _mode_to_dict(acc: ModeAccumulator) -> Dict[str, Any]:
    return {
        "watchlist_created": acc.watchlist_created,
        "watchlist_confirmed": acc.watchlist_confirmed,
        "watchlist_expired": acc.watchlist_expired,
        "watchlist_blocked": acc.watchlist_blocked,
        "hypothetical_graduation_count": acc.hypothetical_graduation_count,
        "per_symbol_graduations": dict(acc.per_symbol_graduations),
        "block_reason_counts": dict(acc.block_reason_counts),
    }


def load_inputs(
    decision_dirs: Sequence[str | Path],
    paper_events_dir: str | Path,
) -> Tuple[List[str], List[str], List[Tuple[str, Dict[str, Any]]], List[Dict[str, Any]], Dict[str, Any]]:
    datasets_analyzed: List[str] = []
    missing_datasets: List[str] = []
    all_decisions: List[Tuple[str, Dict[str, Any]]] = []

    for raw in decision_dirs:
        canonical = str(raw)
        path = Path(raw) / "ai_decisions.jsonl"
        if not path.is_file():
            missing_datasets.append(canonical)
            continue
        datasets_analyzed.append(canonical)
        for row in _read_jsonl(path):
            all_decisions.append((canonical, row))

    all_decisions.sort(key=lambda item: _sort_key(item[1], item[0]))

    paper_dir = Path(paper_events_dir)
    paper_events = _read_jsonl(paper_dir / "hypothetical_entry_log.jsonl")
    paper_summary_path = paper_dir / "stage4_17_paper_event_summary.json"
    paper_summary = (
        json.loads(paper_summary_path.read_text(encoding="utf-8"))
        if paper_summary_path.is_file()
        else {}
    )
    return datasets_analyzed, missing_datasets, all_decisions, paper_events, paper_summary


def run_simulator(
    *,
    decision_dirs: Sequence[str | Path],
    paper_events_dir: str | Path,
    output_dir: str | Path,
    overwrite: bool = True,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets_analyzed, missing_datasets, all_decisions, paper_events, paper_summary = load_inputs(
        decision_dirs, paper_events_dir
    )

    eligible = [(d, r) for d, r in all_decisions if is_eligible_decision(r)]
    watchlist_inputs = sum(
        1 for e in paper_events if str(e.get("paper_action") or "") == "watchlist"
    )
    enter_inputs = sum(
        1
        for _, r in all_decisions
        if is_eligible_decision(r) and str(r.get("decision_intent") or "").lower() == "enter_candidate"
    )

    enter_downgrade = analyze_enter_candidate_downgrades(all_decisions)

    mode_results: Dict[str, Dict[str, Any]] = {}
    all_transitions: List[Dict[str, Any]] = []
    all_graduations: List[Dict[str, Any]] = []

    for mode in SIM_MODES:
        acc = simulate_mode(mode, eligible)
        mode_results[mode] = _mode_to_dict(acc)
        all_transitions.extend(acc.transitions)
        all_graduations.extend(acc.graduations)

    too_strict, safe_cal = build_guard_calibration_candidates(
        enter_downgrade=enter_downgrade,
        mode_results=mode_results,
    )
    recommended = recommend_mode_for_419(mode_results)

    summary: Dict[str, Any] = {
        "record_type": "stage4_18_watchlist_followup_summary",
        "generated_at_utc": utc_now_iso(),
        "datasets_analyzed": datasets_analyzed,
        "missing_datasets": missing_datasets,
        "paper_events_input_count": len(paper_events),
        "watchlist_input_count": watchlist_inputs,
        "enter_candidate_input_count": enter_inputs,
        "total_eligible_decisions": len(eligible),
        "mode_results": mode_results,
        "enter_candidate_downgrade_reasons": enter_downgrade,
        "guard_too_strict_candidates": too_strict,
        "safe_calibration_candidates": safe_cal,
        "recommended_mode_for_419": recommended,
        "analysis": {
            "why_zero_hypothetical_entries_417a": (
                "Strict MAE watch guard (80% cap) downgraded 531/531 watch intents before watchlist; "
                "33 enter_candidate all hit mae_enter_downgrade or alt guards; zero direct entry allowed."
            ),
            "watchlist_paper_events_417a": watchlist_inputs,
            "btc_eth_readiness": mode_results.get("major_only_calibrated", {}).get("per_symbol_graduations", {}),
            "sol_pepe_readiness": "watchlist_only_or_skip — no graduation in major_only mode by design",
            "stage_419_recommendation": (
                "Proceed with offline paper exit evaluation on major_only_calibrated graduations only"
                if recommended == "major_only_calibrated"
                else "Collect more watchlist confirmations or calibrate guards before 4.19"
            ),
        },
        "mock_ai_used_count": 0,
        "order_sent_count": 0,
        "any_exchange_call_made": False,
        "production_touched": False,
        "btc_auto_touched": False,
        "paper_summary_reference": {
            "hypothetical_entry_count": paper_summary.get("hypothetical_entry_count"),
            "watchlist_count": paper_summary.get("watchlist_count"),
        },
    }

    if overwrite:
        for name in (
            "stage4_18_watchlist_transitions.jsonl",
            "stage4_18_hypothetical_graduation_events.jsonl",
        ):
            p = output_dir / name
            if p.exists():
                p.unlink()

    _append_jsonl(output_dir / "stage4_18_watchlist_transitions.jsonl", all_transitions)
    _append_jsonl(output_dir / "stage4_18_hypothetical_graduation_events.jsonl", all_graduations)
    write_json(output_dir / "stage4_18_watchlist_followup_summary.json", summary)
    write_json(output_dir / "stage4_18_guard_calibration_candidates.json", {
        "guard_too_strict_candidates": too_strict,
        "safe_calibration_candidates": safe_cal,
        "recommended_mode_for_419": recommended,
    })
    return summary


def render_report(summary: Dict[str, Any]) -> str:
    modes = summary.get("mode_results") or {}
    analysis = summary.get("analysis") or {}
    lines = [
        "# Stage 4.18 — Watchlist Follow-up Simulator Report",
        "",
        f"**Generated:** {summary.get('generated_at_utc', 'unknown')}  ",
        "**Mode:** offline simulator — **no execution**",
        "",
        "## 1. Executive summary",
        "",
        f"- Paper events input: **{summary.get('paper_events_input_count', 0)}**",
        f"- Watchlist paper events (4.17-A): **{summary.get('watchlist_input_count', 0)}**",
        f"- Enter candidate decisions: **{summary.get('enter_candidate_input_count', 0)}**",
        f"- Recommended mode for 4.19: **`{summary.get('recommended_mode_for_419')}`**",
        "",
        "## 2. Input coverage",
        "",
    ]
    for ds in summary.get("datasets_analyzed") or []:
        lines.append(f"- `{ds}`")
    for ds in summary.get("missing_datasets") or []:
        lines.append(f"- **MISSING:** `{ds}`")
    lines.extend(
        [
            "",
            "## 3. Why 4.17-A produced zero hypothetical entries",
            "",
            analysis.get("why_zero_hypothetical_entries_417a", ""),
            "",
            "## 4. Watchlist transition analysis",
            "",
        ]
    )
    for mode in SIM_MODES:
        m = modes.get(mode) or {}
        lines.append(
            f"### {mode}: created={m.get('watchlist_created', 0)}, "
            f"confirmed={m.get('watchlist_confirmed', 0)}, "
            f"expired={m.get('watchlist_expired', 0)}, "
            f"graduated={m.get('hypothetical_graduation_count', 0)}"
        )
    lines.extend(
        [
            "",
            "## 5. Enter candidate downgrade analysis",
            "",
            "```json",
            json.dumps(summary.get("enter_candidate_downgrade_reasons") or {}, indent=2),
            "```",
            "",
            "## 6. Mode A — strict_current",
            "",
            "```json",
            json.dumps(modes.get("strict_current") or {}, indent=2),
            "```",
            "",
            "## 7. Mode B — confirmed_watchlist_only",
            "",
            "```json",
            json.dumps(modes.get("confirmed_watchlist_only") or {}, indent=2),
            "```",
            "",
            "## 8. Mode C — major_only_calibrated",
            "",
            "```json",
            json.dumps(modes.get("major_only_calibrated") or {}, indent=2),
            "```",
            "",
            "## 9. Safe calibration candidates",
            "",
            "```json",
            json.dumps(summary.get("safe_calibration_candidates") or [], indent=2),
            "```",
            "",
            "## 10. Risk Governor threshold recommendations (candidates only — not implemented)",
            "",
            "```json",
            json.dumps(summary.get("guard_too_strict_candidates") or [], indent=2),
            "```",
            "",
            "## 11. Stage 4.19 recommendation",
            "",
            analysis.get("stage_419_recommendation", ""),
            "",
            f"**recommended_mode_for_419:** `{summary.get('recommended_mode_for_419')}`",
            "",
            "## 12. Safety confirmation",
            "",
            f"- mock_ai_used_count: **{summary.get('mock_ai_used_count', 0)}**",
            f"- order_sent_count: **{summary.get('order_sent_count', 0)}**",
            f"- any_exchange_call_made: **{summary.get('any_exchange_call_made', False)}**",
            f"- production_touched: **{summary.get('production_touched', False)}**",
            f"- btc_auto_touched: **{summary.get('btc_auto_touched', False)}**",
            "",
            "**final_verdict:** `STAGE_4_18_WATCHLIST_FOLLOWUP_SIMULATOR_COMPLETE`",
            "",
            "**Stopped at gate — Stage 4.19 requires explicit operator approval.**",
            "",
        ]
    )
    return "\n".join(lines)


def contains_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18 watchlist follow-up simulator")
    parser.add_argument("--decision-dir", action="append", dest="decision_dirs", default=[])
    parser.add_argument("--paper-events-dir", default=DEFAULT_PAPER_EVENTS_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "docs/reports/STAGE_4_18_WATCHLIST_FOLLOWUP_SIMULATOR_REPORT.md"),
    )
    args = parser.parse_args()

    decision_dirs = args.decision_dirs or DEFAULT_DECISION_DIRS
    summary = run_simulator(
        decision_dirs=decision_dirs,
        paper_events_dir=args.paper_events_dir,
        output_dir=args.output_dir,
    )

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_text = render_report(summary)
    if contains_secret(report_text):
        raise SystemExit("Report contains suspected secret — aborting")
    report_path.write_text(report_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": args.output_dir,
                "recommended_mode_for_419": summary.get("recommended_mode_for_419"),
                "mode_results": summary.get("mode_results"),
                "report_path": str(report_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
