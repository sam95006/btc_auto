"""V18.2.29 stop-loss audit — deterministic diagnostics from lifecycle evidence.

Missing market microstructure fields must be null + not_available_reason.
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


def empty_stop_quality_block(*, reason: str = "no_completed_lifecycle") -> dict[str, Any]:
    """Always-present stop quality shape when no lifecycle is available."""
    return {
        "stop_quality": "NOT_EVALUATED",
        "stop_quality_enabled": True,
        "stop_distance_pct": None,
        "stop_distance_usdt": None,
        "ATR_multiple_or_equivalent": None,
        "structure_reference": None,
        "noise_band": None,
        "expected_noise_band": None,
        "expected_adverse_excursion": None,
        "estimated_loss_if_stop_net": None,
        "fee_to_target_ratio": None,
        "fee_to_stop_ratio": None,
        "fee_to_stop_loss_ratio": None,
        "side": None,
        "not_available_reason": {
            "lifecycle": reason,
            "noise_band": "microstructure noise band not present in lifecycle evidence",
            "fee_to_target_ratio": "expected_net_target_usdt or total_fees not available",
            "fee_to_stop_ratio": "stop_distance_usdt or total_fees not available",
        },
    }


def audit_stop_loss_quality(lifecycle: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(lifecycle, dict) or not lifecycle:
        return empty_stop_quality_block()

    pe = lifecycle.get("prepared_decision_horizon") or {}
    exact = lifecycle.get("exact_pnl_accounting") or {}
    path_exc = lifecycle.get("path_excursion") or {}
    not_available_reason: dict[str, Any] = {}

    side = str(lifecycle.get("side") or "").upper() or None
    stop_distance_pct = _num(lifecycle.get("stop_distance_pct") or pe.get("stop_move_pct"))
    notional_usdt = _num(
        lifecycle.get("notional_usdt") or pe.get("notional_usdt") or exact.get("notional_usdt")
    )
    total_fees = _num(exact.get("total_fees"))

    stop_distance_usdt = None
    if stop_distance_pct is not None and notional_usdt is not None:
        stop_distance_usdt = notional_usdt * stop_distance_pct / 100.0
    else:
        if stop_distance_pct is None:
            not_available_reason["stop_distance_pct"] = (
                "stop_distance_pct not present in lifecycle evidence"
            )
        if notional_usdt is None:
            not_available_reason["notional_usdt"] = (
                "notional_usdt not present in lifecycle evidence"
            )

    atr_pct = _num(
        pe.get("atr_pct")
        or (lifecycle.get("horizon_plan") or {}).get("atr_pct")
        or (pe.get("horizon_plan") or {}).get("atr_pct")
    )
    atr_multiple_or_equivalent = None
    if stop_distance_pct is not None and atr_pct is not None and atr_pct > 0:
        atr_multiple_or_equivalent = stop_distance_pct / atr_pct
    else:
        not_available_reason["ATR_multiple_or_equivalent"] = (
            "atr_pct not present in prepared_decision_horizon/horizon_plan"
        )

    mae_usdt = _num(path_exc.get("mae_usdt"))

    estimated_loss_at_stop_net = None
    fee_to_stop_ratio = None
    if stop_distance_usdt is not None and total_fees is not None:
        estimated_loss_at_stop_net = -abs(stop_distance_usdt) - abs(total_fees)
        if abs(stop_distance_usdt) > 0:
            fee_to_stop_ratio = abs(total_fees) / abs(stop_distance_usdt)
    else:
        not_available_reason["fee_to_stop_ratio"] = (
            "stop_distance_usdt or total_fees not available for fee_to_stop_ratio"
        )

    expected_net_target_usdt = _num(lifecycle.get("expected_net_target_usdt"))
    if expected_net_target_usdt is None:
        mc = lifecycle.get("market_candidate")
        if isinstance(mc, dict):
            expected_net_target_usdt = _num(mc.get("expected_net_target_usdt"))

    fee_to_target_ratio = None
    if total_fees is not None and expected_net_target_usdt is not None and expected_net_target_usdt != 0:
        fee_to_target_ratio = abs(total_fees) / abs(expected_net_target_usdt)
    else:
        not_available_reason["fee_to_target_ratio"] = (
            "expected_net_target_usdt or total_fees not available for fee_to_target_ratio"
        )

    # noise_band is never imputed from MAE — MAE is adverse excursion, not noise band.
    noise_band = None
    not_available_reason["noise_band"] = (
        "microstructure noise band not present in lifecycle evidence"
    )

    expected_adverse_excursion = mae_usdt
    if expected_adverse_excursion is None:
        not_available_reason["expected_adverse_excursion"] = (
            "path_excursion.mae_usdt not_available_in_evidence"
        )

    return {
        "stop_quality": "EVALUATED",
        "stop_quality_enabled": True,
        "stop_distance_pct": stop_distance_pct,
        "stop_distance_usdt": stop_distance_usdt,
        "ATR_multiple_or_equivalent": atr_multiple_or_equivalent,
        "structure_reference": None,
        "noise_band": noise_band,
        "expected_noise_band": noise_band,
        "expected_adverse_excursion": expected_adverse_excursion,
        "estimated_loss_if_stop_net": estimated_loss_at_stop_net,
        "fee_to_target_ratio": fee_to_target_ratio,
        "fee_to_stop_ratio": fee_to_stop_ratio,
        "fee_to_stop_loss_ratio": fee_to_stop_ratio,
        "side": side,
        "not_available_reason": not_available_reason,
    }
