"""V30 cross-cycle position management + trade finalize."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError, _float
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import (
    BybitDemoRealTransport,
    load_demo_env,
)
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import resolve_demo_env_path
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (
    POSITION_STILL_OPEN_MANAGED,
    PersistentPositionLifecycleManager,
)
from backend.nexus_research_ai_autonomy.same_setup_reentry_guard import closure_record_from_finalize
from backend.nexus_research_ai_autonomy.trade_completion_v30 import (
    finalize_closed_trade,
    persist_trade_closure,
)

ENTRY_CONTEXT_SCHEMA = "v30_entry_context_v1"
REGIME = "TREND_UP"


def entry_context_path(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "research_pnl_entry_context.json"


def closure_path(campaign_root: Path) -> Path:
    return campaign_root / "autonomy" / "last_trade_closure.json"


def save_entry_context(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"schema": ENTRY_CONTEXT_SCHEMA, **payload}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_entry_context(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:  # noqa: BLE001
        return None


def clear_entry_context(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)


def manage_tick_once(mgr: PersistentPositionLifecycleManager, tick_i: int) -> dict[str, Any]:
    """One bounded manage tick — may close and finalize."""
    load_demo_env(resolve_demo_env_path())
    client = DemoWriteClient()
    ckpt_path = mgr.checkpoint_path
    campaign_root = ckpt_path.parent.parent if ckpt_path else Path("/data/campaigns/research_v18_2_30")
    ctx_path = entry_context_path(campaign_root)
    ctx = load_entry_context(ctx_path) or {}

    open_pos = [p for p in mgr.positions.values() if p.status == "OPEN"]
    if not open_pos:
        try:
            recovered = mgr.recover_from_exchange(client)
            if recovered:
                open_pos = [recovered]
        except Exception:  # noqa: BLE001
            pass
    if not open_pos:
        return {
            "tick": tick_i,
            "adaptive_action": "NONE",
            "closed": False,
            "reason": "no_open_position",
            "POSITION_STILL_OPEN_MANAGED": False,
        }

    pos = open_pos[0]
    symbol = pos.symbol
    try:
        raw = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
        rows = (raw.get("result") or {}).get("list") or []
        last = _float((rows[0] if rows else {}).get("lastPrice") or pos.entry_price) or pos.entry_price
    except Exception:  # noqa: BLE001
        last = pos.entry_price

    try:
        positions = client.list_positions(symbol)
    except DemoWriteError:
        positions = []

    if not positions:
        exit_reason = "TAKE_PROFIT"
        hold_sec = (time.time() * 1000 - pos.opened_at_ms) / 1000.0 if pos.opened_at_ms else 0.0
        if pos.path_tracker:
            pos.path_tracker.update(last, now_ms=int(time.time() * 1000))
        finalized = _finalize_from_context(
            mgr=mgr,
            pos=pos,
            client=client,
            ctx=ctx,
            exit_px=last,
            exit_reason=exit_reason,
            hold_sec=hold_sec,
            campaign_root=campaign_root,
        )
        clear_entry_context(ctx_path)
        return {
            "tick": tick_i,
            "adaptive_action": "EXIT",
            "closed": True,
            "exit_reason": exit_reason,
            "lifecycle": finalized.get("lifecycle"),
            **finalized.get("contract", {}),
            **{k: finalized[k] for k in ("closed", "position_closed", "net_realized", "ACCOUNTING_COMPLETE") if k in finalized},
        }

    mres = mgr.manage_cycle(
        pos.position_id,
        market={"last_price": last, "price": last, "liquidity": 0.95},
        regime=REGIME,
        ai_proposal="HOLD",
    )
    telemetry = mgr.compute_open_telemetry(pos, last)
    mgr.save_checkpoint(pos, bybit_order_id=ctx.get("bybit_order_id"))

    action = str(mres.get("action") or "HOLD")
    if action == "EXIT":
        exit_reason = str(mres.get("reason") or "managed_exit")
        try:
            p0 = positions[0]
            transport = BybitDemoRealTransport(auto_close=False)
            transport.reduce_only_close(symbol, str(p0.get("side") or "Buy"), str(p0.get("size") or pos.qty))
            time.sleep(0.6)
        except Exception as exc:  # noqa: BLE001
            return {
                "tick": tick_i,
                "adaptive_action": "EXIT",
                "close_error": type(exc).__name__,
                "POSITION_STILL_OPEN_MANAGED": True,
                "open_position_telemetry": telemetry.to_dict(),
            }
        hold_sec = (time.time() * 1000 - pos.opened_at_ms) / 1000.0 if pos.opened_at_ms else 0.0
        finalized = _finalize_from_context(
            mgr=mgr,
            pos=pos,
            client=client,
            ctx=ctx,
            exit_px=last,
            exit_reason=exit_reason,
            hold_sec=hold_sec,
            campaign_root=campaign_root,
        )
        clear_entry_context(ctx_path)
        return {
            "tick": tick_i,
            "adaptive_action": "EXIT",
            "closed": True,
            "exit_reason": exit_reason,
            "open_position_telemetry": telemetry.to_dict(),
            "lifecycle": finalized.get("lifecycle"),
            **finalized.get("contract", {}),
            **{k: finalized[k] for k in ("closed", "position_closed", "net_realized", "ACCOUNTING_COMPLETE") if k in finalized},
        }

    hard_max = int(ctx.get("hard_max") or pos.max_hold_sec or 3600)
    elapsed = (time.time() * 1000 - pos.opened_at_ms) / 1000.0 if pos.opened_at_ms else 0.0
    if elapsed >= hard_max:
        exit_reason = "STRATEGY_HORIZON_EXPIRED"
        try:
            p0 = positions[0]
            transport = BybitDemoRealTransport(auto_close=False)
            transport.reduce_only_close(symbol, str(p0.get("side") or "Buy"), str(p0.get("size") or pos.qty))
            time.sleep(0.6)
        except Exception as exc:  # noqa: BLE001
            return {
                "tick": tick_i,
                "adaptive_action": "EXIT",
                "close_error": type(exc).__name__,
                "POSITION_STILL_OPEN_MANAGED": True,
            }
        finalized = _finalize_from_context(
            mgr=mgr,
            pos=pos,
            client=client,
            ctx=ctx,
            exit_px=last,
            exit_reason=exit_reason,
            hold_sec=elapsed,
            campaign_root=campaign_root,
        )
        clear_entry_context(ctx_path)
        return {
            "tick": tick_i,
            "adaptive_action": "EXIT",
            "closed": True,
            "exit_reason": exit_reason,
            "lifecycle": finalized.get("lifecycle"),
            **finalized.get("contract", {}),
        }

    return {
        "tick": tick_i,
        "adaptive_action": action,
        "reason": mres.get("reason"),
        "POSITION_STILL_OPEN_MANAGED": True,
        "open_position_telemetry": telemetry.to_dict(),
        "closed": False,
    }


def _finalize_from_context(
    *,
    mgr: PersistentPositionLifecycleManager,
    pos: Any,
    client: DemoWriteClient,
    ctx: dict[str, Any],
    exit_px: float,
    exit_reason: str,
    hold_sec: float,
    campaign_root: Path,
) -> dict[str, Any]:
    from backend.nexus_research_ai_autonomy.horizon_feasibility import build_horizon_plan
    from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size

    plan_data = ctx.get("horizon_plan") or {}
    sizing_data = ctx.get("sizing") or {}
    horiz_data = ctx.get("horizon_feasibility") or {}
    econ_data = ctx.get("economic_entry_filter") or {}
    decision = ctx.get("decision") or {}
    order = ctx.get("order") or {}
    vol_h = float(ctx.get("vol_h") or 0.35)

    class _Plan:
        expected_path_range_pct = plan_data.get("expected_path_range_pct", 0.55)

        def to_dict(self) -> dict[str, Any]:
            return plan_data

    class _Horiz:
        def to_dict(self) -> dict[str, Any]:
            return horiz_data

    class _Econ:
        def to_dict(self) -> dict[str, Any]:
            return econ_data

    class _Sizing:
        qty_str = sizing_data.get("qty_str") or str(pos.qty)

        def to_dict(self) -> dict[str, Any]:
            return sizing_data

    finalized = finalize_closed_trade(
        client=client,
        symbol=pos.symbol,
        side=pos.side,
        entry_px=float(pos.entry_price),
        exit_px=exit_px,
        qty=float(pos.qty),
        oid=str(ctx.get("bybit_order_id") or ""),
        entry_ts=int(ctx.get("entry_ts") or pos.opened_at_ms),
        exit_reason=exit_reason,
        hold_sec=hold_sec,
        opened_mono=float(ctx.get("opened_mono") or time.time()),
        wallet_before=ctx.get("wallet_before") or {},
        decision=decision,
        plan=_Plan(),
        horiz=_Horiz(),
        econ=_Econ(),
        sizing=_Sizing(),
        order=order,
        pos=pos,
        hard_max=int(ctx.get("hard_max") or pos.max_hold_sec or 3600),
        vol_h=vol_h,
        setup_signature=ctx.get("setup_signature"),
    )
    mgr.clear_checkpoint()
    record = closure_record_from_finalize(
        finalized,
        setup_signature=str(ctx.get("setup_signature") or ""),
        momentum_at_entry=ctx.get("momentum_at_entry"),
    )
    persist_trade_closure(closure_path(campaign_root), record)
    return finalized


def make_manage_tick_fn(campaign_root: Path):
    def _tick(mgr: PersistentPositionLifecycleManager, tick_i: int) -> dict[str, Any]:
        return manage_tick_once(mgr, tick_i)

    return _tick
