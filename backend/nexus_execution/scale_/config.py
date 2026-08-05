"""Configurable scale targets with env overrides for CI smoke.

Defaults match Founder V10 Lane B full targets. Smoke mode shrinks counts
so unit tests and CI gates remain fast while preserving determinism.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_FUZZ_SCENARIOS = 100_000
DEFAULT_FUZZ_SEED = 20260805
DEFAULT_SESSION_SEED = 911_100

# Logical hours for accelerated Session scale.
DAY_30_HOURS = 30 * 24  # 720
DAY_90_HOURS = 90 * 24  # 2160

# Smoke defaults (CI / pytest).
SMOKE_FUZZ_SCENARIOS = 500
SMOKE_SESSION_CANDIDATE_COUNT = 48

ENV_SMOKE = "NEXUS_V10_SMOKE"
ENV_FUZZ = "NEXUS_V10_FUZZ_SCENARIOS"
ENV_SESSION_CANDIDATES = "NEXUS_V10_SESSION_CANDIDATES"
ENV_FUZZ_SEED = "NEXUS_V10_FUZZ_SEED"
ENV_SESSION_SEED = "NEXUS_V10_SESSION_SEED"


def _truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on", "smoke"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class ScaleConfig:
    """Resolved scale targets for one harness run."""

    fuzz_scenarios: int
    fuzz_seed: int
    session_seed: int
    session_candidate_count_30d: int
    session_candidate_count_90d: int
    smoke: bool
    day_30_hours: float = float(DAY_30_HOURS)
    day_90_hours: float = float(DAY_90_HOURS)

    @property
    def mode(self) -> str:
        return "SMOKE" if self.smoke else "FULL"


def _default_candidates_for_hours(logical_hours: float) -> int:
    """Dense enough for injection catalog coverage across the logical window."""
    # ~1 candidate / logical hour, floor at catalog coverage.
    from backend.nexus_execution.scale_.injections import SCALE_INJECTION_CATALOG

    return max(80, int(logical_hours) + len(SCALE_INJECTION_CATALOG) * 3)


def load_scale_config() -> ScaleConfig:
    """Load scale config from env. ``NEXUS_V10_SMOKE=1`` forces smoke targets."""
    smoke = _truthy(os.environ.get(ENV_SMOKE))
    if smoke:
        fuzz_default = SMOKE_FUZZ_SCENARIOS
        c30 = SMOKE_SESSION_CANDIDATE_COUNT
        c90 = SMOKE_SESSION_CANDIDATE_COUNT
    else:
        fuzz_default = DEFAULT_FUZZ_SCENARIOS
        c30 = _default_candidates_for_hours(DAY_30_HOURS)
        c90 = _default_candidates_for_hours(DAY_90_HOURS)

    # Explicit overrides always win (even in smoke).
    fuzz = _int_env(ENV_FUZZ, fuzz_default)
    override_cands = os.environ.get(ENV_SESSION_CANDIDATES)
    if override_cands is not None and override_cands.strip() != "":
        c30 = int(override_cands)
        c90 = int(override_cands)

    return ScaleConfig(
        fuzz_scenarios=max(1, fuzz),
        fuzz_seed=_int_env(ENV_FUZZ_SEED, DEFAULT_FUZZ_SEED),
        session_seed=_int_env(ENV_SESSION_SEED, DEFAULT_SESSION_SEED),
        session_candidate_count_30d=max(8, c30),
        session_candidate_count_90d=max(8, c90),
        smoke=smoke or fuzz < DEFAULT_FUZZ_SCENARIOS,
    )


__all__ = [
    "DAY_30_HOURS",
    "DAY_90_HOURS",
    "DEFAULT_FUZZ_SCENARIOS",
    "DEFAULT_FUZZ_SEED",
    "DEFAULT_SESSION_SEED",
    "ENV_FUZZ",
    "ENV_FUZZ_SEED",
    "ENV_SESSION_CANDIDATES",
    "ENV_SESSION_SEED",
    "ENV_SMOKE",
    "SMOKE_FUZZ_SCENARIOS",
    "SMOKE_SESSION_CANDIDATE_COUNT",
    "ScaleConfig",
    "load_scale_config",
]
