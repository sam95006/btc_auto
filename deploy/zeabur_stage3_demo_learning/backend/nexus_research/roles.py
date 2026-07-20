"""Role-based analysts + Decision Orchestrator for Phase 5 Gate B.

Roles: Market Context, Structure, Risk Critic, Portfolio, Performance,
       Reflection, Decision Orchestrator.
All deterministic RULES mode when no LLM available.
Research decisions: WATCH_ONLY | REJECTED | RISK_BLOCKED |
                    READY_FOR_SIMULATION | EXPIRED.
Does NOT call real order execution.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from backend.nexus_research.domain_events import (
    RESEARCH_DECISION_PRODUCED,
    ROLE_ASSESSMENT_COMPLETED,
    ROLE_ASSESSMENT_STARTED,
    publish_event,
)
from backend.nexus_research.storage import get_research_store

logger = logging.getLogger(__name__)

# ── Decision statuses ────────────────────────────────────────────────────────
DECISION_WATCH_ONLY = "WATCH_ONLY"
DECISION_REJECTED = "REJECTED"
DECISION_RISK_BLOCKED = "RISK_BLOCKED"
DECISION_READY_FOR_SIMULATION = "READY_FOR_SIMULATION"
DECISION_EXPIRED = "EXPIRED"

# ── Analysis modes ───────────────────────────────────────────────────────────
MODE_RULES = "RULES"
MODE_LLM = "LLM"


def _ts() -> int:
    return int(time.time() * 1000)


class RoleAssessment:
    def __init__(
        self,
        role: str,
        symbol: str,
        direction: str,
        analysis_mode: str,
        verdict: str,
        confidence: float,
        rationale: str,
        signals: dict[str, Any],
        flags: list[str] | None = None,
    ) -> None:
        self.role = role
        self.symbol = symbol
        self.direction = direction
        self.analysis_mode = analysis_mode
        self.verdict = verdict
        self.confidence = confidence
        self.rationale = rationale
        self.signals = signals
        self.flags = flags or []
        self.assessed_at = _ts()
        self.researchOnly = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "symbol": self.symbol,
            "direction": self.direction,
            "analysisMode": self.analysis_mode,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "signals": self.signals,
            "flags": self.flags,
            "assessedAt": self.assessed_at,
            "researchOnly": True,
        }


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ── Individual role analysts ─────────────────────────────────────────────────

class MarketContextAnalyst:
    role = "MARKET_CONTEXT"

    def assess(self, candidate: dict[str, Any], context: dict[str, Any]) -> RoleAssessment:
        publish_event(ROLE_ASSESSMENT_STARTED, {"role": self.role, "symbol": candidate.get("symbol")})
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or candidate.get("direction") or "LONG")
        change24h = _safe_float(candidate.get("change24hPct"))
        funding = _safe_float(candidate.get("fundingRate"))
        flags = []

        # Deterministic rules
        if abs(change24h) > 15:
            flags.append("HIGH_VOLATILITY_24H")
        if direction == "LONG" and change24h < -5:
            flags.append("ADVERSE_TREND_LONG")
        if direction == "SHORT" and change24h > 5:
            flags.append("ADVERSE_TREND_SHORT")
        if abs(funding) > 0.001:
            flags.append("HIGH_FUNDING")

        verdict = "NEUTRAL"
        confidence = 0.5
        if not flags:
            verdict = "FAVORABLE"
            confidence = 0.65
        elif len(flags) >= 2:
            verdict = "UNFAVORABLE"
            confidence = 0.7

        rationale = (
            f"24h change {change24h:+.2f}%; funding {funding:.4f}; "
            f"flags: {', '.join(flags) or 'none'}"
        )
        result = RoleAssessment(
            role=self.role, symbol=sym, direction=direction,
            analysis_mode=MODE_RULES, verdict=verdict, confidence=confidence,
            rationale=rationale,
            signals={"change24hPct": change24h, "fundingRate": funding},
            flags=flags,
        )
        publish_event(ROLE_ASSESSMENT_COMPLETED, {"role": self.role, "symbol": sym, "verdict": verdict})
        get_research_store().append("role_assessments", result.to_dict())
        return result


class StructureAnalyst:
    role = "STRUCTURE"

    def assess(self, candidate: dict[str, Any], context: dict[str, Any]) -> RoleAssessment:
        publish_event(ROLE_ASSESSMENT_STARTED, {"role": self.role, "symbol": candidate.get("symbol")})
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or "LONG")
        oi_change = _safe_float(candidate.get("oiChange5mPct"))
        price_change = _safe_float(candidate.get("priceChange5mPct"))
        spread_bps = _safe_float(candidate.get("spreadBps"))
        flags = []

        if spread_bps > 20:
            flags.append("WIDE_SPREAD")
        if oi_change == 0:
            flags.append("FLAT_OI")

        # Long: rising price + rising OI = structural confirmation
        aligned = (
            (direction == "LONG" and price_change > 0 and oi_change > 0)
            or (direction == "SHORT" and price_change < 0 and oi_change > 0)
        )
        verdict = "ALIGNED" if aligned else "UNALIGNED"
        confidence = 0.6 if aligned else 0.55
        if flags:
            confidence -= 0.1

        rationale = (
            f"5m price {price_change:+.3f}%; OI {oi_change:+.3f}%; "
            f"spread {spread_bps:.1f}bps; structure={'ALIGNED' if aligned else 'UNALIGNED'}"
        )
        result = RoleAssessment(
            role=self.role, symbol=sym, direction=direction,
            analysis_mode=MODE_RULES, verdict=verdict, confidence=confidence,
            rationale=rationale,
            signals={"oiChange5mPct": oi_change, "priceChange5mPct": price_change, "spreadBps": spread_bps},
            flags=flags,
        )
        publish_event(ROLE_ASSESSMENT_COMPLETED, {"role": self.role, "symbol": sym, "verdict": verdict})
        get_research_store().append("role_assessments", result.to_dict())
        return result


class RiskCriticAnalyst:
    role = "RISK_CRITIC"

    def assess(self, candidate: dict[str, Any], context: dict[str, Any]) -> RoleAssessment:
        publish_event(ROLE_ASSESSMENT_STARTED, {"role": self.role, "symbol": candidate.get("symbol")})
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or "LONG")
        risk_score = _safe_float(candidate.get("riskScore"))
        stage = str(candidate.get("stage") or "")
        collecting = bool(candidate.get("collecting"))
        flags = []

        if collecting:
            flags.append("INSUFFICIENT_HISTORY")
        if risk_score >= 70:
            flags.append("HIGH_RISK_SCORE")
        if stage == "OVEREXTENDED":
            flags.append("OVEREXTENDED")
        if risk_score >= 85:
            flags.append("CRITICAL_RISK")

        blocked = "HIGH_RISK_SCORE" in flags or "CRITICAL_RISK" in flags or "OVEREXTENDED" in flags
        verdict = "BLOCKED" if blocked else ("CAUTION" if flags else "ACCEPTABLE")
        confidence = 0.8 if blocked else 0.65

        rationale = (
            f"riskScore={risk_score:.0f}; stage={stage}; "
            f"collecting={collecting}; flags: {', '.join(flags) or 'none'}"
        )
        result = RoleAssessment(
            role=self.role, symbol=sym, direction=direction,
            analysis_mode=MODE_RULES, verdict=verdict, confidence=confidence,
            rationale=rationale,
            signals={"riskScore": risk_score, "stage": stage, "collecting": collecting},
            flags=flags,
        )
        publish_event(ROLE_ASSESSMENT_COMPLETED, {"role": self.role, "symbol": sym, "verdict": verdict})
        get_research_store().append("role_assessments", result.to_dict())
        return result


class PortfolioAnalyst:
    role = "PORTFOLIO"

    def assess(self, candidate: dict[str, Any], context: dict[str, Any]) -> RoleAssessment:
        publish_event(ROLE_ASSESSMENT_STARTED, {"role": self.role, "symbol": candidate.get("symbol")})
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or "LONG")
        active_cases = int(context.get("activeCases") or 0)
        flags = []

        if active_cases >= 10:
            flags.append("CASE_LOAD_HIGH")

        verdict = "OK" if not flags else "CONSTRAINED"
        confidence = 0.6

        rationale = f"activeCases={active_cases}; flags: {', '.join(flags) or 'none'}"
        result = RoleAssessment(
            role=self.role, symbol=sym, direction=direction,
            analysis_mode=MODE_RULES, verdict=verdict, confidence=confidence,
            rationale=rationale,
            signals={"activeCases": active_cases},
            flags=flags,
        )
        publish_event(ROLE_ASSESSMENT_COMPLETED, {"role": self.role, "symbol": sym, "verdict": verdict})
        get_research_store().append("role_assessments", result.to_dict())
        return result


class PerformanceAnalyst:
    role = "PERFORMANCE"

    def assess(self, candidate: dict[str, Any], context: dict[str, Any]) -> RoleAssessment:
        publish_event(ROLE_ASSESSMENT_STARTED, {"role": self.role, "symbol": candidate.get("symbol")})
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or "LONG")
        score = _safe_float(candidate.get("score") or candidate.get("totalScore"))
        flags = []

        if score < 20:
            flags.append("LOW_SCORE")
        elif score >= 60:
            flags.append("HIGH_SCORE")

        verdict = "PROMISING" if score >= 40 else "WEAK"
        confidence = 0.55

        rationale = f"score={score:.1f}; flags: {', '.join(flags) or 'none'}"
        result = RoleAssessment(
            role=self.role, symbol=sym, direction=direction,
            analysis_mode=MODE_RULES, verdict=verdict, confidence=confidence,
            rationale=rationale,
            signals={"score": score},
            flags=flags,
        )
        publish_event(ROLE_ASSESSMENT_COMPLETED, {"role": self.role, "symbol": sym, "verdict": verdict})
        get_research_store().append("role_assessments", result.to_dict())
        return result


class ReflectionAnalyst:
    role = "REFLECTION"

    def assess(self, candidate: dict[str, Any], context: dict[str, Any]) -> RoleAssessment:
        publish_event(ROLE_ASSESSMENT_STARTED, {"role": self.role, "symbol": candidate.get("symbol")})
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or "LONG")
        prior_outcomes = context.get("priorOutcomes") or []
        flags = []

        losses = [o for o in prior_outcomes if str(o.get("result") or "").upper() == "LOSS"]
        if len(losses) >= 2:
            flags.append("RECENT_LOSSES")

        verdict = "CONCERN" if flags else "NEUTRAL"
        confidence = 0.5

        rationale = f"priorOutcomes={len(prior_outcomes)}; losses={len(losses)}; flags: {', '.join(flags) or 'none'}"
        result = RoleAssessment(
            role=self.role, symbol=sym, direction=direction,
            analysis_mode=MODE_RULES, verdict=verdict, confidence=confidence,
            rationale=rationale,
            signals={"priorOutcomeCount": len(prior_outcomes), "losses": len(losses)},
            flags=flags,
        )
        publish_event(ROLE_ASSESSMENT_COMPLETED, {"role": self.role, "symbol": sym, "verdict": verdict})
        get_research_store().append("role_assessments", result.to_dict())
        return result


class DecisionOrchestrator:
    """Orchestrates all roles and produces a ResearchDecision.

    MUST NOT skip Risk Critic assessment.
    Does NOT call real order execution.
    """

    def __init__(self) -> None:
        self._market = MarketContextAnalyst()
        self._structure = StructureAnalyst()
        self._risk = RiskCriticAnalyst()
        self._portfolio = PortfolioAnalyst()
        self._performance = PerformanceAnalyst()
        self._reflection = ReflectionAnalyst()

    def run(
        self,
        case_id: str,
        candidate: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run all role assessments and produce a ResearchDecision."""
        context = context or {}
        sym = str(candidate.get("symbol") or "")
        direction = str(candidate.get("side") or "LONG")

        # Run all roles — Risk Critic is mandatory
        market_a = self._market.assess(candidate, context)
        structure_a = self._structure.assess(candidate, context)
        risk_a = self._risk.assess(candidate, context)        # MANDATORY: never skip
        portfolio_a = self._portfolio.assess(candidate, context)
        performance_a = self._performance.assess(candidate, context)
        reflection_a = self._reflection.assess(candidate, context)

        assessments = [market_a, structure_a, risk_a, portfolio_a, performance_a, reflection_a]

        # Decision logic
        all_flags = [f for a in assessments for f in a.flags]

        if risk_a.verdict == "BLOCKED":
            decision_status = DECISION_RISK_BLOCKED
            summary = f"Risk Critic blocked: {', '.join(risk_a.flags)}"
        elif "INSUFFICIENT_HISTORY" in all_flags:
            decision_status = DECISION_WATCH_ONLY
            summary = "Insufficient history — watch only"
        elif performance_a.verdict == "WEAK" and market_a.verdict == "UNFAVORABLE":
            decision_status = DECISION_REJECTED
            summary = "Weak score + unfavorable market context"
        elif structure_a.verdict == "ALIGNED" and risk_a.verdict == "ACCEPTABLE":
            decision_status = DECISION_READY_FOR_SIMULATION
            summary = "Structure aligned, risk acceptable — eligible for simulation"
        else:
            decision_status = DECISION_WATCH_ONLY
            summary = "Conditions partially met — continue watching"

        result = {
            "caseId": case_id,
            "symbol": sym,
            "direction": direction,
            "decisionStatus": decision_status,
            "summary": summary,
            "analysisMode": MODE_RULES,
            "researchOnly": True,
            "privateApi": False,
            "assessments": [a.to_dict() for a in assessments],
            "allFlags": all_flags,
            "producedAt": _ts(),
            # Phase 6.4: shadow feature evidence IDs only — never mutate production score/side/ranking
            "featureSnapshotId": None,
            "shadowEvaluationId": None,
            "supportingFeatureIds": [],
            "opposingFeatureIds": [],
            "missingFeatureIds": [],
            "featureQualityScore": None,
        }

        # Shadow Feature Evaluation (RULES_ONLY evidence). Failures are non-blocking.
        try:
            from backend.nexus_research.features.shadow_evaluation import get_shadow_evaluator

            before_score = candidate.get("score")
            before_side = candidate.get("side")
            feature_map = {
                "score": candidate.get("score"),
                "priceChange5mPct": candidate.get("priceChange5mPct"),
                "oiChange5mPct": candidate.get("oiChange5mPct"),
                "fundingRate": candidate.get("fundingRate"),
            }
            shadow = get_shadow_evaluator().evaluate(
                candidate=candidate,
                feature_snapshot=feature_map,
                extra_context={"caseId": case_id, "productionDecisionStatus": decision_status},
            )
            if candidate.get("score") != before_score or candidate.get("side") != before_side:
                raise RuntimeError("shadow evaluation mutated production candidate")
            if isinstance(shadow, dict):
                result["featureSnapshotId"] = shadow.get("featureHash")
                result["shadowEvaluationId"] = shadow.get("evaluationId")
                result["featureQualityScore"] = 1.0 if shadow.get("productionUnchanged") else 0.0
                result["shadowDecision"] = shadow.get("shadowDecision")
                result["shadowScore"] = shadow.get("shadowScore")
                result["shadowAgreement"] = (
                    "AGREE"
                    if (
                        (direction == "LONG" and shadow.get("shadowDecision") == "SHADOW_LONG")
                        or (direction == "SHORT" and shadow.get("shadowDecision") == "SHADOW_SHORT")
                    )
                    else "DISAGREE_OR_NEUTRAL"
                )
        except Exception:  # noqa: BLE001
            pass

        get_research_store().append("research_decisions", result)
        publish_event(
            RESEARCH_DECISION_PRODUCED,
            {"caseId": case_id, "symbol": sym, "decisionStatus": decision_status},
        )
        return result
