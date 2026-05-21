from __future__ import annotations

import uuid
from datetime import datetime

from config.autonomy_config import NEXUS_AI_PROPOSAL_MAX_PER_TICK, STRATEGY_VERSION_ACTIVE


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TradeProposalService:
    """P2 structured trade proposals (fleet engine or LLM)."""

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store
        self.max_per_tick = max(1, int(NEXUS_AI_PROPOSAL_MAX_PER_TICK or 3))
        self._tick_count = 0

    def begin_tick(self):
        self._tick_count = 0

    def create_from_request(self, request, *, proposer="fleet_engine", rationale=None):
        request = dict(request or {})
        if self._tick_count >= self.max_per_tick:
            return None
        proposal = {
            "proposal_id": str(uuid.uuid4()),
            "timestamp": _now(),
            "proposer": proposer,
            "status": "pending",
            "strategy_version": STRATEGY_VERSION_ACTIVE,
            "fleet": request.get("fleet"),
            "symbol": request.get("symbol"),
            "side": request.get("side"),
            "market_type": request.get("market_type", "futures"),
            "margin": request.get("margin"),
            "leverage": request.get("leverage"),
            "strategy_key": request.get("strategy_key"),
            "raw_confidence": request.get("raw_confidence", request.get("adjusted_confidence")),
            "adjusted_confidence": request.get("adjusted_confidence"),
            "reason": request.get("reason"),
            "rationale": rationale or request.get("reason"),
            "payload": request,
        }
        self.runtime_store.append_trade_proposal(proposal)
        self._tick_count += 1
        return proposal

    def create_from_llm(self, llm_payload, market_context=None):
        llm_payload = dict(llm_payload or {})
        proposals = []
        for item in llm_payload.get("trade_proposals") or llm_payload.get("proposals") or []:
            if not isinstance(item, dict):
                continue
            request = {
                "fleet": item.get("fleet") or "RADAR",
                "symbol": item.get("symbol"),
                "side": str(item.get("side", "BUY")).upper(),
                "market_type": item.get("market_type", "futures"),
                "margin": item.get("margin"),
                "leverage": item.get("leverage"),
                "strategy_key": item.get("strategy_key", "llm_proposal"),
                "adjusted_confidence": float(item.get("confidence", 0.55) or 0.55),
                "reason": item.get("reason", "llm_trade_proposal"),
            }
            proposal = self.create_from_request(request, proposer="llm_agent", rationale=item.get("rationale"))
            if proposal:
                proposals.append(proposal)
        return proposals

    def recent(self, limit=40):
        return self.runtime_store.recent_trade_proposals(limit=limit)
