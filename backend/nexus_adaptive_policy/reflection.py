"""Deep reflection, counterfactual analysis, and learning proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_adaptive_policy.failure_taxonomy import FailureClassification, FailureType
from backend.nexus_adaptive_policy.trade_case import ProcessQualityVerdict, TradeCase


class CounterfactualAction(str, Enum):
    RAISE_THRESHOLD = "raise_threshold"
    CHANGE_STRATEGY = "change_strategy"
    REDUCE_MARGIN = "reduce_margin"
    WAIT_CONFIRMATION = "wait_confirmation"
    EARLIER_EXIT = "earlier_exit"
    TIME_STOP = "time_stop"
    RISK_CRITIC_BLOCK = "risk_critic_block"
    PORTFOLIO_BLOCK = "portfolio_block"
    NO_TRADE = "no_trade"


ALL_COUNTERFACTUALS = tuple(CounterfactualAction)


@dataclass
class CounterfactualOutcome:
    action: CounterfactualAction
    expected_pnl_delta: float
    confidence: float
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "expected_pnl_delta": self.expected_pnl_delta,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


@dataclass
class LearningProposal:
    proposal_id: str
    case_id: str
    action: str
    parameter: str
    value: Any
    executable: bool = True
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "case_id": self.case_id,
            "action": self.action,
            "parameter": self.parameter,
            "value": self.value,
            "executable": self.executable,
            "rationale": self.rationale,
        }


class CounterfactualAnalyzer:
    """Generate structured counterfactuals for a trade case."""

    def analyze(self, case: TradeCase, failure: FailureClassification | None = None) -> list[CounterfactualOutcome]:
        out: list[CounterfactualOutcome] = []
        ft = failure.failure_type if failure else FailureType.UNKNOWN
        if ft in {FailureType.ENTRY_TOO_EARLY, FailureType.CHASE_ENTRY}:
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.WAIT_CONFIRMATION,
                    expected_pnl_delta=abs(case.pnl_usd) * 0.3,
                    confidence=0.65,
                    rationale="wait for confirmation candle",
                )
            )
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.RAISE_THRESHOLD,
                    expected_pnl_delta=abs(case.pnl_usd) * 0.2,
                    confidence=0.6,
                    rationale="raise entry threshold",
                )
            )
        if ft == FailureType.REGIME_MISMATCH:
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.CHANGE_STRATEGY,
                    expected_pnl_delta=abs(case.pnl_usd) * 0.4,
                    confidence=0.7,
                    rationale="route to regime-aligned strategy",
                )
            )
        if case.process_verdict == ProcessQualityVerdict.BAD_PROCESS_WIN:
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.RISK_CRITIC_BLOCK,
                    expected_pnl_delta=-case.pnl_usd,
                    confidence=0.55,
                    rationale="block low-quality win",
                )
            )
        if case.is_loss():
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.REDUCE_MARGIN,
                    expected_pnl_delta=case.pnl_usd * 0.5,
                    confidence=0.5,
                    rationale="smaller loss with reduced margin",
                )
            )
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.TIME_STOP,
                    expected_pnl_delta=case.pnl_usd * 0.3,
                    confidence=0.45,
                    rationale="cap holding period",
                )
            )
        if not out:
            out.append(
                CounterfactualOutcome(
                    CounterfactualAction.NO_TRADE,
                    expected_pnl_delta=0.0,
                    confidence=0.4,
                    rationale="skip ambiguous case",
                )
            )
        return out


class LearningProposalGenerator:
    """Emit executable proposals only — no vague tune_thresholds text alone."""

    _seq = 0

    def generate(
        self,
        case: TradeCase,
        counterfactuals: list[CounterfactualOutcome],
    ) -> list[LearningProposal]:
        proposals: list[LearningProposal] = []
        for cf in counterfactuals:
            prop = self._from_counterfactual(case, cf)
            if prop:
                proposals.append(prop)
        return proposals

    def _from_counterfactual(self, case: TradeCase, cf: CounterfactualOutcome) -> LearningProposal | None:
        LearningProposalGenerator._seq += 1
        pid = f"proposal_{LearningProposalGenerator._seq:06d}"
        mapping = {
            CounterfactualAction.RAISE_THRESHOLD: ("set_entry_threshold", "min_score_delta", 0.05),
            CounterfactualAction.CHANGE_STRATEGY: ("set_strategy_route", "strategy_id", "regime_aligned"),
            CounterfactualAction.REDUCE_MARGIN: ("set_margin_cap_multiplier", "multiplier", 0.5),
            CounterfactualAction.WAIT_CONFIRMATION: ("require_confirmation", "candles", 1),
            CounterfactualAction.EARLIER_EXIT: ("set_exit_rule", "take_profit_early_pct", 0.5),
            CounterfactualAction.TIME_STOP: ("set_time_stop", "minutes", 45),
            CounterfactualAction.RISK_CRITIC_BLOCK: ("enable_risk_critic_block", "enabled", True),
            CounterfactualAction.PORTFOLIO_BLOCK: ("enable_portfolio_block", "enabled", True),
            CounterfactualAction.NO_TRADE: ("set_no_trade_window", "minutes", 15),
        }
        if cf.action not in mapping:
            return None
        action, parameter, value = mapping[cf.action]
        return LearningProposal(
            proposal_id=pid,
            case_id=case.case_id,
            action=action,
            parameter=parameter,
            value=value,
            executable=True,
            rationale=cf.rationale,
        )


class DeepReflectionEngine:
    """Orchestrate reflection over trade cases."""

    def __init__(self) -> None:
        self.counterfactuals = CounterfactualAnalyzer()
        self.proposals = LearningProposalGenerator()

    def reflect(
        self,
        case: TradeCase,
        failure: FailureClassification | None = None,
    ) -> dict[str, Any]:
        cfs = self.counterfactuals.analyze(case, failure)
        props = self.proposals.generate(case, cfs)
        return {
            "case_id": case.case_id,
            "process_verdict": case.process_verdict.value,
            "strategy_failure": case.is_strategy_failure(),
            "counterfactuals": [c.to_dict() for c in cfs],
            "proposals": [p.to_dict() for p in props],
        }
