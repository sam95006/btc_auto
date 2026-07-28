"""Deterministic replay harness with fixtures and walk-forward."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

FIXTURE_LABELS = {
    "mode": "FIXTURE",
    "live": "NOT_LIVE",
    "executed": "NOT_EXECUTED",
    "authoritative_universe": "NOT_AUTHORITATIVE_UNIVERSE",
}

NAMED_FIXTURES: dict[str, dict[str, Any]] = {
    "btc_trend_up": {"symbol": "BTCUSDT", "regime": "TRENDING_UP", "momentum": 0.3, "volatility": 0.03},
    "btc_trend_down": {"symbol": "BTCUSDT", "regime": "TRENDING_DOWN", "momentum": -0.3, "volatility": 0.03},
    "eth_range": {"symbol": "ETHUSDT", "regime": "RANGE", "momentum": 0.02, "volatility": 0.015},
    "sol_high_vol": {"symbol": "SOLUSDT", "regime": "HIGH_VOLATILITY", "momentum": 0.1, "volatility": 0.12},
    "pepe_low_liq": {"symbol": "PEPEUSDT", "regime": "RANGE", "momentum": 0.05, "volatility": 0.04, "liquidity_tier": "LOW"},
    "midcap_breakout": {"symbol": "ARBUSDT", "regime": "BREAKOUT", "momentum": 0.28, "volatility": 0.05},
    "smallcap_liq_fail": {"symbol": "SMALLUSDT", "regime": "UNCERTAIN", "missing": True},
    "cross_market_transition": {"symbol": "BTCUSDT", "regime": "REVERSAL", "momentum": -0.2},
    "event_risk": {"symbol": "BTCUSDT", "regime": "EVENT_RISK", "spread_bps": 80},
    "full_universe_ranking": {"symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ARBUSDT"], "ranking": True},
}

FAULT_FIXTURES: dict[str, dict[str, Any]] = {
    "missing_funding": {"missing_fields": ["funding_rate"]},
    "missing_oi": {"missing_fields": ["open_interest"]},
    "stale_price": {"price_freshness": "STALE"},
    "stale_orderbook": {"orderbook_freshness": "STALE"},
    "duplicate_tick": {"anomaly_flags": ["duplicate_tick"]},
    "out_of_order_event": {"anomaly_flags": ["out_of_order"]},
    "provider_timeout": {"provider_status": "UNIVERSE_UNAVAILABLE"},
    "provider_partial": {"provider_status": "UNIVERSE_DEGRADED"},
    "partial_evidence": {"completeness": "PARTIAL"},
    "regime_flip": {"regime_sequence": ["TRENDING_UP", "TRENDING_DOWN"]},
    "liquidity_drop": {"liquidity_score": 1.0},
    "spread_spike": {"spread_bps": 100},
    "slippage_spike": {"estimated_slippage": 0.05},
    "candidate_expired": {"status": "EXPIRED"},
    "six_role_missing": {"reviews_missing": True},
    "risk_critic_unknown": {"risk_critic_verdict": "UNKNOWN"},
    "correlation_spike": {"correlation": 0.95},
    "worker_restart": {"worker_health": "DEGRADED"},
    "checksum_failure": {"checksum_valid": False},
}


@dataclass
class WalkForwardFold:
    fold_id: int
    dataset_hash: str
    universe_count: int = 0
    eligible_count: int = 0
    candidate_count: int = 0
    six_role_reviewed_count: int = 0
    risk_pass_count: int = 0
    risk_block_count: int = 0
    portfolio_selected_count: int = 0
    outcome_count: int = 0
    in_sample: bool = True


@dataclass
class ReplayResult:
    fixture_name: str
    deterministic: bool
    output_hash: str
    labels: dict[str, str] = field(default_factory=lambda: dict(FIXTURE_LABELS))
    folds: list[WalkForwardFold] = field(default_factory=list)
    oos_isolated: bool = False
    sample_sufficiency: str = "UNKNOWN"
    error: str | None = None


class ReplayHarness:
    """Deterministic replay with walk-forward >=3 folds."""

    def __init__(self, pipeline_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.pipeline_fn = pipeline_fn

    def run_fixture(self, name: str, *, pipeline_fn: Callable | None = None) -> ReplayResult:
        fn = pipeline_fn or self.pipeline_fn
        fixture = NAMED_FIXTURES.get(name) or FAULT_FIXTURES.get(name)
        if not fixture:
            return ReplayResult(name, False, "", error="unknown_fixture")
        payload = {**fixture, **FIXTURE_LABELS}
        if fn:
            out = fn(payload)
            h = self._hash(out)
            return ReplayResult(name, True, h, labels=dict(FIXTURE_LABELS))
        return ReplayResult(name, True, self._hash(payload), labels=dict(FIXTURE_LABELS))

    def run_deterministic_twice(self, name: str, fn: Callable[[dict], dict]) -> bool:
        f = NAMED_FIXTURES.get(name, {})
        a = fn({**f, **FIXTURE_LABELS})
        b = fn({**f, **FIXTURE_LABELS})
        return self._hash(a) == self._hash(b)

    def walk_forward(
        self,
        datasets: list[list[dict[str, Any]]],
        fn: Callable[[list[dict]], dict[str, Any]],
        *,
        oos_index: int | None = None,
    ) -> ReplayResult:
        if len(datasets) < 3:
            return ReplayResult(
                "walk_forward",
                True,
                "",
                sample_sufficiency="INSUFFICIENT_SAMPLE",
                error="folds_lt_3",
            )
        folds: list[WalkForwardFold] = []
        oos_isolated = oos_index is not None and oos_index == len(datasets) - 1
        for i, ds in enumerate(datasets):
            result = fn(ds)
            folds.append(
                WalkForwardFold(
                    fold_id=i,
                    dataset_hash=self._hash(ds)[:16],
                    universe_count=result.get("universe_count", len(ds)),
                    eligible_count=result.get("eligible_count", 0),
                    candidate_count=result.get("candidate_count", 0),
                    six_role_reviewed_count=result.get("six_role_reviewed_count", 0),
                    risk_pass_count=result.get("risk_pass_count", 0),
                    risk_block_count=result.get("risk_block_count", 0),
                    portfolio_selected_count=result.get("portfolio_selected_count", 0),
                    outcome_count=result.get("outcome_count", 0),
                    in_sample=i != oos_index if oos_index is not None else True,
                )
            )
        suff = "SUFFICIENT" if len(folds) >= 3 else "INSUFFICIENT_SAMPLE"
        return ReplayResult(
            "walk_forward",
            True,
            self._hash([f.dataset_hash for f in folds]),
            folds=folds,
            oos_isolated=oos_isolated,
            sample_sufficiency=suff,
        )

    def _hash(self, obj: Any) -> str:
        return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

    def list_named_fixtures(self) -> list[str]:
        return list(NAMED_FIXTURES.keys())

    def list_fault_fixtures(self) -> list[str]:
        return list(FAULT_FIXTURES.keys())
