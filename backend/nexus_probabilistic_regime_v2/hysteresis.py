"""Hysteresis and minimum dwell for regime label stability."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.nexus_probabilistic_regime_v2.constants import (
    DEFAULT_HYSTERESIS_MARGIN,
    DEFAULT_MIN_DWELL_BARS,
)


@dataclass
class DimensionHysteresisState:
    """Per-dimension dwell / hysteresis tracker."""

    dimension: str
    active_label: str = "UNKNOWN"
    active_score: float = 0.0
    dwell_bars: int = 0
    last_as_of_ms: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def observe(
        self,
        *,
        proposed_label: str,
        proposed_score: float,
        as_of_ms: int,
        min_dwell_bars: int = DEFAULT_MIN_DWELL_BARS,
        hysteresis_margin: float = DEFAULT_HYSTERESIS_MARGIN,
    ) -> dict[str, Any]:
        """Apply min-dwell + hysteresis; reject thrashing flips."""
        if self.last_as_of_ms > 0 and as_of_ms < self.last_as_of_ms:
            # Clock rollback → fail-closed to UNKNOWN.
            self.active_label = "UNKNOWN"
            self.active_score = 0.0
            self.dwell_bars = 0
            self.last_as_of_ms = as_of_ms
            return self._result(
                proposed_label=proposed_label,
                accepted=False,
                reason="CLOCK_ROLLBACK_FAIL_CLOSED",
            )

        # Advance dwell only after the first committed observation.
        if self.last_as_of_ms > 0 and as_of_ms > self.last_as_of_ms:
            self.dwell_bars += 1
        self.last_as_of_ms = as_of_ms

        if proposed_label == self.active_label and self.active_label != "UNKNOWN":
            self.active_score = proposed_score
            return self._result(
                proposed_label=proposed_label,
                accepted=True,
                reason="SAME_LABEL",
            )

        # Formal UNKNOWN/MIXED can enter immediately (fail-closed / conflict).
        if proposed_label in {"UNKNOWN", "MIXED"}:
            self.active_label = proposed_label
            self.active_score = proposed_score
            self.dwell_bars = 0
            return self._result(
                proposed_label=proposed_label,
                accepted=True,
                reason="FORMAL_FAIL_CLOSED_OR_MIXED",
            )

        # Bootstrap first clear label from pristine UNKNOWN immediately.
        if self.active_label == "UNKNOWN" and self.dwell_bars == 0:
            self.active_label = proposed_label
            self.active_score = proposed_score
            self.dwell_bars = 0
            return self._result(
                proposed_label=proposed_label,
                accepted=True,
                reason="BOOTSTRAP_FROM_UNKNOWN",
            )

        # Leaving MIXED (or post-rollback UNKNOWN with dwell>0) requires min dwell.
        if self.active_label in {"UNKNOWN", "MIXED"}:
            if self.dwell_bars < min_dwell_bars:
                return self._result(
                    proposed_label=proposed_label,
                    accepted=False,
                    reason="MIN_DWELL_NOT_MET",
                )
            self.active_label = proposed_label
            self.active_score = proposed_score
            self.dwell_bars = 0
            return self._result(
                proposed_label=proposed_label,
                accepted=True,
                reason="DWELL_MET_FROM_FORMAL",
            )

        # Clear → clear: require dwell + margin over incumbent.
        if self.dwell_bars < min_dwell_bars:
            return self._result(
                proposed_label=proposed_label,
                accepted=False,
                reason="MIN_DWELL_NOT_MET",
            )
        if proposed_score < self.active_score + hysteresis_margin:
            return self._result(
                proposed_label=proposed_label,
                accepted=False,
                reason="HYSTERESIS_MARGIN_NOT_MET",
            )

        self.active_label = proposed_label
        self.active_score = proposed_score
        self.dwell_bars = 0
        return self._result(
            proposed_label=proposed_label,
            accepted=True,
            reason="HYSTERESIS_ACCEPTED",
        )

    def _result(
        self,
        *,
        proposed_label: str,
        accepted: bool,
        reason: str,
    ) -> dict[str, Any]:
        row = {
            "dimension": self.dimension,
            "proposed_label": proposed_label,
            "active_label": self.active_label,
            "active_score": round(self.active_score, 6),
            "dwell_bars": self.dwell_bars,
            "accepted": accepted,
            "reason": reason,
            "as_of_ms": self.last_as_of_ms,
        }
        self.history.append(row)
        return row


class HysteresisBook:
    """Book of per-dimension hysteresis states."""

    def __init__(self) -> None:
        self._states: dict[str, DimensionHysteresisState] = {}

    def state_for(self, dimension: str) -> DimensionHysteresisState:
        if dimension not in self._states:
            self._states[dimension] = DimensionHysteresisState(dimension=dimension)
        return self._states[dimension]

    def snapshot(self) -> dict[str, Any]:
        return {
            dim: {
                "active_label": st.active_label,
                "active_score": st.active_score,
                "dwell_bars": st.dwell_bars,
                "last_as_of_ms": st.last_as_of_ms,
            }
            for dim, st in sorted(self._states.items())
        }
