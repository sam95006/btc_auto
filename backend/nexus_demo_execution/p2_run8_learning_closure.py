"""P2 learning closure from the certified Run #8 exchange lifecycle.

Research-only. Does not create trades, arm autonomy, or mutate hard safety policy.
A single losing trade cannot become policy truth.
"""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from backend.nexus_demo_execution.p1_validation_runtime import apply_disarmed_flags
from backend.nexus_demo_execution.session_limits import FIXED_LEVERAGE, MARGIN_PER_TRADE_CAP


P2_CAMPAIGN_ID = "bybit-demo-p2-run8-learning-closure"
PNL_PROVENANCE = "BYBIT_V5_POSITION_CLOSED_PNL"
ARM_READY_HOLD = "HOLD"
LESSON_STATUS_CANDIDATE = "candidate_only"
MIN_SUPPORT_FOR_POLICY = 3
LESSON_TTL_TRADES = 20
PROTECTED_POLICY_FIELDS = (
    "FIXED_LEVERAGE",
    "MARGIN_PER_TRADE_CAP",
    "execution_permissions",
    "safety_gates",
    "MAINNET",
    "REAL_MONEY",
    "EXCHANGE_WRITE",
    "DEMO_AUTONOMOUS_ENABLED",
    "AUTONOMOUS_SEND",
    "AUTONOMOUS_BYBIT_DEMO_ARM_READY",
)
MISTAKE_TAXONOMY = (
    "ENTRY_TIMING",
    "DIRECTION",
    "SIGNAL_QUALITY",
    "MARKET_REGIME",
    "FEE_DRAG",
    "RISK_SIZING",
    "NO_MISTAKE",
    "VALID_DECISION_BAD_OUTCOME",
)
DISARMED_FLAGS = {
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SEND": "false",
    "EXCHANGE_WRITE": "false",
}


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _text(value: Any) -> str:
    return str(value or "").strip()


def certified_run8_snapshot() -> dict[str, Any]:
    """TEST FIXTURE ONLY. Not authoritative production input."""
    return {
        "source": "TEST_FIXTURE_NOT_AUTHORITATIVE",
        "fixture_only": True,
        "authoritative": False,
        "campaign_id": "bybit-demo-p1-qualification",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "trade_id": "run8_certified_trade",
        "decision_id": "run8_certified_decision",
        "run8_evidence_identity": "run8_certified_lifecycle",
        "candidate_count": 1,
        "entry_read_pass": True,
        "close_read_pass": True,
        "position_flat": True,
        "execution_identity_pass": True,
        "closed_pnl_exact_match": True,
        "P1_EXCHANGE_REALIZED_PNL_PASS": True,
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS": True,
        "P1_PREFLIGHT_PASS": True,
        "RISK_ENGINE_FINAL_AUTHORITY_PASS": True,
        "P1_ENTRY_RECONCILIATION_PASS": True,
        "P1_CLOSE_RECONCILIATION_PASS": True,
        "P1_RUN8_POSITION_FLAT": True,
        "P1_RUN8_EXACT_CLOSED_PNL_MATCH": True,
        "ledger_final_state": "CLOSED",
        "actual_entry_price": "64282.2",
        "actual_exit_price": "64282.2",
        "filled_qty": "0.001",
        "open_fee": "0.03535521",
        "close_fee": "0.03535521",
        "realized_demo_pnl": "-0.07071042",
        "pnl_provenance": PNL_PROVENANCE,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "original_decision_context": {
            "purpose": "P1_QUALIFICATION_ONE_SHOT",
            "campaign_id": "bybit-demo-p1-qualification",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "requested_qty": "0.001",
            "founder_authorized_qualification": True,
        },
    }


def load_run8_learning_input(
    payload: dict[str, Any] | None = None,
    *,
    allow_test_fixture: bool = False,
) -> dict[str, Any]:
    if payload is None:
        if not allow_test_fixture:
            raise ValueError("durable_run8_input_required")
        source = certified_run8_snapshot()
    else:
        source = deepcopy(payload)
    if source.get("fixture_only") and not allow_test_fixture:
        raise ValueError("hardcoded_snapshot_not_authoritative")
    required = (
        "symbol",
        "side",
        "actual_entry_price",
        "actual_exit_price",
        "filled_qty",
        "open_fee",
        "close_fee",
        "realized_demo_pnl",
        "pnl_provenance",
        "ledger_final_state",
    )
    missing = [key for key in required if source.get(key) in (None, "")]
    if missing:
        raise ValueError(f"run8_learning_input_missing:{','.join(missing)}")
    if _text(source.get("ledger_final_state")).upper() != "CLOSED":
        raise ValueError("run8_learning_input_ledger_not_closed")
    if _text(source.get("pnl_provenance")) != PNL_PROVENANCE:
        raise ValueError("run8_learning_input_pnl_not_exchange_grounded")
    if int(source.get("create_order_calls") or 0) != 0:
        raise ValueError("run8_learning_input_exchange_write_not_zero")
    if int(source.get("exchange_write_call_count") or 0) != 0:
        raise ValueError("run8_learning_input_exchange_write_not_zero")
    if not allow_test_fixture:
        from backend.nexus_demo_execution.p2_run8_durable_loader import reject_placeholder_ids

        reject_placeholder_ids(source)
    source.setdefault("candidate_count", 1)
    return source


def reflect_run8(case: dict[str, Any]) -> dict[str, Any]:
    entry = _dec(case["actual_entry_price"])
    exit_px = _dec(case["actual_exit_price"])
    qty = _dec(case["filled_qty"])
    fees = _dec(case["open_fee"]) + _dec(case["close_fee"])
    realized = _dec(case["realized_demo_pnl"])
    side = _text(case.get("side")).lower()
    signed_move = exit_px - entry
    if side in {"sell", "short"}:
        signed_move = entry - exit_px
    gross = signed_move * qty
    outcome_quality = "BAD_NET_PNL" if realized < 0 else "NON_NEGATIVE_NET_PNL"
    if signed_move == 0:
        price_path = "UNCHANGED"
    elif gross < 0:
        price_path = "ADVERSE"
    else:
        price_path = "FAVORABLE"
    from backend.nexus_demo_execution.p2_run8_durable_loader import derive_process_gates

    assessment = case.get("process_assessment") or derive_process_gates(case)
    process_valid = bool(assessment.get("process_valid"))
    if not process_valid:
        decision_quality = "PROCESS_NOT_PROVEN"
        distinction = "PROCESS_GATES_INCOMPLETE_OR_FAILED"
    elif price_path == "UNCHANGED" and fees > 0 and realized < 0:
        decision_quality = "VALID_PROCESS_INSUFFICIENT_EDGE_VS_COST"
        distinction = "BAD_OUTCOME_FROM_FEE_DRAG_NOT_DIRECTIONAL_ERROR"
    elif price_path == "ADVERSE" and abs(gross) > fees:
        decision_quality = "UNDETERMINED_OR_DIRECTIONAL_PRESSURE"
        distinction = "ADVERSE_PRICE_PATH_MAY_BE_RANDOM_OR_BAD_DIRECTION"
    else:
        decision_quality = "VALID_PROCESS_MIXED_COST_AND_PATH"
        distinction = "SEPARATE_PROCESS_QUALITY_FROM_PNL"
    return {
        "outcome_quality": outcome_quality,
        "decision_quality": decision_quality,
        "distinction": distinction,
        "price_path": price_path,
        "gross_pnl": format(gross, "f"),
        "fee_total": format(fees, "f"),
        "realized_demo_pnl": format(realized, "f"),
        "process_valid": process_valid,
        "process_valid_hardcoded": False,
        "process_gates": assessment.get("gates"),
        "pnl_is_not_process": True,
        "exchange_grounded": True,
    }


def classify_mistakes(case: dict[str, Any], reflection: dict[str, Any]) -> dict[str, Any]:
    del case
    fees = _dec(reflection["fee_total"])
    realized = _dec(reflection["realized_demo_pnl"])
    gross = _dec(reflection["gross_pnl"])
    labels: list[str] = []
    if fees > 0 and realized < 0 and abs(gross) <= fees:
        labels.append("FEE_DRAG")
    if reflection.get("process_valid") and reflection["price_path"] == "UNCHANGED" and realized < 0:
        labels.append("VALID_DECISION_BAD_OUTCOME")
    if reflection["price_path"] == "ADVERSE" and abs(gross) > fees:
        labels.append("DIRECTION")
    if not labels:
        labels.append("NO_MISTAKE")
    return {
        "taxonomy": list(MISTAKE_TAXONOMY),
        "labels": labels,
        "primary_mistake": labels[0],
        "direction_error": "DIRECTION" in labels,
        "fee_drag": "FEE_DRAG" in labels,
        "valid_decision_bad_outcome": "VALID_DECISION_BAD_OUTCOME" in labels,
        "one_loss_is_not_policy": True,
    }


def research_counterfactuals(case: dict[str, Any], reflection: dict[str, Any]) -> list[dict[str, Any]]:
    del case
    fees = _dec(reflection["fee_total"])
    realized = _dec(reflection["realized_demo_pnl"])
    skip_pnl = Decimal("0")
    threshold = fees * Decimal("2")
    return [
        {
            "kind": "SKIP",
            "research_only": True,
            "live_trade_generated": False,
            "hypothetical_net_pnl": format(skip_pnl, "f"),
            "delta_vs_actual": format(skip_pnl - realized, "f"),
            "note": "Skipping the round-trip avoids fee-only loss.",
        },
        {
            "kind": "delayed_entry",
            "research_only": True,
            "live_trade_generated": False,
            "hypothetical_net_pnl": None,
            "note": "No durable intra-bar path is available; delayed-entry PnL is not invented.",
        },
        {
            "kind": "alternative_threshold",
            "research_only": True,
            "live_trade_generated": False,
            "required_expected_gross": format(threshold, "f"),
            "note": "Require expected gross edge > 2x round-trip fees before similar entries.",
        },
        {
            "kind": "reduced_confidence_or_size",
            "research_only": True,
            "live_trade_generated": False,
            "note": "Smaller size still fee-dominated if expected move is ~0; SKIP dominates.",
        },
    ]


def _lesson_id(case: dict[str, Any], primary_mistake: str) -> str:
    raw = "|".join(
        [
            _text(case.get("trade_id")),
            _text(case.get("decision_id")),
            _text(case.get("run8_evidence_identity")),
            primary_mistake,
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"LC_run8_{primary_mistake}_{digest}"


def build_lesson_candidate(
    case: dict[str, Any],
    reflection: dict[str, Any],
    mistakes: dict[str, Any],
    counterfactuals: list[dict[str, Any]],
) -> dict[str, Any]:
    lesson_id = _lesson_id(case, mistakes["primary_mistake"])
    return {
        "lesson_id": lesson_id,
        "status": LESSON_STATUS_CANDIDATE,
        "policy_truth": False,
        "active": False,
        "campaign_id": P2_CAMPAIGN_ID,
        "trade_id": case["trade_id"],
        "decision_id": case["decision_id"],
        "run8_evidence_identity": case["run8_evidence_identity"],
        "symbol": case["symbol"],
        "side": case["side"],
        "primary_mistake": mistakes["primary_mistake"],
        "labels": list(mistakes["labels"]),
        "rule": (
            "If expected gross edge <= round-trip fees on a similar BTCUSDT "
            "qualification-style entry, skip or demand a larger expected move."
        ),
        "forbidden_mutations": list(PROTECTED_POLICY_FIELDS),
        "evidence_strength": "SINGLE_EXCHANGE_GROUNDED_CASE",
        "support_count": 1,
        "min_support_for_policy": MIN_SUPPORT_FOR_POLICY,
        "confidence": 0.34,
        "revalidation_required": True,
        "ttl_trades": LESSON_TTL_TRADES,
        "expires_after_trades": LESSON_TTL_TRADES,
        "reflection": reflection,
        "counterfactuals": counterfactuals,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
    }


def _context_key(symbol: str, side: str) -> str:
    return f"{_text(symbol).upper()}|{_text(side).upper()}"


def fee_dominated_context(candidate: dict[str, Any]) -> bool:
    expected = candidate.get("expected_gross_pnl")
    fees = candidate.get("round_trip_fee_estimate")
    if expected in (None, "", "UNKNOWN") or fees in (None, "", "UNKNOWN"):
        return False
    fee_value = _dec(fees)
    return fee_value > 0 and _dec(expected) <= fee_value


def _fee_drag_lesson_matches(candidate: dict[str, Any], row: dict[str, Any]) -> bool:
    lesson = row.get("payload") or row
    primary = row.get("primary_mistake") or lesson.get("primary_mistake")
    if primary != "FEE_DRAG" or not fee_dominated_context(candidate):
        return False
    lesson_symbol = _text(row.get("symbol") or lesson.get("symbol"))
    candidate_symbol = _text(candidate.get("symbol"))
    if lesson_symbol and candidate_symbol and lesson_symbol.upper() != candidate_symbol.upper():
        return False
    return True


class DecisionMemory:
    """Queryable research memory. Does not write exchange or live policy."""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def remember(self, lesson: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
        row = {
            "memory_id": f"DM_{lesson['lesson_id']}",
            "campaign_id": P2_CAMPAIGN_ID,
            "decision_id": case["decision_id"],
            "trade_id": case["trade_id"],
            "run8_evidence_identity": case["run8_evidence_identity"],
            "symbol": case["symbol"],
            "side": case["side"],
            "primary_mistake": lesson["primary_mistake"],
            "lesson_id": lesson["lesson_id"],
            "context_key": _context_key(str(case["symbol"]), str(case["side"])),
            "payload": lesson,
        }
        self._rows.append(row)
        return row

    def query(self, *, symbol: str, side: str) -> list[dict[str, Any]]:
        key = _context_key(symbol, side)
        return [dict(row) for row in self._rows if row.get("context_key") == key]

    def query_context(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows if _fee_drag_lesson_matches(candidate, row)]


class RepeatMistakeGuard:
    """Research guard: change similar-candidate behavior without mutating hard policy."""

    def __init__(self, memory: DecisionMemory) -> None:
        self.memory = memory

    def evaluate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        if hasattr(self.memory, "query_context"):
            matches = self.memory.query_context(candidate)
        else:
            matches = self.memory.query(symbol=str(candidate.get("symbol") or ""), side=str(candidate.get("side") or ""))
        expected_gross = _dec(candidate.get("expected_gross_pnl") or 0)
        fee_estimate = _dec(candidate.get("round_trip_fee_estimate") or 0)
        confidence = float(candidate.get("confidence") or 0.0)
        if not matches:
            return {
                "decision_before_learning": "ALLOW",
                "decision_after_learning": "ALLOW",
                "confidence_before": confidence,
                "confidence_after": confidence,
                "guard_before": "NONE",
                "guard_after": "NONE",
                "reason_for_change": "no_matching_lesson",
                "lesson_id": None,
                "policy_mutated": False,
            }
        lesson = matches[0]["payload"]
        after_confidence = round(max(0.05, confidence * 0.45), 4)
        fee_dominated = fee_estimate > 0 and expected_gross <= fee_estimate
        if lesson.get("primary_mistake") == "FEE_DRAG" and fee_dominated:
            after_decision = "SKIP"
            after_guard = "REPEAT_FEE_DRAG"
            reason = "similar_candidate_expected_edge_not_above_round_trip_fees"
        else:
            after_decision = "ALLOW_WITH_PENALTY"
            after_guard = "SIMILAR_CASE_PENALTY"
            reason = "similar_context_lesson_present_but_not_fee_dominated"
        return {
            "decision_before_learning": "ALLOW",
            "decision_after_learning": after_decision,
            "confidence_before": confidence,
            "confidence_after": after_confidence,
            "guard_before": "NONE",
            "guard_after": after_guard,
            "reason_for_change": reason,
            "lesson_id": lesson.get("lesson_id"),
            "policy_mutated": False,
            "hard_leverage_unchanged": FIXED_LEVERAGE,
            "hard_risk_cap_unchanged": MARGIN_PER_TRADE_CAP,
        }


def _assert_safety_untouched(*, leverage_before: int, cap_before: float) -> None:
    if FIXED_LEVERAGE != leverage_before:
        raise RuntimeError("hard_leverage_mutated")
    if float(MARGIN_PER_TRADE_CAP) != float(cap_before):
        raise RuntimeError("hard_risk_cap_mutated")
    for key, value in DISARMED_FLAGS.items():
        if (os.environ.get(key) or "").strip().lower() != value:
            raise RuntimeError(f"safety_flag_mutated:{key}")


def close_run8_learning(
    payload: dict[str, Any] | None = None,
    *,
    similar_candidate: dict[str, Any] | None = None,
    write_artifact: Callable[[Path, dict[str, Any]], bool] | None = None,
    allow_test_fixture: bool = False,
) -> dict[str, Any]:
    apply_disarmed_flags()
    os.environ["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = ARM_READY_HOLD
    leverage_before = FIXED_LEVERAGE
    cap_before = float(MARGIN_PER_TRADE_CAP)
    case = load_run8_learning_input(payload, allow_test_fixture=allow_test_fixture)
    reflection = reflect_run8(case)
    mistakes = classify_mistakes(case, reflection)
    counterfactuals = research_counterfactuals(case, reflection)
    if any(item.get("live_trade_generated") for item in counterfactuals):
        raise RuntimeError("counterfactual_live_trade_forbidden")
    lesson = build_lesson_candidate(case, reflection, mistakes, counterfactuals)
    memory = DecisionMemory()
    memory.remember(lesson, case)
    guard = RepeatMistakeGuard(memory)
    candidate = similar_candidate or {
        "symbol": case["symbol"],
        "side": case["side"],
        "qty": case["filled_qty"],
        "expected_gross_pnl": "0",
        "round_trip_fee_estimate": str(_dec(case["open_fee"]) + _dec(case["close_fee"])),
        "confidence": 0.62,
    }
    behavior = guard.evaluate(candidate)
    _assert_safety_untouched(leverage_before=leverage_before, cap_before=cap_before)
    evidence = {
        "P2_RUN8_LEARNING_CLOSURE": "COMPLETE",
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "run8_certified_learning_input_ready": True,
        "trade_id": case["trade_id"],
        "decision_id": case["decision_id"],
        "run8_evidence_identity": case["run8_evidence_identity"],
        "reflection": reflection,
        "mistakes": mistakes,
        "counterfactuals": counterfactuals,
        "lesson_candidate": lesson,
        "decision_memory_queryable": True,
        "decision_memory_hits": memory.query(symbol=str(case["symbol"]), side=str(case["side"])),
        "repeat_mistake_guard": behavior,
        "decision_before_learning": behavior["decision_before_learning"],
        "decision_after_learning": behavior["decision_after_learning"],
        "confidence_before": behavior["confidence_before"],
        "confidence_after": behavior["confidence_after"],
        "guard_before": behavior["guard_before"],
        "guard_after": behavior["guard_after"],
        "reason_for_change": behavior["reason_for_change"],
        "lesson_id": lesson["lesson_id"],
        "behavior_change_demonstrated": (
            behavior["decision_before_learning"] != behavior["decision_after_learning"]
        ),
        "lesson_is_not_policy_truth": lesson["policy_truth"] is False,
        "protected_policy_fields": list(PROTECTED_POLICY_FIELDS),
        "hard_leverage": FIXED_LEVERAGE,
        "hard_risk_cap": MARGIN_PER_TRADE_CAP,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact = Path("artifacts") / "bybit_demo_p1" / "p2_run8_learning_closure.json"
    if write_artifact is not None:
        write_artifact(artifact, evidence)
    else:
        try:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
    return evidence


class DurableDecisionMemory:
    """PostgreSQL/SQLite-backed research memory. Empty RAM still sees prior lessons."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def remember(self, lesson: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
        record = {
            "lesson_id": lesson["lesson_id"],
            "source_trade_id": case["trade_id"],
            "source_decision_id": case["decision_id"],
            "source_evidence_hash": case.get("source_evidence_hash") or case.get("run8_evidence_identity"),
            "campaign_id": case.get("campaign_id") or P2_CAMPAIGN_ID,
            "symbol": case["symbol"],
            "side": case["side"],
            "mistake_labels": lesson.get("labels") or lesson.get("mistake_labels") or [],
            "primary_mistake": lesson["primary_mistake"],
            "lesson_rule": lesson.get("rule") or lesson.get("lesson_rule"),
            "support_count": int(lesson.get("support_count") or 1),
            "confidence": lesson.get("confidence"),
            "status": lesson.get("status") or LESSON_STATUS_CANDIDATE,
            "policy_truth": False,
            "revalidation_required": True,
            "ttl_trades": lesson.get("ttl_trades"),
            "payload": {**lesson, "trade_id": case["trade_id"], "decision_id": case["decision_id"]},
        }
        stored = self.store.upsert_lesson(record)
        return stored

    def query_context(self, candidate: dict[str, Any]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for row in self.store.list_lessons():
            if _fee_drag_lesson_matches(candidate, row):
                payload = row.get("payload") or row
                hits.append({"payload": payload, **row})
        return hits

    def query(self, *, symbol: str, side: str) -> list[dict[str, Any]]:
        del symbol, side
        return []


def close_run8_durable_learning(
    *,
    store: Any,
    intents: list[dict[str, Any]] | None = None,
    ledger: Any | None = None,
    market_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from backend.nexus_demo_execution.p2_research_decision_path import research_decision_path
    from backend.nexus_demo_execution.p2_run8_durable_loader import load_run8_from_intents, load_run8_from_ledger

    apply_disarmed_flags()
    os.environ["AUTONOMOUS_BYBIT_DEMO_ARM_READY"] = ARM_READY_HOLD
    leverage_before = FIXED_LEVERAGE
    cap_before = float(MARGIN_PER_TRADE_CAP)
    if intents is not None:
        case = load_run8_from_intents(intents)
    else:
        case = load_run8_from_ledger(ledger)
    reflection = reflect_run8(case)
    mistakes = classify_mistakes(case, reflection)
    counterfactuals = research_counterfactuals(case, reflection)
    lesson = build_lesson_candidate(case, reflection, mistakes, counterfactuals)
    lesson["lesson_id"] = f"LC_{case['source_evidence_hash'][:24]}"
    lesson["source_trade_id"] = case["trade_id"]
    lesson["source_decision_id"] = case["decision_id"]
    lesson["source_evidence_hash"] = case["source_evidence_hash"]
    lesson["policy_truth"] = False
    memory = DurableDecisionMemory(store)
    memory.remember(lesson, case)
    candidate = market_input or {
        "symbol": case["symbol"],
        "side": case["side"],
        "lesson_type": "FEE_DRAG",
        "expected_gross_pnl": "0",
        "round_trip_fee_estimate": str(_dec(case["open_fee"]) + _dec(case["close_fee"])),
        "confidence": 0.62,
        "signal_family": "UNKNOWN",
        "market_regime": "UNKNOWN",
        "horizon": "UNKNOWN",
    }
    empty = DurableDecisionMemory(type("Empty", (), {"list_lessons": staticmethod(lambda: []), "upsert_lesson": staticmethod(lambda row: row)})())
    before = research_decision_path(candidate, memory=empty)
    after = research_decision_path(candidate, memory=memory)
    _assert_safety_untouched(leverage_before=leverage_before, cap_before=cap_before)
    return {
        "P2_1_DURABLE_LEARNING_CLOSURE": "COMPLETE",
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": ARM_READY_HOLD,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "trade_id": case["trade_id"],
        "decision_id": case["decision_id"],
        "order_intent_id": case["order_intent_id"],
        "entry_order_id": case["entry_order_id"],
        "close_order_id": case["close_order_id"],
        "source_evidence_hash": case["source_evidence_hash"],
        "filled_qty_source": case.get("filled_qty_source"),
        "original_decision_context": case["original_decision_context"],
        "process_assessment": case["process_assessment"],
        "process_validation_status": case["process_assessment"].get("process_validation_status"),
        "reflection": reflection,
        "mistakes": mistakes,
        "counterfactuals": counterfactuals,
        "lesson_candidate": lesson,
        "lesson_id": lesson["lesson_id"],
        "policy_truth": False,
        "support_count": 1,
        "decision_before_learning": before["guard"]["decision_before_learning"],
        "decision_after_learning": after["guard"]["decision_after_learning"],
        "confidence_before": before["guard"]["confidence_before"],
        "confidence_after": after["guard"]["confidence_after"],
        "guard_before": before["guard"]["guard_before"],
        "guard_after": after["guard"]["guard_after"],
        "reason_for_change": after["guard"]["reason_for_change"],
        "research_recommendation_before": before["research_recommendation"],
        "research_recommendation_after": after["research_recommendation"],
        "live_execution_veto": False,
        "behavior_change_demonstrated": before["research_recommendation"] != after["research_recommendation"],
        "hard_leverage": FIXED_LEVERAGE,
        "hard_risk_cap": MARGIN_PER_TRADE_CAP,
    }

