"""Build TradeOutcome + Reflection patch proposal after a Demo round-trip (no live strategy mutate)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_learning.reflection import (
    DemoTradeOutcome,
    ReflectionClassifier,
)


@dataclass
class TradeOutcomeRecord:
    symbol: str
    side: str
    strategy: str
    regime: str
    confidence: float
    leverage: int
    gross_pnl: float
    fees: float
    funding: float
    slippage: float
    net_pnl: float
    r_multiple: float
    mae: float
    mfe: float
    holding_ms: int
    entry_quality: str
    exit_quality: str
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "strategy": self.strategy,
            "regime": self.regime,
            "confidence": self.confidence,
            "leverage": self.leverage,
            "grossPnl": self.gross_pnl,
            "fees": self.fees,
            "funding": self.funding,
            "slippage": self.slippage,
            "netPnl": self.net_pnl,
            "rMultiple": self.r_multiple,
            "mae": self.mae,
            "mfe": self.mfe,
            "holdingMs": self.holding_ms,
            "entryQuality": self.entry_quality,
            "exitQuality": self.exit_quality,
            "createdAtMs": self.created_at_ms,
            "livePatchApplied": False,
        }


@dataclass
class ReflectionBundle:
    outcome: TradeOutcomeRecord
    classification: list[str]
    patch_proposed: bool
    patch_proposal: dict[str, Any]
    live_patch_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.to_dict(),
            "classification": list(self.classification),
            "patchProposed": self.patch_proposed,
            "patchProposal": self.patch_proposal,
            "livePatchApplied": False,
            "pipeline": [
                "OUTCOME", "CLASSIFICATION", "PATCH_PROPOSAL",
                "REPLAY", "WALK_FORWARD", "OOS", "SHADOW", "REVIEW", "CANDIDATE_PATCH",
            ],
        }


def build_reflection_bundle(
    *,
    symbol: str,
    side: str,
    strategy: str,
    regime: str,
    confidence: float,
    leverage: int,
    gross_pnl: float,
    fees: float,
    funding: float,
    slippage: float,
    risk_amount: float,
    mae: float = 0.0,
    mfe: float = 0.0,
    holding_ms: int = 0,
    exit_reason: str = "",
) -> ReflectionBundle:
    net = gross_pnl - abs(fees) - abs(funding) - abs(slippage)
    r_mult = net / risk_amount if risk_amount else 0.0
    outcome = TradeOutcomeRecord(
        symbol=symbol,
        side=side,
        strategy=strategy,
        regime=regime,
        confidence=confidence,
        leverage=leverage,
        gross_pnl=gross_pnl,
        fees=fees,
        funding=funding,
        slippage=slippage,
        net_pnl=net,
        r_multiple=r_mult,
        mae=mae,
        mfe=mfe,
        holding_ms=holding_ms,
        entry_quality="ok" if confidence >= 72 else "marginal",
        exit_quality=exit_reason or "unknown",
    )
    demo_outcome = DemoTradeOutcome(
        symbol=symbol,
        direction="LONG" if side in ("Buy", "LONG") else "SHORT",
        pnl=net,
        fees_paid=abs(fees),
        duration_ms=holding_ms,
        lessons=[exit_reason] if exit_reason else [],
    )
    errors = ReflectionClassifier().classify(demo_outcome)
    class_names = [e.value for e in errors]

    patch = {
        "type": "CANDIDATE_PATCH",
        "symbol": symbol,
        "strategy": strategy,
        "regime": regime,
        "suggestion": (
            "tighten_entry_filters" if net < 0 and confidence >= 80
            else "review_stop_distance" if mae > abs(risk_amount)
            else "hold_policy"
        ),
        "errorTypes": class_names,
        "requiresReplay": True,
        "requiresWalkForward": True,
        "requiresOos": True,
        "requiresShadow": True,
        "liveApplyForbidden": True,
    }
    return ReflectionBundle(
        outcome=outcome,
        classification=class_names,
        patch_proposed=True,
        patch_proposal=patch,
        live_patch_applied=False,
    )
