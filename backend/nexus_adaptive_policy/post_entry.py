"""Post-entry risk invariants — tighten only, never widen risk."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PostEntryAction(str, Enum):
    TIGHTEN_STOP = "TIGHTEN_STOP"
    MOVE_TO_BREAKEVEN = "MOVE_TO_BREAKEVEN"
    TRAIL_STOP = "TRAIL_STOP"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    REGIME_EXIT = "REGIME_EXIT"
    DATA_QUALITY_EXIT = "DATA_QUALITY_EXIT"
    TIME_STOP = "TIME_STOP"


class ForbiddenPostEntryAction(str, Enum):
    WIDEN_STOP = "WIDEN_STOP"
    INCREASE_MAX_LOSS = "INCREASE_MAX_LOSS"
    AVERAGE_DOWN = "AVERAGE_DOWN"
    RAISE_LEVERAGE = "RAISE_LEVERAGE"
    CROSS_MARGIN = "CROSS_MARGIN"
    AUTO_ADD_MARGIN = "AUTO_ADD_MARGIN"
    CANCEL_PROTECTION = "CANCEL_PROTECTION"


ALLOWED_ACTIONS = frozenset(PostEntryAction)
FORBIDDEN_ACTIONS = frozenset(ForbiddenPostEntryAction)


@dataclass
class PostEntryVerdict:
    ok: bool
    action: str = ""
    violation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "action": self.action, "violation": self.violation}


class PostEntryRiskInvariant:
    """Validate post-entry adjustments against immutable tighten-only rules."""

    def validate(self, action: str, **params: Any) -> PostEntryVerdict:
        try:
            forbidden = ForbiddenPostEntryAction(action)
            return PostEntryVerdict(ok=False, violation=forbidden.value)
        except ValueError:
            pass

        try:
            allowed = PostEntryAction(action)
        except ValueError:
            return PostEntryVerdict(ok=False, violation="UNKNOWN_ACTION")

        if allowed == PostEntryAction.TIGHTEN_STOP:
            new_stop = float(params.get("new_stop_distance", 0))
            old_stop = float(params.get("old_stop_distance", 0))
            if new_stop > old_stop:
                return PostEntryVerdict(ok=False, violation=ForbiddenPostEntryAction.WIDEN_STOP.value)
        if "leverage" in params and int(params["leverage"]) != 25:
            return PostEntryVerdict(ok=False, violation=ForbiddenPostEntryAction.RAISE_LEVERAGE.value)
        return PostEntryVerdict(ok=True, action=allowed.value)

    def allowed_actions(self) -> list[str]:
        return [a.value for a in PostEntryAction]

    def forbidden_actions(self) -> list[str]:
        return [a.value for a in ForbiddenPostEntryAction]
