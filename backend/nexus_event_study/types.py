"""V14-B Event Study Engine — core typed records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EventDefinition:
    event_id: str
    family: str
    economic_rationale: str
    required_fields: tuple[str, ...]
    pre_window_bars: int
    post_window_bars: int
    control_window_bars: int
    overlap_exclusion_bars: int
    pit_rule: str
    missing_policy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StudyEvent:
    """A candidate event observation (never a trade)."""

    observation_id: str
    event_id: str
    symbol: str
    regime: str
    decision_ts_ms: int
    exchange_ts_ms: int
    receive_ts_ms: int
    side: str
    entry_price: float
    source: str  # synthetic | forensic_ro
    payload: dict[str, Any] = field(default_factory=dict)
    is_trade: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_trade"] = False
        return d


@dataclass(frozen=True)
class WindowSpec:
    kind: str  # pre | post | control
    start_offset_bars: int
    end_offset_bars: int
    start_ts_ms: int | None = None
    end_ts_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventWindows:
    observation_id: str
    pre: WindowSpec
    post: WindowSpec
    control: WindowSpec

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "pre": self.pre.to_dict(),
            "post": self.post.to_dict(),
            "control": self.control.to_dict(),
        }


@dataclass(frozen=True)
class HorizonOutcome:
    horizon: int
    gross_return: float | None
    net_return: float | None
    cost: float | None
    available: bool
    missing_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BootstrapCI:
    statistic: str
    point: float | None
    ci_low: float | None
    ci_high: float | None
    replicates: int
    block: int
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
