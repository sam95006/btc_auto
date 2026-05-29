from __future__ import annotations

import uuid
from datetime import datetime


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DecisionTraceStore:
    """P0 decision trace: who proposed, validation stages, regime, outcome."""

    def __init__(self, runtime_store, batched_writer=None):
        self.runtime_store = runtime_store
        self._batched_writer = batched_writer

    def start_background_flush(self):
        if self._batched_writer is not None:
            self._batched_writer.start()

    def record(
        self,
        proposal,
        validation,
        market_context=None,
        *,
        proposer="fleet_engine",
        order_id=None,
        trace_id=None,
    ):
        trace_id = trace_id or str(uuid.uuid4())
        stages = dict(validation.get("stages") or {})
        record = {
            "trace_id": trace_id,
            "timestamp": _now(),
            "proposer": proposer,
            "fleet": proposal.get("fleet"),
            "symbol": proposal.get("symbol"),
            "side": proposal.get("side"),
            "market_type": proposal.get("market_type", "futures"),
            "market_regime": (market_context or {}).get("market_regime", "normal"),
            "strategy_key": proposal.get("strategy_key"),
            "raw_confidence": proposal.get("raw_confidence", proposal.get("adjusted_confidence", 0.0)),
            "adjusted_confidence": proposal.get("adjusted_confidence", 0.0),
            "approved": bool(validation.get("approved")),
            "reject_layer": None if validation.get("approved") else validation.get("reject_layer", "validation_pipeline"),
            "reject_reason": validation.get("reason"),
            "governance_reason": validation.get("governance_reason"),
            "stages": stages,
            "order_id": order_id,
            "why_not": validation.get("why_not"),
        }
        if self._batched_writer is not None:
            self._batched_writer.enqueue(record)
        else:
            self.runtime_store.append_decision_trace(record)
        return record
