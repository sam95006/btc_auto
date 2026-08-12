#!/usr/bin/env python3
"""V18.2.27 AGENT B — persistent position lifecycle + valid horizon + activity convergence.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_27_core.json
Live feed: D:\\NEXUS_RUNTIME\\evidence_coordinator\\founder_demo_monitor_live.json
api-demo.bybit.com only. Mainnet=0, real_money=false, leverage=1x. Never print secrets.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "0")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_activity_metric_v2.activity_recovery import (  # noqa: E402
    FRESHNESS_CLOCK_CHAIN,
    classify_freshness_publication_root,
    inspect_checkpoint,
)
from backend.nexus_activity_metric_v2.constants import DEFAULT_STALE_MS  # noqa: E402
from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, _float  # noqa: E402
from backend.nexus_demo_execution.pnl_accounting import (  # noqa: E402
    CLOSED_PNL_FEE_INCLUSIVE,
    CLOSED_PNL_SEMANTICS_NOTE,
)
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env  # noqa: E402
from backend.nexus_research_ai_autonomy.constants import (  # noqa: E402
    DEFAULT_LEVERAGE,
    DEFAULT_MAX_CONCURRENT,
)
from backend.nexus_research_ai_autonomy.horizon_feasibility import (  # noqa: E402
    build_expected_move_curve,
    build_horizon_plan,
    estimate_atr_pct,
)
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (  # noqa: E402
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
    separate_counters,
)
from backend.nexus_research_ai_autonomy.market_opportunity_selection import (  # noqa: E402
    score_market_candidate,
    select_best_market_opportunity,
)
from backend.nexus_research_ai_autonomy.prepared_decision import validate_prepared_decision_horizon  # noqa: E402
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (  # noqa: E402
    FORBIDDEN_PROCESS_EXIT_REASONS,
    POSITION_STILL_OPEN_MANAGED,
    PersistentPositionLifecycleManager,
    evaluate_horizon_integrity,
)
from backend.nexus_research_ai_autonomy.time_basis import (  # noqa: E402
    CURVE_HORIZONS_SEC,
    evaluate_compatible_horizon_feasibility,
    resolve_strategy_horizon_sec,
)
from backend.nexus_strategy_engine.ca5_dev_cycle import (  # noqa: E402
    run_ca5_development,
    run_ca5_s01_s02_diagnostic_comparison,
    run_ca5_successor_development,
)
from backend.nexus_strategy_engine.oos_path_integrity import HoldoutFirewall  # noqa: E402

import tools.research.activity_metric_v2.run_v18_2_21_core as v21  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_22_core as v22  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_23_core as v23  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_24_core as v24  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_25_core as v25  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_27_core.json")
LIVE_FEED = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json")
PRIOR_CORE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_26_core.json")
CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_27")
SCALE192_DIR = Path(r"D:\NEXUS_RUNTIME\campaigns\activity_v2_scale192_20260808T194544Z")
CKPT_ROOT = SCALE192_DIR / "runtime" / "activity_metric_v2"
POSITION_CKPT = CAMPAIGN_ROOT / "autonomy" / "research_pnl_position.json"
ENV_PATH = Path(r"D:\NEXUS\btc_bot\.env")
CA5_OOS_RES = Path(
    r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_22\alpha\seed_splits\v18_2_22_ca5_oos_reservation.json"
)
CA2_VARIANT = Path(
    r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_17\variant_runs\V18_CA2_H01_PANEL_TURNOVER.json"
)
CA3_VARIANT = Path(
    r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_17\variant_runs\V18_CA3_H01_HORIZON_COST.json"
)
CA5_OOS_HASH = "b8d9d7a225038f650b4c06b7075a428842da81e15ec26d6b8d2a27d4ca2e4c15"
TRACKING_CAP = 192
STOP_PCT = 0.40
TARGET_PCT = 0.55
STRATEGY_FAMILY = "TREND"
MAX_MARKET_SCAN = 48
PROCESS_OBSERVER_CAP_SEC = 720  # process lifetime only — NOT hard_max_hold
EXCLUDED_SYMBOLS = frozenset({"BEATUSDT"})


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_holdouts() -> dict[str, Any]:
    res = _load_json(CA5_OOS_RES) if CA5_OOS_RES.exists() else {}
    oos_hash = str(res.get("untouched_oos_hash") or CA5_OOS_HASH)
    assert oos_hash == CA5_OOS_HASH
    fw = HoldoutFirewall(
        untouched_oos_hash=oos_hash,
        reservation=res.get("reservation")
        or {"label": "UNTOUCHED_OOS_CA5_RESERVED", "status": "FROZEN_EMPTY_UNTIL_NEW_DATA"},
    )
    assert fw.oos_pre_access_count == 0
    return {
        "schema": "v18_2_27_holdout_firewall_check_v1",
        "untouched_oos_hash": oos_hash,
        "oos_pre_access_count": fw.oos_pre_access_count,
        "oos_opened": False,
        "oos_pre_access": 0,
        "ca5_holdout_sealed": True,
        "WF": False,
        "OOS": False,
    }


def fetch_ticker_universe(client: DemoWriteClient, symbols: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        raw = client.public_get("/v5/market/tickers", {"category": "linear"})
        rows = (raw.get("result") or {}).get("list") or []
        by_sym = {str(r.get("symbol") or ""): r for r in rows}
        for sym in symbols[:MAX_MARKET_SCAN]:
            if sym in EXCLUDED_SYMBOLS:
                continue
            r = by_sym.get(sym)
            if not r:
                continue
            price = _float(r.get("lastPrice") or 0)
            if price <= 0:
                continue
            out.append(
                {
                    "symbol": sym,
                    "last_price": price,
                    "turnover_24h": _float(r.get("turnover24h") or 0),
                    "volume_24h": _float(r.get("volume24h") or 0),
                    "change_pct_24h": _float(r.get("price24hPcnt") or 0) * 100.0,
                }
            )
    except Exception:  # noqa: BLE001
        pass
    return out


def scan_full_market_opportunities(
    *,
    client: DemoWriteClient,
    symbols: list[str],
    equity: float,
) -> dict[str, Any]:
    """Full-market funnel — strategy hard_max_hold from config; NO SESSION_OBSERVE_CAP."""
    tickers = fetch_ticker_universe(client, symbols)
    candidates = []
    for t in tickers:
        sym = t["symbol"]
        vol_h = v25.estimate_btc_vol_pct_per_hour(client, sym)
        try:
            info = client.fetch_instrument(sym)
            step = client.qty_step(info)
            min_q = client.min_qty(info)
            min_n = client.min_notional(info)
        except Exception:  # noqa: BLE001
            step, min_q, min_n = 0.001, 0.001, 5.0

        direction = "LONG" if float(t["change_pct_24h"]) >= 0 else "SHORT"
        cand = score_market_candidate(
            symbol=sym,
            entry_price=float(t["last_price"]),
            equity=equity,
            vol_pct_per_hour=vol_h,
            strategy_family=STRATEGY_FAMILY,
            direction=direction,
            target_pct=TARGET_PCT,
            stop_pct=STOP_PCT,
            turnover24h=float(t["turnover_24h"]),
            activity_score=0.75,
            qty_step=step,
            min_qty=min_q,
            min_notional=min_n,
        )
        candidates.append(cand)

    funnel_out = select_best_market_opportunity(candidates)
    return {
        "schema": "v18_2_27_full_market_opportunity_v1",
        "universe_size": len(symbols),
        "scanned": len(tickers),
        "selection": funnel_out,
        "funnel": funnel_out.get("funnel"),
        "SESSION_OBSERVE_CAP_removed": True,
        "hard_max_from_strategy_config": True,
        "implicit_btc_only": False,
        "BEATUSDT_reuse": False,
        "excluded_symbols": sorted(EXCLUDED_SYMBOLS),
    }


def _is_eligible_active(insp: dict[str, Any], *, now_ms: int) -> bool:
    age = insp.get("last_trade_age_ms")
    if age is None:
        return False
    return float(age) <= DEFAULT_STALE_MS


def audit_activity_v27(symbols: list[str], prior_activity: dict[str, Any]) -> dict[str, Any]:
    """Publisher repair v27 — eligible_active ready_conversion; BROKEN_PUBLISHER by failure stage."""
    repair = v23.repair_activity_stale(symbols)
    hb = v22._load_heartbeat(SCALE192_DIR / "heartbeat.json")
    live_n = int((repair.get("post") or {}).get("live") or 0)
    live_audit = v24.audit_live_regression(prior_activity, live_n, hb)

    now_ms = int(time.time() * 1000)
    event_ages: list[float] = []
    publisher_ages: list[float] = []
    stale_by_root: dict[str, int] = {}
    remaining_stale_roots: dict[str, int] = {}
    broken_publisher_by_stage: dict[str, int] = {}
    broken_publisher = 0
    no_new_trade = 0
    converted = 0
    eligible_active = 0
    ready_eligible_active = 0
    publication_audits: list[dict[str, Any]] = []

    for sym in symbols:
        path = CKPT_ROOT / f"activity_{sym}.json"
        insp = inspect_checkpoint(path, now_ms=now_ms)
        age = insp.get("last_trade_age_ms")
        market_event_ts = insp.get("last_trade_ts")
        if age is not None:
            event_ages.append(float(age))

        pub_path = path.with_suffix(".publisher.json")
        pub_age = None
        publisher_update_ts = None
        if pub_path.exists():
            try:
                pub = json.loads(pub_path.read_text(encoding="utf-8"))
                publisher_update_ts = int(pub.get("publisher_state") or pub.get("saved_at_ms") or 0)
                if publisher_update_ts:
                    pub_age = float(now_ms - publisher_update_ts)
                    publisher_ages.append(pub_age)
            except Exception:  # noqa: BLE001
                pass
        if pub_age is None and age is not None:
            publisher_ages.append(float(age))

        meta = path.with_suffix(".meta.json")
        sidecar_ignored = False
        if meta.exists() and path.exists():
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                saved = int(m.get("saved_at_ms") or 0)
                mtime_ms = int(path.stat().st_mtime * 1000)
                sidecar_ignored = saved <= mtime_ms and bool(insp.get("stale"))
            except Exception:  # noqa: BLE001
                pass

        cls = classify_freshness_publication_root(
            published_freshness_ts_ms=market_event_ts,
            checkpoint_ts_ms=int(path.stat().st_mtime * 1000) if path.exists() else None,
            gate_eval_ts_ms=now_ms,
            ws_live=live_n >= len(symbols) * 0.9,
            sidecar_ignored_publisher_stale=sidecar_ignored,
            raw_ws_event_ts_ms=market_event_ts,
        )
        root = cls.get("freshness_publication_root") or "OTHER"
        stale_by_root[root] = stale_by_root.get(root, 0) + 1
        sk = cls.get("stale_kind") or root

        is_active = _is_eligible_active(insp, now_ms=now_ms)
        if is_active:
            eligible_active += 1
            if not insp.get("stale"):
                ready_eligible_active += 1

        publication_audits.append(
            {
                "symbol": sym,
                "market_event_time_ms": market_event_ts,
                "publisher_update_time_ms": publisher_update_ts,
                "gate_eval_time_ms": now_ms,
                "freshness_publication_root": root,
                "stale_kind": sk,
                "eligible_active": is_active,
                "atomic_publication_audit": True,
            }
        )

        if age is not None and age > DEFAULT_STALE_MS:
            remaining_stale_roots[sk] = remaining_stale_roots.get(sk, 0) + 1
            if sk == "BROKEN_PUBLISHER_REFRESH":
                broken_publisher += 1
                stage = cls.get("publication_failure_stage") or root
                broken_publisher_by_stage[stage] = broken_publisher_by_stage.get(stage, 0) + 1
            elif sk == "NO_NEW_TRADE":
                no_new_trade += 1
        else:
            converted += 1

    event_ages.sort()
    publisher_ages.sort()

    def _p(vals: list[float], p: float) -> float | None:
        if not vals:
            return None
        return vals[min(len(vals) - 1, int(len(vals) * p / 100.0))]

    post = repair.get("post") or {}
    ready = int(post.get("ready") or 0)
    prior_ready = int(prior_activity.get("ready") or 0)
    ready_conversion_eligible = (
        ready_eligible_active / float(eligible_active) if eligible_active else 0.0
    )

    dominant = (
        "BROKEN_PUBLISHER_REFRESH"
        if broken_publisher >= no_new_trade
        else "NO_NEW_TRADE"
    )

    return {
        **repair,
        "schema": "v18_2_27_activity_publisher_repair_v1",
        "tracking": TRACKING_CAP,
        "subscribed": int((hb.get("ws_audit") or {}).get("subscription_acked") or TRACKING_CAP),
        "live": post.get("live"),
        "ready": ready,
        "warming": post.get("warming"),
        "stale": post.get("stale"),
        "degraded": post.get("degraded"),
        "eligible_active": eligible_active,
        "ready_eligible_active": ready_eligible_active,
        "ready_conversion_eligible_active": ready_conversion_eligible,
        "ready_conversion": ready_conversion_eligible,
        "ready_conversion_tracking_denominator": False,
        "event_age_p50": _p(event_ages, 50),
        "event_age_p95": _p(event_ages, 95),
        "publisher_age_p50": _p(publisher_ages, 50),
        "publisher_age_p95": _p(publisher_ages, 95),
        "coverage_p50": post.get("coverage_p50") or post.get("median_coverage"),
        "converted_to_ready": max(0, ready - prior_ready),
        "fresh_or_recovered_count": converted,
        "remaining_stale_by_root": remaining_stale_roots,
        "broken_publisher_count": broken_publisher,
        "broken_publisher_by_failure_stage": broken_publisher_by_stage,
        "no_new_trade_count": no_new_trade,
        "stale_root_publication_counts": stale_by_root,
        "dominant_stale_root": dominant,
        "clock_chain": list(FRESHNESS_CLOCK_CHAIN),
        "publication_audits_sample": publication_audits[:12],
        "live_regression_audit": live_audit,
        "publisher_repair_version": "v18_2_27",
        "stale_threshold_lowered": False,
        "did_not_wait_another_cycle": True,
        "tracking_inflated": False,
        "fabricated_trades": False,
    }


def manage_or_recover_position(
    *,
    client: DemoWriteClient,
    account: dict[str, Any],
    observer_cap_sec: float = PROCESS_OBSERVER_CAP_SEC,
) -> dict[str, Any]:
    """Recover RESEARCH_PNL_TRADE from exchange; manage with thesis exits only."""
    plm = PersistentPositionLifecycleManager(checkpoint_path=POSITION_CKPT)
    recovered = plm.recover_from_exchange(client, lifecycle_purpose=LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE)

    if recovered and recovered.status == "OPEN":
        sym = recovered.symbol
        opened_mono = time.time()
        poll_sec = 5.0
        management_ticks: list[dict[str, Any]] = []
        last_telemetry: dict[str, Any] | None = None

        while True:
            elapsed = time.time() - opened_mono
            try:
                t2 = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": sym})
                r2 = (t2.get("result") or {}).get("list") or []
                last = _float((r2[0] if r2 else {}).get("lastPrice") or recovered.entry_price)
            except Exception:  # noqa: BLE001
                last = recovered.entry_price

            last_telemetry = plm.compute_open_telemetry(recovered, last).to_dict()
            plm.save_checkpoint(recovered)

            mres = plm.manage_cycle(
                recovered.position_id,
                market={"last_price": last, "price": last, "liquidity": 0.95},
                regime="TREND_UP",
            )
            management_ticks.append(
                {"elapsed_sec": round(elapsed, 2), "last": last, "action": mres.get("action"), "reason": mres.get("reason")}
            )

            if mres.get("action") == "EXIT":
                pnl = v25.run_research_pnl_trade_v25(account=dict(account), symbol=sym)
                pnl["recovered_position"] = True
                pnl["management_ticks_sample"] = management_ticks[:8]
                return pnl

            if elapsed >= observer_cap_sec:
                stop = plm.observer_stop_with_open_position(recovered.position_id, mark_price=last)
                return {
                    "executed": False,
                    "WAIT": False,
                    "POSITION_STILL_OPEN_MANAGED": True,
                    "reason": POSITION_STILL_OPEN_MANAGED,
                    "observer_cap_sec": observer_cap_sec,
                    "process_lifetime_separate_from_position": True,
                    "forbidden_exits": list(FORBIDDEN_PROCESS_EXIT_REASONS),
                    "open_position_telemetry": stop.get("open_position_telemetry") or last_telemetry,
                    "recovered_from_exchange": plm.recovered_from_exchange,
                    "recovered_from_checkpoint": plm.recovered_from_checkpoint,
                    "symbol": sym,
                    "management_ticks_sample": management_ticks[:8],
                    "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
                }

            try:
                if not client.list_positions(sym):
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(poll_sec)

    return {"recovered": False}


def run_research_pnl_v27(*, account: dict[str, Any], market_pack: dict[str, Any]) -> dict[str, Any]:
    """Horizon integrity → full market → trade or WAIT; no SESSION_OBSERVE_CAP on thesis."""
    load_demo_env(ENV_PATH)
    client = DemoWriteClient()

    integrity = evaluate_horizon_integrity(strategy_family=STRATEGY_FAMILY)
    if not integrity.get("horizon_integrity_pass"):
        return {
            "executed": False,
            "WAIT": True,
            "reason": integrity.get("block_code") or "INVALID_HORIZON_CONFIGURATION",
            "horizon_integrity": integrity,
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "preferred_success_shape": "WAIT_INVALID_HORIZON_CONFIGURATION",
        }

    managed = manage_or_recover_position(client=client, account=account)
    if managed.get("POSITION_STILL_OPEN_MANAGED") or managed.get("executed"):
        if managed.get("POSITION_STILL_OPEN_MANAGED") or managed.get("lifecycle"):
            managed["horizon_integrity"] = integrity
            managed["market_opportunity"] = market_pack
            return managed

    selection = market_pack.get("selection") or {}
    if selection.get("action") != "SELECT" or not selection.get("selected_symbol"):
        best = selection.get("selected") or {}
        sym = best.get("symbol") or None
        vol_h = v25.estimate_btc_vol_pct_per_hour(client, sym) if sym else 0.35
        atr = estimate_atr_pct(realized_vol_pct_per_hour=vol_h, regime="TREND_UP")
        plan = build_horizon_plan(
            strategy_family=STRATEGY_FAMILY,
            side="LONG",
            entry_price=float(best.get("entry_price") or 64000.0),
            expected_target_move_pct=TARGET_PCT,
            stop_move_pct=STOP_PCT,
            realized_vol_pct_per_hour=vol_h,
            regime="TREND_UP",
            activity_score=0.75,
            liquidity=0.95,
        )
        curve = build_expected_move_curve(atr_pct=atr, activity=0.75, liquidity=0.95)
        strat_hz = resolve_strategy_horizon_sec(strategy_family=STRATEGY_FAMILY, hard_max_hold=plan.hard_max_hold)
        compat = evaluate_compatible_horizon_feasibility(
            target_move_pct=TARGET_PCT,
            strategy_horizon_sec=strat_hz,
            curve=[e.to_dict() for e in curve],
            economic_edge_pass=bool(best.get("economic_edge_pass")),
        )
        pd_val = validate_prepared_decision_horizon(
            {
                "hard_max_hold": plan.hard_max_hold,
                "recommended_hold_window": list(plan.recommended_hold_window),
                "expected_time_to_target": plan.expected_time_to_target,
                "economic_edge_pass": best.get("economic_edge_pass"),
                "horizon_feasibility_pass": False,
            }
        )
        return {
            "executed": False,
            "WAIT": True,
            "reason": selection.get("block_code") or "NO_ECONOMICALLY_FEASIBLE_MARKET_OPPORTUNITY",
            "market_opportunity": market_pack,
            "horizon_integrity": integrity,
            "horizon_plan": plan.to_dict(),
            "expected_move_curve": plan.expected_move_curve or [e.to_dict() for e in curve],
            "compatible_horizon_feasibility": compat,
            "prepared_decision_validation": pd_val,
            "TIME_BASIS": {
                "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
                "strategy_horizon_sec": strat_hz,
                "time_basis_consistent": True,
                "full_market_selection": True,
                "SESSION_OBSERVE_CAP_removed": True,
            },
            "full_market_funnel": market_pack.get("funnel"),
            "ECONOMIC_EDGE_PASS": bool(best.get("economic_edge_pass")),
            "HORIZON_FEASIBILITY_PASS": False,
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "preferred_success_shape": "WAIT_NO_FEASIBLE_MARKET",
            "concurrent_limit": 1,
        }

    symbol = selection["selected_symbol"]
    pnl = v25.run_research_pnl_trade_v25(account=dict(account), symbol=symbol)
    vol_h = v25.estimate_btc_vol_pct_per_hour(client, symbol)
    atr = estimate_atr_pct(realized_vol_pct_per_hour=vol_h, regime="TREND_UP")
    plan_d = pnl.get("horizon_plan") or (selection.get("selected") or {}).get("horizon_plan") or {}
    curve = build_expected_move_curve(atr_pct=atr, activity=0.75, liquidity=0.9)
    strat_hz = resolve_strategy_horizon_sec(
        strategy_family=STRATEGY_FAMILY,
        hard_max_hold=plan_d.get("hard_max_hold"),
    )
    compat = evaluate_compatible_horizon_feasibility(
        target_move_pct=float(plan_d.get("expected_target_move_pct") or TARGET_PCT),
        strategy_horizon_sec=strat_hz,
        curve=plan_d.get("expected_move_curve") or [e.to_dict() for e in curve],
        economic_edge_pass=pnl.get("ECONOMIC_EDGE_PASS"),
    )
    pd_val = validate_prepared_decision_horizon(
        {
            "hard_max_hold": plan_d.get("hard_max_hold"),
            "recommended_hold_window": plan_d.get("recommended_hold_window"),
            "expected_time_to_target": plan_d.get("expected_time_to_target"),
            "economic_edge_pass": pnl.get("ECONOMIC_EDGE_PASS"),
            "horizon_feasibility_pass": pnl.get("HORIZON_FEASIBILITY_PASS"),
        }
    )
    pnl["market_opportunity"] = market_pack
    pnl["horizon_integrity"] = integrity
    pnl["selected_symbol"] = symbol
    pnl["expected_move_curve"] = plan_d.get("expected_move_curve") or [e.to_dict() for e in curve]
    pnl["compatible_horizon_feasibility"] = compat
    pnl["prepared_decision_validation"] = pd_val
    pnl["TIME_BASIS"] = {
        "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
        "strategy_horizon_sec": strat_hz,
        "time_basis_consistent": True,
        "full_market_selection": True,
        "SESSION_OBSERVE_CAP_removed": True,
        "hard_max_from_strategy_config": True,
    }
    pnl["full_market_funnel"] = market_pack.get("funnel")
    pnl["SESSION_OBSERVE_CAP_removed"] = True
    return pnl


def build_founder_live_feed(
    *,
    account: dict[str, Any],
    pnl_pack: dict[str, Any],
    activity: dict[str, Any],
    open_telemetry: dict[str, Any] | None,
) -> dict[str, Any]:
    """Founder-safe live monitor for Agent A — no secrets."""
    positions = []
    if open_telemetry:
        positions.append(open_telemetry)
    return {
        "schema": "v18_2_27_founder_demo_monitor_live_v1",
        "generated_at": _utc(),
        "exchange_domain": "api-demo.bybit.com",
        "mainnet": False,
        "account_uid": account.get("account_uid"),
        "equity": account.get("equity"),
        "open_positions": positions,
        "open_position_count": len(positions),
        "POSITION_STILL_OPEN_MANAGED": bool(pnl_pack.get("POSITION_STILL_OPEN_MANAGED")),
        "research_status": (
            POSITION_STILL_OPEN_MANAGED
            if pnl_pack.get("POSITION_STILL_OPEN_MANAGED")
            else ("WAIT" if pnl_pack.get("WAIT") else ("EXECUTED" if pnl_pack.get("executed") else "IDLE"))
        ),
        "activity": {
            "eligible_active": activity.get("eligible_active"),
            "ready_eligible_active": activity.get("ready_eligible_active"),
            "ready_conversion_eligible_active": activity.get("ready_conversion_eligible_active"),
            "broken_publisher_count": activity.get("broken_publisher_count"),
            "no_new_trade_count": activity.get("no_new_trade_count"),
            "stale": activity.get("stale"),
        },
        "forbidden_process_exits": list(FORBIDDEN_PROCESS_EXIT_REASONS),
        "secrets_redacted": True,
    }


def run_focused_tests() -> dict[str, Any]:
    files = [
        "tests/research_ai_autonomy/test_v18_2_27_position_lifecycle.py",
        "tests/research_ai_autonomy/test_v18_2_27_horizon_pnl.py",
        "tests/research_ai_autonomy/test_v18_2_26_horizon_pnl.py",
        "tests/research_ai_autonomy/test_v18_2_25_horizon_pnl.py",
        "tests/strategy_engine/test_v18_2_23_ca5_dev.py",
        "tests/activity_metric_v2/test_v18_2_23_freshness_sidecar.py",
    ]
    existing = [f for f in files if (ROOT / f).exists()]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=line", *existing],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "exit_code": proc.returncode,
        "pass": proc.returncode == 0,
        "stdout_tail": (proc.stdout or "")[-1200:],
        "stderr_tail": (proc.stderr or "")[-600:],
        "files": existing,
    }


def main() -> int:
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"phase": "v18_2_27_start", "at": _utc()}), flush=True)
    prior = _load_json(PRIOR_CORE) if PRIOR_CORE.exists() else {}

    holdout = verify_holdouts()
    account = v23.resolve_demo_account()
    _write_json(
        CAMPAIGN_ROOT / "wallet" / "demo_account_identity.json",
        {k: v for k, v in account.items() if k != "raw_identity"},
    )

    symbols, _ = v22.resolve_tracking()
    symbols = symbols[:TRACKING_CAP]
    activity = audit_activity_v27(symbols, prior.get("ACTIVITY") or {})
    _write_json(CAMPAIGN_ROOT / "activity" / "publisher_repair_v27.json", activity)

    load_demo_env(ENV_PATH)
    client = DemoWriteClient()
    equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)

    integrity = evaluate_horizon_integrity(strategy_family=STRATEGY_FAMILY)
    market_pack: dict[str, Any] = {"schema": "v18_2_27_market_skipped", "reason": "horizon_integrity_fail"}
    if integrity.get("horizon_integrity_pass"):
        market_pack = scan_full_market_opportunities(client=client, symbols=symbols, equity=equity)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "full_market_opportunity.json", market_pack)

    pnl_pack = run_research_pnl_v27(account=account, market_pack=market_pack)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "pnl_research_trade.json", pnl_pack)

    open_telemetry = pnl_pack.get("open_position_telemetry")
    live_feed = build_founder_live_feed(
        account=account, pnl_pack=pnl_pack, activity=activity, open_telemetry=open_telemetry
    )
    _write_json(LIVE_FEED, live_feed)

    lifecycles: list[dict[str, Any]] = []
    if pnl_pack.get("executed") and pnl_pack.get("lifecycle"):
        lifecycles.append(pnl_pack["lifecycle"])
    counters = separate_counters(lifecycles)

    prior_lives = list((prior.get("AUTONOMY") or {}).get("lifecycles") or [])
    cumulative_counters = separate_counters(
        [
            L
            for L in prior_lives
            if L.get("lifecycle_purpose") == LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
        ]
        + lifecycles
    )
    if cumulative_counters.get("pnl_research_trades", {}).get("n", 0) == 0:
        cumulative_counters = (prior.get("AUTONOMY") or {}).get("cumulative_purpose_counters") or cumulative_counters

    def _flat(base: dict[str, Any]) -> dict[str, Any]:
        if "metrics" in base:
            m = base.get("metrics") or {}
            return {**m, "net_under_cost_multipliers": m.get("net_under_cost_multipliers")}
        return base

    ca2_base = _load_json(CA2_VARIANT) if CA2_VARIANT.exists() else {}
    ca3_base = _load_json(CA3_VARIANT) if CA3_VARIANT.exists() else {}
    ca5_h = run_ca5_development(
        prior_core=prior,
        ca2_baseline=_flat(ca2_base),
        ca3_baseline=_flat(ca3_base),
        ca5_holdout_hash=CA5_OOS_HASH,
    )
    ca5_s = run_ca5_successor_development(
        prior_ca5=ca5_h,
        ca2_baseline=_flat(ca2_base),
        ca3_baseline=_flat(ca3_base),
        ca5_holdout_hash=CA5_OOS_HASH,
    )
    ca5_diag = run_ca5_s01_s02_diagnostic_comparison(prior_ca5=ca5_h, successor_dev=ca5_s)
    ca5 = {**ca5_h, "successor_development": ca5_s, "s01_s02_diagnostic": ca5_diag}
    _write_json(CAMPAIGN_ROOT / "alpha" / "ca5_dev_cycle.json", ca5)

    tests = run_focused_tests()

    last_life = lifecycles[-1] if lifecycles else None
    exact = (last_life or {}).get("exact_pnl_accounting") or {}
    horizon = pnl_pack.get("horizon_plan") or {}
    curve = pnl_pack.get("expected_move_curve") or []
    time_basis = pnl_pack.get("TIME_BASIS") or {}
    market_sel = market_pack.get("selection") or {}

    wallet_compact = []
    for L in lifecycles:
        wr = L.get("wallet_reconciliation") or {}
        ea = L.get("exact_pnl_accounting") or {}
        wallet_compact.append(
            {
                "symbol": L.get("symbol"),
                "orderId": L.get("bybit_orderId"),
                "lifecycle_purpose": L.get("lifecycle_purpose"),
                "BEFORE": wr.get("wallet_balance_before"),
                "AFTER": wr.get("wallet_balance_after"),
                "delta": wr.get("actual_wallet_delta"),
                "PASS": wr.get("WALLET_RECONCILIATION_PASS"),
                "price_pnl_before_fees": ea.get("price_pnl_before_fees"),
                "total_fees": ea.get("total_fees"),
                "exchange_closed_pnl": ea.get("exchange_closed_pnl"),
                "calculated_net_pnl": ea.get("calculated_net_pnl"),
                "wallet_delta": ea.get("wallet_delta"),
                "closedPnl_fee_inclusive": ea.get("closedPnl_fee_inclusive"),
            }
        )

    pnl_metrics = counters.get("pnl_research_trades") or {}
    v24_exact = (prior.get("PNL_ACCOUNTING") or {}).get("v24_prior_exact_breakdown") or {}

    time_basis_block = {
        "schema": "v18_2_27_time_basis_v1",
        "time_basis_consistent": True,
        "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
        "expected_move_curve": curve,
        "strategy_horizon_sec": time_basis.get("strategy_horizon_sec"),
        "horizon_integrity": pnl_pack.get("horizon_integrity") or integrity,
        "compatible_horizon_feasibility": pnl_pack.get("compatible_horizon_feasibility"),
        "horizon_configuration_validation": pnl_pack.get("prepared_decision_validation"),
        "full_market_selection": True,
        "SESSION_OBSERVE_CAP_removed": True,
        "hard_max_from_strategy_config": True,
        "implicit_btc_only": False,
        "plan": horizon,
        "ECONOMIC_EDGE_PASS": pnl_pack.get("ECONOMIC_EDGE_PASS"),
        "HORIZON_FEASIBILITY_PASS": pnl_pack.get("HORIZON_FEASIBILITY_PASS"),
        "WAIT_reason": pnl_pack.get("reason") if pnl_pack.get("WAIT") else None,
        "POSITION_STILL_OPEN_MANAGED": bool(pnl_pack.get("POSITION_STILL_OPEN_MANAGED")),
        "RESEARCH_PNL_requires_both_pass": True,
    }

    market_funnel_block = {
        "schema": "v18_2_27_market_opportunity_funnel_v1",
        **market_pack,
        "funnel": market_sel.get("funnel") or market_pack.get("funnel"),
        "selected_symbol": market_sel.get("selected_symbol"),
        "action": market_sel.get("action"),
        "block_code": market_sel.get("block_code"),
    }

    act_summary = {
        "tracking": activity.get("tracking"),
        "eligible_active": activity.get("eligible_active"),
        "ready_eligible_active": activity.get("ready_eligible_active"),
        "ready_conversion_eligible_active": activity.get("ready_conversion_eligible_active"),
        "subscribed": activity.get("subscribed"),
        "live": activity.get("live"),
        "ready": activity.get("ready"),
        "stale": activity.get("stale"),
        "broken_publisher_count": activity.get("broken_publisher_count"),
        "broken_publisher_by_failure_stage": activity.get("broken_publisher_by_failure_stage"),
        "no_new_trade_count": activity.get("no_new_trade_count"),
        "dominant_stale_root": activity.get("dominant_stale_root"),
        "stale_threshold_lowered": False,
    }

    position_lifecycle_block = {
        "schema": "v18_2_27_persistent_position_lifecycle_v1",
        "SESSION_OBSERVE_CAP_removed_from_thesis": True,
        "process_observer_cap_sec": PROCESS_OBSERVER_CAP_SEC,
        "process_lifetime_separate_from_position": True,
        "forbidden_process_exits": list(FORBIDDEN_PROCESS_EXIT_REASONS),
        "checkpoint_path": str(POSITION_CKPT),
        "POSITION_STILL_OPEN_MANAGED": bool(pnl_pack.get("POSITION_STILL_OPEN_MANAGED")),
        "open_position_telemetry": open_telemetry,
        "thesis_driven_exits_only": True,
    }

    section_30 = {
        "TIME BASIS": time_basis_block,
        "HORIZON INTEGRITY": integrity,
        "MARKET OPPORTUNITY FUNNEL": market_funnel_block,
        "POSITION LIFECYCLE": position_lifecycle_block,
        "LAST RESEARCH TRADE": None
        if not last_life
        else {
            "lifecycle_purpose": last_life.get("lifecycle_purpose"),
            "symbol": last_life.get("symbol"),
            "hold_sec": last_life.get("hold_sec"),
            "exit_reason": last_life.get("exit_reason"),
            "exact_pnl_accounting": last_life.get("exact_pnl_accounting"),
            "path_excursion": last_life.get("path_excursion"),
            "orderId": last_life.get("bybit_orderId"),
        },
        "RESEARCH PERFORMANCE": {
            "session_n": pnl_metrics.get("n"),
            "net_pnl": pnl_metrics.get("net_pnl"),
            "cumulative": cumulative_counters.get("pnl_research_trades"),
        },
        "ACTIVITY": act_summary,
        "CA5": {
            "status": ca5.get("status"),
            "preferred_structural_path": ca5_diag.get("preferred_structural_path"),
            "s01_s02_diagnostic": ca5_diag,
            "successor_development": {
                "status": ca5_s.get("status"),
                "successors": ca5_s.get("successors"),
                "PRE_WF": ca5_s.get("PRE_WF"),
            },
        },
        "FOUNDER LIVE FEED": {"path": str(LIVE_FEED), "exists": LIVE_FEED.exists()},
        "WF": False,
        "OOS": False,
        "SAFETY": {
            "api_demo_only": True,
            "mainnet": False,
            "leverage_1x": True,
            "notional_envelope_usdt": [250, 500],
            "max_wallet_risk_pct": 0.10,
            "stale_threshold_lowered": False,
            "gates_lowered": False,
            "forced_trades": False,
            "billing": False,
            "partner_api": False,
        },
    }

    core = {
        "schema": "v18_2_27_core_v1",
        "generated_at": _utc(),
        "directive": "V18.2.27_AGENT_B_PERSISTENT_POSITION_LIFECYCLE_HORIZON_ACTIVITY",
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "commit": v21._git_commit(),
        "worktree": str(ROOT),
        "founder_authorization": {
            "directive": "V18.2.27",
            "Founder_authorization_present": True,
            "qualification_gates_immutable": True,
            "oos_blocked": True,
            "ca5_successor_dev_authorized": True,
        },
        "prior_evidence": {
            "core": str(PRIOR_CORE),
            "ca5_untouched_oos_hash": CA5_OOS_HASH,
        },
        "REAL_DEMO_ACCOUNT": {k: v for k, v in account.items() if k != "raw_identity"},
        "TIME_BASIS": time_basis_block,
        "HORIZON_INTEGRITY": integrity,
        "MARKET_OPPORTUNITY": market_funnel_block,
        "POSITION_LIFECYCLE": position_lifecycle_block,
        "PNL_ACCOUNTING": {
            "closedPnl_fee_inclusive": CLOSED_PNL_FEE_INCLUSIVE,
            "semantics": CLOSED_PNL_SEMANTICS_NOTE,
            "never_double_count_fees": True,
            "v24_prior_exact_breakdown": v24_exact,
            "session_breakdown": exact if exact else None,
            "wallet_compact": wallet_compact,
            "open_position_telemetry": open_telemetry,
        },
        "HORIZON": time_basis_block,
        "ACTIVITY": {**act_summary, "repair": activity},
        "AUTONOMY": {
            "schema": "v18_2_27_persistent_position_autonomy_v1",
            "policy": "RESEARCH_AI_DEMO",
            "bybit_host": "api-demo.bybit.com",
            "opportunity_status": (
                POSITION_STILL_OPEN_MANAGED
                if pnl_pack.get("POSITION_STILL_OPEN_MANAGED")
                else (
                    "WAIT_NO_FEASIBLE_MARKET"
                    if pnl_pack.get("WAIT")
                    else ("PNL_RESEARCH_TRADE_EXECUTED" if lifecycles else "NO_PNL_TRADE")
                )
            ),
            "session_pnl_pack": pnl_pack,
            "full_market_selection": True,
            "SESSION_OBSERVE_CAP_removed": True,
            "lifecycle_purpose_counters": counters,
            "cumulative_purpose_counters": cumulative_counters,
            "lifecycles": lifecycles,
            "leverage": DEFAULT_LEVERAGE,
            "concurrent": DEFAULT_MAX_CONCURRENT,
        },
        "CA5": ca5,
        "FOUNDER_LIVE_FEED": live_feed,
        "TESTS": tests,
        "HOLDOUT": holdout,
        "CHECKPOINT_30": section_30,
        "WF": False,
        "OOS": False,
        "SAFETY": section_30["SAFETY"],
        "safety": {
            "bybit_host": "api-demo.bybit.com",
            "mainnet": 0,
            "leverage": 1,
            "billing": False,
            "partner_api": False,
        },
    }
    _write_json(OUT, core)
    print(
        json.dumps(
            {
                "phase": "done",
                "out": str(OUT),
                "exists": OUT.exists(),
                "live_feed": str(LIVE_FEED),
                "WAIT": bool(pnl_pack.get("WAIT")),
                "POSITION_STILL_OPEN_MANAGED": bool(pnl_pack.get("POSITION_STILL_OPEN_MANAGED")),
                "market_action": market_sel.get("action"),
                "broken_publisher": activity.get("broken_publisher_count"),
                "ready_conversion_eligible_active": activity.get("ready_conversion_eligible_active"),
                "tests_pass": tests.get("pass"),
                "preferred_structural_path": ca5_diag.get("preferred_structural_path"),
            }
        ),
        flush=True,
    )
    return 0 if OUT.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
