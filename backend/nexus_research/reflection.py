"""Phase 5 Gate C — Post-Simulation Reflection & Attribution.

RESEARCH ONLY. After a simulated position closes, performs:
  - Trade attribution (entry timing, score quality, market context, fee drag)
  - Reflection summary with classification
  - PatchProposal generation (PROPOSED state only — never auto-applied to production)

Constraints:
  - NEVER modifies production code or config files.
  - NEVER modifies trading logic, strategy engines, or scoring formulas.
  - Patch proposals target SIMULATION-ONLY apply states.
  - All outputs stored in in-memory research store (append-only).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any

from backend.nexus_research.domain_events import (
    REFLECTION_COMPLETED,
    REFLECTION_TRIGGERED,
    PATCH_PROPOSED,
    publish_event,
)
from backend.nexus_research.storage import get_research_store

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Classification labels ──────────────────────────────────────────────────────
CLASS_WIN = "WIN"
CLASS_LOSS = "LOSS"
CLASS_BREAKEVEN = "BREAKEVEN"

# ── Reflection outcome types ───────────────────────────────────────────────────
OUTCOME_PROFITABLE = "PROFITABLE"
OUTCOME_LOSS_WITHIN_LIMIT = "LOSS_WITHIN_LIMIT"
OUTCOME_LARGE_LOSS = "LARGE_LOSS"
OUTCOME_FEE_DRAG = "FEE_DRAG"      # profitable gross but net negative due to fees
OUTCOME_NEUTRAL = "NEUTRAL"

# ── Patch proposal states ──────────────────────────────────────────────────────
PATCH_PROPOSED_STATE = "PROPOSED"  # see patch_governance.py for full state machine

_BREAKEVEN_THRESHOLD_USD = 0.5


class TradeAttribution:
    """Attribution breakdown for a closed simulated position."""

    def __init__(
        self,
        position: dict[str, Any],
        candidate: dict[str, Any] | None,
    ) -> None:
        self.position = position
        self.candidate = candidate or {}
        self.realised_pnl: float = position.get("realisedPnl") or 0.0
        self.entry_fee: float = position.get("entryFee") or 0.0
        self.exit_fee: float = position.get("exitFee") or 0.0
        self.funding_accrued: float = position.get("fundingAccrued") or 0.0
        self.gross_pnl: float = self.realised_pnl + self.entry_fee + self.exit_fee + self.funding_accrued
        self.total_cost: float = self.entry_fee + self.exit_fee + abs(self.funding_accrued)
        self.score: float = float(self.candidate.get("score", 0.0))
        self.entry_price: float = float(position.get("entryPrice") or 0.0)
        self.exit_price: float = float(position.get("exitPrice") or self.entry_price)
        self.side: str = position.get("side", "LONG")

    @property
    def price_move_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        delta = self.exit_price - self.entry_price
        if self.side == "SHORT":
            delta = -delta
        return delta / self.entry_price * 100.0

    @property
    def fee_drag_pct(self) -> float:
        notional = self.position.get("notional") or (
            self.position.get("qty", 0.0) * self.entry_price
        )
        if notional <= 0:
            return 0.0
        return self.total_cost / notional * 100.0

    @property
    def outcome_class(self) -> str:
        if abs(self.realised_pnl) < _BREAKEVEN_THRESHOLD_USD:
            return CLASS_BREAKEVEN
        return CLASS_WIN if self.realised_pnl > 0 else CLASS_LOSS

    @property
    def outcome_type(self) -> str:
        if self.realised_pnl > 0:
            if self.gross_pnl > 0 and self.realised_pnl < 0:
                return OUTCOME_FEE_DRAG
            return OUTCOME_PROFITABLE
        if abs(self.realised_pnl) < _BREAKEVEN_THRESHOLD_USD:
            return OUTCOME_NEUTRAL
        loss_limit = 500.0  # simple threshold; could be from config
        if abs(self.realised_pnl) > loss_limit:
            return OUTCOME_LARGE_LOSS
        return OUTCOME_LOSS_WITHIN_LIMIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "realisedPnl": self.realised_pnl,
            "grossPnl": self.gross_pnl,
            "entryFee": self.entry_fee,
            "exitFee": self.exit_fee,
            "fundingAccrued": self.funding_accrued,
            "totalCost": self.total_cost,
            "priceMovePct": round(self.price_move_pct, 4),
            "feeDragPct": round(self.fee_drag_pct, 4),
            "outcomeClass": self.outcome_class,
            "outcomeType": self.outcome_type,
            "scoreUsed": self.score,
            "researchOnly": True,
        }


class ReflectionRecord:
    """Full reflection record for a closed simulated position."""

    def __init__(
        self,
        position_id: str,
        symbol: str,
        side: str,
        attribution: TradeAttribution,
        notes: list[str],
        patch_proposals: list[dict[str, Any]],
    ) -> None:
        self.reflection_id = str(uuid.uuid4())
        self.position_id = position_id
        self.symbol = symbol
        self.side = side
        self.attribution = attribution
        self.notes = notes
        self.patch_proposals = patch_proposals
        self.created_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reflectionId": self.reflection_id,
            "positionId": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "attribution": self.attribution.to_dict(),
            "notes": self.notes,
            "patchProposals": self.patch_proposals,
            "createdAtMs": self.created_at_ms,
            "researchOnly": True,
        }


def _build_patch_proposals(
    attribution: TradeAttribution,
    symbol: str,
    existing_reflections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate PatchProposal records (PROPOSED state only, no auto-apply)."""
    proposals: list[dict[str, Any]] = []

    # Proposal: reduce score threshold if repeated losses on high-score candidates
    recent_losses = [
        r for r in existing_reflections[-10:]
        if r.get("attribution", {}).get("outcomeClass") == CLASS_LOSS
        and r.get("symbol") == symbol
    ]
    if len(recent_losses) >= 3 and attribution.score > 70:
        proposals.append({
            "proposalId": str(uuid.uuid4()),
            "state": PATCH_PROPOSED_STATE,
            "scope": "simulation_only",
            "problem": f"3+ recent losses on {symbol} with score > 70",
            "evidence": {
                "recentLossCount": len(recent_losses),
                "scoreUsed": attribution.score,
                "symbol": symbol,
            },
            "suggestedChange": {
                "parameter": "score_scale_min",
                "direction": "increase",
                "delta": 5.0,
                "rationale": "Raise minimum score threshold for simulation entries on this symbol",
            },
            "sampleSize": len(existing_reflections),
            "requiresMinSample": 10,
            "requiresReplay": True,
            "requiresWalkForward": True,
            "requiresRollbackPlan": True,
            "rollbackDescription": "Revert score_scale_min to prior value if soak fails",
            "autoApplyProduction": False,
            "researchOnly": True,
        })

    # Proposal: flag high fee drag
    if attribution.fee_drag_pct > 0.5:
        proposals.append({
            "proposalId": str(uuid.uuid4()),
            "state": PATCH_PROPOSED_STATE,
            "scope": "simulation_only",
            "problem": f"Fee drag {attribution.fee_drag_pct:.2f}% exceeds 0.5% threshold",
            "evidence": {
                "feeDragPct": attribution.fee_drag_pct,
                "totalCost": attribution.total_cost,
                "symbol": symbol,
            },
            "suggestedChange": {
                "parameter": "taker_fee_bps or position size",
                "direction": "reduce",
                "rationale": "Consider switching to limit orders or reducing position size",
            },
            "sampleSize": 1,
            "requiresMinSample": 5,
            "requiresReplay": False,
            "requiresWalkForward": False,
            "requiresRollbackPlan": False,
            "rollbackDescription": "",
            "autoApplyProduction": False,
            "researchOnly": True,
        })

    return proposals


class ReflectionAnalyst:
    """Runs post-simulation reflection after a position closes."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._total_reflections = 0
        self._total_proposals = 0

    def reflect(
        self,
        position: dict[str, Any],
        candidate: dict[str, Any] | None = None,
    ) -> ReflectionRecord:
        """Perform reflection on a closed simulated position."""
        position_id = position.get("positionId", str(uuid.uuid4()))
        symbol = position.get("symbol", "UNKNOWN")
        side = position.get("side", "LONG")

        publish_event(
            REFLECTION_TRIGGERED,
            {"positionId": position_id, "symbol": symbol, "researchOnly": True},
            idempotency_key=f"reflect_trigger_{position_id}",
        )

        attribution = TradeAttribution(position, candidate)
        notes: list[str] = []

        # Load existing reflections for this symbol to check patterns
        store = get_research_store()
        existing = store.query("sim_reflections", limit=50)
        existing_for_symbol = [r for r in existing if r.get("symbol") == symbol]

        # Generate notes
        notes.append(
            f"Outcome: {attribution.outcome_class} — PnL={attribution.realised_pnl:.4f} USD"
        )
        if attribution.price_move_pct != 0:
            notes.append(
                f"Price moved {attribution.price_move_pct:+.3f}% "
                f"({'favorable' if attribution.realised_pnl >= 0 else 'adverse'})"
            )
        if attribution.fee_drag_pct > 0.3:
            notes.append(f"Fee drag {attribution.fee_drag_pct:.3f}% — consider limit orders")
        if attribution.funding_accrued != 0:
            notes.append(
                f"Funding accrued: {attribution.funding_accrued:.4f} USD "
                f"({'paid' if attribution.funding_accrued > 0 else 'received'})"
            )
        win_count = sum(
            1 for r in existing_for_symbol
            if r.get("attribution", {}).get("outcomeClass") == CLASS_WIN
        )
        loss_count = sum(
            1 for r in existing_for_symbol
            if r.get("attribution", {}).get("outcomeClass") == CLASS_LOSS
        )
        notes.append(
            f"Symbol history: {win_count} wins / {loss_count} losses "
            f"(last {len(existing_for_symbol)} reflections)"
        )

        # Build patch proposals (never auto-applied to production)
        patch_proposals = _build_patch_proposals(attribution, symbol, existing_for_symbol)

        record = ReflectionRecord(
            position_id=position_id,
            symbol=symbol,
            side=side,
            attribution=attribution,
            notes=notes,
            patch_proposals=patch_proposals,
        )

        with self._lock:
            self._total_reflections += 1
            self._total_proposals += len(patch_proposals)

        # Persist to research store
        store.append("sim_reflections", record.to_dict())

        # Publish proposals to event bus
        for proposal in patch_proposals:
            publish_event(
                PATCH_PROPOSED,
                {"proposalId": proposal["proposalId"], "symbol": symbol,
                 "scope": "simulation_only", "state": PATCH_PROPOSED_STATE,
                 "autoApplyProduction": False, "researchOnly": True},
                idempotency_key=f"patch_{proposal['proposalId']}",
            )

        publish_event(
            REFLECTION_COMPLETED,
            {
                "reflectionId": record.reflection_id,
                "positionId": position_id,
                "symbol": symbol,
                "outcomeClass": attribution.outcome_class,
                "patchCount": len(patch_proposals),
                "researchOnly": True,
            },
            idempotency_key=f"reflect_done_{position_id}",
        )

        logger.info(
            "[reflection] %s %s %s pnl=%.4f class=%s proposals=%d",
            position_id, symbol, side,
            attribution.realised_pnl, attribution.outcome_class, len(patch_proposals),
        )
        return record

    def list_reflections(
        self,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        store = get_research_store()
        records = store.query("sim_reflections", limit=limit)
        if symbol:
            records = [r for r in records if r.get("symbol") == symbol]
        return records

    def status(self) -> dict[str, Any]:
        store = get_research_store()
        total = store.count("sim_reflections")
        recent = store.query("sim_reflections", limit=10)
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "totalReflections": self._total_reflections,
            "totalProposals": self._total_proposals,
            "storedReflections": total,
            "recentReflections": recent,
            "autoApplyProduction": False,
            "generatedAt": int(time.time() * 1000),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_ANALYST: ReflectionAnalyst | None = None
_ANALYST_LOCK = threading.Lock()


def get_reflection_analyst() -> ReflectionAnalyst:
    global _ANALYST
    with _ANALYST_LOCK:
        if _ANALYST is None:
            _ANALYST = ReflectionAnalyst()
            logger.info("[reflection] ReflectionAnalyst initialised (researchOnly=true)")
        return _ANALYST
