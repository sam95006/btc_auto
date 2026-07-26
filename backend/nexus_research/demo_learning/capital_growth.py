"""TRACK 7 — Capital Growth Controller.

Manages risk tier progression (promotion/demotion) based on observed
performance windows.  Promotion is deliberate and slow; demotion is
fast and defensive.

No live patches.  No orders.  Research-only logic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_research.demo_strategy.risk_tiers import (
    RiskTier,
    RiskTierName,
    RISK_TIERS,
    TIER_PROGRESSION,
    get_tier,
)

RESEARCH_ONLY: bool = True


# ── Performance Window ────────────────────────────────────────────────────────

@dataclass
class PerformanceWindow:
    """Rolling window of trade outcomes for tier evaluation."""

    trades: list[dict[str, Any]] = field(default_factory=list)
    window_size: int = 20

    @property
    def count(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.get("pnl", 0) > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.get("pnl", 0) <= 0)

    @property
    def win_rate(self) -> float:
        return self.wins / self.count if self.count > 0 else 0.0

    @property
    def gross_profit(self) -> float:
        return sum(t["pnl"] for t in self.trades if t.get("pnl", 0) > 0)

    @property
    def gross_loss(self) -> float:
        return abs(sum(t["pnl"] for t in self.trades if t.get("pnl", 0) <= 0))

    @property
    def profit_factor(self) -> float:
        return self.gross_profit / self.gross_loss if self.gross_loss > 0 else float("inf")

    @property
    def expectancy(self) -> float:
        if self.count == 0:
            return 0.0
        return sum(t.get("pnl", 0) for t in self.trades) / self.count

    @property
    def max_consecutive_losses(self) -> int:
        max_streak = 0
        streak = 0
        for t in self.trades:
            if t.get("pnl", 0) <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    def add_trade(self, trade: dict[str, Any]) -> None:
        self.trades.append(trade)
        if len(self.trades) > self.window_size:
            self.trades = self.trades[-self.window_size:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "wins": self.wins,
            "losses": self.losses,
            "winRate": round(self.win_rate, 4),
            "profitFactor": round(self.profit_factor, 4) if self.profit_factor != float("inf") else 999.0,
            "expectancy": round(self.expectancy, 4),
            "maxConsecutiveLosses": self.max_consecutive_losses,
        }


# ── Equity High Water Mark ────────────────────────────────────────────────────

@dataclass
class EquityHighWaterMark:
    """Tracks all-time equity peak for drawdown calculation."""

    hwm: float = 0.0
    current_equity: float = 0.0
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def update(self, equity: float) -> bool:
        """Returns True if new HWM was set."""
        self.current_equity = equity
        self.updated_at_ms = int(time.time() * 1000)
        if equity > self.hwm:
            self.hwm = equity
            return True
        return False

    @property
    def drawdown_pct(self) -> float:
        if self.hwm <= 0:
            return 0.0
        return (self.hwm - self.current_equity) / self.hwm * 100.0

    @property
    def is_at_hwm(self) -> bool:
        return self.current_equity >= self.hwm

    def to_dict(self) -> dict[str, Any]:
        return {
            "hwm": self.hwm,
            "currentEquity": self.current_equity,
            "drawdownPct": round(self.drawdown_pct, 4),
            "isAtHwm": self.is_at_hwm,
            "updatedAtMs": self.updated_at_ms,
        }


# ── Drawdown Deleveraging ─────────────────────────────────────────────────────

class DrawdownDeleveraging:
    """Reduce risk budget when drawdown exceeds thresholds."""

    THRESHOLDS = [
        (5.0, 0.75),   # >5% DD → 75% budget
        (10.0, 0.50),  # >10% DD → 50% budget
        (15.0, 0.25),  # >15% DD → 25% budget
        (20.0, 0.0),   # >20% DD → halt trading
    ]

    def compute_multiplier(self, drawdown_pct: float) -> float:
        mult = 1.0
        for threshold, factor in self.THRESHOLDS:
            if drawdown_pct >= threshold:
                mult = factor
        return mult

    def should_halt(self, drawdown_pct: float) -> bool:
        return drawdown_pct >= 20.0


# ── Promotion Gate ────────────────────────────────────────────────────────────

class PromotionGateResult(str, Enum):
    PROMOTED = "PROMOTED"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"


@dataclass
class PromotionEvaluation:
    result: PromotionGateResult
    current_tier: RiskTierName
    target_tier: RiskTierName | None
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "currentTier": self.current_tier.value,
            "targetTier": self.target_tier.value if self.target_tier else None,
            "reasons": self.reasons,
            "metrics": self.metrics,
        }


class PromotionGate:
    """Evaluate readiness for tier upgrade.

    Requirements:
      - Minimum sample size (window full)
      - Expectancy > 0
      - Profit factor >= 1.3
      - Win rate in band 55-65%
      - Drawdown < 8%
      - No incidents in window
      - New HWM achieved
    """

    MIN_SAMPLE_SIZE: int = 10
    MIN_EXPECTANCY: float = 0.0
    MIN_PROFIT_FACTOR: float = 1.3
    MIN_WIN_RATE: float = 0.55
    MAX_WIN_RATE: float = 0.65
    MAX_DRAWDOWN_PCT: float = 8.0
    MAX_RISK_BUDGET_INCREASE_PCT: float = 20.0

    def evaluate(
        self,
        current_tier: RiskTierName,
        window: PerformanceWindow,
        hwm: EquityHighWaterMark,
        incidents: int = 0,
    ) -> PromotionEvaluation:
        tier_idx = TIER_PROGRESSION.index(current_tier)
        if tier_idx >= len(TIER_PROGRESSION) - 1:
            return PromotionEvaluation(
                result=PromotionGateResult.BLOCKED,
                current_tier=current_tier,
                target_tier=None,
                reasons=["Already at maximum tier"],
            )

        target_tier = TIER_PROGRESSION[tier_idx + 1]
        failures: list[str] = []
        metrics: dict[str, Any] = {}

        metrics["sampleSize"] = window.count
        if window.count < self.MIN_SAMPLE_SIZE:
            failures.append(f"Insufficient sample: {window.count} < {self.MIN_SAMPLE_SIZE}")

        metrics["expectancy"] = round(window.expectancy, 4)
        if window.expectancy <= self.MIN_EXPECTANCY:
            failures.append(f"Expectancy not positive: {window.expectancy:.4f}")

        metrics["profitFactor"] = round(window.profit_factor, 4) if window.profit_factor != float("inf") else 999.0
        if window.profit_factor < self.MIN_PROFIT_FACTOR:
            failures.append(f"PF below threshold: {window.profit_factor:.2f} < {self.MIN_PROFIT_FACTOR}")

        metrics["winRate"] = round(window.win_rate, 4)
        if window.win_rate < self.MIN_WIN_RATE:
            failures.append(f"Win rate too low: {window.win_rate:.2%} < {self.MIN_WIN_RATE:.0%}")
        elif window.win_rate > self.MAX_WIN_RATE:
            failures.append(f"Win rate suspiciously high: {window.win_rate:.2%} > {self.MAX_WIN_RATE:.0%}")

        metrics["drawdownPct"] = round(hwm.drawdown_pct, 4)
        if hwm.drawdown_pct > self.MAX_DRAWDOWN_PCT:
            failures.append(f"Drawdown too large: {hwm.drawdown_pct:.2f}% > {self.MAX_DRAWDOWN_PCT}%")

        metrics["incidents"] = incidents
        if incidents > 0:
            failures.append(f"Incidents in window: {incidents}")

        metrics["atHwm"] = hwm.is_at_hwm
        if not hwm.is_at_hwm:
            failures.append("Not at equity high water mark")

        if failures:
            return PromotionEvaluation(
                result=PromotionGateResult.NOT_READY,
                current_tier=current_tier,
                target_tier=target_tier,
                reasons=failures,
                metrics=metrics,
            )

        return PromotionEvaluation(
            result=PromotionGateResult.PROMOTED,
            current_tier=current_tier,
            target_tier=target_tier,
            reasons=["All promotion criteria met"],
            metrics=metrics,
        )


# ── Demotion Gate ─────────────────────────────────────────────────────────────

class DemotionTrigger(str, Enum):
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    NEGATIVE_EXPECTANCY = "NEGATIVE_EXPECTANCY"
    PF_DETERIORATION = "PF_DETERIORATION"
    DRAWDOWN_BREACH = "DRAWDOWN_BREACH"
    API_INCIDENT = "API_INCIDENT"
    DUPLICATE_DETECTION = "DUPLICATE_DETECTION"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"


@dataclass
class DemotionEvaluation:
    demoted: bool
    current_tier: RiskTierName
    target_tier: RiskTierName | None
    triggers: list[DemotionTrigger] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "demoted": self.demoted,
            "currentTier": self.current_tier.value,
            "targetTier": self.target_tier.value if self.target_tier else None,
            "triggers": [t.value for t in self.triggers],
            "reasons": self.reasons,
        }


class DemotionGate:
    """Fast demotion — faster than promotion (defensive).

    Triggers:
      - 3+ consecutive losses
      - Expectancy turns negative
      - PF drops below 1.0
      - Drawdown > 10%
      - API/duplicate/reconciliation incidents
    """

    MAX_CONSECUTIVE_LOSSES: int = 3
    MAX_DRAWDOWN_FOR_DEMOTION: float = 10.0
    MIN_PF_FOR_HOLD: float = 1.0

    def evaluate(
        self,
        current_tier: RiskTierName,
        window: PerformanceWindow,
        hwm: EquityHighWaterMark,
        *,
        api_incidents: int = 0,
        duplicate_detections: int = 0,
        recon_mismatches: int = 0,
    ) -> DemotionEvaluation:
        tier_idx = TIER_PROGRESSION.index(current_tier)
        if tier_idx <= 0:
            return DemotionEvaluation(
                demoted=False,
                current_tier=current_tier,
                target_tier=None,
                reasons=["Already at minimum tier"],
            )

        triggers: list[DemotionTrigger] = []
        reasons: list[str] = []

        if window.max_consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            triggers.append(DemotionTrigger.CONSECUTIVE_LOSSES)
            reasons.append(f"{window.max_consecutive_losses} consecutive losses")

        if window.count >= 5 and window.expectancy < 0:
            triggers.append(DemotionTrigger.NEGATIVE_EXPECTANCY)
            reasons.append(f"Negative expectancy: {window.expectancy:.4f}")

        if window.count >= 5 and window.profit_factor < self.MIN_PF_FOR_HOLD:
            triggers.append(DemotionTrigger.PF_DETERIORATION)
            reasons.append(f"PF below hold threshold: {window.profit_factor:.2f}")

        if hwm.drawdown_pct > self.MAX_DRAWDOWN_FOR_DEMOTION:
            triggers.append(DemotionTrigger.DRAWDOWN_BREACH)
            reasons.append(f"Drawdown breach: {hwm.drawdown_pct:.2f}%")

        if api_incidents > 0:
            triggers.append(DemotionTrigger.API_INCIDENT)
            reasons.append(f"API incidents: {api_incidents}")

        if duplicate_detections > 0:
            triggers.append(DemotionTrigger.DUPLICATE_DETECTION)
            reasons.append(f"Duplicate detections: {duplicate_detections}")

        if recon_mismatches > 0:
            triggers.append(DemotionTrigger.RECONCILIATION_MISMATCH)
            reasons.append(f"Reconciliation mismatches: {recon_mismatches}")

        if not triggers:
            return DemotionEvaluation(
                demoted=False,
                current_tier=current_tier,
                target_tier=None,
                reasons=["No demotion triggers"],
            )

        target_tier = TIER_PROGRESSION[tier_idx - 1]
        return DemotionEvaluation(
            demoted=True,
            current_tier=current_tier,
            target_tier=target_tier,
            triggers=triggers,
            reasons=reasons,
        )


# ── Capital Growth Controller (Orchestrator) ──────────────────────────────────

@dataclass
class GrowthState:
    """Serializable state for the capital growth controller."""

    current_tier: RiskTierName = RiskTierName.VALIDATION
    equity: float = 0.0
    hwm: EquityHighWaterMark = field(default_factory=EquityHighWaterMark)
    window: PerformanceWindow = field(default_factory=PerformanceWindow)
    incidents_in_window: int = 0
    api_incidents: int = 0
    duplicate_detections: int = 0
    recon_mismatches: int = 0
    promotions_count: int = 0
    demotions_count: int = 0
    last_evaluation_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "currentTier": self.current_tier.value,
            "equity": self.equity,
            "hwm": self.hwm.to_dict(),
            "window": self.window.to_dict(),
            "incidentsInWindow": self.incidents_in_window,
            "apiIncidents": self.api_incidents,
            "duplicateDetections": self.duplicate_detections,
            "reconMismatches": self.recon_mismatches,
            "promotionsCount": self.promotions_count,
            "demotionsCount": self.demotions_count,
            "lastEvaluationMs": self.last_evaluation_ms,
        }


class CapitalGrowthController:
    """Orchestrates tier progression: promotion (slow), demotion (fast).

    Risk budget upgrade is capped at +0.25 ppt (percentage points) per step,
    equivalent to a max ~10-20% relative increase depending on current tier.
    """

    MAX_BUDGET_INCREASE_PPT: float = 0.30

    def __init__(self, state: GrowthState | None = None) -> None:
        self.state = state or GrowthState()
        self._promotion_gate = PromotionGate()
        self._demotion_gate = DemotionGate()
        self._drawdown = DrawdownDeleveraging()

    @property
    def current_tier(self) -> RiskTier:
        return get_tier(self.state.current_tier)

    @property
    def drawdown_multiplier(self) -> float:
        return self._drawdown.compute_multiplier(self.state.hwm.drawdown_pct)

    @property
    def effective_risk_pct(self) -> float:
        tier = self.current_tier
        return tier.max_risk_pct * self.drawdown_multiplier

    def record_trade(self, trade: dict[str, Any]) -> None:
        self.state.window.add_trade(trade)

    def update_equity(self, equity: float) -> bool:
        """Update equity, returns True if new HWM."""
        self.state.equity = equity
        return self.state.hwm.update(equity)

    def record_incident(
        self,
        *,
        api: bool = False,
        duplicate: bool = False,
        recon: bool = False,
    ) -> None:
        self.state.incidents_in_window += 1
        if api:
            self.state.api_incidents += 1
        if duplicate:
            self.state.duplicate_detections += 1
        if recon:
            self.state.recon_mismatches += 1

    def evaluate(self) -> dict[str, Any]:
        """Run promotion/demotion evaluation. Returns evaluation result."""
        self.state.last_evaluation_ms = int(time.time() * 1000)

        demotion = self._demotion_gate.evaluate(
            self.state.current_tier,
            self.state.window,
            self.state.hwm,
            api_incidents=self.state.api_incidents,
            duplicate_detections=self.state.duplicate_detections,
            recon_mismatches=self.state.recon_mismatches,
        )

        if demotion.demoted and demotion.target_tier is not None:
            self.state.current_tier = demotion.target_tier
            self.state.demotions_count += 1
            self._reset_incident_counters()
            return {"action": "DEMOTED", "evaluation": demotion.to_dict()}

        promotion = self._promotion_gate.evaluate(
            self.state.current_tier,
            self.state.window,
            self.state.hwm,
            incidents=self.state.incidents_in_window,
        )

        if promotion.result == PromotionGateResult.PROMOTED and promotion.target_tier is not None:
            old_tier = get_tier(self.state.current_tier)
            new_tier = get_tier(promotion.target_tier)
            increase_ppt = new_tier.max_risk_pct - old_tier.max_risk_pct
            if increase_ppt <= self.MAX_BUDGET_INCREASE_PPT:
                self.state.current_tier = promotion.target_tier
                self.state.promotions_count += 1
                self._reset_incident_counters()
                return {"action": "PROMOTED", "evaluation": promotion.to_dict()}
            else:
                return {
                    "action": "PROMOTION_CAPPED",
                    "evaluation": promotion.to_dict(),
                    "reason": f"Budget increase {increase_ppt:.2f} ppt exceeds cap {self.MAX_BUDGET_INCREASE_PPT} ppt",
                }

        return {"action": "HOLD", "evaluation": promotion.to_dict()}

    def should_halt_trading(self) -> bool:
        return self._drawdown.should_halt(self.state.hwm.drawdown_pct)

    def get_state(self) -> dict[str, Any]:
        return self.state.to_dict()

    def _reset_incident_counters(self) -> None:
        self.state.incidents_in_window = 0
        self.state.api_incidents = 0
        self.state.duplicate_detections = 0
        self.state.recon_mismatches = 0
