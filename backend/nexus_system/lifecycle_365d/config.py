"""365-day system lifecycle campaign configuration.

Defaults target Founder S1 full logical window. Smoke mode shrinks candidate
density for CI while preserving logical_days=365 clock coverage.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

LOGICAL_DAYS = 365
LOGICAL_HOURS = LOGICAL_DAYS * 24  # 8760
DEFAULT_SEED = 911_365
SMOKE_CANDIDATE_COUNT = 72

ENV_SMOKE = "NEXUS_V11_1_SYSTEM_365D_SMOKE"
ENV_CANDIDATES = "NEXUS_V11_1_SYSTEM_365D_CANDIDATES"
ENV_SEED = "NEXUS_V11_1_SYSTEM_365D_SEED"
ENV_PASSES = "NEXUS_V11_1_SYSTEM_365D_PASSES"


def _truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on", "smoke"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _default_candidates(*, smoke: bool) -> int:
    if smoke:
        return SMOKE_CANDIDATE_COUNT
    from backend.nexus_system.lifecycle_365d.injections import LIFECYCLE_INJECTION_CATALOG

    # Dense enough for day-indexed regimes + catalog coverage; not hour-dense.
    return max(LOGICAL_DAYS * 2, LOGICAL_DAYS + len(LIFECYCLE_INJECTION_CATALOG) * 5)


@dataclass(frozen=True)
class Lifecycle365Config:
    logical_days: int
    logical_hours: float
    candidate_count: int
    seed: int
    smoke: bool
    passes: int

    @property
    def mode(self) -> str:
        return "SMOKE" if self.smoke else "FULL"


def load_lifecycle_365_config() -> Lifecycle365Config:
    smoke = _truthy(os.environ.get(ENV_SMOKE))
    candidates = _default_candidates(smoke=smoke)
    override = os.environ.get(ENV_CANDIDATES)
    if override is not None and override.strip() != "":
        candidates = max(16, int(override))
        # Explicit override may still be smoke-sized; keep smoke flag from env.
    return Lifecycle365Config(
        logical_days=LOGICAL_DAYS,
        logical_hours=float(LOGICAL_HOURS),
        candidate_count=max(16, candidates),
        seed=_int_env(ENV_SEED, DEFAULT_SEED),
        smoke=smoke,
        passes=max(1, _int_env(ENV_PASSES, 2)),
    )


__all__ = [
    "DEFAULT_SEED",
    "ENV_CANDIDATES",
    "ENV_PASSES",
    "ENV_SEED",
    "ENV_SMOKE",
    "LOGICAL_DAYS",
    "LOGICAL_HOURS",
    "Lifecycle365Config",
    "SMOKE_CANDIDATE_COUNT",
    "load_lifecycle_365_config",
]
