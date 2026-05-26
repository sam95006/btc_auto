from __future__ import annotations

from backend.autonomy.dca_accumulator_bridge import DcaAccumulatorBridge
from backend.autonomy.grid_signal_bridge import GridSignalBridge
from backend.governance.funding_arb_proposer import FundingArbProposer
from backend.risk.volatility_position_sizer import VolatilityPositionSizer


class StrategyProposalHub:
    """Aggregate P3 strategy modules (grid, funding arb, DCA) + vol sizing."""

    def __init__(self):
        self.grid_bridge = GridSignalBridge()
        self.funding_proposer = FundingArbProposer()
        self.dca_bridge = DcaAccumulatorBridge()
        self.volatility_sizer = VolatilityPositionSizer()

    def collect_proposals(self, prices, market_contexts=None, positions=None, deployable_pool=0.0):
        market_contexts = dict(market_contexts or {})
        positions = list(positions or [])
        pool = float(deployable_pool or 0.0)
        rows = []
        rows.extend(
            self.grid_bridge.collect_proposals(
                prices,
                market_contexts=market_contexts,
                positions=positions,
                deployable_pool=pool,
            )
        )
        rows.extend(
            self.funding_proposer.collect_proposals(
                prices,
                market_contexts=market_contexts,
                positions=positions,
                deployable_pool=pool,
            )
        )
        rows.extend(
            self.dca_bridge.collect_proposals(
                prices,
                market_contexts=market_contexts,
                positions=positions,
                deployable_pool=pool,
            )
        )
        return [self.scale_proposal(row, market_contexts) for row in rows if row]

    def scale_proposal(self, proposal, market_contexts=None):
        proposal = dict(proposal or {})
        fleet = str(proposal.get("fleet") or "BTC").upper()
        ctx = dict((market_contexts or {}).get(fleet, {}) or {})
        return self.volatility_sizer.scale_proposal(proposal, market_context=ctx)

    def status_snapshot(self):
        return {
            "grid_enabled": self.grid_bridge.enabled(),
            "funding_arb_enabled": self.funding_proposer.enabled(),
            "dca_enabled": self.dca_bridge.enabled(),
            "volatility_sizing": True,
        }
