"""Persistent position lifecycle — PROCESS/OBSERVER vs POSITION/STRATEGY lifetime.

V18.2.27: RESEARCH_PNL_TRADE positions recover from Bybit Demo + local checkpoint.
Observer may stop; return POSITION_STILL_OPEN_MANAGED instead of flattening.
Forbidden process exits must never close thesis positions.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.exit_quality import canonicalize_exit_reason
from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
from backend.nexus_research_ai_autonomy.position_manager import PositionManager, ResearchPosition

FORBIDDEN_PROCESS_EXIT_REASONS = frozenset(
    {
        "SESSION_OBSERVER_EXPIRED_CLOSE",
        "TEST_RUN_FINISHED_CLOSE",
        "CURSOR_TASK_FINISHED_CLOSE",
    }
)

POSITION_STILL_OPEN_MANAGED = "POSITION_STILL_OPEN_MANAGED"
CHECKPOINT_SCHEMA = "v18_2_27_position_lifecycle_checkpoint_v1"
DEFAULT_FEE_RATE_ROUNDTRIP = 0.0011


@dataclass
class OpenPositionTelemetry:
    """Live open-position accounting — separate unrealized from realized."""

    symbol: str
    side: str
    qty: float
    entry_price: float
    mark_price: float
    unrealized_usdt: float
    unrealized_pct: float
    estimated_exit_fee_usdt: float
    estimated_net_if_closed_now: float
    mfe_usdt: float = 0.0
    mae_usdt: float = 0.0
    hold_sec: float = 0.0
    lifecycle_purpose: str = LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LifecycleCheckpoint:
    position_id: str
    decision_id: str
    symbol: str
    side: str
    qty: float
    entry_price: float
    stop_price: float | None
    take_profit_price: float | None
    max_hold_sec: int
    opened_at_ms: int
    bybit_order_id: str | None = None
    lifecycle_purpose: str = LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
    strategy_family: str = "TREND"
    regime_at_entry: str = ""
    trail_pct: float | None = None
    path_tracker: dict[str, Any] | None = None
    saved_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PersistentPositionLifecycleManager(PositionManager):
    """PositionManager with exchange-first recovery and forbidden process exits."""

    def __init__(
        self,
        *,
        checkpoint_path: Path | None = None,
        fee_rate_roundtrip: float = DEFAULT_FEE_RATE_ROUNDTRIP,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.checkpoint_path = checkpoint_path
        self.fee_rate_roundtrip = float(fee_rate_roundtrip)
        self.recovered_from_exchange = False
        self.recovered_from_checkpoint = False

    def is_forbidden_exit(self, reason: str | None) -> bool:
        r = str(reason or "").upper()
        return r in FORBIDDEN_PROCESS_EXIT_REASONS

    def save_checkpoint(self, pos: ResearchPosition, *, bybit_order_id: str | None = None) -> None:
        if self.checkpoint_path is None:
            return
        ck = LifecycleCheckpoint(
            position_id=pos.position_id,
            decision_id=pos.decision_id,
            symbol=pos.symbol,
            side=pos.side,
            qty=pos.qty,
            entry_price=pos.entry_price,
            stop_price=pos.stop_price,
            take_profit_price=pos.take_profit_price,
            max_hold_sec=pos.max_hold_sec,
            opened_at_ms=pos.opened_at_ms,
            bybit_order_id=bybit_order_id,
            lifecycle_purpose=pos.lifecycle_purpose,
            strategy_family=pos.strategy_family,
            regime_at_entry=pos.regime_at_entry,
            trail_pct=pos.trail_pct,
            path_tracker=pos.path_tracker.to_dict() if pos.path_tracker else None,
            saved_at_ms=int(time.time() * 1000),
        )
        payload = {"schema": CHECKPOINT_SCHEMA, "checkpoint": ck.to_dict()}
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.checkpoint_path)

    def load_checkpoint(self) -> LifecycleCheckpoint | None:
        if self.checkpoint_path is None or not self.checkpoint_path.exists():
            return None
        try:
            raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            d = raw.get("checkpoint") or raw
            return LifecycleCheckpoint(**{k: d[k] for k in LifecycleCheckpoint.__dataclass_fields__ if k in d})
        except Exception:  # noqa: BLE001
            return None

    def clear_checkpoint(self) -> None:
        if self.checkpoint_path and self.checkpoint_path.exists():
            self.checkpoint_path.unlink(missing_ok=True)

    def recover_from_exchange(
        self,
        client: Any,
        *,
        lifecycle_purpose: str = LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
    ) -> ResearchPosition | None:
        """Query exchange first; reconcile with local checkpoint — no duplicate, no auto-close."""
        existing = [
            p
            for p in self.positions.values()
            if p.status == "OPEN" and p.lifecycle_purpose == lifecycle_purpose
        ]
        if existing:
            return existing[0]

        ck = self.load_checkpoint()
        try:
            positions = client.list_positions()
        except Exception:  # noqa: BLE001
            positions = []

        open_rows = [p for p in positions if float(p.get("size") or 0) > 0]
        if not open_rows:
            if ck and ck.lifecycle_purpose == lifecycle_purpose:
                self.clear_checkpoint()
            return None

        row = open_rows[0]
        sym = str(row.get("symbol") or "")
        side_raw = str(row.get("side") or "Buy")
        side = "LONG" if side_raw.lower() in {"buy", "long"} else "SHORT"
        qty = float(row.get("size") or 0)
        entry = float(row.get("avgPrice") or row.get("entryPrice") or 0)
        if qty <= 0 or entry <= 0:
            return None

        if ck and ck.symbol == sym and ck.lifecycle_purpose == lifecycle_purpose:
            pos = self._position_from_checkpoint(ck, entry_price=entry, qty=qty)
            self.recovered_from_checkpoint = True
        else:
            pos = self._position_from_exchange_row(row, lifecycle_purpose=lifecycle_purpose)
            self.recovered_from_exchange = True

        self.positions[pos.position_id] = pos
        return pos

    def _position_from_checkpoint(
        self, ck: LifecycleCheckpoint, *, entry_price: float, qty: float
    ) -> ResearchPosition:
        from backend.nexus_research_ai_autonomy.exit_quality import PathExcursionTracker

        tracker = None
        if ck.path_tracker:
            tracker = PathExcursionTracker(
                entry_price=float(ck.path_tracker.get("entry_price") or entry_price),
                side=ck.side,
                qty=float(ck.path_tracker.get("qty") or qty),
                target_price=ck.path_tracker.get("target_price"),
                stop_price=ck.path_tracker.get("stop_price"),
                opened_at_ms=int(ck.path_tracker.get("opened_at_ms") or ck.opened_at_ms),
                peak_price=ck.path_tracker.get("peak_price"),
                trough_price=ck.path_tracker.get("trough_price"),
            )
        elif entry_price > 0:
            tracker = PathExcursionTracker(
                entry_price=entry_price,
                side=ck.side,
                qty=qty,
                target_price=ck.take_profit_price,
                stop_price=ck.stop_price,
                opened_at_ms=ck.opened_at_ms,
                peak_price=entry_price,
                trough_price=entry_price,
            )
        return ResearchPosition(
            position_id=ck.position_id,
            decision_id=ck.decision_id,
            symbol=ck.symbol,
            side=ck.side,
            qty=qty,
            entry_price=entry_price,
            stop_price=ck.stop_price,
            max_hold_sec=int(ck.max_hold_sec),
            opened_at_ms=ck.opened_at_ms,
            regime_at_entry=ck.regime_at_entry,
            strategy_family=ck.strategy_family,
            take_profit_price=ck.take_profit_price,
            trail_pct=ck.trail_pct,
            trail_anchor=entry_price,
            lifecycle_purpose=ck.lifecycle_purpose,
            peak_price=entry_price,
            trough_price=entry_price,
            path_tracker=tracker,
        )

    def _position_from_exchange_row(self, row: dict[str, Any], *, lifecycle_purpose: str) -> ResearchPosition:
        from backend.nexus_research_ai_autonomy.exit_quality import PathExcursionTracker
        import uuid

        sym = str(row.get("symbol") or "")
        side_raw = str(row.get("side") or "Buy")
        side = "LONG" if side_raw.lower() in {"buy", "long"} else "SHORT"
        qty = float(row.get("size") or 0)
        entry = float(row.get("avgPrice") or row.get("entryPrice") or 0)
        opened = int(time.time() * 1000)
        tracker = PathExcursionTracker(
            entry_price=entry,
            side=side,
            qty=qty,
            opened_at_ms=opened,
            peak_price=entry,
            trough_price=entry,
        )
        return ResearchPosition(
            position_id=f"rp_rec_{uuid.uuid4().hex[:12]}",
            decision_id=f"recovered_{sym}",
            symbol=sym,
            side=side,
            qty=qty,
            entry_price=entry,
            stop_price=float(row.get("stopLoss") or 0) or None,
            max_hold_sec=3600,
            opened_at_ms=opened,
            regime_at_entry="",
            strategy_family="TREND",
            take_profit_price=float(row.get("takeProfit") or 0) or None,
            lifecycle_purpose=lifecycle_purpose,
            peak_price=entry,
            trough_price=entry,
            path_tracker=tracker,
        )

    def compute_open_telemetry(self, pos: ResearchPosition, mark_price: float) -> OpenPositionTelemetry:
        now = int(time.time() * 1000)
        held = (now - pos.opened_at_ms) / 1000.0 if pos.opened_at_ms else 0.0
        if pos.path_tracker:
            pos.path_tracker.update(mark_price, now_ms=now)
        pct, usdt = (0.0, 0.0)
        if pos.path_tracker:
            pct, usdt = pos.path_tracker.unrealized(mark_price)
        notional = abs(float(pos.qty) * float(pos.entry_price))
        exit_fee = notional * self.fee_rate_roundtrip * 0.5
        net_if_closed = usdt - exit_fee
        snap = pos.path_tracker.to_dict() if pos.path_tracker else {}
        return OpenPositionTelemetry(
            symbol=pos.symbol,
            side=pos.side,
            qty=pos.qty,
            entry_price=pos.entry_price,
            mark_price=mark_price,
            unrealized_usdt=usdt,
            unrealized_pct=pct,
            estimated_exit_fee_usdt=exit_fee,
            estimated_net_if_closed_now=net_if_closed,
            mfe_usdt=float(snap.get("mfe_usdt") or 0.0),
            mae_usdt=float(snap.get("mae_usdt") or 0.0),
            hold_sec=held,
            lifecycle_purpose=pos.lifecycle_purpose,
        )

    def manage_cycle(
        self,
        position_id: str,
        *,
        market: dict[str, Any],
        regime: str,
        ai_proposal: str | None = None,
        ai_widens_max_risk: bool = False,
        signal_invalidated: bool = False,
        proposed_exit_reason: str | None = None,
    ) -> dict[str, Any]:
        if proposed_exit_reason and self.is_forbidden_exit(proposed_exit_reason):
            pos = self.positions.get(position_id)
            px = float(market.get("last_price") or market.get("price") or 0.0)
            telemetry = self.compute_open_telemetry(pos, px) if pos else None
            return {
                "action": "HOLD",
                "reason": POSITION_STILL_OPEN_MANAGED,
                "forbidden_exit_blocked": proposed_exit_reason,
                "path": "PROCESS_OBSERVER",
                "open_position_telemetry": telemetry.to_dict() if telemetry else None,
            }
        return super().manage_cycle(
            position_id,
            market=market,
            regime=regime,
            ai_proposal=ai_proposal,
            ai_widens_max_risk=ai_widens_max_risk,
            signal_invalidated=signal_invalidated,
        )

    def observer_stop_with_open_position(
        self, position_id: str, *, mark_price: float
    ) -> dict[str, Any]:
        """Observer lifetime ended — position continues managed elsewhere."""
        pos = self.positions.get(position_id)
        if not pos or pos.status != "OPEN":
            return {"action": "NONE", "reason": "no_open_position"}
        telemetry = self.compute_open_telemetry(pos, mark_price)
        self.save_checkpoint(pos)
        return {
            "action": POSITION_STILL_OPEN_MANAGED,
            "reason": POSITION_STILL_OPEN_MANAGED,
            "position": pos.to_dict(),
            "open_position_telemetry": telemetry.to_dict(),
            "forbidden_flatten_on_observer_stop": True,
            "checkpoint_saved": self.checkpoint_path is not None,
        }

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
        canonical = canonicalize_exit_reason(reason)
        if self.is_forbidden_exit(canonical) or self.is_forbidden_exit(reason):
            telemetry = self.compute_open_telemetry(pos, px)
            return {
                "action": "HOLD",
                "reason": POSITION_STILL_OPEN_MANAGED,
                "forbidden_exit_blocked": reason,
                "path": path,
                "open_position_telemetry": telemetry.to_dict(),
            }
        result = super()._close(
            pos, px, reason, regime, market, evidence_delta, risk_delta, ai_proposal, path
        )
        if result.get("action") == "EXIT":
            self.clear_checkpoint()
        return result


def evaluate_horizon_integrity(*, strategy_family: str = "TREND", entry_price: float = 64000.0) -> dict[str, Any]:
    """Pre-scan integrity check — strategy config must satisfy hard_max >= window min."""
    from backend.nexus_research_ai_autonomy.horizon_feasibility import (
        INVALID_HORIZON_CONFIGURATION,
        build_horizon_plan,
        validate_horizon_configuration,
    )

    plan = build_horizon_plan(
        strategy_family=strategy_family,
        side="LONG",
        entry_price=entry_price,
        realized_vol_pct_per_hour=0.35,
    )
    ok, reasons, block = validate_horizon_configuration(plan)
    win = plan.recommended_hold_window
    return {
        "schema": "v18_2_27_horizon_integrity_v1",
        "horizon_integrity_pass": ok,
        "strategy_family": strategy_family,
        "hard_max_hold": plan.hard_max_hold,
        "recommended_hold_window": list(win),
        "invariant_hard_max_gte_window_min": ok,
        "block_code": block if not ok else None,
        "reasons": reasons,
        "INVALID_HORIZON_CONFIGURATION": block == INVALID_HORIZON_CONFIGURATION if not ok else False,
        "no_silent_clamp": True,
    }
