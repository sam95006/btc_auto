from __future__ import annotations

from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value):
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


class ExecutionQualityMonitor:
    """P3 execution quality: slippage proxy and validation block rate."""

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def evaluate(self, recent_trades=None, validation_events=None):
        recent_trades = list(recent_trades or [])
        validation_events = list(validation_events or self.runtime_store.recent_trade_validation_events(limit=120))
        slippage_samples = [_safe_float(item.get("slippage")) for item in recent_trades if item.get("slippage") is not None]
        avg_slippage = sum(slippage_samples) / len(slippage_samples) if slippage_samples else 0.0
        blocks = sum(1 for item in validation_events if not item.get("approved"))
        total = len(validation_events) or 1
        return {
            "generated_at": _now(),
            "trade_sample_size": len(recent_trades),
            "validation_sample_size": len(validation_events),
            "avg_slippage": round(avg_slippage, 6),
            "validation_block_rate": round(blocks / total, 4),
            "health": "degraded" if blocks / total > 0.65 else "normal",
        }
