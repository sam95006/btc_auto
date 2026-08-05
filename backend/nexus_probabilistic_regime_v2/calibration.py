"""Calibration interface for regime probabilities (bindable, non-mutating)."""
from __future__ import annotations

from typing import Any, Mapping

from backend.nexus_probabilistic_regime_v2.constants import (
    CALIBRATION_INTERFACE_VERSION,
    OUTPUT_KEYS,
)


def identity_calibrate(probs: Mapping[str, float]) -> dict[str, float]:
    """Default calibration: clamp to [0,1], no remapping."""
    out: dict[str, float] = {}
    for k in OUTPUT_KEYS:
        if k not in probs:
            continue
        v = float(probs[k])
        out[k] = max(0.0, min(1.0, v))
    return out


def calibration_contract() -> dict[str, Any]:
    """Public calibration interface consumers can version-pin."""
    return {
        "interface_version": CALIBRATION_INTERFACE_VERSION,
        "required_keys": list(OUTPUT_KEYS),
        "range": [0.0, 1.0],
        "default_calibrator": "identity_calibrate",
        "notes": (
            "Calibration remaps descriptive probabilities only; "
            "it must not invent predictive edge or mutate risk/leverage."
        ),
        "mutates_risk_or_leverage": False,
        "predictive_edge_claimed": False,
    }


def apply_calibration(
    probs: Mapping[str, float],
    *,
    calibrator: str = "identity",
) -> dict[str, Any]:
    if calibrator != "identity":
        # Unknown calibrators fail-closed to zeros rather than inventing maps.
        return {
            "calibrator": calibrator,
            "accepted": False,
            "reason": "UNKNOWN_CALIBRATOR_FAIL_CLOSED",
            "probabilities": {k: 0.0 for k in OUTPUT_KEYS},
            "interface": calibration_contract(),
        }
    calibrated = identity_calibrate(probs)
    # Ensure all keys present after calibration.
    for k in OUTPUT_KEYS:
        calibrated.setdefault(k, 0.0)
    return {
        "calibrator": "identity",
        "accepted": True,
        "reason": "OK",
        "probabilities": calibrated,
        "interface": calibration_contract(),
    }
