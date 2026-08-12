"""V18.2.30 bounded research cycle — one market opportunity OR manage ticks.

Position-first. Max concurrent Research = 1.
Does not lower Entry/Stop/Economic/Horizon/Risk/Preflight gates.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (
    POSITION_STILL_OPEN_MANAGED,
    PersistentPositionLifecycleManager,
)


def _resolve_default_campaign_root() -> Path:
    try:
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root

        return campaign_root()
    except Exception:  # noqa: BLE001
        return Path("/data/campaigns/research_v18_2_30")


DEFAULT_CAMPAIGN_ROOT = _resolve_default_campaign_root()


def reconcile_research_position(
    *,
    campaign_root: Path | None = None,
    demo_client: Any | None = None,
) -> dict[str, Any]:
    """Bybit-first reconcile of RESEARCH_PNL_TRADE. Fail-open for scheduler health only."""
    root = campaign_root or DEFAULT_CAMPAIGN_ROOT
    ckpt = root / "autonomy" / "research_pnl_position.json"
    mgr = PersistentPositionLifecycleManager(checkpoint_path=ckpt)
    out: dict[str, Any] = {
        "ok": True,
        "open": False,
        "exchange_connectivity": "UNKNOWN",
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "checkpoint_path": str(ckpt),
    }
    try:
        recovered = None
        if demo_client is not None:
            recovered = mgr.recover_from_exchange(demo_client)
            out["exchange_connectivity"] = "OK"
        else:
            ck = mgr.load_checkpoint()
            if ck is not None:
                # Checkpoint-only recovery (no exchange write / offline verify).
                pos = mgr._position_from_checkpoint(  # noqa: SLF001
                    ck, entry_price=float(ck.entry_price), qty=float(ck.qty)
                )
                mgr.positions[pos.position_id] = pos
                mgr.recovered_from_checkpoint = True
                recovered = pos
                out["exchange_connectivity"] = "CHECKPOINT_ONLY"
            else:
                out["exchange_connectivity"] = "CHECKPOINT_ONLY"

        if recovered is not None:
            out["open"] = True
            out["POSITION_STILL_OPEN_MANAGED"] = True
            out["symbol"] = getattr(recovered, "symbol", None)
            out["side"] = getattr(recovered, "side", None)
            out["position"] = recovered.to_dict() if hasattr(recovered, "to_dict") else None
            out["manager"] = mgr
            return out
        out["manager"] = mgr
        return out
    except Exception as exc:  # noqa: BLE001
        out["ok"] = False
        out["exchange_connectivity"] = "DEGRADED"
        out["error"] = type(exc).__name__
        out["detail"] = str(exc)[:300]
        return out


def run_manage_ticks(ctx: dict[str, Any]) -> dict[str, Any]:
    """Bounded manage ticks — never an unbounded while-True for Cursor validation."""
    recon = ctx.get("reconcile") or {}
    mgr = recon.get("manager")
    max_ticks = int(ctx.get("max_manage_ticks") or 8)
    poll = float(ctx.get("manage_poll_sec") or 15.0)
    if mgr is None:
        return {
            "ok": True,
            "action": "NO_ACTION",
            "reason": "no_manager",
            "POSITION_STILL_OPEN_MANAGED": True,
            "ticks": 0,
        }

    ticks: list[dict[str, Any]] = []
    closed = False
    last_action = "HOLD"
    for i in range(max_ticks):
        tick_fn = ctx.get("manage_tick_fn")
        if callable(tick_fn):
            tick = tick_fn(mgr, i)
        else:
            # Default: hold / report still open (live adaptive wiring supplied by runner)
            tick = {
                "tick": i,
                "adaptive_action": "HOLD",
                "POSITION_STILL_OPEN_MANAGED": True,
            }
        ticks.append(tick)
        last_action = str(tick.get("adaptive_action") or tick.get("action") or "HOLD")
        if tick.get("closed"):
            closed = True
            break
        if i + 1 < max_ticks and poll > 0 and not ctx.get("dry"):
            time.sleep(min(poll, 2.0) if ctx.get("fast_poll") else poll)

    return {
        "ok": True,
        "closed": closed,
        "action": last_action,
        "ticks": len(ticks),
        "tick_detail": ticks[-3:],
        "POSITION_STILL_OPEN_MANAGED": (not closed),
        "adaptive_live_evaluation": True,
    }


def run_flat_opportunity_cycle(ctx: dict[str, Any]) -> dict[str, Any]:
    """One full-market opportunity cycle when FLAT. WAIT must not kill service."""
    cycle_fn = ctx.get("flat_cycle_fn")
    if callable(cycle_fn):
        result = cycle_fn(ctx)
        if not isinstance(result, dict):
            return {"ok": False, "WAIT": True, "reason": "invalid_cycle_result"}
        # Normalize WAIT
        if result.get("WAIT") or result.get("decision") == "WAIT" or not result.get("executed"):
            result.setdefault("WAIT", True)
            result.setdefault("ok", True)
        return result
    return {
        "ok": True,
        "WAIT": True,
        "reason": "flat_cycle_fn_not_bound",
        "persist_wait_reason": True,
        "no_gate_lowering": True,
        "no_manufactured_trades": True,
    }


def build_cycle_bindings(
    *,
    campaign_root: Path | None = None,
    demo_client: Any | None = None,
    flat_cycle_fn: Any | None = None,
    manage_tick_fn: Any | None = None,
    dry: bool = False,
) -> dict[str, Any]:
    root = campaign_root or DEFAULT_CAMPAIGN_ROOT

    def _reconcile() -> dict[str, Any]:
        return reconcile_research_position(campaign_root=root, demo_client=demo_client)

    def _manage(c: dict[str, Any]) -> dict[str, Any]:
        c = {**c, "dry": dry, "manage_tick_fn": manage_tick_fn}
        return run_manage_ticks(c)

    def _cycle(c: dict[str, Any]) -> dict[str, Any]:
        c = {**c, "dry": dry, "flat_cycle_fn": flat_cycle_fn, "campaign_root": str(root)}
        return run_flat_opportunity_cycle(c)

    return {
        "reconcile_fn": _reconcile,
        "manage_fn": _manage,
        "cycle_fn": _cycle,
        "campaign_root": root,
        "exchange_write": os.environ.get("EXCHANGE_WRITE", "false").lower() in {"1", "true"},
    }
