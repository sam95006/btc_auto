"""Shared testnet sandbox helpers (Binance testnet trial trading only)."""

from __future__ import annotations

import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED
from config.testnet_sandbox_config import (
    SANDBOX_MIN_APPROVAL_SCORE,
    SANDBOX_MIN_CONFIDENCE,
    SANDBOX_RELAX_GROWTH_BLOCKS,
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def sandbox_active() -> bool:
    """Read env at call time so tests and runtime overrides apply without reload."""
    return _env_bool("NEXUS_TESTNET_SANDBOX", BOLD_TESTNET_ENABLED)


def sandbox_min_confidence() -> float:
    return float(os.getenv("NEXUS_SANDBOX_MIN_CONFIDENCE", str(SANDBOX_MIN_CONFIDENCE)) or SANDBOX_MIN_CONFIDENCE)


def sandbox_min_approval_score() -> float:
    return float(os.getenv("NEXUS_SANDBOX_MIN_APPROVAL_SCORE", str(SANDBOX_MIN_APPROVAL_SCORE)) or SANDBOX_MIN_APPROVAL_SCORE)


def sandbox_relax_growth_blocks() -> bool:
    return _env_bool("NEXUS_SANDBOX_RELAX_GROWTH", SANDBOX_RELAX_GROWTH_BLOCKS) and sandbox_active()
