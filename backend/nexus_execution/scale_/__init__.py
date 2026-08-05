"""V10 Execution Session Scale helpers (Lane B owned package).

Deterministic simulated scale harness support for 100k execution fuzz and
accelerated multi-day Session runs. Never performs exchange writes.
"""
from __future__ import annotations

from backend.nexus_execution.scale_.config import (
    DEFAULT_FUZZ_SCENARIOS,
    ScaleConfig,
    load_scale_config,
)
from backend.nexus_execution.scale_.injections import (
    FOCUSED_TERMINAL_INJECTIONS,
    SCALE_INJECTION_CATALOG,
    SCALE_LONG_SESSION_INJECTIONS,
)

__all__ = [
    "DEFAULT_FUZZ_SCENARIOS",
    "FOCUSED_TERMINAL_INJECTIONS",
    "SCALE_INJECTION_CATALOG",
    "SCALE_LONG_SESSION_INJECTIONS",
    "ScaleConfig",
    "load_scale_config",
]
