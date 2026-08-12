"""Position management — FAST SAFETY vs AI MANAGEMENT; management journal.

V18.2.24: RESEARCH_PNL_TRADE supports initial SL, TP, trailing, time exit,
regime/signal invalidation. Do NOT close solely because execution was proven.

V18.2.25: max_hold = STRATEGY_HORIZON_EXPIRED (thesis), not transport timer.
Canonical exit reasons; MFE/MAE path tracking; no arbitrary mandatory min hold.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.exit_quality import (
    PathExcursionTracker,
    canonicalize_exit_reason,
)
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (
    LIFECYCLE_PURPOSE_EXECUTION_CANARY,
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
)
from backend.nexus_research_ai_autonomy.research_risk import ResearchRiskEngine


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ResearchPosition:
    position_id: str
    decision_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_price: float | None
    max_hold_sec: int
    opened_at_ms: int
    regime_at_entry: str
    strategy_family: str
    status: str = "OPEN"  # OPEN | CLOSING | CLOSED
    max_risk_pct: float = 1.5
    realized_pnl_pct: float | None = None
    exit_reason: str | None = None
    closed_at_ms: int | None = None
    take_profit_price: float | None = None
    trail_pct: float | None = None
    trail_anchor: float | None = None
    lifecycle_purpose: str = LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
    min_hold_sec: int = 0  # advisory only — never mandatory for PnL research
    peak_price: float | None = None
    trough_price: float | None = None
    path_tracker: PathExcursionTracker | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.path_tracker is not None:
            d["path_tracker"] = self.path_tracker.to_dict()
        return d


@dataclass
class ManagementJournalEntry:
    timestamp: int
    position_id: str
    regime: str
    market_state: dict[str, Any]
    evidence_delta: list[str]
    risk_delta: dict[str, Any]
    ai_management_proposal: str | None
    final_deterministic_action: str
    reason: str
    path: str  # FAST_SAFETY | AI_MANAGEMENT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PositionManager:
    def __init__(self, risk: ResearchRiskEngine | None = None) -> None:
        self.risk = risk or ResearchRiskEngine()
        self.positions: dict[str, ResearchPosition] = {}
        self.journal: list[ManagementJournalEntry] = []

    def open_from_execution(self, *, decision: dict[str, Any], fill_price: float, qty: float) -> ResearchPosition:
        stop = decision.get("stop_price") or (decision.get("stop_logic") or {}).get("price")
        tp = decision.get("target_price") or (decision.get("take_profit_logic") or {}).get("price")
        trail = decision.get("trail_pct")
        purpose = str(
            decision.get("lifecycle_purpose") or LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
        )
        # V25: no arbitrary mandatory min hold for RESEARCH_PNL_TRADE
        min_hold = 0
        if purpose == LIFECYCLE_PURPOSE_EXECUTION_CANARY:
            min_hold = 0
        hard = decision.get("hard_max_hold")
        max_hold = int(hard if hard is not None else (decision.get("max_hold") or 3600))
        opened = _now_ms()
        tracker = PathExcursionTracker(
            entry_price=float(fill_price),
            side=str(decision.get("side") or ""),
            qty=float(qty),
            target_price=float(tp) if tp is not None else None,
            stop_price=float(stop) if stop is not None else None,
            opened_at_ms=opened,
            peak_price=float(fill_price),
            trough_price=float(fill_price),
        )
        pos = ResearchPosition(
            position_id=f"rp_{uuid.uuid4().hex[:12]}",
            decision_id=str(decision.get("decision_id") or ""),
            symbol=str(decision.get("symbol") or ""),
            side=str(decision.get("side") or ""),
            qty=float(qty),
            entry_price=float(fill_price),
            stop_price=float(stop) if stop is not None else None,
            max_hold_sec=max_hold,
            opened_at_ms=opened,
            regime_at_entry=str(decision.get("regime") or ""),
            strategy_family=str(decision.get("strategy_family") or ""),
            take_profit_price=float(tp) if tp is not None else None,
            trail_pct=float(trail) if trail is not None else None,
            trail_anchor=float(fill_price),
            lifecycle_purpose=purpose,
            min_hold_sec=min_hold,
            peak_price=float(fill_price),
            trough_price=float(fill_price),
            path_tracker=tracker,
        )
        self.positions[pos.position_id] = pos
        return pos

    def _journal(
        self,
        pos: ResearchPosition,
        *,
        regime: str,
        market_state: dict[str, Any],
        evidence_delta: list[str],
        risk_delta: dict[str, Any],
        ai_proposal: str | None,
        action: str,
        reason: str,
        path: str,
    ) -> ManagementJournalEntry:
        entry = ManagementJournalEntry(
            timestamp=_now_ms(),
            position_id=pos.position_id,
            regime=regime,
            market_state=dict(market_state),
            evidence_delta=list(evidence_delta),
            risk_delta=dict(risk_delta),
            ai_management_proposal=ai_proposal,
            final_deterministic_action=action,
            reason=reason,
            path=path,
        )
        self.journal.append(entry)
        return entry

    def manage_cycle(
        self,
        position_id: str,
        *,
        market: dict[str, Any],
        regime: str,
        ai_proposal: str | None = None,
        ai_widens_max_risk: bool = False,
        signal_invalidated: bool = False,
    ) -> dict[str, Any]:
        pos = self.positions.get(position_id)
        if not pos or pos.status != "OPEN":
            return {"action": "NONE", "reason": "no_open_position"}

        px = float(market.get("last_price") or market.get("price") or 0.0)
        now = _now_ms()
        evidence_delta: list[str] = []
        risk_delta: dict[str, Any] = {}
        held_sec = (now - pos.opened_at_ms) / 1000.0

        if px > 0:
            if pos.peak_price is None or px > pos.peak_price:
                pos.peak_price = px
            if pos.trough_price is None or px < pos.trough_price:
                pos.trough_price = px
            if pos.path_tracker is not None:
                pos.path_tracker.update(px, now_ms=now)

        # --- FAST SAFETY (never waits for AI) ---
        # Canary may immediate-close; RESEARCH_PNL_TRADE never closes solely for "execution proven"
        if pos.lifecycle_purpose == LIFECYCLE_PURPOSE_EXECUTION_CANARY and market.get(
            "canary_force_close"
        ):
            evidence_delta.append("canary_forced_close")
            return self._close(
                pos, px, "canary_forced_close", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
            )

        if pos.stop_price is not None and px > 0:
            if pos.side == "LONG" and px <= float(pos.stop_price):
                evidence_delta.append("hard_stop_hit")
                return self._close(pos, px, "STOP_LOSS", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY")
            if pos.side == "SHORT" and px >= float(pos.stop_price):
                evidence_delta.append("hard_stop_hit")
                return self._close(pos, px, "STOP_LOSS", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY")

        # Take profit (strategy exit — allowed for RESEARCH_PNL_TRADE)
        if pos.take_profit_price is not None and px > 0:
            if pos.side == "LONG" and px >= float(pos.take_profit_price):
                evidence_delta.append("take_profit_hit")
                return self._close(
                    pos, px, "TAKE_PROFIT", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
                )
            if pos.side == "SHORT" and px <= float(pos.take_profit_price):
                evidence_delta.append("take_profit_hit")
                return self._close(
                    pos, px, "TAKE_PROFIT", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
                )

        # Trailing stop update + hit
        if pos.trail_pct is not None and px > 0 and pos.entry_price > 0:
            trail = abs(float(pos.trail_pct)) / 100.0
            if pos.side == "LONG":
                floor = float(pos.peak_price or px) * (1.0 - trail)
                if pos.stop_price is None or floor > float(pos.stop_price):
                    pos.stop_price = floor
                    risk_delta["trail_stop"] = floor
                if px <= float(pos.stop_price):
                    evidence_delta.append("trailing_stop_hit")
                    return self._close(
                        pos, px, "TRAILING_STOP", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
                    )
            else:
                ceiling = float(pos.trough_price or px) * (1.0 + trail)
                if pos.stop_price is None or ceiling < float(pos.stop_price):
                    pos.stop_price = ceiling
                    risk_delta["trail_stop"] = ceiling
                if px >= float(pos.stop_price):
                    evidence_delta.append("trailing_stop_hit")
                    return self._close(
                        pos, px, "TRAILING_STOP", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
                    )

        # Thesis expired — NOT a transport timer
        if held_sec >= pos.max_hold_sec:
            evidence_delta.append("strategy_horizon_expired")
            return self._close(
                pos, px, "STRATEGY_HORIZON_EXPIRED", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
            )

        if market.get("data_failure") or market.get("exchange_failure") or market.get("emergency_risk_exit"):
            evidence_delta.append("risk_emergency")
            return self._close(
                pos, px, "RISK_EMERGENCY", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
            )

        if float(market.get("liquidity") or 1.0) < 0.1:
            evidence_delta.append("liquidity_risk")
            return self._close(
                pos, px, "LIQUIDITY_RISK", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
            )

        # Regime / signal invalidation — no mandatory min-hold gate for RESEARCH_PNL
        if signal_invalidated:
            evidence_delta.append("signal_invalidation")
            return self._close(
                pos, px, "SIGNAL_INVALIDATION", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
            )
        if (
            regime
            and pos.regime_at_entry
            and regime != pos.regime_at_entry
            and market.get("regime_invalidated")
        ):
            evidence_delta.append("regime_invalidation")
            return self._close(
                pos, px, "REGIME_INVALIDATION", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
            )

        # unrealized loss hard bound
        if px > 0 and pos.entry_price > 0:
            if pos.side == "LONG":
                pnl_pct = (px - pos.entry_price) / pos.entry_price * 100.0
            else:
                pnl_pct = (pos.entry_price - px) / pos.entry_price * 100.0
            risk_delta["unrealized_pnl_pct"] = pnl_pct
            if pnl_pct <= -pos.max_risk_pct:
                evidence_delta.append("risk_emergency_max_loss")
                return self._close(
                    pos, px, "RISK_EMERGENCY", regime, market, evidence_delta, risk_delta, None, "FAST_SAFETY"
                )

        # --- AI MANAGEMENT (proposal only) — no arbitrary mandatory min hold ---
        proposal = str(ai_proposal or "HOLD").upper()

        allowed, why = self.risk.allow_management_action(
            proposal=proposal,
            widens_max_risk=bool(ai_widens_max_risk),
            fast_safety_triggered=False,
        )
        if not allowed:
            self._journal(
                pos,
                regime=regime,
                market_state=market,
                evidence_delta=evidence_delta + ["ai_proposal_blocked"],
                risk_delta=risk_delta,
                ai_proposal=proposal,
                action="HOLD",
                reason=why,
                path="AI_MANAGEMENT",
            )
            return {"action": "HOLD", "reason": why, "ai_proposal": proposal}

        if proposal in {"EXIT", "TAKE_PROFIT", "REDUCE"}:
            action = "EXIT" if proposal != "HOLD" else "HOLD"
            if action == "EXIT":
                return self._close(
                    pos,
                    px,
                    f"ai_mgmt_{proposal.lower()}",
                    regime,
                    market,
                    evidence_delta,
                    risk_delta,
                    proposal,
                    "AI_MANAGEMENT",
                )

        self._journal(
            pos,
            regime=regime,
            market_state=market,
            evidence_delta=evidence_delta,
            risk_delta=risk_delta,
            ai_proposal=proposal,
            action="HOLD",
            reason="hold",
            path="AI_MANAGEMENT",
        )
        return {"action": "HOLD", "reason": "hold", "ai_proposal": proposal}

    def _close(
        self,
        pos: ResearchPosition,
        px: float,
        reason: str,
        regime: str,
        market: dict[str, Any],
        evidence_delta: list[str],
        risk_delta: dict[str, Any],
        ai_proposal: str | None,
        path: str,
    ) -> dict[str, Any]:
        if px > 0 and pos.entry_price > 0:
            if pos.side == "LONG":
                pnl = (px - pos.entry_price) / pos.entry_price * 100.0
            else:
                pnl = (pos.entry_price - px) / pos.entry_price * 100.0
        else:
            pnl = 0.0
        canonical = canonicalize_exit_reason(reason)
        pos.realized_pnl_pct = pnl
        pos.exit_reason = canonical
        pos.closed_at_ms = _now_ms()
        pos.status = "CLOSED"
        path_snap = pos.path_tracker.to_dict() if pos.path_tracker else None
        self._journal(
            pos,
            regime=regime,
            market_state=market,
            evidence_delta=evidence_delta,
            risk_delta={**risk_delta, "realized_pnl_pct": pnl},
            ai_proposal=ai_proposal,
            action="EXIT",
            reason=canonical,
            path=path,
        )
        return {
            "action": "EXIT",
            "reason": canonical,
            "path": path,
            "pnl_pct": pnl,
            "position": pos.to_dict(),
            "hold_sec": (pos.closed_at_ms - pos.opened_at_ms) / 1000.0,
            "lifecycle_purpose": pos.lifecycle_purpose,
            "path_excursion": path_snap,
        }

    def open_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.status == "OPEN")
