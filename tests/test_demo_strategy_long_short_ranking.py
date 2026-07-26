"""Strategy ranking covers LONG and SHORT; ineligible regimes stay blocked."""
from __future__ import annotations

from backend.nexus_research.demo_strategy.candidate_ranking import ranked_symbols
from backend.nexus_research.demo_strategy.market_features import extract_features
from backend.nexus_research.demo_strategy.strategy_evaluator import evaluate, evaluate_all


def _row(symbol: str, **kw):
    base = {
        "symbol": symbol,
        "trendScore": 45.0,
        "momentumScore": 32.0,
        "rsi14": 58.0,
        "atrPct": 1.8,
        "fundingRate8hPct": 0.01,
        "openInterestUsd": 1.25e10,
        "volume24hUsd": 2.8e10,
        "spreadBps": 1.2,
        "freshnessMs": 5_000,
    }
    base.update(kw)
    return base


class TestLongShortRanking:
    def test_evaluate_all_three_symbols(self):
        results = evaluate_all()
        assert len(results) >= 3
        symbols = {r.symbol for r in results}
        assert {"BTCUSDT", "ETHUSDT", "SOLUSDT"} <= symbols

    def test_short_path_on_bearish_fixture(self):
        feat = extract_features(
            _row("BTCUSDT", trendScore=-45.0, momentumScore=-32.0, rsi14=42.0),
            source="simulation",
        )
        ev = evaluate(feat, "SHORT")
        d = ev.to_dict()
        assert d["direction"] == "SHORT"
        assert "compositeScore" in d

    def test_stale_data_blocks_trade(self):
        feat = extract_features(_row("ETHUSDT", freshnessMs=500_000), source="simulation")
        ev = evaluate(feat, "LONG")
        assert ev.allow_trade is False
        assert any(
            "AGE" in str(r).upper() or "STALE" in str(r).upper() or "FRESH" in str(r).upper()
            for r in (ev.block_reasons or [])
        )

    def test_wide_spread_blocks_trade(self):
        feat = extract_features(_row("SOLUSDT", spreadBps=80.0), source="simulation")
        ev = evaluate(feat, "LONG")
        assert ev.allow_trade is False

    def test_ranked_symbols_priority_order(self):
        order = ranked_symbols()
        assert order[0] == "BTCUSDT"
        assert "ETHUSDT" in order and "SOLUSDT" in order

    def test_evaluate_all_sorted_by_score_desc(self):
        ranked = sorted(evaluate_all(), key=lambda r: r.composite_score, reverse=True)
        scores = [r.composite_score for r in ranked]
        assert scores == sorted(scores, reverse=True)
