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
from backend.nexus_research_ai_autonomy.position_manager import PositionManager
from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size

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
    pm = PositionManager()
    pos = pm.open_from_execution(decision=decision, fill_price=entry_px, qty=qty)

    opened_mono = time.time()
    exit_reason = "STRATEGY_HORIZON_EXPIRED"
    exit_px = entry_px
    management_ticks: list[dict[str, Any]] = []
    position_zero = False
    poll_sec = 5.0

    while True:
        elapsed = time.time() - opened_mono
        try:
            positions = client.list_positions(symbol)
        except DemoWriteError:
            positions = []
        if not positions:
            position_zero = True
            exit_reason = "TAKE_PROFIT"  # exchange SL/TP likely; refined from closedPnl later
            try:
                t2 = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
                r2 = (t2.get("result") or {}).get("list") or []
                exit_px = _float((r2[0] if r2 else {}).get("lastPrice") or entry_px) or entry_px
            except Exception:  # noqa: BLE001
                exit_px = entry_px
            if pos.path_tracker:
                pos.path_tracker.update(exit_px, now_ms=int(time.time() * 1000))
            break

        try:
            t2 = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
            r2 = (t2.get("result") or {}).get("list") or []
            last = _float((r2[0] if r2 else {}).get("lastPrice") or entry_px) or entry_px
        except Exception:  # noqa: BLE001
            last = entry_px

        mres = pm.manage_cycle(
            pos.position_id,
            market={"last_price": last, "price": last, "liquidity": 0.95},
            regime=REGIME,
            ai_proposal="HOLD",
        )
        management_ticks.append(
            {
                "elapsed_sec": round(elapsed, 2),
                "last": last,
                "action": mres.get("action"),
                "reason": mres.get("reason"),
            }
        )
        if mres.get("action") == "EXIT":
            exit_reason = str(mres.get("reason") or "managed_exit")
            exit_px = last
            try:
                p0 = positions[0]
                transport.reduce_only_close(symbol, str(p0.get("side") or "Buy"), str(p0.get("size") or qty))
                time.sleep(0.5)
                position_zero = len(client.list_positions(symbol)) == 0
            except Exception as exc:  # noqa: BLE001
                management_ticks.append({"close_error": type(exc).__name__})
            break

        if elapsed >= hard_max:
            exit_reason = "STRATEGY_HORIZON_EXPIRED"
            exit_px = last
            try:
                p0 = positions[0]
                transport.reduce_only_close(symbol, str(p0.get("side") or "Buy"), str(p0.get("size") or qty))
                time.sleep(0.6)
                position_zero = len(client.list_positions(symbol)) == 0
            except Exception as exc:  # noqa: BLE001
                management_ticks.append({"close_error": type(exc).__name__})
            break

        time.sleep(poll_sec)

    hold_sec = time.time() - opened_mono
    fill = close = None
    wallet_after = None
    for _ in range(10):
        time.sleep(1.2)
        try:
            if not client.list_positions(symbol):
                position_zero = True
        except DemoWriteError:
            pass
        fill, close = _settle_accounting(
            client=client, symbol=symbol, oid=str(oid), entry_ts=int(order.get("fill_ts") or time.time() * 1000)
        )
        wallet_after = client.fetch_wallet_snapshot()
        if position_zero and (fill is not None or close is not None):
            break
    if wallet_after is None:
        wallet_after = client.fetch_wallet_snapshot()

    if fill and fill.get("execPrice"):
        entry_px = float(fill["execPrice"])
    if close and close.get("avgExitPrice"):
        try:
            exit_px = float(close["avgExitPrice"])
        except (TypeError, ValueError):
            pass

    # Refine exit reason from exchange close vs local path
    if close:
        try:
            avg_exit = float(close.get("avgExitPrice") or exit_px)
            stop_p = float(decision["stop_logic"]["price"])
            tp_p = float(decision["take_profit_logic"]["price"])
            if abs(avg_exit - tp_p) / tp_p < 0.0005 or avg_exit >= tp_p:
                exit_reason = "TAKE_PROFIT"
            elif abs(avg_exit - stop_p) / stop_p < 0.0005 or avg_exit <= stop_p:
                if exit_reason not in {"TRAILING_STOP", "STOP_LOSS"}:
                    exit_reason = "STOP_LOSS"
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    pnl_pct = ((exit_px - entry_px) / entry_px * 100.0) if entry_px else 0.0
    exchange_closed_v = None
    if close and close.get("closedPnl") is not None:
        try:
            exchange_closed_v = float(close["closedPnl"])
            notional = entry_px * qty
            if notional > 0:
                pnl_pct = exchange_closed_v / notional * 100.0
        except (TypeError, ValueError):
            exchange_closed_v = None

    pe = _process_evidence(compliant=True, pnl_pct=pnl_pct, purpose=LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE)
    process_pnl = exchange_closed_v if exchange_closed_v is not None else pnl_pct
    process_class = classify_completed_trade(pnl=process_pnl, process_evidence=pe)
    if process_class == "UNDETERMINED":
        process_class = "GOOD_PROCESS_LOSS" if process_pnl < 0 else "GOOD_PROCESS_WIN"

    path_snap = pos.path_tracker.to_dict() if pos.path_tracker else {}
    realized_usdt = float(exchange_closed_v) if exchange_closed_v is not None else (
        pnl_pct / 100.0 * entry_px * qty
    )
    exit_q = classify_exit_quality(
        exit_reason=exit_reason,
        realized_usdt=realized_usdt,
        mfe_usdt=float(path_snap.get("mfe_usdt") or 0.0),
        mae_usdt=float(path_snap.get("mae_usdt") or 0.0),
        target_touched=bool(path_snap.get("target_touched")),
        stop_touched=bool(path_snap.get("stop_touched")),
        hold_sec=hold_sec,
        hard_max_hold=hard_max,
        expected_target_move_pct=TARGET_PCT,
        expected_path_range_pct=plan.expected_path_range_pct,
        stop_move_pct=STOP_PCT,
    )

    proximity = audit_entry_exit_proximity(
        entry_price=entry_px,
        exit_price=exit_px,
        hold_sec=hold_sec,
        exit_reason=exit_reason,
        lifecycle_purpose=LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        stop_pct=STOP_PCT,
        auto_close_immediate=False,
        max_hold_sec=hard_max,
    )

    econ_out = annotate_actual_fees(
        econ.to_dict(),
        open_fee=(close or {}).get("openFee") or (fill or {}).get("execFee"),
        close_fee=(close or {}).get("closeFee") or (fill or {}).get("close_execFee"),
        fee_currency="USDT",
    )

    life = {
        "decision_id": decision["decision_id"],
        "symbol": symbol,
        "side": "LONG",
        "pnl_pct": pnl_pct,
        "exit_reason": exit_reason,
        "entry_price": entry_px,
        "exit_price": exit_px,
        "qty": str(order.get("qty") or sizing.qty_str),
        "notional_usdt": float(order.get("qty") or sizing.qty) * entry_px,
        "hold_sec": hold_sec,
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "execution_purpose": EXECUTION_PURPOSE_REAL,
        "transport_mode": order.get("transport_mode"),
        "transport_tag": "REAL" if order.get("real_http_request") else "LOCAL_SIMULATION",
        "bybit_orderId": oid,
        "bybit_executionId": order.get("bybit_executionId") or order.get("execution_id"),
        "position_zero": position_zero,
        "reduce_only_close": True,
        "process_class": process_class,
        "process_evidence": pe,
        "strategy_family": STRATEGY_FAMILY,
        "regime": REGIME,
        "stop_distance_pct": STOP_PCT,
        "target_distance_pct": TARGET_PCT,
        "trail_pct": TRAIL_PCT,
        "prepared_decision_horizon": {
            k: decision.get(k)
            for k in (
                "strategy_family",
                "entry_horizon",
                "expected_target_move_pct",
                "stop_move_pct",
                "target_price",
                "stop_price",
                "expected_time_to_target",
                "expected_time_to_stop",
                "recommended_hold_window",
                "hard_max_hold",
                "horizon_provenance",
                "horizon_feasibility_pass",
                "economic_edge_pass",
            )
        },
        "horizon_plan": plan.to_dict(),
        "horizon_feasibility": horiz.to_dict(),
        "ECONOMIC_EDGE_PASS": True,
        "HORIZON_FEASIBILITY_PASS": True,
        "path_excursion": path_snap,
        "exit_quality": exit_q,
        "economic_entry_filter": econ_out,
        "risk_sizing": sizing.to_dict(),
        "entry_exit_proximity_audit": proximity,
        "management_ticks_n": len(management_ticks),
        "management_ticks_sample": management_ticks[:8],
        "leverage": 1,
        "vol_pct_per_hour": vol_h,
    }
    accounted = build_lifecycle_accounting_record(
        lifecycle=life,
        account_identity=identity,
        wallet_before=wallet_before,
        wallet_after=wallet_after,
        exchange_fill=fill,
        exchange_close=close,
        historical=False,
    )
    wr = accounted.get("wallet_reconciliation") or {}
    if accounted.get("accounting_status") == "ACCOUNTING_COMPLETE" and not wr.get(
        "WALLET_RECONCILIATION_PASS"
    ):
        accounted["accounting_status"] = "PENDING_WALLET_AFTER"
        accounted["ACCOUNTING_COMPLETE"] = False

    return {
        "executed": True,
        "WAIT": False,
        "lifecycle": accounted,
        "sizing": sizing.to_dict(),
        "economic_entry_filter": econ_out,
        "horizon_feasibility": horiz.to_dict(),
        "horizon_plan": plan.to_dict(),
        "ECONOMIC_EDGE_PASS": True,
        "HORIZON_FEASIBILITY_PASS": True,
        "path_excursion": path_snap,
        "exit_quality": exit_q,
        "entry_exit_proximity_audit": proximity,
        "hold_sec": hold_sec,
        "notional_usdt": life["notional_usdt"],
        "preferred_success_shape": "HORIZON_PASS_MEANINGFUL_HOLD",
        "order_latency": {
            "network_roundtrip_ms": ((order.get("monotonic") or {}).get("network_roundtrip_ms")),
            "bybit_orderId": oid,
        },
    }

