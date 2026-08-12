"""Formal parameter anti-thrash lock (no per-minute churn)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_strategy_expert_router.constants import FORMAL_PARAM_MIN_DWELL_MS
from backend.nexus_strategy_expert_router.hard_bans import HardBanViolation


@dataclass(frozen=True)
class FormalRouterParams:
    """Sparse formal params — changes require dwell, not minute thrash."""

    min_data_trust: float = 0.45
    max_uncertainty_for_entry: float = 0.72
    max_cost_bps_for_entry: float = 35.0
    min_liquidity_score: float = 0.35
    max_portfolio_exposure: float = 0.85
    defensive_stress_boost: float = 1.25

    def to_dict(self) -> dict[str, float]:
        return {
            "min_data_trust": self.min_data_trust,
            "max_uncertainty_for_entry": self.max_uncertainty_for_entry,
            "max_cost_bps_for_entry": self.max_cost_bps_for_entry,
            "min_liquidity_score": self.min_liquidity_score,
            "max_portfolio_exposure": self.max_portfolio_exposure,
            "defensive_stress_boost": self.defensive_stress_boost,
        }


@dataclass
class FormalParamLock:
    params: FormalRouterParams = field(default_factory=FormalRouterParams)
    last_change_ts_ms: int = 0
    change_count: int = 0
    rejected_thrash_count: int = 0

    def propose_update(
        self,
        new_params: FormalRouterParams,
        *,
        ts_ms: int,
        force: bool = False,
    ) -> dict[str, Any]:
        """Accept formal param changes only after minimum dwell.

        Per-minute thrashing is a hard ban unless ``force`` is used by tests
        that assert rejection.
        """
        if new_params == self.params:
            return {
                "accepted": False,
                "reason": "unchanged",
                "params": self.params.to_dict(),
                "locked": self.is_locked(ts_ms),
            }

        elapsed = ts_ms - self.last_change_ts_ms if self.last_change_ts_ms else FORMAL_PARAM_MIN_DWELL_MS
        if not force and self.last_change_ts_ms and elapsed < FORMAL_PARAM_MIN_DWELL_MS:
            self.rejected_thrash_count += 1
            if elapsed < 60_000:
                # Explicit hard-ban path for sub-minute thrash attempts.
                raise HardBanViolation(
                    f"no_per_minute_formal_param_thrash:elapsed_ms={elapsed}"
                )
            return {
                "accepted": False,
                "reason": "dwell_not_elapsed",
                "elapsed_ms": elapsed,
                "min_dwell_ms": FORMAL_PARAM_MIN_DWELL_MS,
                "params": self.params.to_dict(),
                "locked": True,
            }

        self.params = new_params
        self.last_change_ts_ms = ts_ms
        self.change_count += 1
        return {
            "accepted": True,
            "reason": "accepted_after_dwell" if not force else "forced",
            "params": self.params.to_dict(),
            "locked": False,
        }

    def is_locked(self, ts_ms: int) -> bool:
        if not self.last_change_ts_ms:
            return False
        return (ts_ms - self.last_change_ts_ms) < FORMAL_PARAM_MIN_DWELL_MS

    def to_dict(self) -> dict[str, Any]:
        return {
            "params": self.params.to_dict(),
            "last_change_ts_ms": self.last_change_ts_ms,
            "change_count": self.change_count,
            "rejected_thrash_count": self.rejected_thrash_count,
            "min_dwell_ms": FORMAL_PARAM_MIN_DWELL_MS,
        }
