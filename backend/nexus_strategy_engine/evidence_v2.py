"""NEXUS_DECISION_OUTCOME_EVIDENCE_V2 + deterministic process baseline."""
from __future__ import annotations

from typing import Any

from backend.nexus_strategy_engine.constants import (
    DETERMINISTIC_PROCESS,
    EVIDENCE_SCHEMA_VERSION,
    MISSING,
    UNKNOWN,
    UNAVAILABLE,
)

DECISION_FIELDS = (
    "trade_id",
    "candidate_id",
    "hypothesis_id",
    "strategy_family",
    "strategy_version",
    "symbol",
    "symbol_profile",
    "timestamp",
    "direction",
    "market_regime",
    "regime_confidence",
    "timeframe_context",
    "universe_snapshot_id",
    "instrument_snapshot_id",
    "data_snapshot_checksum",
    "feature_snapshot_checksum",
    "entry_event",
    "entry_confirmation",
    "entry_rejection_reasons",
    "entry_price",
    "entry_delay_bars",
    "entry_distance_from_event",
    "entry_distance_from_structure",
    "stop_price",
    "stop_basis",
    "stop_distance",
    "target_price",
    "target_basis",
    "target_distance",
    "expected_reward_to_risk",
    "spread_bps",
    "estimated_slippage_bps",
    "entry_fee_estimate",
    "exit_fee_estimate",
    "funding_estimate",
    "expected_total_cost",
    "gross_movement_to_cost_ratio",
    "volume_context",
    "turnover_context",
    "open_interest_context",
    "funding_context",
    "mark_index_basis_context",
    "relative_strength_context",
    "volatility_context",
    "liquidity_context",
    "data_quality_status",
    "cost_gate_status",
    "risk_gate_status",
    "hard_block_reasons",
    "AI_reasoning_reference",
    "retrieved_lesson_ids",
    "applied_lesson_ids",
)

OUTCOME_FIELDS = (
    "actual_entry_price",
    "actual_exit_price",
    "exit_reason",
    "holding_bars",
    "gross_pnl",
    "fees",
    "slippage",
    "funding",
    "net_pnl",
    "MFE",
    "MAE",
    "MFE_before_MAE",
    "MAE_before_MFE",
    "realized_reward_to_risk",
    "stop_touched",
    "target_touched",
    "same_bar_ambiguity",
    "adverse_first_applied",
    "rule_violation_count",
    "prohibited_action_count",
    "data_stale_during_trade",
    "regime_changed_during_trade",
    "liquidity_deterioration",
    "cost_estimation_error",
    "position_size_valid",
    "liquidation_distance_valid",
)


def evidence_v2_schema() -> dict[str, Any]:
    return {
        "schema": EVIDENCE_SCHEMA_VERSION,
        "decision_fields": list(DECISION_FIELDS),
        "outcome_fields": list(OUTCOME_FIELDS),
        "missing_tokens": [MISSING, UNKNOWN, UNAVAILABLE],
        "fabrication_forbidden": True,
    }


def empty_evidence_shell(**overrides: Any) -> dict[str, Any]:
    packet: dict[str, Any] = {k: UNKNOWN for k in DECISION_FIELDS}
    packet.update({k: UNKNOWN for k in OUTCOME_FIELDS})
    packet["schema"] = EVIDENCE_SCHEMA_VERSION
    packet["entry_rejection_reasons"] = []
    packet["hard_block_reasons"] = []
    packet["retrieved_lesson_ids"] = []
    packet["applied_lesson_ids"] = []
    packet["rule_violation_count"] = 0
    packet["prohibited_action_count"] = 0
    packet.update(overrides)
    return packet


def completeness_ratio(packet: dict[str, Any]) -> float:
    fields = list(DECISION_FIELDS) + list(OUTCOME_FIELDS)
    known = 0
    for f in fields:
        v = packet.get(f)
        if v in (None, "", MISSING, UNKNOWN, UNAVAILABLE):
            continue
        if isinstance(v, list) and not v and f.endswith("_reasons"):
            known += 1
            continue
        known += 1
    return known / max(len(fields), 1)


def deterministic_process_baseline(packet: dict[str, Any]) -> dict[str, Any]:
    """Baseline before AI — loss/win alone never decide compliance."""
    hard = list(packet.get("hard_block_reasons") or [])
    violations = int(packet.get("rule_violation_count") or 0)
    prohibited = int(packet.get("prohibited_action_count") or 0)
    cost = str(packet.get("cost_gate_status") or UNKNOWN)
    risk = str(packet.get("risk_gate_status") or UNKNOWN)
    data_q = str(packet.get("data_quality_status") or UNKNOWN)
    stop = packet.get("stop_price")
    size_ok = packet.get("position_size_valid")
    liq_ok = packet.get("liquidation_distance_valid")

    noncompliant_reasons: list[str] = []
    if hard:
        noncompliant_reasons.append("hard_gate_present")
    if cost in {"FAIL", "BLOCK", "FAILED"}:
        noncompliant_reasons.append("cost_gate_failed")
    if risk in {"FAIL", "BLOCK", "FAILED", "EXCEEDED"}:
        noncompliant_reasons.append("risk_exceeded")
    if data_q in {"STALE", "INVALID"}:
        noncompliant_reasons.append("stale_or_invalid_data")
    if stop in (None, MISSING, 0, 0.0):
        noncompliant_reasons.append("invalid_or_absent_stop")
    elif stop == UNAVAILABLE:
        noncompliant_reasons.append("invalid_or_absent_stop")
    # UNKNOWN stop contributes to insufficiency, not automatic noncompliance
    if size_ok is False:
        noncompliant_reasons.append("invalid_position_size")
    if liq_ok is False:
        noncompliant_reasons.append("liquidation_distance_invalid")
    if violations > 0:
        noncompliant_reasons.append("rule_violation")
    if prohibited > 0:
        noncompliant_reasons.append("prohibited_action")
    if packet.get("control_fixture_label") == "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE":
        pass

    critical_known = all(
        packet.get(k) not in (None, "", UNKNOWN, MISSING, UNAVAILABLE)
        for k in ("entry_price", "stop_price", "target_price", "cost_gate_status", "data_quality_status")
    )

    if noncompliant_reasons:
        status = "PROCESS_NONCOMPLIANT"
    elif not critical_known:
        status = "PROCESS_EVIDENCE_INSUFFICIENT"
    else:
        status = "PROCESS_COMPLIANT"

    assert status in DETERMINISTIC_PROCESS
    return {
        "deterministic_process_status": status,
        "noncompliant_reasons": noncompliant_reasons,
        "pnl_does_not_decide_process": True,
        "evidence_completeness_ratio": completeness_ratio(packet),
    }


def build_evidence_from_sim_row(
    *,
    row: dict[str, Any],
    hypothesis: dict[str, Any],
    trade_id: str,
    candidate_id: str,
    universe_snapshot_id: str,
    data_checksum: str,
    intentional_violation: str | None = None,
) -> dict[str, Any]:
    hyp_id = hypothesis.get("strategy_id") or hypothesis.get("hypothesis_id")
    packet = empty_evidence_shell(
        trade_id=trade_id,
        candidate_id=candidate_id,
        hypothesis_id=hyp_id,
        strategy_family=hypothesis.get("strategy_family"),
        strategy_version=hypothesis.get("strategy_version", "v1"),
        symbol=row.get("symbol"),
        symbol_profile=row.get("symbol_profile") or UNKNOWN,
        timestamp=row.get("entry_ts") or UNKNOWN,
        direction=row.get("side") or UNKNOWN,
        market_regime=row.get("regime") or UNKNOWN,
        regime_confidence=row.get("regime_confidence", UNKNOWN),
        timeframe_context={"entry": "15m", "context": "60m"},
        universe_snapshot_id=universe_snapshot_id,
        instrument_snapshot_id=f"{row.get('symbol')}|linear",
        data_snapshot_checksum=data_checksum,
        feature_snapshot_checksum=UNKNOWN,
        entry_event=hypothesis.get("event_definition") or UNKNOWN,
        entry_confirmation=True,
        entry_price=row.get("entry_price"),
        entry_delay_bars=row.get("entry_delay_bars", 0),
        stop_price=row.get("stop"),
        stop_basis=hypothesis.get("stop_definition") or UNKNOWN,
        target_price=row.get("take_profit"),
        target_basis=hypothesis.get("target_definition") or UNKNOWN,
        spread_bps=row.get("spread_bps", UNKNOWN),
        estimated_slippage_bps=row.get("slippage_bps", UNKNOWN),
        entry_fee_estimate=row.get("fees"),
        expected_total_cost=(float(row.get("fees") or 0) + float(row.get("spread_cost") or 0) + float(row.get("slippage") or 0)),
        data_quality_status="OK" if row.get("entry_status") == "ENTRY_FILLED" else UNKNOWN,
        cost_gate_status="PASS" if not row.get("block_reason") else "FAIL",
        risk_gate_status="PASS",
        hard_block_reasons=[],
        actual_entry_price=row.get("entry_price"),
        actual_exit_price=row.get("exit_price", UNKNOWN),
        exit_reason=row.get("exit_status") or UNKNOWN,
        holding_bars=row.get("holding_bars", UNKNOWN),
        gross_pnl=row.get("gross_pnl"),
        fees=row.get("fees"),
        slippage=row.get("slippage"),
        funding=row.get("funding"),
        net_pnl=row.get("net_pnl"),
        MFE=row.get("mfe") or row.get("MFE") or UNKNOWN,
        MAE=row.get("mae") or row.get("MAE") or UNKNOWN,
        MFE_before_MAE=row.get("MFE_before_MAE", UNKNOWN),
        MAE_before_MFE=row.get("MAE_before_MFE", UNKNOWN),
        stop_touched=row.get("stop_touched", UNKNOWN),
        target_touched=row.get("target_touched", UNKNOWN),
        same_bar_ambiguity=row.get("same_bar_ambiguity", False),
        adverse_first_applied=True,
        position_size_valid=True,
        liquidation_distance_valid=True,
    )
    if intentional_violation:
        packet["control_fixture_label"] = "CONTROL_FIXTURE_NOT_MARKET_PERFORMANCE"
        if intentional_violation == "stale_data":
            packet["data_quality_status"] = "STALE"
        elif intentional_violation == "cost_gate":
            packet["cost_gate_status"] = "FAIL"
        elif intentional_violation == "missing_stop":
            packet["stop_price"] = MISSING
        elif intentional_violation == "hard_block":
            packet["hard_block_reasons"] = ["spread_above_limit"]
        elif intentional_violation == "invalid_size":
            packet["position_size_valid"] = False
        packet["rule_violation_count"] = 1
    return packet
