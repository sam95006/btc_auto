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
    fees: float | None
    funding: float | None
    slippage: float | None
    net_pnl: float | None
    r_multiple: float | None
    mae: float | None
    mfe: float | None
    holding_ms: int
    entry_quality: str
    exit_quality: str
    incomplete: bool = False
    missing_fields: list[str] = field(default_factory=list)
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
            "incomplete": self.incomplete,
            "missingFields": list(self.missing_fields),
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
    fees: float | None,
    funding: float | None,
    slippage: float | None,
    risk_amount: float,
    mae: float | None = None,
    mfe: float | None = None,
    holding_ms: int = 0,
    exit_reason: str = "",
) -> ReflectionBundle:
    missing: list[str] = []
    if fees is None:
        missing.append("fees")
    if funding is None:
        missing.append("funding")
    if slippage is None:
        missing.append("slippage")
    if mae is None:
        missing.append("mae")
    if mfe is None:
        missing.append("mfe")
    incomplete = bool(missing)
    if incomplete:
        net = None
        r_mult = None
    else:
        net = float(gross_pnl) - abs(float(fees)) - abs(float(funding)) - abs(float(slippage))
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
        incomplete=incomplete,
        missing_fields=missing,
    )
    # Classifier still needs numeric DemoTradeOutcome; missing fee/funding stay
    # None on TradeOutcomeRecord — never publish 0 as if verified.
    fee_for_class = abs(float(fees)) if fees is not None else 0.0
    pnl_for_class = float(net) if net is not None else float(gross_pnl)
    demo_outcome = DemoTradeOutcome(
        symbol=symbol,
        direction="LONG" if side in ("Buy", "LONG") else "SHORT",
        pnl=pnl_for_class,
        fees_paid=fee_for_class,
        duration_ms=holding_ms,
        lessons=[exit_reason] if exit_reason else (["INCOMPLETE_OUTCOME"] if incomplete else []),
    )
    errors = ReflectionClassifier().classify(demo_outcome)
    class_names = [e.value for e in errors]
    if incomplete:
        class_names = list(dict.fromkeys(class_names + ["INCOMPLETE_OUTCOME"]))

    mae_cmp = float(mae) if mae is not None else 0.0
    patch = {
        "type": "CANDIDATE_PATCH",
        "symbol": symbol,
        "strategy": strategy,
        "regime": regime,
        "suggestion": (
            "await_complete_exchange_requery"
            if incomplete
            else (
                "tighten_entry_filters" if (net is not None and net < 0 and confidence >= 80)
                else "review_stop_distance" if mae_cmp > abs(risk_amount)
                else "hold_policy"
            )
        ),
        "errorTypes": class_names,
        "incomplete": incomplete,
        "missingFields": missing,
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
