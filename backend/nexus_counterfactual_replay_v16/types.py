"""Typed records for V16-B Counterfactual Replay Engine."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Bar:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    receive_ts_ms: int = 0
    data_trust: float = 1.0
    regime: str = "UNKNOWN"
    regime_transition: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionTrade:
    """Observed Decision/Trade snapshot — never mutated as ledger truth."""

    decision_id: str
    trade_id: str
    symbol: str
    side: str  # LONG | SHORT
    strategy_expert: str
    decision_ts_ms: int
    entry_ts_ms: int
    exit_ts_ms: int
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit_price: float
    size: float
    data_trust_at_decision: float
    regime_at_decision: str
    confirmation_ready_ts_ms: int | None = None
    ledger_fingerprint: str = ""
    is_fixture: bool = True
    labels: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["labels"] = list(self.labels)
        return d


@dataclass
class PathOutcome:
    path_id: str
    decision_id: str
    trade_id: str
    executed: bool
    blocked: bool
    block_reason: str | None
    entry_ts_ms: int | None
    exit_ts_ms: int | None
    entry_price: float | None
    exit_price: float | None
    size: float
    side: str
    strategy_expert: str
    gross_pnl: float | None
    cost_total: float | None
    net_pnl: float | None
    slippage_cost: float | None
    fee_cost: float | None
    spread_cost: float | None
    comparability: str
    coverage: str
    pit_ok: bool
    cost_included: bool
    notes: str
    is_counterfactual: bool = True
    is_real_performance: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
