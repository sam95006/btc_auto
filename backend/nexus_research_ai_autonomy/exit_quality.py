"""MFE/MAE tracking + exit quality classification — diagnostic only.

Do NOT auto-rewrite live strategy from these labels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

EXIT_REASONS = (
    "STOP_LOSS",
    "TAKE_PROFIT",
    "ADAPTIVE_PROFIT_CAPTURE",
    "TRAILING_STOP",
    "MOMENTUM_EXHAUSTION",
    "REGIME_INVALIDATION",
    "SIGNAL_INVALIDATION",
    "LIQUIDITY_RISK",
    "RISK_EMERGENCY",
    "STRATEGY_HORIZON_EXPIRED",
)

EXIT_QUALITY_CLASSES = (
    "HIGH_CAPTURE_WIN",
    "LOW_CAPTURE_WIN",
    "EXIT_TOO_EARLY",
    "EXIT_TOO_LATE",
    "NO_EDGE_AFTER_ENTRY",
    "WRONG_DIRECTION",
    "BAD_ENTRY_TIMING",
    "REGIME_FAILURE",
    "VALID_CONTROLLED_LOSS",
    "EDGE_EXISTED_EXIT_TOO_EARLY",
    "TARGET_WAS_UNREALISTIC_FOR_HORIZON",
    "STOP_WAS_TOO_TIGHT",
    "THESIS_INVALIDATED_CORRECT_EXIT",
    "VALID_PROFIT_CAPTURE",
    "OTHER",
    "UNKNOWN",
)

# Map internal manager reasons → canonical exit reasons
REASON_MAP = {
    "hard_stop": "STOP_LOSS",
    "stop_loss": "STOP_LOSS",
    "take_profit": "TAKE_PROFIT",
    "trailing_stop": "TRAILING_STOP",
    "regime_signal_invalidation": "REGIME_INVALIDATION",
    "regime_invalidation": "REGIME_INVALIDATION",
    "signal_invalidation": "SIGNAL_INVALIDATION",
    "critical_liquidity": "LIQUIDITY_RISK",
    "liquidity_risk": "LIQUIDITY_RISK",
    "max_loss": "RISK_EMERGENCY",
    "infra_failure": "RISK_EMERGENCY",
    "risk_emergency": "RISK_EMERGENCY",
    "max_hold": "STRATEGY_HORIZON_EXPIRED",
    "strategy_horizon_expired": "STRATEGY_HORIZON_EXPIRED",
    "canary_forced_close": "RISK_EMERGENCY",
    "adaptive_profit_capture": "ADAPTIVE_PROFIT_CAPTURE",
    "momentum_exhaustion": "MOMENTUM_EXHAUSTION",
    "momentum_decay": "MOMENTUM_EXHAUSTION",
}


def canonicalize_exit_reason(reason: str | None) -> str:
    r = str(reason or "").strip().lower()
    if r.upper() in EXIT_REASONS:
        return r.upper()
    return REASON_MAP.get(r, "UNKNOWN" if not r else REASON_MAP.get(r.split("_")[0], "UNKNOWN"))


@dataclass
class PathExcursionTracker:
    """Track MFE/MAE during an open position."""

    entry_price: float
    side: str
    qty: float
    target_price: float | None = None
    stop_price: float | None = None
    opened_at_ms: int = 0
    peak_price: float | None = None
    trough_price: float | None = None
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    mfe_usdt: float = 0.0
    mae_usdt: float = 0.0
    time_to_mfe_sec: float | None = None
    time_to_mae_sec: float | None = None
    target_touched: bool = False
    stop_touched: bool = False
    highest_unrealized_usdt: float = 0.0
    lowest_unrealized_usdt: float = 0.0
    samples: list[dict[str, Any]] = field(default_factory=list)

    def unrealized(self, px: float) -> tuple[float, float]:
        """Return (pnl_pct, pnl_usdt)."""
        entry = float(self.entry_price)
        if entry <= 0 or px <= 0:
            return 0.0, 0.0
        side_u = str(self.side or "LONG").upper()
        if side_u in {"LONG", "BUY"}:
            pct = (px - entry) / entry * 100.0
        else:
            pct = (entry - px) / entry * 100.0
        usdt = pct / 100.0 * entry * abs(float(self.qty))
        return pct, usdt

    def update(self, px: float, *, now_ms: int) -> None:
        if px <= 0:
            return
        if self.peak_price is None or px > self.peak_price:
            self.peak_price = px
        if self.trough_price is None or px < self.trough_price:
            self.trough_price = px
        pct, usdt = self.unrealized(px)
        held = (now_ms - self.opened_at_ms) / 1000.0 if self.opened_at_ms else 0.0
        if usdt >= self.highest_unrealized_usdt:
            self.highest_unrealized_usdt = usdt
            self.mfe_usdt = max(self.mfe_usdt, usdt)
            self.mfe_pct = max(self.mfe_pct, pct)
            self.time_to_mfe_sec = held
        if usdt <= self.lowest_unrealized_usdt:
            self.lowest_unrealized_usdt = usdt
            self.mae_usdt = min(self.mae_usdt, usdt)  # more negative
            self.mae_pct = min(self.mae_pct, pct)
            self.time_to_mae_sec = held
        # Favorable excursion also from peak/trough
        fav_pct, fav_usdt = self.unrealized(float(self.peak_price if str(self.side).upper() in {"LONG", "BUY"} else self.trough_price or px))
        adv_pct, adv_usdt = self.unrealized(float(self.trough_price if str(self.side).upper() in {"LONG", "BUY"} else self.peak_price or px))
        if fav_usdt > self.mfe_usdt:
            self.mfe_usdt = fav_usdt
            self.mfe_pct = fav_pct
            if self.time_to_mfe_sec is None:
                self.time_to_mfe_sec = held
        if adv_usdt < self.mae_usdt:
            self.mae_usdt = adv_usdt
            self.mae_pct = adv_pct
            if self.time_to_mae_sec is None:
                self.time_to_mae_sec = held
        side_u = str(self.side or "LONG").upper()
        if self.target_price is not None:
            if side_u in {"LONG", "BUY"} and px >= float(self.target_price):
                self.target_touched = True
            if side_u in {"SHORT", "SELL"} and px <= float(self.target_price):
                self.target_touched = True
        if self.stop_price is not None:
            if side_u in {"LONG", "BUY"} and px <= float(self.stop_price):
                self.stop_touched = True
            if side_u in {"SHORT", "SELL"} and px >= float(self.stop_price):
                self.stop_touched = True
        if len(self.samples) < 64:
            self.samples.append({"t_sec": round(held, 2), "px": px, "u_usdt": round(usdt, 6)})

    def to_dict(self) -> dict[str, Any]:
        return {
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
            "mfe_usdt": self.mfe_usdt,
            "mae_usdt": self.mae_usdt,
            "time_to_mfe_sec": self.time_to_mfe_sec,
            "time_to_mae_sec": self.time_to_mae_sec,
            "target_touched": self.target_touched,
            "stop_touched": self.stop_touched,
            "highest_unrealized_usdt": self.highest_unrealized_usdt,
            "lowest_unrealized_usdt": self.lowest_unrealized_usdt,
            "peak_price": self.peak_price,
            "trough_price": self.trough_price,
            "samples_n": len(self.samples),
        }


def exit_efficiency(*, realized_usdt: float, mfe_usdt: float) -> float | None:
    """realized / MFE when MFE > 0; None if no favorable excursion."""
    if mfe_usdt is None or mfe_usdt <= 1e-12:
        return None
    return float(realized_usdt) / float(mfe_usdt)


def classify_exit_quality(
    *,
    exit_reason: str | None,
    realized_usdt: float,
    mfe_usdt: float,
    mae_usdt: float,
    target_touched: bool,
    stop_touched: bool,
    hold_sec: float | None,
    hard_max_hold: float | None = None,
    expected_target_move_pct: float | None = None,
    expected_path_range_pct: float | None = None,
    stop_move_pct: float | None = None,
) -> dict[str, Any]:
    """Diagnostic classification only — no live strategy rewrite."""
    reason = canonicalize_exit_reason(exit_reason)
    clazz = "UNKNOWN"
    detail = ""

    # Unrealistic target for horizon
    if (
        expected_target_move_pct is not None
        and expected_path_range_pct is not None
        and float(expected_path_range_pct) + 1e-12 < float(expected_target_move_pct) * 0.85
        and reason == "STRATEGY_HORIZON_EXPIRED"
        and not target_touched
    ):
        clazz = "TARGET_WAS_UNREALISTIC_FOR_HORIZON"
        detail = "path_range_below_target_and_horizon_expired"
    elif mfe_usdt <= 0.02 and mae_usdt >= -0.05 and abs(realized_usdt) < 0.5:
        clazz = "NO_EDGE_AFTER_ENTRY"
        detail = "flat_path_after_entry"
    elif mfe_usdt >= 0.5 and realized_usdt < mfe_usdt * 0.35 and reason in {
        "STRATEGY_HORIZON_EXPIRED",
        "SIGNAL_INVALIDATION",
        "REGIME_INVALIDATION",
    }:
        clazz = "EDGE_EXISTED_EXIT_TOO_EARLY"
        detail = f"mfe={mfe_usdt:.4f} realized={realized_usdt:.4f}"
    elif (
        stop_move_pct is not None
        and float(stop_move_pct) < 0.20
        and stop_touched
        and mae_usdt > -abs(realized_usdt) - 0.01
    ):
        clazz = "STOP_WAS_TOO_TIGHT"
        detail = f"stop_move_pct={stop_move_pct}"
    elif reason in {"REGIME_INVALIDATION", "SIGNAL_INVALIDATION"} and realized_usdt <= 0:
        clazz = "THESIS_INVALIDATED_CORRECT_EXIT"
        detail = reason
    elif realized_usdt > 0 and (target_touched or reason in {"TAKE_PROFIT", "TRAILING_STOP"}):
        clazz = "VALID_PROFIT_CAPTURE"
        detail = reason
    elif realized_usdt <= 0 and reason in {"STOP_LOSS", "TRAILING_STOP", "RISK_EMERGENCY", "LIQUIDITY_RISK"}:
        clazz = "VALID_CONTROLLED_LOSS"
        detail = reason
    elif reason == "STRATEGY_HORIZON_EXPIRED" and mfe_usdt < 0.15:
        clazz = "NO_EDGE_AFTER_ENTRY"
        detail = "horizon_expired_without_edge"
    else:
        clazz = "UNKNOWN"
        detail = f"reason={reason} mfe={mfe_usdt:.4f} mae={mae_usdt:.4f}"

    eff = exit_efficiency(realized_usdt=realized_usdt, mfe_usdt=mfe_usdt)
    return {
        "schema": "v18_2_25_exit_quality_v1",
        "exit_reason_canonical": reason,
        "exit_quality_class": clazz,
        "known_classes": list(EXIT_QUALITY_CLASSES),
        "known_exit_reasons": list(EXIT_REASONS),
        "detail": detail,
        "exit_efficiency": eff,
        "diagnostic_only": True,
        "auto_rewrite_live_strategy": False,
        "hold_sec": hold_sec,
        "hard_max_hold": hard_max_hold,
    }
