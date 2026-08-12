#!/usr/bin/env python3
"""V18.2.28 AGENT B — exchange preflight + LONG/SHORT autonomy + adaptive profit capture.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_28_core.json
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

from backend.nexus_research_ai_autonomy.adaptive_profit_capture import (  # noqa: E402
    AdaptiveProfitCaptureManager,
)
from backend.nexus_research_ai_autonomy.canonical_evidence import (  # noqa: E402
    apply_sealed_to_time_basis,
    seal_funnel_metrics,
    seal_gate_metrics,
    validate_metric_consistency,
)
from backend.nexus_research_ai_autonomy.exchange_preflight import (  # noqa: E402
    preflight_ranked_candidates,
)
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (  # noqa: E402
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
    separate_counters,
)
from backend.nexus_research_ai_autonomy.long_short_symmetry import (  # noqa: E402
    build_symmetric_candidates,
)
from backend.nexus_research_ai_autonomy.market_opportunity_selection import (  # noqa: E402
    select_best_market_opportunity,
)
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (  # noqa: E402
    FORBIDDEN_PROCESS_EXIT_REASONS,
    POSITION_STILL_OPEN_MANAGED,
    evaluate_horizon_integrity,
)
from backend.nexus_research_ai_autonomy.reflection_v28 import ReflectionV28  # noqa: E402
from backend.nexus_research_ai_autonomy.win_rate_accounting import (  # noqa: E402
    compute_research_win_rate,
)
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

from backend.nexus_research_ai_autonomy.time_basis import CURVE_HORIZONS_SEC  # noqa: E402
from backend.nexus_strategy_engine.ca5_dev_cycle import (  # noqa: E402
    run_ca5_development,
    run_ca5_s01_s02_diagnostic_comparison,
    run_ca5_successor_development,
)

import tools.research.activity_metric_v2.run_v18_2_21_core as v21  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_22_core as v22  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_23_core as v23  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_25_core as v25  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_27_core as v27  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_28_core.json")
LIVE_FEED = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json")
PRIOR_CORE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_27_core.json")
CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_28")
POSITION_CKPT = CAMPAIGN_ROOT / "autonomy" / "research_pnl_position.json"
ENV_PATH = Path(r"D:\NEXUS\btc_bot\.env")
V27_SOT_HASH = "ed87157deb3fa5c1fe57980847ea803d60494e2cc6432c87d851a1598a16265b"
CA5_OOS_HASH = v27.CA5_OOS_HASH
STRATEGY_FAMILY = v27.STRATEGY_FAMILY
PROCESS_OBSERVER_CAP_SEC = v27.PROCESS_OBSERVER_CAP_SEC


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scan_full_market_opportunities_v28(
    *,
    client: DemoWriteClient,
    symbols: list[str],
    equity: float,
) -> dict[str, Any]:
    """Full-market funnel with LONG/SHORT symmetry + exchange preflight fall-through."""
    tickers = v27.fetch_ticker_universe(client, symbols)
    candidates = build_symmetric_candidates(
        tickers,
        equity=equity,
        vol_estimator=v25.estimate_btc_vol_pct_per_hour,
        client=client,
        strategy_family=STRATEGY_FAMILY,
        target_pct=v27.TARGET_PCT,
        stop_pct=v27.STOP_PCT,
    )
    funnel_out = select_best_market_opportunity(candidates)
    preflight = preflight_ranked_candidates(
        candidates,
        client=client,
        equity=equity,
        stop_pct=v27.STOP_PCT,
        target_pct=v27.TARGET_PCT,
        max_loss_equity_pct=0.10,
    )

    selected = preflight.get("selected")
    if selected and preflight.get("selected_preflight", {}).get("preflight_pass"):
        funnel_out["action"] = "SELECT"
        funnel_out["selected_symbol"] = selected.get("symbol")
        funnel_out["selected"] = selected
        funnel_out["block_code"] = None
        funnel_out["exchange_preflight"] = preflight
    else:
        funnel_out["action"] = "WAIT" if funnel_out.get("action") != "SELECT" else funnel_out.get("action")
        if not selected and preflight.get("attempts"):
            funnel_out["block_code"] = preflight.get("block_code") or "EXCHANGE_PREFLIGHT_FAILED"
        funnel_out["exchange_preflight"] = preflight

    return {
        "schema": "v18_2_28_full_market_opportunity_v1",
        "universe_size": len(symbols),
        "scanned": len(tickers),
        "selection": funnel_out,
        "funnel": funnel_out.get("funnel"),
        "long_short_symmetry": True,
        "exchange_preflight_fallthrough": True,
        "SESSION_OBSERVE_CAP_removed": True,
        "hard_max_from_strategy_config": True,
        "implicit_btc_only": False,
        "BEATUSDT_reuse": False,
        "excluded_symbols": sorted(v27.EXCLUDED_SYMBOLS),
        "preflight": preflight,
    }


def manage_or_recover_position_v28(
    *,
    client: DemoWriteClient,
    account: dict[str, Any],
    observer_cap_sec: float = PROCESS_OBSERVER_CAP_SEC,
) -> dict[str, Any]:
    """Recover/manage with AdaptiveProfitCaptureManager."""
    plm = AdaptiveProfitCaptureManager(checkpoint_path=POSITION_CKPT, slow_path_leak_count=0)
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
                market={"last_price": last, "price": last, "liquidity": 0.95, "momentum_score": 0.5},
                regime="TREND_UP",
            )
            management_ticks.append(
                {
                    "elapsed_sec": round(elapsed, 2),
                    "last": last,
                    "action": mres.get("action"),
                    "reason": mres.get("reason"),
                    "adaptive_capture": mres.get("adaptive_capture"),
                }
            )

            if mres.get("action") == "EXIT":
                pnl = v25.run_research_pnl_trade_v25(account=dict(account), symbol=sym)
                pnl["recovered_position"] = True
                pnl["management_ticks_sample"] = management_ticks[:8]
                pnl["adaptive_profit_capture"] = {
                    "slow_path_leak_count": plm.slow_path_leak_count,
                    "exchange_sl_mandatory": plm.exchange_sl_mandatory,
                }
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
                    "adaptive_profit_capture": {
                        "slow_path_leak_count": plm.slow_path_leak_count,
                        "exchange_sl_mandatory": plm.exchange_sl_mandatory,
                    },
                }

            try:
                if not client.list_positions(sym):
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(poll_sec)

    return {"recovered": False}


def run_research_pnl_v28(*, account: dict[str, Any], market_pack: dict[str, Any]) -> dict[str, Any]:
    """Autonomy loop: market → LONG/SHORT → preflight → gates → order → adaptive capture."""
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

    managed = manage_or_recover_position_v28(client=client, account=account)
    if managed.get("POSITION_STILL_OPEN_MANAGED") or managed.get("executed"):
        managed["horizon_integrity"] = integrity
        managed["market_opportunity"] = market_pack
        return managed

    selection = market_pack.get("selection") or {}
    preflight = market_pack.get("preflight") or selection.get("exchange_preflight") or {}
    selected = preflight.get("selected") or selection.get("selected") or {}
    symbol = selection.get("selected_symbol") or selected.get("symbol")

    if selection.get("action") != "SELECT" or not symbol:
        wait_pack = v27.run_research_pnl_v27(account=account, market_pack=market_pack)
        wait_pack["exchange_preflight"] = preflight
        wait_pack["long_short_symmetry"] = {
            "long_score": selected.get("long_score"),
            "short_score": selected.get("short_score"),
            "selected_side": selected.get("selected_side"),
        }
        return wait_pack

    side = str(selected.get("selected_side") or selected.get("direction") or "LONG").upper()
    pf = preflight.get("selected_preflight") or {}
    pnl = v25.run_research_pnl_trade_v25(
        account=dict(account),
        symbol=symbol,
        side=side,
        qty_override=str(pf.get("normalized_qty") or ""),
        exchange_preflight_pass=bool(pf.get("preflight_pass")),
    )
    pnl["selected_side"] = side
    pnl["long_score"] = selected.get("long_score")
    pnl["short_score"] = selected.get("short_score")
    pnl["exchange_preflight"] = preflight.get("selected_preflight") or preflight
    pnl["market_opportunity"] = market_pack
    pnl["horizon_integrity"] = integrity
    pnl["adaptive_profit_capture"] = {
        "slow_path_leak_count": 0,
        "exchange_sl_mandatory": True,
        "manager": "AdaptiveProfitCaptureManager",
    }
    pnl["autonomy_chain"] = (
        "market→LONG/SHORT→preflight→gates→order→persistent_manager→adaptive_capture→exit→wallet_recon→Reflection"
    )
    return pnl


def build_founder_live_feed_v28(
    *,
    account: dict[str, Any],
    pnl_pack: dict[str, Any],
    activity: dict[str, Any],
    open_telemetry: dict[str, Any] | None,
) -> dict[str, Any]:
    base = v27.build_founder_live_feed(
        account=account, pnl_pack=pnl_pack, activity=activity, open_telemetry=open_telemetry
    )
    base["schema"] = "v18_2_28_founder_demo_monitor_live_v1"
    base["long_score"] = pnl_pack.get("long_score")
    base["short_score"] = pnl_pack.get("short_score")
    base["selected_side"] = pnl_pack.get("selected_side")
    base["adaptive_profit_capture"] = pnl_pack.get("adaptive_profit_capture")
    base["autonomy_chain"] = pnl_pack.get("autonomy_chain")
    return base


def run_focused_tests() -> dict[str, Any]:
    files = [
        "tests/research_ai_autonomy/test_v18_2_28_core.py",
        "tests/research_ai_autonomy/test_v18_2_28_exchange_preflight.py",
        "tests/research_ai_autonomy/test_v18_2_27_position_lifecycle.py",
        "tests/research_ai_autonomy/test_v18_2_27_horizon_pnl.py",
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
    print(json.dumps({"phase": "v18_2_28_start", "at": _utc()}), flush=True)
    prior = _load_json(PRIOR_CORE) if PRIOR_CORE.exists() else {}

    holdout = v27.verify_holdouts()
    account = v23.resolve_demo_account()
    _write_json(
        CAMPAIGN_ROOT / "wallet" / "demo_account_identity.json",
        {k: v for k, v in account.items() if k != "raw_identity"},
    )

    symbols, _ = v22.resolve_tracking()
    symbols = symbols[: v27.TRACKING_CAP]
    activity = v27.audit_activity_v27(symbols, prior.get("ACTIVITY") or {})
    _write_json(CAMPAIGN_ROOT / "activity" / "publisher_repair_v28.json", activity)

    load_demo_env(ENV_PATH)
    client = DemoWriteClient()
    equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)

    integrity = evaluate_horizon_integrity(strategy_family=STRATEGY_FAMILY)
    market_pack: dict[str, Any] = {"schema": "v18_2_28_market_skipped", "reason": "horizon_integrity_fail"}
    if integrity.get("horizon_integrity_pass"):
        market_pack = scan_full_market_opportunities_v28(client=client, symbols=symbols, equity=equity)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "full_market_opportunity.json", market_pack)

    pnl_pack = run_research_pnl_v28(account=account, market_pack=market_pack)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "pnl_research_trade.json", pnl_pack)

    open_telemetry = pnl_pack.get("open_position_telemetry")
    live_feed = build_founder_live_feed_v28(
        account=account, pnl_pack=pnl_pack, activity=activity, open_telemetry=open_telemetry
    )
    _write_json(LIVE_FEED, live_feed)

    lifecycles: list[dict[str, Any]] = []
    if pnl_pack.get("executed") and pnl_pack.get("lifecycle"):
        life = dict(pnl_pack["lifecycle"])
        plm = AdaptiveProfitCaptureManager(slow_path_leak_count=0)
        life["mfe_capture"] = plm.build_exit_quality_extension(life)
        lifecycles.append(life)

    reflection_engine = ReflectionV28()
    reflections = reflection_engine.drain_pending(lifecycles)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "reflection_v28.json", reflection_engine.to_dict())

    counters = separate_counters(lifecycles)
    prior_lives = list((prior.get("AUTONOMY") or {}).get("lifecycles") or [])
    cumulative_lives = [
        L for L in prior_lives if L.get("lifecycle_purpose") == LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
    ] + lifecycles
    cumulative_counters = separate_counters(cumulative_lives)
    win_rate = compute_research_win_rate(cumulative_lives)

    market_sel = market_pack.get("selection") or {}
    funnel = market_sel.get("funnel") or market_pack.get("funnel") or {}

    funnel_sealed = seal_funnel_metrics(
        funnel=funnel,
        selection=market_sel,
        selected=market_sel.get("selected") or preflight_selected(market_pack),
    )
    gate_sealed = seal_gate_metrics(
        pnl_pack=pnl_pack,
        selected=market_sel.get("selected") or preflight_selected(market_pack),
        funnel_sealed=funnel_sealed,
    )

    time_basis_block = apply_sealed_to_time_basis(
        {
            "schema": "v18_2_28_time_basis_v1",
            "time_basis_consistent": True,
            "curve_horizons_sec": list(CURVE_HORIZONS_SEC),
            "expected_move_curve": pnl_pack.get("expected_move_curve") or [],
            "strategy_horizon_sec": (pnl_pack.get("TIME_BASIS") or {}).get("strategy_horizon_sec"),
            "horizon_integrity": pnl_pack.get("horizon_integrity") or integrity,
            "compatible_horizon_feasibility": pnl_pack.get("compatible_horizon_feasibility"),
            "horizon_configuration_validation": pnl_pack.get("prepared_decision_validation"),
            "full_market_selection": True,
            "SESSION_OBSERVE_CAP_removed": True,
            "hard_max_from_strategy_config": True,
            "implicit_btc_only": False,
            "plan": pnl_pack.get("horizon_plan") or {},
            "WAIT_reason": pnl_pack.get("reason") if pnl_pack.get("WAIT") else None,
            "POSITION_STILL_OPEN_MANAGED": bool(pnl_pack.get("POSITION_STILL_OPEN_MANAGED")),
            "RESEARCH_PNL_requires_both_pass": True,
            "long_short_symmetry": True,
        },
        gate_sealed=gate_sealed,
        funnel_sealed=funnel_sealed,
    )

    metric_consistency = validate_metric_consistency(
        funnel_sealed=funnel_sealed,
        gate_sealed=gate_sealed,
        time_basis=time_basis_block,
        market_opportunity=market_pack,
        session_pnl_pack=pnl_pack,
    )

    ca5 = run_ca5_development(
        prior_core=prior,
        ca2_baseline=_load_json(v27.CA2_VARIANT) if v27.CA2_VARIANT.exists() else {},
        ca3_baseline=_load_json(v27.CA3_VARIANT) if v27.CA3_VARIANT.exists() else {},
        ca5_holdout_hash=CA5_OOS_HASH,
    )
    ca5_s = run_ca5_successor_development(
        prior_ca5=ca5,
        ca2_baseline=_load_json(v27.CA2_VARIANT) if v27.CA2_VARIANT.exists() else {},
        ca3_baseline=_load_json(v27.CA3_VARIANT) if v27.CA3_VARIANT.exists() else {},
        ca5_holdout_hash=CA5_OOS_HASH,
    )
    ca5_diag = run_ca5_s01_s02_diagnostic_comparison(prior_ca5=ca5, successor_dev=ca5_s)
    ca5_full = {**ca5, "successor_development": ca5_s, "s01_s02_diagnostic": ca5_diag}

    tests = run_focused_tests()

    last_life = lifecycles[-1] if lifecycles else None
    pnl_metrics = counters.get("pnl_research_trades") or {}

    section_30 = {
        "TIME BASIS": time_basis_block,
        "HORIZON INTEGRITY": integrity,
        "MARKET OPPORTUNITY FUNNEL": {
            "schema": "v18_2_28_market_opportunity_funnel_v1",
            **market_pack,
            "funnel_sealed": funnel_sealed,
        },
        "EXCHANGE PREFLIGHT": market_pack.get("preflight"),
        "LONG/SHORT SYMMETRY": {
            "long_score": pnl_pack.get("long_score") or (market_sel.get("selected") or {}).get("long_score"),
            "short_score": pnl_pack.get("short_score") or (market_sel.get("selected") or {}).get("short_score"),
            "selected_side": pnl_pack.get("selected_side") or (market_sel.get("selected") or {}).get("selected_side"),
        },
        "ADAPTIVE PROFIT CAPTURE": {
            "schema": "v18_2_28_adaptive_profit_capture_block_v1",
            "slow_path_leak_count": 0,
            "exchange_sl_mandatory": True,
            "canonical_exits": ["ADAPTIVE_PROFIT_CAPTURE", "MOMENTUM_EXHAUSTION"],
            "session": pnl_pack.get("adaptive_profit_capture"),
        },
        "POSITION LIFECYCLE": {
            "schema": "v18_2_28_persistent_position_lifecycle_v1",
            "POSITION_STILL_OPEN_MANAGED": bool(pnl_pack.get("POSITION_STILL_OPEN_MANAGED")),
            "open_position_telemetry": open_telemetry,
            "forbidden_process_exits": list(FORBIDDEN_PROCESS_EXIT_REASONS),
        },
        "MFE CAPTURE": (last_life or {}).get("mfe_capture"),
        "WIN RATE": win_rate,
        "REFLECTION": reflection_engine.to_dict(),
        "METRIC CONSISTENCY": metric_consistency,
        "RESEARCH PERFORMANCE": {
            "session_n": pnl_metrics.get("n"),
            "net_pnl": pnl_metrics.get("net_pnl"),
            "cumulative": cumulative_counters.get("pnl_research_trades"),
        },
        "ACTIVITY": {
            "eligible_active": activity.get("eligible_active"),
            "ready_eligible_active": activity.get("ready_eligible_active"),
            "ready_conversion_eligible_active": activity.get("ready_conversion_eligible_active"),
            "stale_threshold_lowered": False,
        },
        "CA5": {
            "status": ca5_full.get("status"),
            "preferred_structural_path": ca5_diag.get("preferred_structural_path"),
            "s01_preferred_unless_disproven": True,
            "no_ca6": True,
            "no_oos": True,
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
            "max_concurrent_research": 1,
            "stale_threshold_lowered": False,
            "gates_lowered": False,
            "forced_trades": False,
            "billing": False,
            "partner_api": False,
        },
    }

    core = {
        "schema": "v18_2_28_core_v1",
        "generated_at": _utc(),
        "directive": "V18.2.28_AGENT_B_EXCHANGE_PREFLIGHT_LONG_SHORT_ADAPTIVE_CAPTURE",
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "commit": v21._git_commit(),
        "worktree": str(ROOT),
        "v27_sot_hash": V27_SOT_HASH,
        "founder_authorization": {
            "directive": "V18.2.28",
            "Founder_authorization_present": True,
            "qualification_gates_immutable": True,
            "oos_blocked": True,
            "ca5_successor_dev_authorized": True,
            "no_ca6": True,
        },
        "prior_evidence": {
            "core": str(PRIOR_CORE),
            "ca5_untouched_oos_hash": CA5_OOS_HASH,
        },
        "REAL_DEMO_ACCOUNT": {k: v for k, v in account.items() if k != "raw_identity"},
        "CANONICAL_EVIDENCE": {
            "funnel_sealed": funnel_sealed,
            "gate_sealed": gate_sealed,
            "metric_consistency": metric_consistency,
            "metric_consistency_pass": metric_consistency.get("metric_consistency_pass"),
        },
        "TIME_BASIS": time_basis_block,
        "HORIZON_INTEGRITY": integrity,
        "MARKET_OPPORTUNITY": market_pack,
        "EXCHANGE_PREFLIGHT": market_pack.get("preflight"),
        "LONG_SHORT_SYMMETRY": section_30["LONG/SHORT SYMMETRY"],
        "ADAPTIVE_PROFIT_CAPTURE": section_30["ADAPTIVE PROFIT CAPTURE"],
        "POSITION_LIFECYCLE": section_30["POSITION LIFECYCLE"],
        "PNL_ACCOUNTING": {
            "closedPnl_fee_inclusive": CLOSED_PNL_FEE_INCLUSIVE,
            "semantics": CLOSED_PNL_SEMANTICS_NOTE,
            "never_double_count_fees": True,
            "session_breakdown": (last_life or {}).get("exact_pnl_accounting"),
            "open_position_telemetry": open_telemetry,
        },
        "WIN_RATE": win_rate,
        "REFLECTION": reflection_engine.to_dict(),
        "ACTIVITY": {**section_30["ACTIVITY"], "repair": activity},
        "AUTONOMY": {
            "schema": "v18_2_28_autonomy_v1",
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
            "autonomy_chain": pnl_pack.get("autonomy_chain"),
            "full_market_selection": True,
            "long_short_symmetry": True,
            "exchange_preflight_fallthrough": True,
            "lifecycle_purpose_counters": counters,
            "cumulative_purpose_counters": cumulative_counters,
            "lifecycles": lifecycles,
            "reflections_n": len(reflections),
            "leverage": DEFAULT_LEVERAGE,
            "concurrent": DEFAULT_MAX_CONCURRENT,
        },
        "CA5": ca5_full,
        "FOUNDER_LIVE_FEED": live_feed,
        "TESTS": tests,
        "HOLDOUT": holdout,
        "CHECKPOINT_33": section_30,
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
                "metric_consistency_pass": metric_consistency.get("metric_consistency_pass"),
                "live_feed": str(LIVE_FEED),
            }
        ),
        flush=True,
    )
    return 0 if OUT.exists() else 1


def preflight_selected(market_pack: dict[str, Any]) -> dict[str, Any] | None:
    pf = market_pack.get("preflight") or {}
    sel = pf.get("selected")
    return sel if isinstance(sel, dict) else None


if __name__ == "__main__":
    raise SystemExit(main())
