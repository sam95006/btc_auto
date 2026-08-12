"""Same-setup re-entry control — no blind repeat of failed unchanged thesis."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.trade_completion_v30 import (
    CLOSURE_SCHEMA,
    build_setup_signature,
    load_last_trade_closure,
)

# Material change thresholds — not a fixed cooldown-only gate.
PRICE_CHANGE_PCT_MIN = 0.35
MOMENTUM_FLIP_MIN = 0.15
REGIME_CHANGE_BLOCKS_REPEAT = True


def closure_path(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "last_trade_closure.json"


def evaluate_same_setup_reentry(
    *,
    symbol: str,
    side: str,
    setup_signature: str,
    closure_path: Path,
    current_price: float | None = None,
    current_regime: str | None = None,
    current_momentum: float | None = None,
    strategy_family: str = "TREND",
    regime: str = "TREND_UP",
) -> dict[str, Any]:
    """Block unchanged failed setup; allow materially changed fresh evidence."""
    last = load_last_trade_closure(closure_path)
    if last is None:
        return {"pass": True, "reason": "no_prior_closure", "same_setup_signature": False}

    prev_sig = str(last.get("setup_signature") or "")
    same_sig = bool(prev_sig and prev_sig == setup_signature)
    out: dict[str, Any] = {
        "pass": True,
        "same_setup_signature": same_sig,
        "previous_setup_signature": prev_sig,
        "last_exit_reason": last.get("exit_reason"),
        "last_net_realized": last.get("net_realized"),
        "last_hold_sec": last.get("hold_sec"),
    }

    if not same_sig:
        out["reason"] = "different_setup"
        return out

    acct_ok = bool(last.get("ACCOUNTING_COMPLETE"))
    refl_req = bool(last.get("reflection_required"))
    refl_done = bool(last.get("Reflection_created") or last.get("reflection_created"))
    if not acct_ok:
        out.update({"pass": False, "reason": "PRIOR_ACCOUNTING_INCOMPLETE"})
        return out
    if refl_req and not refl_done:
        out.update({"pass": False, "reason": "PRIOR_REFLECTION_INCOMPLETE"})
        return out

    prev_price = last.get("exit_price") or last.get("entry_price")
    prev_regime = str(last.get("regime") or last.get("regime_at_entry") or "")
    prev_momentum = last.get("momentum_at_entry")
    material: list[str] = []

    if current_price and prev_price:
        try:
            move = abs(float(current_price) - float(prev_price)) / float(prev_price) * 100.0
            if move >= PRICE_CHANGE_PCT_MIN:
                material.append(f"price_move_{move:.2f}pct")
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    if (
        REGIME_CHANGE_BLOCKS_REPEAT
        and current_regime
        and prev_regime
        and str(current_regime).upper() != prev_regime.upper()
    ):
        material.append("regime_changed")

    if current_momentum is not None and prev_momentum is not None:
        try:
            if float(current_momentum) * float(prev_momentum) < 0 and abs(float(current_momentum)) >= MOMENTUM_FLIP_MIN:
                material.append("momentum_flipped")
        except (TypeError, ValueError):
            pass

    last_exit = str(last.get("exit_reason") or "").upper()
    last_net = last.get("net_realized")
    try:
        last_loss = last_net is not None and float(last_net) < 0
    except (TypeError, ValueError):
        last_loss = False
    bad_repeat = last_loss or last_exit in {
        "STOP_LOSS",
        "TRAILING_STOP",
        "STRATEGY_HORIZON_EXPIRED",
        "managed_exit",
    }

    if bad_repeat and not material:
        out.update(
            {
                "pass": False,
                "reason": "SAME_SETUP_REPEAT_BLOCKED",
                "invalidation": "unchanged_market_after_loss_or_weak_exit",
                "material_change_evidence": material,
            }
        )
        return out

    out["reason"] = "material_change_allows_reentry" if material else "prior_win_or_neutral_repeat_allowed"
    out["material_change_evidence"] = material
    return out


def default_setup_signature(
    *,
    symbol: str,
    side: str,
    strategy_family: str = "TREND",
    regime: str = "TREND_UP",
    target_pct: float = 0.55,
    stop_pct: float = 0.40,
) -> str:
    return build_setup_signature(
        symbol=symbol,
        side=side,
        strategy_family=strategy_family,
        regime=regime,
        target_pct=target_pct,
        stop_pct=stop_pct,
    )


def closure_record_from_finalize(
    finalize: dict[str, Any],
    *,
    setup_signature: str,
    momentum_at_entry: float | None = None,
) -> dict[str, Any]:
    life = finalize.get("lifecycle") or {}
    refl = finalize.get("reflection") or {}
    ea = life.get("exact_pnl_accounting") or {}
    return {
        "schema": CLOSURE_SCHEMA,
        "closed_at_ms": int(time.time() * 1000),
        "closed": True,
        "position_closed": True,
        "setup_signature": setup_signature,
        "symbol": life.get("symbol"),
        "side": life.get("side"),
        "entry_price": life.get("entry_price"),
        "exit_price": life.get("exit_price"),
        "exit_reason": life.get("exit_reason"),
        "hold_sec": life.get("hold_sec"),
        "net_realized": ea.get("calculated_net_pnl"),
        "ACCOUNTING_COMPLETE": life.get("ACCOUNTING_COMPLETE"),
        "settlement_state": life.get("settlement_state"),
        "bybit_orderId": life.get("bybit_orderId"),
        "wallet_before": life.get("wallet_before"),
        "wallet_after": life.get("wallet_after"),
        "wallet_reconciliation": life.get("wallet_reconciliation"),
        "regime": life.get("regime"),
        "regime_at_entry": life.get("regime_at_entry"),
        "momentum_at_entry": momentum_at_entry,
        "process_class": life.get("process_class"),
        "reflection_required": refl.get("reflection_required"),
        "reflection_created": refl.get("reflection_created"),
        "Reflection_created": refl.get("reflection_created"),
        "mistake_signature": refl.get("mistake_signature"),
        "CandidateLesson_created": refl.get("candidate_lesson_created"),
        "MFE": (life.get("path_excursion") or {}).get("mfe_usdt"),
        "MAE": (life.get("path_excursion") or {}).get("mae_usdt"),
        # Persist full lifecycle for pending accounting retry + reflection.
        "lifecycle": life,
    }
