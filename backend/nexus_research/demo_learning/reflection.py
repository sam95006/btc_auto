"""TRACK 8 — Reflection & Closed-Loop Learning.

Post-trade reflection pipeline that classifies errors, captures decision
snapshots, evaluates execution quality, and produces candidate patches.

CRITICAL: Reflection must NOT auto-modify live strategy.
Pipeline stops at MANUAL_REVIEW / CANDIDATE_PATCH stage.

No live patches.  No orders.  Research-only logic.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


RESEARCH_ONLY: bool = True


# ── Error Taxonomy ────────────────────────────────────────────────────────────

class ErrorType(str, Enum):
    MARKET_DIRECTION_ERROR = "MARKET_DIRECTION_ERROR"
    REGIME_MISCLASSIFICATION = "REGIME_MISCLASSIFICATION"
    ENTRY_TOO_EARLY = "ENTRY_TOO_EARLY"
    ENTRY_TOO_LATE = "ENTRY_TOO_LATE"
    EXIT_TOO_EARLY = "EXIT_TOO_EARLY"
    EXIT_TOO_LATE = "EXIT_TOO_LATE"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SLIPPAGE_EXCESSIVE = "SLIPPAGE_EXCESSIVE"
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    STOP_TOO_WIDE = "STOP_TOO_WIDE"
    POSITION_TOO_LARGE = "POSITION_TOO_LARGE"
    POSITION_TOO_SMALL = "POSITION_TOO_SMALL"
    LEVERAGE_TOO_HIGH = "LEVERAGE_TOO_HIGH"
    LEVERAGE_MISMATCH = "LEVERAGE_MISMATCH"  # legacy alias path
    FEE_DRAG = "FEE_DRAG"
    FUNDING_DRAG = "FUNDING_DRAG"
    FUNDING_RATE_IGNORED = "FUNDING_RATE_IGNORED"
    DUPLICATE_ORDER_RISK = "DUPLICATE_ORDER_RISK"
    AMBIGUOUS_TIMEOUT = "AMBIGUOUS_TIMEOUT"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    STALE_DATA = "STALE_DATA"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    LIQUIDITY_MISJUDGMENT = "LIQUIDITY_MISJUDGMENT"
    CORRELATION_BLINDNESS = "CORRELATION_BLINDNESS"
    NEWS_EVENT_MISSED = "NEWS_EVENT_MISSED"
    OVERTRADING = "OVERTRADING"
    REVENGE_TRADE = "REVENGE_TRADE"
    FOMO_ENTRY = "FOMO_ENTRY"
    NO_ERROR = "NO_ERROR"
    UNCLASSIFIED = "UNCLASSIFIED"


# Required Track-8 taxonomy (must remain stable for classifiers / UI contracts).
REQUIRED_REFLECTION_TAXONOMY: frozenset[str] = frozenset({
    "MARKET_DIRECTION_ERROR",
    "REGIME_MISCLASSIFICATION",
    "ENTRY_TOO_EARLY",
    "ENTRY_TOO_LATE",
    "SPREAD_TOO_WIDE",
    "SLIPPAGE_EXCESSIVE",
    "STOP_TOO_TIGHT",
    "STOP_TOO_WIDE",
    "POSITION_TOO_LARGE",
    "LEVERAGE_TOO_HIGH",
    "FEE_DRAG",
    "FUNDING_DRAG",
    "DUPLICATE_ORDER_RISK",
    "AMBIGUOUS_TIMEOUT",
    "RECONCILIATION_MISMATCH",
    "STALE_DATA",
    "PROVIDER_FAILURE",
    "EXIT_TOO_EARLY",
    "EXIT_TOO_LATE",
})


# ── Market Snapshot ───────────────────────────────────────────────────────────

@dataclass
class MarketSnapshot:
    """Market conditions at the time of decision."""

    symbol: str
    price: float
    timestamp_ms: int
    volatility_1h: float = 0.0
    volume_24h: float = 0.0
    trend_bias: str = "NEUTRAL"
    regime: str = "UNKNOWN"
    funding_rate: float = 0.0
    orderbook_imbalance: float = 0.0
    nearby_levels: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "timestampMs": self.timestamp_ms,
            "volatility1h": self.volatility_1h,
            "volume24h": self.volume_24h,
            "trendBias": self.trend_bias,
            "regime": self.regime,
            "fundingRate": self.funding_rate,
            "orderbookImbalance": self.orderbook_imbalance,
            "nearbyLevels": self.nearby_levels,
        }


# ── Decision Snapshot ─────────────────────────────────────────────────────────

@dataclass
class DecisionSnapshot:
    """Full snapshot of the decision context at entry/exit."""

    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    action: str = ""  # ENTER_LONG, ENTER_SHORT, EXIT_LONG, EXIT_SHORT
    market: MarketSnapshot | None = None
    signals_used: list[str] = field(default_factory=list)
    confidence: float = 0.0
    risk_tier: str = ""
    reasoning: str = ""
    alternatives_considered: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisionId": self.decision_id,
            "timestampMs": self.timestamp_ms,
            "action": self.action,
            "market": self.market.to_dict() if self.market else None,
            "signalsUsed": self.signals_used,
            "confidence": self.confidence,
            "riskTier": self.risk_tier,
            "reasoning": self.reasoning,
            "alternativesConsidered": self.alternatives_considered,
        }


# ── Entry/Exit Quality ────────────────────────────────────────────────────────

@dataclass
class EntryQuality:
    """Measures how good the entry was relative to optimal."""

    entry_price: float
    optimal_entry_price: float  # best price in next N bars
    slippage_bps: float = 0.0
    timing_score: float = 0.0  # 0-1, 1 = perfect timing
    level_respect: bool = False  # entered near a key level?

    @property
    def entry_efficiency(self) -> float:
        if self.optimal_entry_price == 0:
            return 0.0
        diff = abs(self.entry_price - self.optimal_entry_price)
        return max(0.0, 1.0 - diff / self.optimal_entry_price)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entryPrice": self.entry_price,
            "optimalEntryPrice": self.optimal_entry_price,
            "slippageBps": self.slippage_bps,
            "timingScore": self.timing_score,
            "levelRespect": self.level_respect,
            "entryEfficiency": round(self.entry_efficiency, 4),
        }


@dataclass
class ExitQuality:
    """Measures how good the exit was relative to optimal."""

    exit_price: float
    optimal_exit_price: float  # best price before reversal
    held_duration_ms: int = 0
    exit_reason: str = ""  # STOP_HIT, TAKE_PROFIT, TRAILING, MANUAL, TIME_EXIT
    profit_captured_pct: float = 0.0  # % of available move captured

    def to_dict(self) -> dict[str, Any]:
        return {
            "exitPrice": self.exit_price,
            "optimalExitPrice": self.optimal_exit_price,
            "heldDurationMs": self.held_duration_ms,
            "exitReason": self.exit_reason,
            "profitCapturedPct": round(self.profit_captured_pct, 4),
        }


# ── Risk Compliance ───────────────────────────────────────────────────────────

@dataclass
class RiskCompliance:
    """Was the trade within risk parameters?"""

    within_risk_budget: bool = True
    actual_risk_pct: float = 0.0
    allowed_risk_pct: float = 0.0
    leverage_compliant: bool = True
    position_size_compliant: bool = True
    stop_placed: bool = True
    stop_respected: bool = True
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "withinRiskBudget": self.within_risk_budget,
            "actualRiskPct": self.actual_risk_pct,
            "allowedRiskPct": self.allowed_risk_pct,
            "leverageCompliant": self.leverage_compliant,
            "positionSizeCompliant": self.position_size_compliant,
            "stopPlaced": self.stop_placed,
            "stopRespected": self.stop_respected,
            "violations": self.violations,
        }


# ── Execution Quality Report ──────────────────────────────────────────────────

@dataclass
class ExecutionQualityReport:
    """Comprehensive execution quality analysis."""

    trade_id: str
    entry_quality: EntryQuality | None = None
    exit_quality: ExitQuality | None = None
    risk_compliance: RiskCompliance | None = None
    overall_score: float = 0.0  # 0-100

    def to_dict(self) -> dict[str, Any]:
        return {
            "tradeId": self.trade_id,
            "entryQuality": self.entry_quality.to_dict() if self.entry_quality else None,
            "exitQuality": self.exit_quality.to_dict() if self.exit_quality else None,
            "riskCompliance": self.risk_compliance.to_dict() if self.risk_compliance else None,
            "overallScore": round(self.overall_score, 2),
        }


# ── Demo Trade Outcome ────────────────────────────────────────────────────────

@dataclass
class DemoTradeOutcome:
    """Full outcome record for a closed demo trade."""

    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    qty: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees_paid: float = 0.0
    duration_ms: int = 0
    entry_decision: DecisionSnapshot | None = None
    exit_decision: DecisionSnapshot | None = None
    entry_market: MarketSnapshot | None = None
    exit_market: MarketSnapshot | None = None
    execution_report: ExecutionQualityReport | None = None
    error_classifications: list[ErrorType] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    closed_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "tradeId": self.trade_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entryPrice": self.entry_price,
            "exitPrice": self.exit_price,
            "qty": self.qty,
            "pnl": self.pnl,
            "pnlPct": self.pnl_pct,
            "feesPaid": self.fees_paid,
            "durationMs": self.duration_ms,
            "entryDecision": self.entry_decision.to_dict() if self.entry_decision else None,
            "exitDecision": self.exit_decision.to_dict() if self.exit_decision else None,
            "entryMarket": self.entry_market.to_dict() if self.entry_market else None,
            "exitMarket": self.exit_market.to_dict() if self.exit_market else None,
            "executionReport": self.execution_report.to_dict() if self.execution_report else None,
            "errorClassifications": [e.value for e in self.error_classifications],
            "lessons": self.lessons,
            "closedAtMs": self.closed_at_ms,
        }


# ── Reflection Classifier ────────────────────────────────────────────────────

class ReflectionClassifier:
    """Classifies trade errors from outcome data.

    Uses heuristic rules to assign ErrorType labels.
    Does NOT auto-modify strategy.
    """

    def classify(self, outcome: DemoTradeOutcome) -> list[ErrorType]:
        errors: list[ErrorType] = []

        # Operational / infra labels can attach even on winning trades.
        lesson_blob = " ".join(outcome.lessons).upper()
        if "AMBIGUOUS_TIMEOUT" in lesson_blob or "TIMEOUT_AMBIGUOUS" in lesson_blob:
            errors.append(ErrorType.AMBIGUOUS_TIMEOUT)
        if "RECONCILIATION_MISMATCH" in lesson_blob:
            errors.append(ErrorType.RECONCILIATION_MISMATCH)
        if "DUPLICATE_ORDER" in lesson_blob:
            errors.append(ErrorType.DUPLICATE_ORDER_RISK)
        if "STALE_DATA" in lesson_blob:
            errors.append(ErrorType.STALE_DATA)
        if "PROVIDER_FAILURE" in lesson_blob:
            errors.append(ErrorType.PROVIDER_FAILURE)

        if outcome.pnl >= 0 and not errors:
            return [ErrorType.NO_ERROR]
        if outcome.pnl >= 0:
            return errors

        if outcome.entry_market and outcome.exit_market:
            entry_trend = outcome.entry_market.trend_bias
            if outcome.direction == "LONG" and entry_trend == "BEARISH":
                errors.append(ErrorType.MARKET_DIRECTION_ERROR)
            elif outcome.direction == "SHORT" and entry_trend == "BULLISH":
                errors.append(ErrorType.MARKET_DIRECTION_ERROR)

        if outcome.entry_market and outcome.entry_market.regime == "UNKNOWN":
            errors.append(ErrorType.REGIME_MISCLASSIFICATION)

        if outcome.execution_report and outcome.execution_report.entry_quality:
            eq = outcome.execution_report.entry_quality
            if eq.slippage_bps > 10.0:
                errors.append(ErrorType.SLIPPAGE_EXCESSIVE)
            if eq.timing_score < 0.3:
                if outcome.entry_price > eq.optimal_entry_price and outcome.direction == "LONG":
                    errors.append(ErrorType.ENTRY_TOO_LATE)
                elif outcome.entry_price < eq.optimal_entry_price and outcome.direction == "SHORT":
                    errors.append(ErrorType.ENTRY_TOO_LATE)
                else:
                    errors.append(ErrorType.ENTRY_TOO_EARLY)

        if outcome.execution_report and outcome.execution_report.exit_quality:
            xq = outcome.execution_report.exit_quality
            if xq.exit_reason == "STOP_HIT" and xq.profit_captured_pct < -50:
                errors.append(ErrorType.STOP_TOO_TIGHT)
            elif xq.profit_captured_pct < 20 and xq.exit_reason != "STOP_HIT":
                errors.append(ErrorType.EXIT_TOO_LATE)

        if outcome.execution_report and outcome.execution_report.risk_compliance:
            rc = outcome.execution_report.risk_compliance
            if not rc.within_risk_budget:
                errors.append(ErrorType.POSITION_TOO_LARGE)
            if not rc.leverage_compliant:
                errors.append(ErrorType.LEVERAGE_TOO_HIGH)
            viol = " ".join(rc.violations).upper()
            if "SPREAD" in viol:
                errors.append(ErrorType.SPREAD_TOO_WIDE)
            if "STOP_WIDE" in viol:
                errors.append(ErrorType.STOP_TOO_WIDE)

        if outcome.fees_paid > 0 and abs(outcome.pnl) > 0:
            if outcome.fees_paid >= abs(outcome.pnl) * 0.5:
                errors.append(ErrorType.FEE_DRAG)

        if outcome.entry_market and abs(outcome.entry_market.funding_rate) >= 0.001:
            # High funding relative to a small losing trade.
            if abs(outcome.pnl) > 0 and abs(outcome.entry_market.funding_rate) * abs(outcome.qty) * outcome.entry_price >= abs(outcome.pnl) * 0.25:
                errors.append(ErrorType.FUNDING_DRAG)

        if not errors:
            errors.append(ErrorType.UNCLASSIFIED)

        return errors


# ── Patch Proposal ────────────────────────────────────────────────────────────

class PatchStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLIED = "APPLIED"


@dataclass
class PatchProposal:
    """A proposed strategy modification derived from reflection.

    Pipeline stops at MANUAL_REVIEW — never auto-applies.
    """

    patch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: PatchStatus = PatchStatus.CANDIDATE
    source_trade_id: str = ""
    error_types: list[ErrorType] = field(default_factory=list)
    description: str = ""
    parameter_changes: dict[str, Any] = field(default_factory=dict)
    expected_improvement: str = ""
    confidence: float = 0.0
    requires_backtest: bool = True
    requires_walkforward: bool = True
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "patchId": self.patch_id,
            "status": self.status.value,
            "sourceTradeId": self.source_trade_id,
            "errorTypes": [e.value for e in self.error_types],
            "description": self.description,
            "parameterChanges": self.parameter_changes,
            "expectedImprovement": self.expected_improvement,
            "confidence": self.confidence,
            "requiresBacktest": self.requires_backtest,
            "requiresWalkforward": self.requires_walkforward,
            "createdAtMs": self.created_at_ms,
        }


# ── Patch Promotion Gate ──────────────────────────────────────────────────────

class PatchPromotionGate:
    """Gate for promoting patches from CANDIDATE → MANUAL_REVIEW.

    A patch is promoted to review only if:
      - backtest shows improvement
      - walkforward confirms
      - OOS does not degrade

    Never auto-applies to live strategy.
    """

    def evaluate(
        self,
        patch: PatchProposal,
        *,
        backtest_improved: bool = False,
        walkforward_confirmed: bool = False,
        oos_no_degradation: bool = False,
    ) -> PatchProposal:
        if patch.status != PatchStatus.CANDIDATE:
            return patch

        if backtest_improved and walkforward_confirmed and oos_no_degradation:
            patch.status = PatchStatus.MANUAL_REVIEW
        return patch


# ── Replay / WalkForward / OOS Request Stubs ──────────────────────────────────

@dataclass
class ReplayRequest:
    """Request to replay a trade scenario with modified parameters."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trade_id: str = ""
    patch_id: str = ""
    modified_params: dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "tradeId": self.trade_id,
            "patchId": self.patch_id,
            "modifiedParams": self.modified_params,
            "status": self.status,
            "result": self.result,
        }


@dataclass
class WalkForwardRequest:
    """Request walk-forward validation of a proposed patch."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    patch_id: str = ""
    window_count: int = 5
    status: str = "PENDING"
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "patchId": self.patch_id,
            "windowCount": self.window_count,
            "status": self.status,
            "result": self.result,
        }


@dataclass
class OOSValidationRequest:
    """Request out-of-sample validation of a proposed patch."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    patch_id: str = ""
    oos_period_days: int = 30
    status: str = "PENDING"
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "patchId": self.patch_id,
            "oosPeriodDays": self.oos_period_days,
            "status": self.status,
            "result": self.result,
        }


# ── Reflection Pipeline ───────────────────────────────────────────────────────

class ReflectionPipeline:
    """Orchestrates the full reflection loop.

    Flow:
      1. Receive DemoTradeOutcome
      2. Classify errors
      3. Generate PatchProposal (CANDIDATE)
      4. Request Replay/WalkForward/OOS (stubs)
      5. Evaluate via PatchPromotionGate → MANUAL_REVIEW
      6. STOP — human reviews

    Never auto-applies patches to live strategy.
    """

    def __init__(self) -> None:
        self._classifier = ReflectionClassifier()
        self._patch_gate = PatchPromotionGate()
        self._outcomes: list[DemoTradeOutcome] = []
        self._patches: list[PatchProposal] = []
        self._replay_requests: list[ReplayRequest] = []
        self._walkforward_requests: list[WalkForwardRequest] = []
        self._oos_requests: list[OOSValidationRequest] = []

    def reflect(self, outcome: DemoTradeOutcome) -> dict[str, Any]:
        """Run reflection on a trade outcome. Returns analysis."""
        errors = self._classifier.classify(outcome)
        outcome.error_classifications = errors
        self._outcomes.append(outcome)

        result: dict[str, Any] = {
            "tradeId": outcome.trade_id,
            "errors": [e.value for e in errors],
            "pnl": outcome.pnl,
            "patch": None,
            "replayRequest": None,
        }

        if ErrorType.NO_ERROR in errors:
            return result

        patch = self._generate_patch(outcome, errors)
        self._patches.append(patch)
        result["patch"] = patch.to_dict()

        replay = ReplayRequest(trade_id=outcome.trade_id, patch_id=patch.patch_id)
        self._replay_requests.append(replay)
        result["replayRequest"] = replay.to_dict()

        return result

    def promote_patch(
        self,
        patch_id: str,
        *,
        backtest_improved: bool = False,
        walkforward_confirmed: bool = False,
        oos_no_degradation: bool = False,
    ) -> PatchProposal | None:
        """Attempt to promote a patch. Returns updated patch or None."""
        for patch in self._patches:
            if patch.patch_id == patch_id:
                self._patch_gate.evaluate(
                    patch,
                    backtest_improved=backtest_improved,
                    walkforward_confirmed=walkforward_confirmed,
                    oos_no_degradation=oos_no_degradation,
                )
                return patch
        return None

    def get_patches(self, status: PatchStatus | None = None) -> list[PatchProposal]:
        if status is None:
            return list(self._patches)
        return [p for p in self._patches if p.status == status]

    def get_outcomes(self) -> list[DemoTradeOutcome]:
        return list(self._outcomes)

    def _generate_patch(
        self, outcome: DemoTradeOutcome, errors: list[ErrorType]
    ) -> PatchProposal:
        """Generate a candidate patch from classified errors."""
        param_changes: dict[str, Any] = {}
        description_parts: list[str] = []

        for error in errors:
            if error == ErrorType.STOP_TOO_TIGHT:
                param_changes["stop_buffer_multiplier"] = 1.2
                description_parts.append("Widen stop buffer by 20%")
            elif error == ErrorType.STOP_TOO_WIDE:
                param_changes["stop_buffer_multiplier"] = 0.85
                description_parts.append("Tighten stop buffer by 15%")
            elif error == ErrorType.ENTRY_TOO_EARLY:
                param_changes["entry_confirmation_bars"] = 2
                description_parts.append("Require 2 confirmation bars before entry")
            elif error == ErrorType.ENTRY_TOO_LATE:
                param_changes["entry_aggression"] = 1.1
                description_parts.append("Increase entry aggression")
            elif error == ErrorType.EXIT_TOO_LATE:
                param_changes["trailing_stop_activation_pct"] = 0.5
                description_parts.append("Activate trailing stop earlier")
            elif error == ErrorType.POSITION_TOO_LARGE:
                param_changes["risk_pct_override"] = -0.1
                description_parts.append("Reduce position size by 10%")
            elif error == ErrorType.MARKET_DIRECTION_ERROR:
                param_changes["trend_filter_strength"] = 1.5
                description_parts.append("Strengthen trend filter")
            elif error == ErrorType.REGIME_MISCLASSIFICATION:
                param_changes["regime_lookback_periods"] = 30
                description_parts.append("Extend regime lookback window")

        return PatchProposal(
            source_trade_id=outcome.trade_id,
            error_types=errors,
            description="; ".join(description_parts) if description_parts else "Unclassified error — needs manual analysis",
            parameter_changes=param_changes,
            expected_improvement="Reduce recurrence of classified error types",
            confidence=0.4 if len(param_changes) > 0 else 0.1,
            requires_backtest=True,
            requires_walkforward=True,
        )
