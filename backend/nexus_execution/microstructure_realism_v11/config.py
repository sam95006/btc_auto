"""V11 Execution Microstructure Realism — config with smoke overrides.

Default full target: 250,000 deterministic generated scenarios.
Smoke / CI:
  NEXUS_V11_MICRO_SMOKE=1
  NEXUS_V11_MICRO_SCENARIOS=<int>
  NEXUS_V11_MICRO_SEED=<int>
"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_SCENARIOS = 250_000
DEFAULT_SEED = 20260805
SMOKE_SCENARIOS = 800

ENV_SMOKE = "NEXUS_V11_MICRO_SMOKE"
ENV_SCENARIOS = "NEXUS_V11_MICRO_SCENARIOS"
ENV_SEED = "NEXUS_V11_MICRO_SEED"


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
class MicroConfig:
    scenarios: int
    seed: int
    smoke: bool

    @property
    def mode(self) -> str:
        return "SMOKE" if self.smoke else "FULL"


def load_micro_config() -> MicroConfig:
    smoke = _truthy(os.environ.get(ENV_SMOKE))
    default = SMOKE_SCENARIOS if smoke else DEFAULT_SCENARIOS
    scenarios = max(1, _int_env(ENV_SCENARIOS, default))
    return MicroConfig(
        scenarios=scenarios,
        seed=_int_env(ENV_SEED, DEFAULT_SEED),
        smoke=smoke or scenarios < DEFAULT_SCENARIOS,
    )


__all__ = [
    "DEFAULT_SCENARIOS",
    "DEFAULT_SEED",
    "ENV_SCENARIOS",
    "ENV_SEED",
    "ENV_SMOKE",
    "SMOKE_SCENARIOS",
    "MicroConfig",
    "load_micro_config",
]
