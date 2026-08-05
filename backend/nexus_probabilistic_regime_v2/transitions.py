"""Transition probability estimator over dimension label histories."""
from __future__ import annotations

from typing import Any


def estimate_transition_probability(
    label_history: list[str],
    *,
    lookback: int = 8,
) -> dict[str, Any]:
    """Estimate recent flip rate as a transition probability proxy.

    Descriptive only — not a predictive regime-timing signal.
    """
    if not label_history:
        return {
            "regime_transition_probability": 0.0,
            "sample_size": 0,
            "flip_count": 0,
            "reason": "empty_history",
        }
    window = label_history[-lookback:]
    if len(window) < 2:
        return {
            "regime_transition_probability": 0.0,
            "sample_size": len(window),
            "flip_count": 0,
            "reason": "insufficient_history",
        }
    flips = sum(1 for i in range(1, len(window)) if window[i] != window[i - 1])
    # Normalize by possible flips.
    p = flips / float(len(window) - 1)
    return {
        "regime_transition_probability": round(max(0.0, min(1.0, p)), 6),
        "sample_size": len(window),
        "flip_count": flips,
        "window_labels": list(window),
        "reason": "ok",
        "predictive_edge_claimed": False,
    }
