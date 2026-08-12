"""V18.2.29 entry quality diagnostics — deterministic classification from lifecycle evidence.

If a field is missing, output null + not_available_reason (no backfilled proxies).
"""

from __future__ import annotations

from typing import Any


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def audit_entry_quality_v29(
    *,
    lifecycle: dict[str, Any] | None,
    direction_ambiguity_supported: bool,
) -> dict[str, Any]:
    if not isinstance(lifecycle, dict) or not lifecycle:
        return {
            "entry_quality_enabled": True,
            "entry_quality_pass": None,
            "last_entry_quality": None,
            "last_entry_class": None,
            "spread": None,
            "slippage": None,
            "noise_band": None,
            "stop_distance_pct": None,
            "fee_to_target_ratio": None,
            "fee_to_stop_ratio": None,
            "not_available_reason": {"lifecycle": "no_completed_lifecycle"},
        }

    process_evidence = lifecycle.get("process_evidence") or {}
    risk_gate = process_evidence.get("risk_gate_results") or {}
    cost_gate = process_evidence.get("cost_gate_results") or {}
    data_quality = process_evidence.get("data_quality_results") or {}

    entry_rule_compliance = process_evidence.get("entry_rule_compliance")
    exit_rule_compliance = process_evidence.get("exit_rule_compliance")

    total_fees = _num((lifecycle.get("exact_pnl_accounting") or {}).get("total_fees"))

    expected_net_target_usdt = _num(lifecycle.get("expected_net_target_usdt"))
    if expected_net_target_usdt is None and isinstance(lifecycle.get("market_candidate"), dict):
        expected_net_target_usdt = _num(lifecycle["market_candidate"].get("expected_net_target_usdt"))

    fee_to_target_ratio = None
    if total_fees is not None and expected_net_target_usdt is not None and expected_net_target_usdt != 0:
        fee_to_target_ratio = total_fees / abs(expected_net_target_usdt)

    not_available_reason: dict[str, Any] = {}

    if direction_ambiguity_supported:
        entry_class = "AMBIGUOUS_DIRECTION"
    elif entry_rule_compliance != "PASS":
        entry_class = "OTHER"
    elif data_quality.get("status") != "PASS":
        entry_class = "OTHER"
    elif risk_gate.get("status") == "FAIL" or cost_gate.get("status") == "FAIL":
        entry_class = "COST_HEAVY" if cost_gate.get("status") == "FAIL" else "OTHER"
    else:
        entry_class = "CLEAR_ENTRY"

    not_available_reason["spread_bps"] = "spread_bps not present in lifecycle evidence"
    not_available_reason["slippage"] = (
        "slippage not present in lifecycle evidence "
        "(use process_evidence.slippage_pct only if available)"
    )
    not_available_reason["noise_band"] = (
        "microstructure noise band not present in lifecycle evidence"
    )

    stop_distance_pct = lifecycle.get("stop_distance_pct")
    fee_to_stop_ratio = None
    stop_pct = _num(stop_distance_pct)
    notional = _num(
        lifecycle.get("notional_usdt")
        or (lifecycle.get("prepared_decision_horizon") or {}).get("notional_usdt")
        or (lifecycle.get("exact_pnl_accounting") or {}).get("notional_usdt")
    )
    if total_fees is not None and stop_pct is not None and notional is not None and stop_pct > 0:
        stop_usdt = notional * stop_pct / 100.0
        if stop_usdt > 0:
            fee_to_stop_ratio = abs(total_fees) / abs(stop_usdt)
    else:
        not_available_reason["fee_to_stop_ratio"] = (
            "incomplete stop/notional/fees for fee_to_stop_ratio"
        )

    if fee_to_target_ratio is None:
        not_available_reason["fee_to_target_ratio"] = (
            "expected_net_target_usdt or total_fees not available"
        )

    return {
        "entry_quality_enabled": True,
        "entry_quality_pass": entry_class in {"CLEAR_ENTRY"},
        "last_entry_quality": {
            "class": entry_class,
            "entry_rule_compliance": entry_rule_compliance,
            "exit_rule_compliance": exit_rule_compliance,
        },
        "last_entry_class": entry_class,
        "spread": None,
        "slippage": None,
        "noise_band": None,
        "stop_distance_pct": stop_distance_pct,
        "fee_to_target_ratio": fee_to_target_ratio,
        "fee_to_stop_ratio": fee_to_stop_ratio,
        "not_available_reason": not_available_reason,
    }
