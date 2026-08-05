"""Synthetic development fixtures for cost/execution sensitivity (non-OOS)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.nexus_cost_sensitivity.constants import DEVELOPMENT_INTERVAL_ID, RANDOM_SEED


@dataclass(frozen=True, slots=True)
class SyntheticCandidate:
    candidate_id: str
    mechanism_family: str
    symbol: str
    side: str  # LONG | SHORT
    qty: Decimal
    entry_price: Decimal
    exit_price: Decimal
    sample_trade_count: int
    development_interval_id: str = DEVELOPMENT_INTERVAL_ID
    oos_consumed: bool = False
    evidence_class: str = "FIXTURE_SYNTHETIC_DEVELOPMENT_ONLY"


def build_synthetic_candidates(*, seed: int = RANDOM_SEED) -> list[SyntheticCandidate]:
    """Fixed deterministic fixture set — never treated as live edge evidence."""
    # Seed retained for provenance; fixtures are explicit tables (no RNG drift).
    _ = seed
    rows: list[tuple[str, str, str, str, str, str, str, int]] = [
        # id, family, symbol, side, qty, entry, exit, n_trades
        ("C01", "ORDER_FLOW_IMBALANCE", "BTCUSDT", "LONG", "0.010", "60000", "60120", 40),
        ("C02", "ABSORPTION", "BTCUSDT", "LONG", "0.020", "60000", "60080", 36),
        ("C03", "LIQUIDATION_CASCADE", "ETHUSDT", "SHORT", "0.50", "3200", "3188", 28),
        ("C04", "SPREAD_SHOCK", "ETHUSDT", "LONG", "0.40", "3200", "3205", 24),
        ("C05", "FUNDING_BASIS", "BTCUSDT", "LONG", "0.015", "60000", "60040", 32),
        ("C06", "FLOW_REVERSAL", "SOLUSDT", "SHORT", "20", "140", "139.4", 20),
        ("C07", "LIQUIDITY_WITHDRAWAL", "SOLUSDT", "LONG", "15", "140", "140.2", 18),
        ("C08", "VOL_EXPANSION", "XRPUSDT", "LONG", "2000", "0.55", "0.552", 22),
        ("C09", "QUEUE_SENSITIVE_MAKER", "BTCUSDT", "LONG", "0.008", "60000", "60090", 30),
        ("C10", "SIZE_SCALING_FRAGILE", "ETHUSDT", "LONG", "2.0", "3200", "3208", 16),
        ("C11", "LATENCY_FRAGILE", "BTCUSDT", "SHORT", "0.012", "60000", "59940", 26),
        ("C12", "LOW_EDGE_COST_DESTROY", "BTCUSDT", "LONG", "0.010", "60000", "60010", 14),
    ]
    out: list[SyntheticCandidate] = []
    for cid, fam, sym, side, qty, entry, exit_, n in rows:
        out.append(
            SyntheticCandidate(
                candidate_id=cid,
                mechanism_family=fam,
                symbol=sym,
                side=side,
                qty=Decimal(qty),
                entry_price=Decimal(entry),
                exit_price=Decimal(exit_),
                sample_trade_count=n,
            )
        )
    return out


def candidate_as_dict(c: SyntheticCandidate) -> dict[str, Any]:
    return {
        "candidate_id": c.candidate_id,
        "mechanism_family": c.mechanism_family,
        "symbol": c.symbol,
        "side": c.side,
        "qty": format(c.qty, "f"),
        "entry_price": format(c.entry_price, "f"),
        "exit_price": format(c.exit_price, "f"),
        "sample_trade_count": c.sample_trade_count,
        "development_interval_id": c.development_interval_id,
        "oos_consumed": c.oos_consumed,
        "evidence_class": c.evidence_class,
        "profitability_claimed": False,
        "qualified_claimed": False,
    }
