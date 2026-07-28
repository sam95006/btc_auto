"""Trade case records and process-quality verdicts."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProcessQualityVerdict(str, Enum):
    GOOD_PROCESS_WIN = "GOOD_PROCESS_WIN"
    GOOD_PROCESS_LOSS = "GOOD_PROCESS_LOSS"
    BAD_PROCESS_WIN = "BAD_PROCESS_WIN"
    BAD_PROCESS_LOSS = "BAD_PROCESS_LOSS"
    INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"


@dataclass
class TradeCase:
    case_id: str
    symbol: str
    side: str
    leverage: int
    margin_usd: float
    pnl_usd: float
    process_verdict: ProcessQualityVerdict
    strategy_id: str = "unknown"
    evidence_complete: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_win(self) -> bool:
        return self.pnl_usd > 0

    def is_loss(self) -> bool:
        return self.pnl_usd < 0

    def is_strategy_failure(self) -> bool:
        """Loss alone does not imply strategy failure."""
        if self.process_verdict == ProcessQualityVerdict.INCOMPLETE_EVIDENCE:
            return False
        return self.process_verdict in {
            ProcessQualityVerdict.BAD_PROCESS_LOSS,
            ProcessQualityVerdict.BAD_PROCESS_WIN,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "symbol": self.symbol,
            "side": self.side,
            "leverage": self.leverage,
            "margin_usd": self.margin_usd,
            "pnl_usd": self.pnl_usd,
            "process_verdict": self.process_verdict.value,
            "strategy_id": self.strategy_id,
            "evidence_complete": self.evidence_complete,
            "is_win": self.is_win(),
            "is_strategy_failure": self.is_strategy_failure(),
            "metadata": dict(self.metadata),
        }


def classify_process_quality(
    *,
    pnl_usd: float,
    followed_plan: bool,
    evidence_complete: bool,
    risk_rules_followed: bool,
) -> ProcessQualityVerdict:
    if not evidence_complete:
        return ProcessQualityVerdict.INCOMPLETE_EVIDENCE
    good_process = followed_plan and risk_rules_followed
    win = pnl_usd > 0
    if good_process and win:
        return ProcessQualityVerdict.GOOD_PROCESS_WIN
    if good_process and not win:
        return ProcessQualityVerdict.GOOD_PROCESS_LOSS
    if not good_process and win:
        return ProcessQualityVerdict.BAD_PROCESS_WIN
    return ProcessQualityVerdict.BAD_PROCESS_LOSS
