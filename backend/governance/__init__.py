from .execution_governor import ExecutionGovernor
from .trade_proposal_service import TradeProposalService

__all__ = ["ExecutionGovernor", "TradeProposalService", "UpgradePipeline"]


def __getattr__(name):
    if name == "UpgradePipeline":
        from .upgrade_pipeline import UpgradePipeline

        return UpgradePipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
