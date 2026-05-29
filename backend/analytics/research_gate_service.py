"""Unified research gate: walk-forward + kline edge (Binance-only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.analytics.kline_backtest_engine import KlineBacktestEngine
from backend.analytics.walk_forward_evaluator import WalkForwardEvaluator
from config.backtest_config import (
    RESEARCH_GATE_BLOCK_WHEN_FAIL,
    RESEARCH_GATE_ENABLED,
    RESEARCH_GATE_REQUIRE_FOR_LEARNING,
    WALK_FORWARD_MIN_LATEST_WIN_RATE,
    WALK_FORWARD_MIN_POSITIVE_RATIO,
)


class ResearchGateService:
    def __init__(self, futures_client=None, walk_forward_evaluator=None):
        self.kline_engine = KlineBacktestEngine(futures_client=futures_client)
        self.walk_forward_evaluator = walk_forward_evaluator or WalkForwardEvaluator()

    def evaluate_walk_forward(self, trade_results: List[dict]) -> Dict[str, Any]:
        status = self.walk_forward_evaluator.evaluate(trade_results)
        ready = bool(status.get("ready"))
        positive_ratio = float(status.get("positive_window_ratio") or 0.0)
        latest = dict(status.get("latest_window") or {})
        latest_wr = float(latest.get("win_rate") or 0.0)
        wf_pass = True
        if ready:
            wf_pass = positive_ratio >= WALK_FORWARD_MIN_POSITIVE_RATIO and latest_wr >= WALK_FORWARD_MIN_LATEST_WIN_RATE
        status["oos_pass"] = wf_pass
        status["thresholds"] = {
            "min_positive_window_ratio": WALK_FORWARD_MIN_POSITIVE_RATIO,
            "min_latest_win_rate": WALK_FORWARD_MIN_LATEST_WIN_RATE,
        }
        return status

    def evaluate_symbol_kline(self, symbol: str, side: str) -> Dict[str, Any]:
        return self.kline_engine.evaluate(symbol, side)

    def build_status(
        self,
        trade_results: List[dict],
        *,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not RESEARCH_GATE_ENABLED:
            return {
                "enabled": False,
                "research_pass": True,
                "reason": "research_gate_disabled",
            }

        walk_forward = self.evaluate_walk_forward(trade_results)
        kline = None
        if symbol and side:
            kline = self.evaluate_symbol_kline(symbol, side)

        wf_pass = bool(walk_forward.get("oos_pass", True))
        kline_pass = True if not kline else bool(kline.get("approved"))
        research_pass = wf_pass and kline_pass
        block_entries = RESEARCH_GATE_BLOCK_WHEN_FAIL and not research_pass

        return {
            "enabled": True,
            "research_pass": research_pass,
            "block_new_entries": block_entries,
            "walk_forward": walk_forward,
            "kline_research": kline,
            "learning_auto_apply_allowed": (
                research_pass if RESEARCH_GATE_REQUIRE_FOR_LEARNING else True
            ),
            "reason": (
                "research_pass"
                if research_pass
                else (
                    "walk_forward_fail"
                    if not wf_pass
                    else "kline_edge_fail"
                )
            ),
        }
