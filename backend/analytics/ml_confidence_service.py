"""Lightweight ML-style confidence assist (FreqAI-inspired).

This does NOT replace the LLM. It provides a simple, data-driven prior from recent
trade outcomes (symbol-level), which the LLM can use as an extra guardrail.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _bayes_winrate(wins: int, losses: int, alpha: float = 2.0, beta: float = 2.0) -> float:
    # Beta prior smoothing; prevents extreme 0/1 with tiny samples.
    return float((wins + alpha) / (wins + losses + alpha + beta))


class MlConfidenceAssist:
    """Produces a 0..1 confidence prior per symbol from recent trades."""

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def build_symbol_priors(self, limit: int = 300) -> Dict[str, Dict[str, Any]]:
        trades = list(self.runtime_store.recent_trade_results(limit=limit))
        buckets: Dict[str, List[float]] = {}
        for item in trades:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper().replace("/", "")
            if not symbol:
                continue
            buckets.setdefault(symbol, []).append(_safe_float(item.get("pnl")))

        priors = {}
        for symbol, pnls in buckets.items():
            wins = sum(1 for p in pnls if p > 0)
            losses = sum(1 for p in pnls if p < 0)
            samples = wins + losses
            priors[symbol] = {
                "samples": samples,
                "win_rate": round(_bayes_winrate(wins, losses), 4) if samples else 0.5,
                "net_pnl": round(sum(pnls), 4),
            }
        return priors

