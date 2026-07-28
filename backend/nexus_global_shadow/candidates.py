"""Global candidate ranking — deterministic hash tiebreak, no random/wall-clock."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_global_shadow.contracts import (
    Candidate,
    IntelligenceSnapshot,
    MarketRegime,
    Regime,
    StrategyContext,
)


class GlobalCandidateRanker:
    """Deterministic candidate generation and ranking."""

    RANKING_VERSION = "v1"

    def build_candidate(
        self,
        symbol: str,
        universe_snapshot_id: str,
        direction: str,
        strategy_ctx: StrategyContext,
        intelligence: IntelligenceSnapshot,
        regime: MarketRegime,
        *,
        input_snapshot_hash: str = "",
    ) -> Candidate:
        direction = direction.upper()
        status = "WATCHING"
        blocks: list[str] = []
        if direction not in {"LONG", "SHORT", "NEUTRAL", "REJECTED"}:
            blocks.append("invalid_direction")
            direction = "REJECTED"
        if strategy_ctx.strategy_status == "BLOCKED":
            blocks.append("strategy_blocked")
            status = "REJECTED"
        if regime.regime == Regime.UNCERTAIN.value:
            blocks.append("regime_uncertain")
            status = "REJECTED"
        if intelligence.missing_evidence:
            blocks.append("intelligence_incomplete")
            if status != "REJECTED":
                status = "RISK_BLOCKED"
        if blocks and status == "WATCHING":
            status = "REJECTED"
        components = self._score_components(strategy_ctx, intelligence, regime, direction)
        waterfall = self._waterfall(components, blocks)
        rank_score = sum(components.values()) if not blocks else None
        return Candidate(
            symbol=symbol,
            universe_snapshot_id=universe_snapshot_id,
            direction=direction,
            strategy_id=strategy_ctx.strategy_id,
            regime=regime.regime,
            entry_thesis=f"{direction} via {strategy_ctx.strategy_id}",
            entry_condition=strategy_ctx.entry_prerequisites[0] if strategy_ctx.entry_prerequisites else "",
            invalidation=strategy_ctx.invalidation,
            confidence=components.get("confidence"),
            confidence_calibration="HEURISTIC",
            quality_score=components.get("quality"),
            risk_score=components.get("risk"),
            regime_fit=components.get("regime_fit"),
            strategy_fit=strategy_ctx.strategy_fit,
            liquidity_fit=components.get("liquidity"),
            spread=intelligence.spread,
            estimated_slippage=None,
            funding_context=intelligence.funding,
            open_interest_context=intelligence.open_interest,
            evidence_quality=intelligence.quality,
            supporting_evidence=list(intelligence.supporting_evidence),
            contradicting_evidence=list(intelligence.contradicting_evidence),
            missing_evidence=list(intelligence.missing_evidence),
            block_reasons=blocks,
            status=status,
            rank_score=rank_score,
            ranking_version=self.RANKING_VERSION,
            score_components=components,
            score_waterfall=waterfall,
        )

    def rank(self, candidates: list[Candidate]) -> list[Candidate]:
        eligible = [c for c in candidates if c.status not in {"REJECTED", "EXPIRED"}]

        def sort_key(c: Candidate) -> tuple:
            score = c.rank_score if c.rank_score is not None else -1.0
            tie = self._tiebreak_hash(c)
            return (-score, tie, c.candidate_id)

        ranked = sorted(eligible, key=sort_key)
        for i, c in enumerate(ranked, start=1):
            c.rank = i
        return ranked + [c for c in candidates if c.status in {"REJECTED", "EXPIRED"}]

    def _tiebreak_hash(self, c: Candidate) -> str:
        payload = json.dumps(
            {"candidate_id": c.candidate_id, "symbol": c.symbol, "strategy_id": c.strategy_id},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _score_components(
        self,
        strategy: StrategyContext,
        intel: IntelligenceSnapshot,
        regime: MarketRegime,
        direction: str,
    ) -> dict[str, float]:
        fit = strategy.strategy_fit or 0.0
        conf = regime.confidence or 0.0
        liq = intel.liquidity or 0.0
        liq_norm = min(1.0, liq / 100.0) if liq else 0.0
        risk = 1.0 - min(1.0, (intel.spread or 0) / 100.0)
        return {
            "strategy_fit": fit,
            "regime_fit": conf,
            "quality": fit * conf,
            "liquidity": liq_norm,
            "risk": risk,
            "confidence": (fit + conf) / 2.0,
            "direction_bias": 1.0 if direction in {"LONG", "SHORT"} else 0.0,
        }

    def _waterfall(self, components: dict[str, float], blocks: list[str]) -> list[str]:
        lines = [f"{k}={v:.4f}" for k, v in sorted(components.items())]
        if blocks:
            lines.append(f"blocked:{','.join(blocks)}")
        return lines

    def snapshot_hash(self, payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
