"""Adaptive profit capture — extends persistent position lifecycle.

Computes remaining edge, continuation_score, giveback_risk, dynamic profit zone,
profit locking. Canonical exits: ADAPTIVE_PROFIT_CAPTURE, MOMENTUM_EXHAUSTION.
Exchange-side SL mandatory; slow_path_leak_count=0 invariant.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (
    PersistentPositionLifecycleManager,
)
from backend.nexus_research_ai_autonomy.position_manager import ResearchPosition

ADAPTIVE_PROFIT_CAPTURE = "ADAPTIVE_PROFIT_CAPTURE"
MOMENTUM_EXHAUSTION = "MOMENTUM_EXHAUSTION"
CAPTURE_SCHEMA = "v18_2_28_adaptive_profit_capture_v1"


@dataclass
class AdaptiveCaptureState:
    remaining_edge_pct: float = 0.0
    continuation_score: float = 0.0
    giveback_risk: float = 0.0
    dynamic_profit_zone_usdt: float = 0.0
    profit_locked: bool = False
    profit_lock_floor_usdt: float = 0.0
    profit_lock_started_at_ms: int | None = None
    mfe_usdt: float = 0.0
    capture_ticks: list[dict[str, Any]] = field(default_factory=list)
    last_adaptive_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # V29: null when lock never activated — do not emit 0.0 as a fake floor.
        d["profit_lock_level"] = self.profit_lock_floor_usdt if self.profit_locked else None
        d["protected_pnl_floor"] = self.profit_lock_floor_usdt if self.profit_locked else None
        d["profit_lock_started_at"] = self.profit_lock_started_at_ms
        d["adaptive_action"] = self.last_adaptive_action or "NOT_ACTIVATED"
        return d


def compute_mfe_capture_metrics(*, realized_usdt: float, mfe_usdt: float) -> dict[str, Any]:
    """MFE_capture_ratio and profit_left_from_MFE."""
    mfe = float(mfe_usdt or 0.0)
    realized = float(realized_usdt or 0.0)
    if mfe <= 1e-12:
        ratio = None
        left = 0.0
    else:
        ratio = max(0.0, min(1.5, realized / mfe))
        left = max(0.0, mfe - realized)
    return {
        "MFE_capture_ratio": ratio,
        "profit_left_from_MFE": left,
        "mfe_usdt": mfe,
        "realized_usdt": realized,
    }


def empty_adaptive_profit_capture_block(
    *,
    reason: str = "no_completed_lifecycle",
    evaluated: bool = False,
) -> dict[str, Any]:
    """Always-present adaptive capture shape — fields never disappear."""
    return {
        "schema": "v18_2_29_adaptive_profit_capture_v1",
        "evaluated": evaluated,
        "adaptive_action": "NOT_ACTIVATED" if evaluated else None,
        "profit_lock_level": None,
        "protected_pnl_floor": None,
        "profit_lock_started_at": None,
        "profit_lock_state": False if evaluated else None,
        "remaining_edge": None,
        "continuation_score": None,
        "giveback_risk": None,
        "mfe_usdt": None,
        "reason": reason,
        "not_available_reason": reason if not evaluated else None,
    }


def summarize_adaptive_capture_from_lifecycle(lifecycle: dict[str, Any] | None) -> dict[str, Any]:
    """Honest post-trade adaptive capture summary from existing lifecycle evidence.

    Does NOT invent adaptive decisions that were never taken.
    When MFE is zero/absent, reports evaluated=true + NOT_ACTIVATED + NO_MEANINGFUL_POSITIVE_MFE.
    """
    if not isinstance(lifecycle, dict) or not lifecycle:
        return empty_adaptive_profit_capture_block(reason="no_completed_lifecycle", evaluated=False)

    path = lifecycle.get("path_excursion") or {}
    adaptive = (
        lifecycle.get("adaptive_capture")
        or lifecycle.get("adaptive_capture_state")
        or lifecycle.get("adaptive_profit_capture")
        or {}
    )
    if not isinstance(adaptive, dict):
        adaptive = {}

    mfe = path.get("mfe_usdt")
    try:
        mfe_f = float(mfe) if mfe is not None else None
    except (TypeError, ValueError):
        mfe_f = None

    action = adaptive.get("adaptive_action") or adaptive.get("last_adaptive_action")
    remaining = adaptive.get("remaining_edge_pct")
    if remaining is None:
        remaining = adaptive.get("remaining_edge")
    continuation = adaptive.get("continuation_score")
    giveback = adaptive.get("giveback_risk")
    lock_level = adaptive.get("profit_lock_level")
    if lock_level is None:
        lock_level = adaptive.get("profit_lock_floor_usdt")
    protected = adaptive.get("protected_pnl_floor")
    if protected is None:
        protected = adaptive.get("profit_lock_floor_usdt")
    started = adaptive.get("profit_lock_started_at")
    if started is None:
        started = adaptive.get("profit_lock_started_at_ms")
    locked = adaptive.get("profit_locked")
    if locked is None:
        locked = adaptive.get("profit_lock_state")

    meaningful_mfe = mfe_f is not None and mfe_f >= 0.25

    if action in {ADAPTIVE_PROFIT_CAPTURE, MOMENTUM_EXHAUSTION, "TIGHTEN_PROTECTION", "TRAIL"}:
        reason = f"activated:{action}"
        adaptive_action = str(action)
    elif locked:
        reason = "PROFIT_LOCK_ACTIVE"
        adaptive_action = "TIGHTEN_PROTECTION"
    elif meaningful_mfe:
        reason = "POSITIVE_MFE_OBSERVED_BUT_NO_ADAPTIVE_EXIT"
        adaptive_action = "NOT_ACTIVATED"
    elif mfe_f is not None and mfe_f <= 1e-12:
        reason = "NO_MEANINGFUL_POSITIVE_MFE"
        adaptive_action = "NOT_ACTIVATED"
    elif mfe_f is None:
        reason = "mfe_usdt not present in path_excursion"
        adaptive_action = "NOT_ACTIVATED"
    else:
        reason = "NO_MEANINGFUL_POSITIVE_MFE"
        adaptive_action = "NOT_ACTIVATED"

    not_available: dict[str, Any] = {}
    if remaining is None:
        not_available["remaining_edge"] = (
            "remaining_edge not recorded on lifecycle (manager tick telemetry absent)"
        )
    if continuation is None:
        not_available["continuation_score"] = (
            "continuation_score not recorded on lifecycle (manager tick telemetry absent)"
        )
    if giveback is None:
        not_available["giveback_risk"] = (
            "giveback_risk not recorded on lifecycle (manager tick telemetry absent)"
        )
    if lock_level is None and not locked:
        not_available["profit_lock_level"] = "profit lock never activated"
    if protected is None and not locked:
        not_available["protected_pnl_floor"] = "profit lock never activated"
    if started is None and not locked:
        not_available["profit_lock_started_at"] = "profit lock never activated"
    if mfe_f is None:
        not_available["mfe_usdt"] = "path_excursion.mfe_usdt not_available_in_evidence"

    return {
        "schema": "v18_2_29_adaptive_profit_capture_v1",
        "evaluated": True,
        "adaptive_action": adaptive_action,
        "profit_lock_level": lock_level,
        "protected_pnl_floor": protected,
        "profit_lock_started_at": started,
        "profit_lock_state": bool(locked) if locked is not None else False,
        "remaining_edge": remaining,
        "continuation_score": continuation,
        "giveback_risk": giveback,
        "mfe_usdt": mfe_f,
        "reason": reason,
        "not_available_reason": not_available or None,
    }


class AdaptiveProfitCaptureManager(PersistentPositionLifecycleManager):
    """PersistentPositionLifecycleManager + adaptive profit capture layer."""

    def __init__(self, *, slow_path_leak_count: int = 0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.capture_states: dict[str, AdaptiveCaptureState] = {}
        self.slow_path_leak_count = int(slow_path_leak_count)
        self.exchange_sl_mandatory = True

    def _capture_state(self, pos: ResearchPosition) -> AdaptiveCaptureState:
        if pos.position_id not in self.capture_states:
            self.capture_states[pos.position_id] = AdaptiveCaptureState()
        return self.capture_states[pos.position_id]

    def _compute_adaptive_signals(
        self,
        pos: ResearchPosition,
        *,
        px: float,
        market: dict[str, Any],
        held_sec: float,
        now_ms: int,
    ) -> AdaptiveCaptureState:
        st = self._capture_state(pos)
        tracker = pos.path_tracker
        mfe = float(tracker.mfe_usdt if tracker else 0.0)
        st.mfe_usdt = mfe

        if tracker and px > 0:
            u_pct, u_usdt = tracker.unrealized(px)
        else:
            u_pct, u_usdt = 0.0, 0.0

        target_px = float(pos.take_profit_price or 0)
        if target_px > 0 and pos.entry_price > 0:
            if pos.side == "LONG":
                total_edge = (target_px - pos.entry_price) / pos.entry_price * 100.0
                captured = u_pct
            else:
                total_edge = (pos.entry_price - target_px) / pos.entry_price * 100.0
                captured = u_pct
            st.remaining_edge_pct = max(0.0, total_edge - captured)
        else:
            st.remaining_edge_pct = max(0.0, 0.55 - u_pct)

        momentum = float(market.get("momentum_score") or market.get("liquidity") or 0.5)
        vol = float(market.get("realized_vol_pct") or 0.3)
        st.continuation_score = max(0.0, min(1.0, momentum * 0.6 + (1.0 - min(1.0, vol / 2.0)) * 0.4))

        if mfe > 0.01:
            giveback = max(0.0, (mfe - u_usdt) / mfe)
        else:
            giveback = 0.0
        st.giveback_risk = giveback

        # Dynamic profit zone — scale with MFE and continuation
        zone_frac = 0.35 + 0.25 * st.continuation_score
        st.dynamic_profit_zone_usdt = max(0.0, mfe * zone_frac)

        # Profit locking — ratchet stop when giveback risk high after meaningful MFE.
        if mfe >= 0.25 and u_usdt > 0:
            lock_floor = mfe * 0.45
            if giveback >= 0.40 or (held_sec > 120 and st.continuation_score < 0.35):
                if not st.profit_locked:
                    # Lock starts "now" deterministically at the first tick which enables it.
                    st.profit_lock_started_at_ms = now_ms
                st.profit_locked = True
                st.profit_lock_floor_usdt = max(st.profit_lock_floor_usdt, lock_floor)
                if pos.side == "LONG" and pos.entry_price > 0:
                    lock_px = pos.entry_price + (lock_floor / abs(pos.qty)) if pos.qty else pos.entry_price
                    if pos.stop_price is None or lock_px > float(pos.stop_price):
                        pos.stop_price = lock_px
                elif pos.side == "SHORT" and pos.entry_price > 0:
                    lock_px = pos.entry_price - (lock_floor / abs(pos.qty)) if pos.qty else pos.entry_price
                    if pos.stop_price is None or lock_px < float(pos.stop_price):
                        pos.stop_price = lock_px

        st.capture_ticks.append(
            {
                "held_sec": round(held_sec, 2),
                "u_usdt": round(u_usdt, 6),
                "remaining_edge_pct": round(st.remaining_edge_pct, 4),
                "continuation_score": round(st.continuation_score, 4),
                "giveback_risk": round(st.giveback_risk, 4),
                "profit_locked": st.profit_locked,
            }
        )
        if len(st.capture_ticks) > 32:
            st.capture_ticks = st.capture_ticks[-32:]
        return st

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
        now_ms = int(time.time() * 1000)
        held_sec = (now_ms - pos.opened_at_ms) / 1000.0 if pos.opened_at_ms else 0.0

        if px > 0 and pos.path_tracker:
            pos.path_tracker.update(px, now_ms=now_ms)

        st = self._compute_adaptive_signals(
            pos, px=px, market=market, held_sec=held_sec, now_ms=now_ms
        )

        # Adaptive profit capture exit
        if pos.path_tracker:
            _, u_usdt = pos.path_tracker.unrealized(px)
            mfe = st.mfe_usdt
            if mfe >= 0.30 and u_usdt >= st.dynamic_profit_zone_usdt and st.giveback_risk >= 0.35:
                st.last_adaptive_action = ADAPTIVE_PROFIT_CAPTURE
                close_res = self._close(
                    pos,
                    px,
                    ADAPTIVE_PROFIT_CAPTURE,
                    regime,
                    market,
                    ["adaptive_profit_capture"],
                    {"capture_state": st.to_dict()},
                    None,
                    "AI_MANAGEMENT",
                )
                close_res["adaptive_capture"] = st.to_dict()
                return close_res
            if mfe >= 0.20 and st.continuation_score < 0.25 and st.giveback_risk >= 0.50:
                st.last_adaptive_action = MOMENTUM_EXHAUSTION
                close_res = self._close(
                    pos,
                    px,
                    MOMENTUM_EXHAUSTION,
                    regime,
                    market,
                    ["momentum_exhaustion"],
                    {"capture_state": st.to_dict()},
                    None,
                    "AI_MANAGEMENT",
                )
                close_res["adaptive_capture"] = st.to_dict()
                return close_res

        # Delegate to persistent lifecycle (exchange SL, thesis exits)
        result = super().manage_cycle(
            position_id,
            market=market,
            regime=regime,
            ai_proposal=ai_proposal,
            ai_widens_max_risk=ai_widens_max_risk,
            signal_invalidated=signal_invalidated,
        )
        result["adaptive_capture"] = st.to_dict()
        result["slow_path_leak_count"] = self.slow_path_leak_count
        result["exchange_sl_mandatory"] = self.exchange_sl_mandatory
        return result

    def build_exit_quality_extension(self, lifecycle: dict[str, Any]) -> dict[str, Any]:
        """Attach MFE capture metrics to lifecycle exit quality."""
        path = lifecycle.get("path_excursion") or {}
        realized = float(
            (lifecycle.get("exact_pnl_accounting") or {}).get("calculated_net_pnl")
            or lifecycle.get("exchange_closed_pnl", {}).get("closedPnl")
            or 0.0
        )
        mfe = float(path.get("mfe_usdt") or 0.0)
        mfe_metrics = compute_mfe_capture_metrics(realized_usdt=realized, mfe_usdt=mfe)
        adaptive = lifecycle.get("adaptive_capture") or lifecycle.get("adaptive_capture_state") or {}
        return {
            **mfe_metrics,
            "schema": CAPTURE_SCHEMA,
            "slow_path_leak_count": self.slow_path_leak_count,
            # Profit-lock telemetry stitched into exit quality (best-effort; missing fields => null).
            "profit_lock_level": adaptive.get("profit_lock_level"),
            "protected_pnl_floor": adaptive.get("protected_pnl_floor"),
            "profit_lock_started_at": adaptive.get("profit_lock_started_at"),
            "adaptive_action": adaptive.get("adaptive_action"),
        }
