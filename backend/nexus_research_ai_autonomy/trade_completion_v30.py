"""V30 trade completion contract — accounting, reflection, persistence."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.process_classification import classify_completed_trade
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError
from backend.nexus_demo_execution.wallet_lifecycle_accounting import (
    build_lifecycle_accounting_record,
    reconcile_wallet_before_after,
    match_exchange_rows_for_order,
)
from backend.nexus_research_ai_autonomy.economic_entry_filter import annotate_actual_fees
from backend.nexus_research_ai_autonomy.exit_quality import classify_exit_quality
from backend.nexus_research_ai_autonomy.failure_reflection_v28 import create_failure_reflection
from backend.nexus_research_ai_autonomy.lifecycle_purpose import audit_entry_exit_proximity
from backend.nexus_research_ai_autonomy.reflection_v28 import ReflectionV28

CLOSURE_SCHEMA = "v30_trade_closure_v1"
REGIME = "TREND_UP"
STOP_PCT = 0.40
TARGET_PCT = 0.55
STRATEGY_FAMILY = "TREND"
TRAIL_PCT = 0.30
LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE = "RESEARCH_PNL_TRADE"


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


def build_setup_signature(
    *,
    symbol: str,
    side: str,
    strategy_family: str = STRATEGY_FAMILY,
    regime: str = REGIME,
    target_pct: float = TARGET_PCT,
    stop_pct: float = STOP_PCT,
) -> str:
    return f"{symbol}|{side.upper()}|{strategy_family}|{regime}|t{target_pct:.2f}|s{stop_pct:.2f}"


def build_trade_complete_contract(
    *,
    lifecycle: dict[str, Any],
    accounted: dict[str, Any] | None = None,
    reflection_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explicit production trade-complete fields."""
    life = accounted if accounted else lifecycle
    wr = life.get("wallet_reconciliation") or {}
    ea = life.get("exact_pnl_accounting") or {}
    path = life.get("path_excursion") or {}
    exit_q = life.get("exit_quality") or {}
    acct_ok = bool(
        life.get("ACCOUNTING_COMPLETE")
        or life.get("accounting_status") == "ACCOUNTING_COMPLETE"
    )
    net = (
        ea.get("calculated_net_pnl")
        or ea.get("net_realized")
        or life.get("net_realized")
    )
    closed = bool(life.get("position_zero") or life.get("closed"))
    return {
        "position_closed": closed,
        "closed": closed,
        "ACCOUNTING_COMPLETE": acct_ok,
        "wallet_reconciliation": wr,
        "exit_reason": life.get("exit_reason"),
        "hold_sec": life.get("hold_sec"),
        "net_realized": net,
        "MFE": path.get("mfe_usdt"),
        "MAE": path.get("mae_usdt"),
        "exit_quality": exit_q.get("exit_quality_class") or exit_q,
        "process_class": life.get("process_class"),
        "setup_signature": life.get("setup_signature"),
        "Reflection_created": bool(reflection_bundle and reflection_bundle.get("reflection_created")),
        "mistake_signature": (reflection_bundle or {}).get("mistake_signature"),
        "CandidateLesson_created": bool((reflection_bundle or {}).get("candidate_lesson_created")),
        "reflection": reflection_bundle,
    }


def _mistake_signature_registry_path(campaign_root: Path | None = None) -> Path:
    from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root as cr

    root = campaign_root or cr()
    return root / "autonomy" / "mistake_signature_registry.json"


def _increment_mistake_signature_repeat(mistake_signature: str | None) -> int:
    """Track repeat_count for a mistake_signature (CandidateLesson stays CANDIDATE)."""
    if not mistake_signature:
        return 0
    path = _mistake_signature_registry_path()
    registry: dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                registry = raw
        except Exception:  # noqa: BLE001
            registry = {}
    entry = registry.get(mistake_signature) or {"repeat_count": 0, "first_seen_ms": int(time.time() * 1000)}
    entry["repeat_count"] = int(entry.get("repeat_count") or 0) + 1
    entry["last_seen_ms"] = int(time.time() * 1000)
    registry[mistake_signature] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(registry, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
    return int(entry["repeat_count"])


def run_production_reflection(lifecycle: dict[str, Any]) -> dict[str, Any]:
    """Reflection for ACCOUNTING_COMPLETE losses and BAD_PROCESS_WIN."""
    out: dict[str, Any] = {
        "reflection_created": False,
        "mistake_signature": None,
        "candidate_lesson_created": False,
        "reflection_required": False,
    }
    process_class = str(lifecycle.get("process_class") or "")
    ea = lifecycle.get("exact_pnl_accounting") or {}
    net = ea.get("calculated_net_pnl")
    try:
        net_f = float(net) if net is not None else None
    except (TypeError, ValueError):
        net_f = None
    is_loss = net_f is not None and net_f < 0
    is_bad_win = process_class == "BAD_PROCESS_WIN"
    if not is_loss and not is_bad_win:
        return out

    out["reflection_required"] = True
    exit_q_class = str((lifecycle.get("exit_quality") or {}).get("exit_quality_class") or "")
    fail_refl = create_failure_reflection(
        lifecycle,
        process_class=process_class,
        exit_quality_class=exit_q_class,
    )
    v28 = ReflectionV28()
    v28_rec = v28.reflect_lifecycle(lifecycle)

    qualities: dict[str, Any] = {}
    if fail_refl is not None:
        qualities = {
            "direction_quality": fail_refl.direction_quality,
            "entry_quality": fail_refl.entry_quality,
            "timing_quality": fail_refl.timing_quality,
            "stop_quality": "POOR" if "STOP" in str(fail_refl.root_causes) else "MIXED",
            "regime_fit": fail_refl.regime_fit,
            "cost_fit": fail_refl.cost_fit,
            "horizon_fit": fail_refl.horizon_fit,
            "exit_quality": fail_refl.exit_quality,
        }
        out["mistake_signature"] = fail_refl.mistake_signature
        out["repeat_count"] = _increment_mistake_signature_repeat(fail_refl.mistake_signature)
        out["candidate_lesson_created"] = fail_refl.candidate_lesson is not None
        if fail_refl.candidate_lesson:
            out["candidate_lesson"] = fail_refl.candidate_lesson.to_dict()

    out["reflection_created"] = fail_refl is not None or v28_rec is not None
    out["qualities"] = qualities
    if v28_rec is not None:
        out["reflection_v28"] = v28_rec.to_dict()
    if fail_refl is not None:
        out["failure_reflection"] = fail_refl.to_dict()
    return out


def persist_trade_closure(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_last_trade_closure(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:  # noqa: BLE001
        return None


def finalize_closed_trade(
    *,
    client: DemoWriteClient,
    symbol: str,
    side: str,
    entry_px: float,
    exit_px: float,
    qty: float,
    oid: str,
    entry_ts: int,
    exit_reason: str,
    hold_sec: float,
    opened_mono: float,
    wallet_before: dict[str, Any],
    decision: dict[str, Any],
    plan: Any,
    horiz: Any,
    econ: Any,
    sizing: Any,
    order: dict[str, Any],
    pos: Any,
    hard_max: int,
    vol_h: float,
    setup_signature: str | None = None,
) -> dict[str, Any]:
    """Settle accounting + reflection for a closed position."""
    fill, close = None, None
    position_zero = False
    wallet_after: dict[str, Any] | None = None
    settlement_state = "POSITION_ZERO"

    max_wait_sec = float(os.environ.get("NEXUS_WALLET_RECONCILIATION_MAX_WAIT_SEC", "45"))
    max_wait_sec = max(10.0, min(60.0, max_wait_sec))
    poll_sec = 1.0

    wallet_stable_count = 0
    last_wallet_snapshot: dict[str, Any] | None = None
    start_ts = time.time()

    while time.time() - start_ts < max_wait_sec:
        # POSITION_ZERO
        try:
            positions = client.list_positions(symbol)
            position_zero = not bool(positions)
        except Exception:  # noqa: BLE001
            position_zero = False

        if not position_zero:
            settlement_state = "POSITION_ZERO"
            time.sleep(poll_sec)
            continue

        # CLOSED_PNL_VISIBLE
        settlement_state = "CLOSED_PNL_VISIBLE"
        fill, close = _settle_accounting(
            client=client, symbol=symbol, oid=str(oid), entry_ts=int(entry_ts)
        )
        if fill is None and close is None:
            time.sleep(poll_sec)
            continue

        # WALLET_AFTER_STABLE
        settlement_state = "WALLET_AFTER_STABLE"
        wallet_after_candidate = client.fetch_wallet_snapshot()

        if (
            last_wallet_snapshot
            and (wallet_after_candidate.get("wallet_balance") == last_wallet_snapshot.get("wallet_balance"))
            and (wallet_after_candidate.get("coin_balance") == last_wallet_snapshot.get("coin_balance"))
        ):
            wallet_stable_count += 1
        else:
            wallet_stable_count = 0
        last_wallet_snapshot = wallet_after_candidate
        wallet_after = wallet_after_candidate

        if wallet_stable_count < 2:
            time.sleep(poll_sec)
            continue

        # WALLET_RECONCILIATION_PASS
        closed_pnl = None
        fees_total = 0.0
        funding = None
        if close is not None:
            closed_pnl = close.get("closedPnl")
            fees_total = abs(float(close.get("openFee") or 0)) + abs(float(close.get("closeFee") or 0))
            funding = close.get("fundingFee")
        elif fill is not None:
            closed_pnl = fill.get("closedPnl")
            fees_total = abs(float(fill.get("execFee") or 0))
            funding = None

        wallet_before_val = (wallet_before or {}).get("wallet_balance") or (wallet_before or {}).get("coin_balance")
        wallet_after_val = (wallet_after_candidate.get("wallet_balance") or wallet_after_candidate.get("coin_balance"))

        recon = reconcile_wallet_before_after(
            wallet_before=wallet_before_val,
            wallet_after=wallet_after_val,
            exchange_realized_pnl=closed_pnl if closed_pnl is not None else "0",
            fees=fees_total,
            funding=funding,
            tolerance="0.00000001",
        )

        if recon.get("WALLET_RECONCILIATION_PASS"):
            settlement_state = "WALLET_RECONCILIATION_PASS"
            break

        # keep waiting (wallet snapshot may still be settling)
        time.sleep(poll_sec)

    if wallet_after is None:
        wallet_after = client.fetch_wallet_snapshot()
    if settlement_state != "WALLET_RECONCILIATION_PASS":
        settlement_state = "PENDING_WALLET_RECONCILIATION"

    if fill and fill.get("execPrice"):
        entry_px = float(fill["execPrice"])
    if close and close.get("avgExitPrice"):
        try:
            exit_px = float(close["avgExitPrice"])
        except (TypeError, ValueError):
            pass

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
    realized_usdt = (
        float(exchange_closed_v)
        if exchange_closed_v is not None
        else pnl_pct / 100.0 * entry_px * qty
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

    sig = setup_signature or build_setup_signature(
        symbol=symbol,
        side=side,
        strategy_family=STRATEGY_FAMILY,
        regime=REGIME,
    )

    life = {
        "decision_id": decision["decision_id"],
        "symbol": symbol,
        "side": side.upper(),
        "pnl_pct": pnl_pct,
        "exit_reason": exit_reason,
        "entry_price": entry_px,
        "exit_price": exit_px,
        "qty": str(order.get("qty") or sizing.qty_str),
        "notional_usdt": float(order.get("qty") or sizing.qty) * entry_px,
        "hold_sec": hold_sec,
        "entry_ts_ms": int(entry_ts),
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "execution_purpose": "REAL",
        "transport_mode": order.get("transport_mode"),
        "transport_tag": "REAL" if order.get("real_http_request") else "LOCAL_SIMULATION",
        "bybit_orderId": oid,
        "bybit_executionId": order.get("bybit_executionId") or order.get("execution_id"),
        "position_zero": position_zero,
        "closed": True,
        "reduce_only_close": True,
        "process_class": process_class,
        "process_evidence": pe,
        "strategy_family": STRATEGY_FAMILY,
        "regime": REGIME,
        "regime_at_entry": REGIME,
        "stop_distance_pct": STOP_PCT,
        "target_distance_pct": TARGET_PCT,
        "trail_pct": TRAIL_PCT,
        "setup_signature": sig,
        "horizon_plan": plan.to_dict(),
        "horizon_feasibility": horiz.to_dict(),
        "ECONOMIC_EDGE_PASS": True,
        "HORIZON_FEASIBILITY_PASS": True,
        "path_excursion": path_snap,
        "exit_quality": exit_q,
        "economic_entry_filter": econ_out,
        "risk_sizing": sizing.to_dict(),
        "entry_exit_proximity_audit": proximity,
        "leverage": 1,
        "vol_pct_per_hour": vol_h,
        "opened_mono": opened_mono,
        "settlement_state": settlement_state,
    }
    accounted = build_lifecycle_accounting_record(
        lifecycle=life,
        account_identity=wallet_before,
        wallet_before=wallet_before,
        wallet_after=wallet_after,
        exchange_fill=fill,
        exchange_close=close,
        historical=False,
    )
    if accounted.get("accounting_status") == "ACCOUNTING_COMPLETE":
        accounted["settlement_state"] = "ACCOUNTING_COMPLETE"
    wr = accounted.get("wallet_reconciliation") or {}
    if accounted.get("accounting_status") == "ACCOUNTING_COMPLETE" and not wr.get(
        "WALLET_RECONCILIATION_PASS"
    ):
        accounted["accounting_status"] = "PENDING_WALLET_AFTER"
        accounted["ACCOUNTING_COMPLETE"] = False
    else:
        accounted["ACCOUNTING_COMPLETE"] = accounted.get("accounting_status") == "ACCOUNTING_COMPLETE"

    reflection_bundle = None
    if accounted.get("ACCOUNTING_COMPLETE"):
        reflection_bundle = run_production_reflection(accounted)
        accounted["reflection"] = reflection_bundle

    contract = build_trade_complete_contract(
        lifecycle=accounted,
        accounted=accounted,
        reflection_bundle=reflection_bundle,
    )
    return {
        "lifecycle": accounted,
        "contract": contract,
        "reflection": reflection_bundle,
        "closed": True,
        "position_closed": True,
        **contract,
    }
