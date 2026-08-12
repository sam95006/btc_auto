"""Stable V30 research PnL trade — backend-only (no version runner imports)."""
from __future__ import annotations

import math
import statistics
import time
import uuid
from typing import Any

from backend.nexus_autonomy.process_classification import classify_completed_trade
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError, _float
from backend.nexus_demo_execution.wallet_lifecycle_accounting import (
    build_lifecycle_accounting_record,
    match_exchange_rows_for_order,
)
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import (
    EXECUTION_PURPOSE_REAL,
    BybitDemoRealTransport,
    load_demo_env,
)
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import resolve_demo_env_path
from backend.nexus_research_ai_autonomy.economic_entry_filter import (
    annotate_actual_fees,
    evaluate_economic_entry,
)
from backend.nexus_research_ai_autonomy.exit_quality import classify_exit_quality
from backend.nexus_research_ai_autonomy.horizon_feasibility import (
    annotate_prepared_decision_horizon,
    build_horizon_plan,
    evaluate_horizon_feasibility,
)
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
    audit_entry_exit_proximity,
)
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (
    POSITION_STILL_OPEN_MANAGED,
    PersistentPositionLifecycleManager,
)
from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size
from backend.nexus_research_ai_autonomy.trade_completion_v30 import build_setup_signature
from backend.nexus_research_ai_autonomy.trade_manage_v30 import entry_context_path, save_entry_context

STOP_PCT = 0.40
TARGET_PCT = 0.55
STRATEGY_FAMILY = "TREND"

REGIME = "TREND_UP"
TRAIL_PCT = 0.30
RESEARCH_PNL_PREFERRED_EXPECTED_NET_TP_USDT = 1.0


def estimate_btc_vol_pct_per_hour(client: DemoWriteClient, symbol: str = "BTCUSDT") -> float:
    try:
        raw = client.public_get(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": "5", "limit": 48},
        )
        rows = (raw.get("result") or {}).get("list") or []
        closes: list[float] = []
        for r in rows:
            if isinstance(r, (list, tuple)) and len(r) >= 5:
                closes.append(float(r[4]))
            elif isinstance(r, dict):
                closes.append(float(r.get("close") or r.get("c") or 0))
        closes = [c for c in closes if c > 0]
        if len(closes) < 6:
            return 0.35
        rets = [
            math.log(closes[i] / closes[i + 1])
            for i in range(len(closes) - 1)
            if closes[i + 1] > 0
        ]
        if len(rets) < 4:
            return 0.35
        std_5m = statistics.pstdev(rets)
        hourly = abs(std_5m) * math.sqrt(12) * 100.0
        return max(0.10, min(2.5, hourly))
    except Exception:  # noqa: BLE001
        return 0.35


def _settle_accounting(*, client: DemoWriteClient, symbol: str, oid: str, entry_ts: int):
    fill = close = None
    try:
        exs = client.list_executions(symbol=symbol, limit=100)
        cps = client.list_closed_pnl(symbol=symbol, limit=50)
    except DemoWriteError:
        return None, None
    fill, close = match_exchange_rows_for_order(order_id=oid, executions=exs, closed_pnls=cps)
    fee_total = 0.0
    entry_exec = close_exec = None
    for row in exs:
        if str(row.get("orderId") or "") == str(oid):
            entry_exec = row
            fee_total += abs(float(row.get("execFee") or 0))
            entry_ts = int(row.get("execTime") or entry_ts)
    for row in exs:
        t = int(row.get("execTime") or 0)
        if (
            str(row.get("orderId") or "") != str(oid)
            and abs(t - entry_ts) < 900_000
            and str(row.get("side") or "") != str((entry_exec or {}).get("side") or "")
        ):
            close_exec = row
            fee_total += abs(float(row.get("execFee") or 0))
            break
    if close is None and close_exec is not None:
        close_oid = str(close_exec.get("orderId") or "")
        for row in cps:
            if str(row.get("orderId") or "") == close_oid:
                close = row
                break
        if close is None:
            for row in cps:
                t = int(row.get("updatedTime") or row.get("createdTime") or 0)
                if abs(t - entry_ts) < 900_000:
                    close = row
                    break
    if fill is None and entry_exec is not None:
        fill = {
            "orderId": entry_exec.get("orderId"),
            "execId": entry_exec.get("execId"),
            "executionId": entry_exec.get("execId"),
            "execPrice": entry_exec.get("execPrice"),
            "execQty": entry_exec.get("execQty"),
            "execFee": str(fee_total),
            "feeCurrency": entry_exec.get("feeCurrency") or "USDT",
            "execTime": entry_exec.get("execTime"),
            "close_orderId": (close_exec or {}).get("orderId"),
            "close_execFee": (close_exec or {}).get("execFee"),
            "close_execPrice": (close_exec.get("execPrice") if close_exec else None),
            "isMaker": entry_exec.get("isMaker"),
        }
    elif fill is not None:
        fill["execFee"] = str(fee_total)
        if close_exec:
            fill["close_orderId"] = close_exec.get("orderId")
            fill["close_execFee"] = close_exec.get("execFee")
            fill["close_execPrice"] = close_exec.get("execPrice")
    return fill, close


def _process_evidence(*, compliant: bool, pnl_pct: float, purpose: str) -> dict[str, Any]:
    return {
        "rule_violation_ids": [],
        "missing_evidence_ids": [],
        "risk_gate_results": {"status": "PASS", "concurrent": 1, "leverage": 1},
        "cost_gate_results": {"status": "PASS"},
        "data_quality_results": {"status": "PASS"},
        "prohibited_action_results": [],
        "entry_rule_compliance": "PASS" if compliant else "FAIL",
        "exit_rule_compliance": "PASS",
        "why": f"lifecycle_purpose={purpose}",
        "execution_quality": "demo_rest",
        "chain": "horizon→econ→size→order→manage→exit→wallet_recon→Reflection",
        "pnl_pct": pnl_pct,
        "process_quality_independent_of_pnl": True,
    }


def run_research_pnl_trade_v30(
    *,
    account: dict[str, Any],
    symbol: str = "BTCUSDT",
    side: str = "LONG",
    qty_override: str | None = None,
    exchange_preflight_pass: bool = False,
) -> dict[str, Any]:
    """Horizon-gated RESEARCH_PNL_TRADE — WAIT on mismatch; never generic 180s timer."""
    load_demo_env(resolve_demo_env_path())
    client = DemoWriteClient()
    identity = account.get("raw_identity") or account
    equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)

    tickers = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
    rows = (tickers.get("result") or {}).get("list") or []
    price = _float((rows[0] if rows else {}).get("lastPrice") or 0)
    if price <= 0:
        return {"executed": False, "reason": "price_missing", "WAIT": True}

    vol_h = estimate_btc_vol_pct_per_hour(client, symbol)
    # V27: full thesis plan from strategy config — NO SESSION_OBSERVE_CAP on hard_max_hold
    plan = build_horizon_plan(
        strategy_family=STRATEGY_FAMILY,
        side=side.upper() if side.upper() in {"LONG", "SHORT"} else "LONG",
        entry_price=price,
        expected_target_move_pct=TARGET_PCT,
        stop_move_pct=STOP_PCT,
        realized_vol_pct_per_hour=vol_h,
        regime=REGIME,
        activity_score=0.75,
        liquidity=0.95,
    )
    thesis_plan = plan

    info = client.fetch_instrument(symbol)
    step = client.qty_step(info)
    min_q = client.min_qty(info)
    min_n = client.min_notional(info)

    sizing = compute_risk_based_size(
        equity=equity,
        entry_price=price,
        stop_distance_pct=STOP_PCT,
        target_distance_pct=TARGET_PCT,
        fee_rate_roundtrip=0.0011,
        slippage_pct=0.02,
        liquidity=0.95,
        confidence=0.78,
        qty_step=step,
        min_qty=min_q,
        min_notional=min_n,
        preferred_notional=350.0,
    )
    if sizing.action == "WAIT":
        return {
            "executed": False,
            "WAIT": True,
            "reason": "risk_based_sizing_wait",
            "sizing": sizing.to_dict(),
            "horizon_plan": plan.to_dict(),
            "thesis_horizon_plan": thesis_plan.to_dict(),
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        }

    econ = evaluate_economic_entry(
        notional_usdt=sizing.notional_usdt,
        target_distance_pct=TARGET_PCT,
        roundtrip_fee_pct=0.11,
        slippage_pct=0.02,
        preferred_net_tp_usdt=RESEARCH_PNL_PREFERRED_EXPECTED_NET_TP_USDT,
    )
    econ_pass = econ.action == "PASS"
    horiz = evaluate_horizon_feasibility(plan=plan, economic_edge_pass=econ_pass)
    if not horiz.horizon_feasibility_pass or horiz.action == "WAIT":
        return {
            "executed": False,
            "WAIT": True,
            "reason": horiz.block_code or "HORIZON_TARGET_MISMATCH",
            "sizing": sizing.to_dict(),
            "economic_entry_filter": econ.to_dict(),
            "horizon_feasibility": horiz.to_dict(),
            "horizon_plan": plan.to_dict(),
            "thesis_horizon_plan": thesis_plan.to_dict(),
            "ECONOMIC_EDGE_PASS": econ_pass,
            "HORIZON_FEASIBILITY_PASS": False,
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "note": "honest_WAIT_do_not_enter_and_hope; do_not_shrink_target",
            "preferred_success_shape": "WAIT_ON_MISMATCH",
        }
    if not econ_pass:
        return {
            "executed": False,
            "WAIT": True,
            "reason": "economic_entry_filter_wait",
            "sizing": sizing.to_dict(),
            "economic_entry_filter": econ.to_dict(),
            "horizon_feasibility": horiz.to_dict(),
            "ECONOMIC_EDGE_PASS": False,
            "HORIZON_FEASIBILITY_PASS": True,
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "note": "do_not_raise_risk_to_force_1u",
        }

    wallet_before = client.fetch_wallet_snapshot()
    hard_max = int(plan.hard_max_hold)
    transport = BybitDemoRealTransport(auto_close=False, max_hold_sec=hard_max)
    order_side = "Sell" if str(side).upper() == "SHORT" else "Buy"
    intent = {
        "symbol": symbol,
        "side": order_side,
        "qty": qty_override or sizing.qty_str,
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "stop_distance_pct": STOP_PCT,
        "target_distance_pct": TARGET_PCT,
        "force_immediate_close": False,
        "exchange_preflight_pass": exchange_preflight_pass,
    }
    order = transport.send_research_order(intent)
    if not order.get("accepted"):
        return {
            "executed": False,
            "WAIT": False,
            "reason": order.get("reason") or "order_rejected",
            "order": order,
            "sizing": sizing.to_dict(),
            "economic_entry_filter": econ.to_dict(),
            "horizon_feasibility": horiz.to_dict(),
        }

    oid = order.get("bybit_orderId") or order.get("order_id")
    entry_px = float(order.get("entry_price") or price)
    qty = float(order.get("qty") or sizing.qty)
    # Rebuild plan prices at fill
    plan = build_horizon_plan(
        strategy_family=STRATEGY_FAMILY,
        side=side.upper() if side.upper() in {"LONG", "SHORT"} else "LONG",
        entry_price=entry_px,
        expected_target_move_pct=TARGET_PCT,
        stop_move_pct=STOP_PCT,
        realized_vol_pct_per_hour=vol_h,
        regime=REGIME,
        activity_score=0.75,
        liquidity=0.95,
        hard_max_hold_override=hard_max,
    )
    decision = annotate_prepared_decision_horizon(
        {
            "decision_id": f"pd_pnl_{uuid.uuid4().hex[:12]}",
            "symbol": symbol,
            "side": side.upper() if side.upper() in {"LONG", "SHORT"} else "LONG",
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "regime": REGIME,
            "trail_pct": TRAIL_PCT,
            "horizon_feasibility_pass": True,
            "economic_edge_pass": True,
            "stop_logic": {"price": plan.stop_price, "pct": STOP_PCT},
            "take_profit_logic": {"price": plan.target_price, "pct": TARGET_PCT},
        },
        plan,
    )
    # Protective exits prioritize Risk — use exchange SL/TP already set by transport;
    # local stop mirrors plan (may be trail-updated).
    decision["stop_logic"]["price"] = float(order.get("protective_stop") or plan.stop_price)
    decision["take_profit_logic"]["price"] = float(order.get("take_profit") or plan.target_price)

    try:
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root

        ckpt_root = campaign_root()
    except Exception:  # noqa: BLE001
        ckpt_root = None
    ckpt = (
        ckpt_root / "autonomy" / "research_pnl_position.json"
        if ckpt_root is not None
        else None
    )
    pm = PersistentPositionLifecycleManager(checkpoint_path=ckpt)
    pos = pm.open_from_execution(decision=decision, fill_price=entry_px, qty=qty)
    opened_mono = time.time()
    entry_ts = int(order.get("fill_ts") or time.time() * 1000)
    setup_signature = build_setup_signature(
        symbol=symbol,
        side=side.upper(),
        strategy_family=STRATEGY_FAMILY,
        regime=REGIME,
    )
    pm.save_checkpoint(pos, bybit_order_id=str(oid))
    if ckpt_root is not None:
        save_entry_context(
            entry_context_path(ckpt_root),
            {
                "bybit_order_id": str(oid),
                "entry_ts": entry_ts,
                "opened_mono": opened_mono,
                "hard_max": hard_max,
                "wallet_before": wallet_before,
                "decision": decision,
                "order": order,
                "horizon_plan": plan.to_dict(),
                "horizon_feasibility": horiz.to_dict(),
                "economic_entry_filter": econ.to_dict(),
                "sizing": sizing.to_dict(),
                "vol_h": vol_h,
                "setup_signature": setup_signature,
                "momentum_at_entry": None,
                "symbol": symbol,
                "side": side.upper(),
            },
        )

    return {
        "executed": True,
        "WAIT": False,
        "closed": False,
        "position_closed": False,
        "POSITION_STILL_OPEN_MANAGED": True,
        "position_open": True,
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "symbol": symbol,
        "side": side.upper(),
        "entry_price": entry_px,
        "bybit_orderId": oid,
        "setup_signature": setup_signature,
        "sizing": sizing.to_dict(),
        "economic_entry_filter": econ.to_dict(),
        "horizon_feasibility": horiz.to_dict(),
        "horizon_plan": plan.to_dict(),
        "ECONOMIC_EDGE_PASS": True,
        "HORIZON_FEASIBILITY_PASS": True,
        "notional_usdt": float(qty) * entry_px,
        "preferred_success_shape": "POSITION_OPEN_MANAGED_ACROSS_CYCLES",
        "order_latency": {
            "network_roundtrip_ms": ((order.get("monotonic") or {}).get("network_roundtrip_ms")),
            "bybit_orderId": oid,
        },
        "ai_used_for_entry": False,
        "ai_required_for_entry": False,
        "entry_path": "deterministic_v30_scan",
    }

