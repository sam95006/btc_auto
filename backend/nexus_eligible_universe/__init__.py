"""V18-C Live Eligible Universe Engine.

Dynamic Eligible Universe from public instrument catalog with fail-closed
gates. UNKNOWN / missing measurements never default to ELIGIBLE.
"""
from __future__ import annotations

from backend.nexus_eligible_universe.engine import (
    classify_instrument,
    compute_funnel,
    evaluate_universe,
)
from backend.nexus_eligible_universe.fixtures import fixture_instruments
from backend.nexus_eligible_universe.hard_bans import hard_ban_probe_matrix

__all__ = [
    "classify_instrument",
    "compute_funnel",
    "evaluate_universe",
    "fixture_instruments",
    "hard_ban_probe_matrix",
]
