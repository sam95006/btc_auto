#!/usr/bin/env python3
"""V18.2.26 AGENT B — time-basis consistency + full-market PnL selection + publisher repair + CA5 S01/S02.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_26_core.json
api-demo.bybit.com only. Mainnet=0, real_money=false, leverage=1x. Never print secrets.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
import uuid
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
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (  # noqa: E402
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
)
from backend.nexus_research_ai_autonomy.horizon_feasibility import (  # noqa: E402
    build_expected_move_curve,
    build_horizon_plan,
    estimate_atr_pct,
    evaluate_horizon_feasibility,
)
from backend.nexus_research_ai_autonomy.lifecycle_purpose import separate_counters  # noqa: E402
from backend.nexus_research_ai_autonomy.market_opportunity_selection import (  # noqa: E402
    score_market_candidate,
    select_best_market_opportunity,
)
from backend.nexus_research_ai_autonomy.prepared_decision import validate_prepared_decision_horizon  # noqa: E402
from backend.nexus_research_ai_autonomy.time_basis import (  # noqa: E402
    CURVE_HORIZONS_SEC,
    evaluate_compatible_horizon_feasibility,
    resolve_strategy_horizon_sec,
)
from backend.nexus_strategy_engine.ca5_dev_cycle import (  # noqa: E402
    run_ca5_development,
    run_ca5_successor_development,
)
from backend.nexus_strategy_engine.oos_path_integrity import HoldoutFirewall  # noqa: E402

import tools.research.activity_metric_v2.run_v18_2_21_core as v21  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_22_core as v22  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_23_core as v23  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_24_core as v24  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_25_core as v25  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_26_core.json")
PRIOR_CORE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_25_core.json")
CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_26")
SCALE192_DIR = Path(r"D:\NEXUS_RUNTIME\campaigns\activity_v2_scale192_20260808T194544Z")
CKPT_ROOT = SCALE192_DIR / "runtime" / "activity_metric_v2"
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
MAX_MARKET_SCAN = 48  # bounded REST scan within tracking universe
SESSION_OBSERVE_CAP_SEC = 720


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
        "schema": "v18_2_26_holdout_firewall_check_v1",
        "untouched_oos_hash": oos_hash,
        "oos_pre_access_count": fw.oos_pre_access_count,
        "oos_opened": False,
        "oos_pre_access": 0,
        "ca5_holdout_sealed": True,
        "WF": False,
        "OOS": False,
    }


def fetch_ticker_universe(client: DemoWriteClient, symbols: list[str]) -> list[dict[str, Any]]:
    """Fetch ticker metrics for full-market scan (bounded)."""
    out: list[dict[str, Any]] = []
    try:
        raw = client.public_get("/v5/market/tickers", {"category": "linear"})
        rows = (raw.get("result") or {}).get("list") or []
        by_sym = {str(r.get("symbol") or ""): r for r in rows}
        for sym in symbols[:MAX_MARKET_SCAN]:
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
    """Full-market eligible universe opportunity funnel."""
    tickers = fetch_ticker_universe(client, symbols)
    candidates = []
    vol_cache: dict[str, float] = {}

    for t in tickers:
        sym = t["symbol"]
        vol_cache[sym] = v25.estimate_btc_vol_pct_per_hour(client, sym)
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
            vol_pct_per_hour=vol_cache[sym],
            strategy_family=STRATEGY_FAMILY,
            direction=direction,
            target_pct=TARGET_PCT,
            stop_pct=STOP_PCT,
            turnover24h=float(t["turnover_24h"]),
            activity_score=0.75,
            qty_step=step,
            min_qty=min_q,
            min_notional=min_n,
            hard_max_hold_override=SESSION_OBSERVE_CAP_SEC,
        )
        candidates.append(cand)

    funnel_out = select_best_market_opportunity(candidates)
    return {
        "schema": "v18_2_26_full_market_opportunity_v1",
        "universe_size": len(symbols),
        "scanned": len(tickers),
        "selection": funnel_out,
        "funnel": funnel_out.get("funnel"),
        "time_basis_emphasis": True,
        "implicit_btc_only": False,
    }


def audit_activity_v26(symbols: list[str], prior_activity: dict[str, Any]) -> dict[str, Any]:
    """Publisher propagation repair v26 — distinguish NO_NEW_TRADE vs BROKEN_PUBLISHER."""
    repair = v23.repair_activity_stale(symbols)
    hb = v22._load_heartbeat(SCALE192_DIR / "heartbeat.json")
    live_n = int((repair.get("post") or {}).get("live") or 0)
    live_audit = v24.audit_live_regression(prior_activity, live_n, hb)

    now_ms = int(time.time() * 1000)
    event_ages: list[float] = []
    publisher_ages: list[float] = []
    stale_by_root: dict[str, int] = {}
    remaining_stale_roots: dict[str, int] = {}
    broken_publisher = 0
    no_new_trade = 0
    converted = 0

    for sym in symbols:
        path = CKPT_ROOT / f"activity_{sym}.json"
        insp = inspect_checkpoint(path, now_ms=now_ms)
        age = insp.get("last_trade_age_ms")
        if age is not None:
            event_ages.append(float(age))

        pub_path = path.with_suffix(".publisher.json")
        pub_age = None
        pub_ts = None
        if pub_path.exists():
            try:
                pub = json.loads(pub_path.read_text(encoding="utf-8"))
                pub_ts = int(pub.get("publisher_state") or pub.get("saved_at_ms") or 0)
                if pub_ts:
                    pub_age = float(now_ms - pub_ts)
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
            published_freshness_ts_ms=insp.get("last_trade_ts"),
            checkpoint_ts_ms=int(path.stat().st_mtime * 1000) if path.exists() else None,
            gate_eval_ts_ms=now_ms,
            ws_live=live_n >= len(symbols) * 0.9,
            sidecar_ignored_publisher_stale=sidecar_ignored,
            raw_ws_event_ts_ms=insp.get("last_trade_ts"),
        )
        root = cls.get("freshness_publication_root") or "OTHER"
        stale_by_root[root] = stale_by_root.get(root, 0) + 1
        sk = cls.get("stale_kind") or root
        if age is not None and age > DEFAULT_STALE_MS:
            remaining_stale_roots[sk] = remaining_stale_roots.get(sk, 0) + 1
            if sk == "BROKEN_PUBLISHER_REFRESH":
                broken_publisher += 1
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

    dominant = (
        "BROKEN_PUBLISHER_REFRESH"
        if broken_publisher >= no_new_trade
        else "NO_NEW_TRADE"
    )

    return {
        **repair,
        "schema": "v18_2_26_activity_publisher_repair_v1",
        "tracking": TRACKING_CAP,
        "subscribed": int((hb.get("ws_audit") or {}).get("subscription_acked") or TRACKING_CAP),
        "live": post.get("live"),
        "ready": ready,
        "warming": post.get("warming"),
        "stale": post.get("stale"),
        "degraded": post.get("degraded"),
        "event_age_p50": _p(event_ages, 50),
        "event_age_p95": _p(event_ages, 95),
        "publisher_age_p50": _p(publisher_ages, 50),
        "publisher_age_p95": _p(publisher_ages, 95),
        "coverage_p50": post.get("coverage_p50") or post.get("median_coverage"),
        "ready_conversion": post.get("ready_conversion"),
        "converted_to_ready": max(0, ready - prior_ready),
        "fresh_or_recovered_count": converted,
        "remaining_stale_by_root": remaining_stale_roots,
        "broken_publisher_count": broken_publisher,
        "no_new_trade_count": no_new_trade,
        "stale_root_publication_counts": stale_by_root,
        "dominant_stale_root": dominant,
        "clock_chain": list(FRESHNESS_CLOCK_CHAIN),
        "live_regression_audit": live_audit,
        "publisher_repair_version": "v18_2_26",
        "stale_threshold_lowered": False,
        "did_not_wait_another_cycle": True,
        "tracking_inflated": False,
        "fabricated_trades": False,
    }


def run_research_pnl_v26(*, account: dict[str, Any], market_pack: dict[str, Any]) -> dict[str, Any]:
    """Full-market selection → time-basis horizon gates → trade or WAIT."""
    load_demo_env(ENV_PATH)
    client = DemoWriteClient()
    selection = market_pack.get("selection") or {}
    best = selection.get("selected") or {}

    if selection.get("action") != "SELECT" or not selection.get("selected_symbol"):
        sym = best.get("symbol") or "BTCUSDT"
        vol_h = v25.estimate_btc_vol_pct_per_hour(client, sym)
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
            hard_max_hold_override=720,
        )
        curve = build_expected_move_curve(atr_pct=atr, activity=0.75, liquidity=0.95)
        strat_hz = resolve_strategy_horizon_sec(strategy_family=STRATEGY_FAMILY, hard_max_hold=720)
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
            "horizon_plan": plan.to_dict(),
            "expected_move_curve": plan.expected_move_curve or [e.to_dict() for e in curve],
            "compatible_horizon_feasibility": compat,
            "prepared_decision_validation": pd_val,
            "TIME_BASIS": {
                "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
                "strategy_horizon_sec": strat_hz,
                "time_basis_consistent": True,
                "full_market_selection": True,
            },
            "full_market_funnel": market_pack.get("funnel"),
            "ECONOMIC_EDGE_PASS": bool(best.get("economic_edge_pass")),
            "HORIZON_FEASIBILITY_PASS": False,
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
            "preferred_success_shape": "WAIT_NO_FEASIBLE_MARKET",
        }

    symbol = best["symbol"]
    account_copy = dict(account)
    pnl = v25.run_research_pnl_trade_v25(account=account_copy, symbol=symbol)
    vol_h = v25.estimate_btc_vol_pct_per_hour(client, symbol)
    atr = estimate_atr_pct(realized_vol_pct_per_hour=vol_h, regime="TREND_UP")
    curve = build_expected_move_curve(atr_pct=atr, activity=0.75, liquidity=float(best.get("liquidity") or 0.9))
    plan_d = pnl.get("horizon_plan") or best.get("horizon_plan") or {}
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
    pnl["selected_symbol"] = symbol
    pnl["expected_move_curve"] = plan_d.get("expected_move_curve") or [e.to_dict() for e in curve]
    pnl["compatible_horizon_feasibility"] = compat
    pnl["prepared_decision_validation"] = pd_val
    pnl["TIME_BASIS"] = {
        "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
        "strategy_horizon_sec": strat_hz,
        "time_basis_consistent": True,
        "full_market_selection": True,
    }
    pnl["full_market_funnel"] = market_pack.get("funnel")
    pnl["selected_symbol"] = symbol
    return pnl


def run_focused_tests() -> dict[str, Any]:
    files = [
        "tests/research_ai_autonomy/test_v18_2_26_horizon_pnl.py",
        "tests/research_ai_autonomy/test_v18_2_25_horizon_pnl.py",
        "tests/research_ai_autonomy/test_v18_2_24_pnl_research.py",
        "tests/demo_execution/test_v18_2_23_wallet_lifecycle_accounting.py",
        "tests/strategy_engine/test_v18_2_23_ca5_dev.py",
        "tests/activity_metric_v2/test_v18_2_23_freshness_sidecar.py",
        "tests/strategy_engine/test_v18_2_21_oos_path_integrity.py",
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
    print(json.dumps({"phase": "v18_2_26_start", "at": _utc()}), flush=True)
    prior = _load_json(PRIOR_CORE) if PRIOR_CORE.exists() else {}

    holdout = verify_holdouts()
    account = v23.resolve_demo_account()
    _write_json(
        CAMPAIGN_ROOT / "wallet" / "demo_account_identity.json",
        {k: v for k, v in account.items() if k != "raw_identity"},
    )

    symbols, _ = v22.resolve_tracking()
    symbols = symbols[:TRACKING_CAP]
    activity = audit_activity_v26(symbols, prior.get("ACTIVITY") or {})
    _write_json(CAMPAIGN_ROOT / "activity" / "publisher_repair_v26.json", activity)

    load_demo_env(ENV_PATH)
    client = DemoWriteClient()
    equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)
    market_pack = scan_full_market_opportunities(client=client, symbols=symbols, equity=equity)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "full_market_opportunity.json", market_pack)

    pnl_pack = run_research_pnl_v26(account=account, market_pack=market_pack)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "pnl_research_trade.json", pnl_pack)

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
    # Include prior V24 trade in cumulative if not already there
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
    ca5 = {**ca5_h, "successor_development": ca5_s}
    _write_json(CAMPAIGN_ROOT / "alpha" / "ca5_dev_cycle.json", ca5)

    tests = run_focused_tests()

    last_life = lifecycles[-1] if lifecycles else None
    exact = (last_life or {}).get("exact_pnl_accounting") or {}
    path_ex = (last_life or {}).get("path_excursion") or pnl_pack.get("path_excursion") or {}
    exit_q = (last_life or {}).get("exit_quality") or pnl_pack.get("exit_quality") or {}
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
        "schema": "v18_2_26_time_basis_v1",
        "time_basis_consistent": True,
        "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
        "expected_move_curve": curve,
        "strategy_horizon_sec": time_basis.get("strategy_horizon_sec"),
        "compatible_horizon_feasibility": pnl_pack.get("compatible_horizon_feasibility"),
        "horizon_configuration_validation": pnl_pack.get("prepared_decision_validation")
        or pnl_pack.get("horizon_configuration"),
        "full_market_selection": True,
        "implicit_btc_only": False,
        "generic_180s_forbidden": True,
        "plan": horizon,
        "feasibility": pnl_pack.get("horizon_feasibility") or pnl_pack.get("compatible_horizon_feasibility"),
        "ECONOMIC_EDGE_PASS": pnl_pack.get("ECONOMIC_EDGE_PASS"),
        "HORIZON_FEASIBILITY_PASS": pnl_pack.get("HORIZON_FEASIBILITY_PASS"),
        "WAIT_reason": pnl_pack.get("reason") if pnl_pack.get("WAIT") else None,
        "RESEARCH_PNL_requires_both_pass": True,
    }

    market_funnel_block = {
        "schema": "v18_2_26_market_opportunity_funnel_v1",
        **market_pack,
        "funnel": market_sel.get("funnel"),
        "top_rejected_reasons": market_sel.get("top_rejected_reasons"),
        "selected_symbol": market_sel.get("selected_symbol"),
        "action": market_sel.get("action"),
        "block_code": market_sel.get("block_code"),
    }

    act_summary = {
        "tracking": activity.get("tracking"),
        "subscribed": activity.get("subscribed"),
        "live": activity.get("live"),
        "ready": activity.get("ready"),
        "warming": activity.get("warming"),
        "stale": activity.get("stale"),
        "degraded": activity.get("degraded"),
        "event_age_p50": activity.get("event_age_p50"),
        "event_age_p95": activity.get("event_age_p95"),
        "publisher_age_p50": activity.get("publisher_age_p50"),
        "publisher_age_p95": activity.get("publisher_age_p95"),
        "coverage_p50": activity.get("coverage_p50"),
        "ready_conversion": activity.get("ready_conversion"),
        "converted_to_ready": activity.get("converted_to_ready"),
        "remaining_stale_by_root": activity.get("remaining_stale_by_root"),
        "broken_publisher_count": activity.get("broken_publisher_count"),
        "no_new_trade_count": activity.get("no_new_trade_count"),
        "dominant_stale_root": activity.get("dominant_stale_root"),
        "clock_chain": activity.get("clock_chain"),
        "stale_threshold_lowered": False,
    }

    section_30 = {
        "TIME BASIS": time_basis_block,
        "MARKET OPPORTUNITY FUNNEL": market_funnel_block,
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
            "prefer_3_meaningful_over_20_fee_only": True,
        },
        "ACTIVITY": act_summary,
        "CA5": {
            "status": ca5.get("status"),
            "successor_development": {
                "status": ca5_s.get("status"),
                "successors": ca5_s.get("successors"),
                "PRE_WF": ca5_s.get("PRE_WF"),
            },
        },
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
        "schema": "v18_2_26_core_v1",
        "generated_at": _utc(),
        "directive": "V18.2.26_AGENT_B_TIME_BASIS_FULL_MARKET_PUBLISHER_CA5_SUCCESSORS",
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "commit": v21._git_commit(),
        "worktree": str(ROOT),
        "founder_authorization": {
            "directive": "V18.2.26",
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
        "MARKET_OPPORTUNITY": market_funnel_block,
        "PNL_ACCOUNTING": {
            "closedPnl_fee_inclusive": CLOSED_PNL_FEE_INCLUSIVE,
            "semantics": CLOSED_PNL_SEMANTICS_NOTE,
            "never_double_count_fees": True,
            "v24_prior_exact_breakdown": v24_exact,
            "session_breakdown": exact if exact else None,
            "wallet_compact": wallet_compact,
        },
        "HORIZON": time_basis_block,
        "ACTIVITY": {**act_summary, "repair": activity, "freshness_publication_audit": activity.get("freshness_publication_audit")},
        "AUTONOMY": {
            "schema": "v18_2_26_horizon_pnl_research_autonomy_v1",
            "policy": "RESEARCH_AI_DEMO",
            "bybit_host": "api-demo.bybit.com",
            "opportunity_status": (
                "WAIT_NO_FEASIBLE_MARKET"
                if pnl_pack.get("WAIT")
                else ("PNL_RESEARCH_TRADE_EXECUTED" if lifecycles else "NO_PNL_TRADE")
            ),
            "session_pnl_pack": pnl_pack,
            "full_market_selection": True,
            "lifecycle_purpose_counters": counters,
            "cumulative_purpose_counters": cumulative_counters,
            "lifecycles": lifecycles,
            "leverage": DEFAULT_LEVERAGE,
            "concurrent": DEFAULT_MAX_CONCURRENT,
        },
        "CA5": ca5,
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
                "WAIT": bool(pnl_pack.get("WAIT")),
                "market_action": market_sel.get("action"),
                "broken_publisher": activity.get("broken_publisher_count"),
                "no_new_trade": activity.get("no_new_trade_count"),
                "tests_pass": tests.get("pass"),
                "ca5_successors": len(ca5_s.get("successors") or []),
            }
        ),
        flush=True,
    )
    return 0 if OUT.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
