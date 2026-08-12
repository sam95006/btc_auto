"""Sample-size requirement gates (development research only)."""
from __future__ import annotations

from typing import Any

from backend.nexus_research_validation.constants import (
    MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE,
    MIN_SAMPLE_OBSERVATIONS,
    MIN_SAMPLE_TRADES,
)


def sample_size_requirements(
    *,
    n_observations: int,
    n_trades: int,
    n_eff: float,
) -> dict[str, Any]:
    obs_ok = int(n_observations) >= MIN_SAMPLE_OBSERVATIONS
    trades_ok = int(n_trades) >= MIN_SAMPLE_TRADES
    eff_ok = float(n_eff) >= MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE
    sufficient = obs_ok and trades_ok and eff_ok
    blockers: list[str] = []
    if not obs_ok:
        blockers.append("OBSERVATIONS_BELOW_MIN")
    if not trades_ok:
        blockers.append("TRADES_BELOW_MIN")
    if not eff_ok:
        blockers.append("EFFECTIVE_SAMPLE_BELOW_MIN")
    return {
        "n_observations": int(n_observations),
        "n_trades": int(n_trades),
        "n_eff": float(n_eff),
        "min_observations": MIN_SAMPLE_OBSERVATIONS,
        "min_trades": MIN_SAMPLE_TRADES,
        "min_n_eff": MIN_EFFECTIVE_SAMPLE_AFTER_DEPENDENCE,
        "observations_ok": obs_ok,
        "trades_ok": trades_ok,
        "n_eff_ok": eff_ok,
        "sufficient": sufficient,
        "blockers": blockers,
        "development_only": True,
        "not_qualification_claim": True,
    }
