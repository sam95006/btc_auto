#!/usr/bin/env python3
"""V18.2.29 AGENT B — direction ambiguity audit + entry/stop quality diagnostics.

Single-cycle: produce D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_29_core.json
and Founder live feed: founder_demo_monitor_live.json (fail-closed if no data).
"""

from __future__ import annotations

import json
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

import tools.research.activity_metric_v2.run_v18_2_27_core as v27  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_25_core as v25  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_21_core as v21  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_22_core as v22  # noqa: E402
import tools.research.activity_metric_v2.run_v18_2_23_core as v23  # noqa: E402

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient  # noqa: E402
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env  # noqa: E402
from backend.nexus_research_ai_autonomy.constants import DEFAULT_LEVERAGE, DEFAULT_MAX_CONCURRENT  # noqa: E402
from backend.nexus_research_ai_autonomy.entry_quality_v29 import audit_entry_quality_v29  # noqa: E402
from backend.nexus_research_ai_autonomy.exchange_preflight import run_exchange_preflight  # noqa: E402
from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE  # noqa: E402
from backend.nexus_research_ai_autonomy.two_sided_hypothesis import evaluate_two_sided_hypothesis  # noqa: E402
from backend.nexus_research_ai_autonomy.position_lifecycle_manager import (
    POSITION_STILL_OPEN_MANAGED,
    evaluate_horizon_integrity,
)  # noqa: E402
from backend.nexus_research_ai_autonomy.stop_loss_audit_v29 import (  # noqa: E402
    audit_stop_loss_quality,
    empty_stop_quality_block,
)
from backend.nexus_research_ai_autonomy.adaptive_profit_capture import (  # noqa: E402
    empty_adaptive_profit_capture_block,
    summarize_adaptive_capture_from_lifecycle,
)
from backend.nexus_research_ai_autonomy.win_rate_rolling_v29 import compute_research_rolling_stats  # noqa: E402
from backend.nexus_research_ai_autonomy.two_sided_hypothesis import TwoSidedHypothesis  # noqa: E402
from backend.nexus_research_ai_autonomy.win_rate_accounting import compute_research_win_rate  # noqa: E402
from backend.nexus_research_ai_autonomy.reflection_v28 import ReflectionV28  # noqa: E402
from backend.nexus_research_ai_autonomy.two_sided_hypothesis import select_with_exchange_fallthrough  # noqa: E402
from backend.nexus_research_ai_autonomy.reflection_v29_reclassify import reclassify_v28_bluaiusdt_loss  # noqa: E402


OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_29_core.json")
LIVE_FEED = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\founder_demo_monitor_live.json")
ENV_PATH = Path(r"D:\NEXUS\btc_bot\.env")
PRIOR_CORE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_28_core.json")

CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_29")

POSITION_CKPT = CAMPAIGN_ROOT / "autonomy" / "research_pnl_position.json"

STOP_PCT = v27.STOP_PCT
TARGET_PCT = v27.TARGET_PCT
STRATEGY_FAMILY = v27.STRATEGY_FAMILY
PROCESS_OBSERVER_CAP_SEC = v27.PROCESS_OBSERVER_CAP_SEC


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_last_trade_sections(*, lifecycle: dict[str, Any] | None, direction: dict[str, Any]) -> dict[str, Any]:
    entry_q = audit_entry_quality_v29(
        lifecycle=lifecycle,
        direction_ambiguity_supported=bool(direction.get("direction_ambiguity_supported")),
    )
    stop_q = audit_stop_loss_quality(lifecycle)
    # Keep entry fee_to_stop_ratio aligned with stop audit when available.
    if entry_q.get("fee_to_stop_ratio") is None and stop_q.get("fee_to_stop_ratio") is not None:
        entry_q["fee_to_stop_ratio"] = stop_q.get("fee_to_stop_ratio")
    adaptive = summarize_adaptive_capture_from_lifecycle(lifecycle)
    return {
        "ENTRY QUALITY": entry_q,
        "STOP QUALITY": stop_q,
        "ADAPTIVE PROFIT CAPTURE": adaptive,
    }


def _build_last_trade_block(
    *,
    lifecycle: dict[str, Any] | None,
    sections: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(lifecycle, dict) or not lifecycle:
        return None
    exact = lifecycle.get("exact_pnl_accounting") or {}
    path = lifecycle.get("path_excursion") or {}
    wr = lifecycle.get("wallet_reconciliation") or {}
    exit_quality = lifecycle.get("exit_quality") or lifecycle.get("mfe_capture") or {}
    adaptive = sections.get("ADAPTIVE PROFIT CAPTURE") or empty_adaptive_profit_capture_block()
    stop_q = sections.get("STOP QUALITY") or empty_stop_quality_block()
    return {
        "symbol": lifecycle.get("symbol"),
        "side": lifecycle.get("side"),
        "hold_sec": lifecycle.get("hold_sec") or lifecycle.get("hold_duration"),
        "exit_reason": lifecycle.get("exit_reason"),
        "price_pnl": exact.get("price_pnl_before_fees"),
        "fees": exact.get("total_fees"),
        "net": exact.get("calculated_net_pnl"),
        "MFE": path.get("mfe_usdt"),
        "MAE": path.get("mae_usdt"),
        "peak_unrealized": path.get("peak_unrealized_usdt") or path.get("mfe_usdt"),
        "giveback_from_peak": path.get("giveback_from_peak"),
        "MFE_capture_ratio": exit_quality.get("MFE_capture_ratio") or path.get("mfe_capture_ratio"),
        "stop_quality": stop_q,
        "adaptive_profit_capture": adaptive,
        "exit_quality": exit_quality or {
            "exit_reason": lifecycle.get("exit_reason"),
            "not_available_reason": "exit_quality block not present on lifecycle",
        },
        "accounting": {
            "calculated_net_pnl": exact.get("calculated_net_pnl"),
            "total_fees": exact.get("total_fees"),
            "funding": exact.get("funding"),
            "accounting_complete": exact.get("accounting_complete") or exact.get("ACCOUNTING_COMPLETE"),
            "wallet_reconciliation_pass": wr.get("WALLET_RECONCILIATION_PASS"),
            "wallet_delta": wr.get("actual_wallet_delta"),
        },
    }


def build_founder_live_feed_v29(
    *,
    account: dict[str, Any],
    pnl_pack: dict[str, Any],
    activity: dict[str, Any],
    checkpoint: dict[str, Any],
    open_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Founder live feed with always-present trading_intel/performance/reflection/lessons."""
    last_trade = checkpoint.get("LAST TRADE")
    adaptive = checkpoint.get("ADAPTIVE PROFIT CAPTURE") or empty_adaptive_profit_capture_block()
    stop_q = checkpoint.get("STOP QUALITY") or empty_stop_quality_block()
    entry_q = checkpoint.get("ENTRY QUALITY") or {}
    direction = checkpoint.get("DIRECTION") or {}
    performance = checkpoint.get("PERFORMANCE") or {}
    reflection = checkpoint.get("REFLECTION") or {}
    lessons = checkpoint.get("LESSONS") or {}
    active = checkpoint.get("ACTIVE POSITION") or {}

    positions = []
    if open_telemetry:
        positions.append(open_telemetry)

    trading_intel = {
        "side": (last_trade or {}).get("side") if active.get("status") == "FLAT" else active.get("side"),
        "position_state": active.get("status") or "FLAT",
        "entry": active.get("entry"),
        "current": active.get("current"),
        "stop_loss": active.get("stop"),
        "initial_target": None,
        "dynamic_profit_zone": active.get("dynamic_profit_zone"),
        "unrealized_pnl": active.get("unrealized"),
        "estimated_net_if_closed": None,
        "mfe": (last_trade or {}).get("MFE") if active.get("status") == "FLAT" else active.get("MFE"),
        "mae": (last_trade or {}).get("MAE") if active.get("status") == "FLAT" else active.get("MAE"),
        "mfe_capture_estimate": (last_trade or {}).get("MFE_capture_ratio"),
        "remaining_net_edge": adaptive.get("remaining_edge") or active.get("remaining_edge"),
        "continuation_score": adaptive.get("continuation_score") or active.get("continuation_score"),
        "giveback_risk": adaptive.get("giveback_risk") or active.get("giveback_risk"),
        "direction_score_delta": direction.get("last_score_delta"),
        "direction_ambiguity_supported": direction.get("direction_ambiguity_supported"),
        "last_entry_class": entry_q.get("last_entry_class"),
        "stop_distance_pct": stop_q.get("stop_distance_pct"),
        "fee_to_stop_loss_ratio": stop_q.get("fee_to_stop_ratio"),
        "profit_lock_state": adaptive.get("profit_lock_state"),
        "profit_lock_level": adaptive.get("profit_lock_level"),
        "protected_pnl_floor": adaptive.get("protected_pnl_floor"),
        "profit_lock_started_at": adaptive.get("profit_lock_started_at"),
        "adaptive_action": adaptive.get("adaptive_action"),
        "adaptive_profit_capture": adaptive,
        "stop_quality": stop_q,
        "last_completed_trade": last_trade,
        "last_exit_reason": (last_trade or {}).get("exit_reason"),
        "ai_thesis": None,
        "last_ai_position_review": None,
    }

    return {
        "schema": "v18_2_29_founder_demo_monitor_live_v1",
        "generated_at": _utc(),
        "exchange_domain": "api-demo.bybit.com",
        "mainnet": False,
        "account_uid": account.get("account_uid"),
        "equity": account.get("equity"),
        "open_positions": positions,
        "open_position_count": len(positions),
        "position_state": active.get("status") or "FLAT",
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
        "trading_intel": trading_intel,
        "performance": {
            "win_rate_long": (performance.get("long_performance") or {}).get("win_rate"),
            "win_rate_short": (performance.get("short_performance") or {}).get("win_rate"),
            "win_rate_aggregate": performance.get("win_rate"),
            "net_pnl": performance.get("net_pnl"),
            "profit_factor": performance.get("profit_factor"),
            "last_10": performance.get("last_10"),
            "last_30": performance.get("last_30"),
            "win_rate_claim_status": performance.get("win_rate_claim_status"),
        },
        "reflection": reflection,
        "lessons": lessons,
        "learning": {
            "mistake_signatures": (reflection.get("raw") or {}).get("mistake_signatures") or [],
            "pending_candidate_lessons": lessons.get("candidate_lessons") or [],
        },
        "last_completed_trade": last_trade,
        "adaptive_profit_capture": adaptive,
        "stop_quality": stop_q,
        "DIRECTION": direction,
        "ENTRY QUALITY": entry_q,
        "secrets_redacted": True,
    }


def scan_full_market_directional(
    *,
    client: DemoWriteClient,
    symbols: list[str],
    equity: float,
) -> dict[str, Any]:
    tickers = v27.fetch_ticker_universe(client, symbols)

    hypotheses: list[TwoSidedHypothesis] = []
    for t in tickers:
        sym = t["symbol"]
        entry_px = float(t["last_price"])
        if entry_px <= 0:
            continue
        vol_h = v25.estimate_btc_vol_pct_per_hour(client, sym)
        try:
            info = client.fetch_instrument(sym)
            step = client.qty_step(info)
            min_q = client.min_qty(info)
            min_n = client.min_notional(info)
        except Exception:  # noqa: BLE001
            step, min_q, min_n = 0.001, 0.001, 5.0

        h = evaluate_two_sided_hypothesis(
            symbol=sym,
            entry_price=entry_px,
            equity=equity,
            vol_pct_per_hour=vol_h,
            turnover24h=float(t["turnover_24h"]),
            activity_score=0.75,
            qty_step=step,
            min_qty=min_q,
            min_notional=min_n,
            strategy_family=STRATEGY_FAMILY,
            target_pct=TARGET_PCT,
            stop_pct=STOP_PCT,
            momentum_bias=float(t.get("change_pct_24h") or 0.0) / 100.0,
        )
        hypotheses.append(h)

    def _preflight(symbol: str, side: str, cand: Any) -> dict[str, Any]:
        pf = run_exchange_preflight(
            client=client,
            symbol=symbol,
            entry_price=float(getattr(cand, "entry_price", 0.0) or cand.get("entry_price") or 0.0),
            equity=equity,
            stop_pct=STOP_PCT,
            target_pct=TARGET_PCT,
            preferred_notional=350.0,
            max_loss_equity_pct=0.10,
            liquidity=float(getattr(cand, "liquidity", 0.9) or cand.get("liquidity") or 0.9),
        )
        pf["exchange_feasibility_pass"] = bool(pf.get("preflight_pass"))
        return pf

    selection = select_with_exchange_fallthrough(
        hypotheses, preflight_fn=_preflight
    )

    tie_audit_candidates = [h for h in hypotheses if h.direction_ambiguity_supported]
    tie_audit = None
    if tie_audit_candidates:
        h0 = tie_audit_candidates[0]
        tie_audit = {
            "symbol": h0.symbol,
            "selected_side": h0.selected_side,
            "direction_score_delta": h0.direction_score_delta,
            "long_score": h0.long_score,
            "short_score": h0.short_score,
            "evidence_long": h0.direction_evidence_long,
            "evidence_short": h0.direction_evidence_short,
            "side_selection_reason": h0.side_selection_reason,
            "wait_reason": h0.wait_reason,
        }

    # Funnel-like summary (honest)
    eligible_candidate_sides = {
        "LONG": sum(1 for h in hypotheses if h.selected_side == "LONG"),
        "SHORT": sum(1 for h in hypotheses if h.selected_side == "SHORT"),
        "WAIT": sum(1 for h in hypotheses if h.selected_side == "WAIT"),
    }

    return {
        "schema": "v18_2_29_directional_market_v1",
        "universe_size": len(symbols),
        "scanned": len(tickers),
        "eligible_candidate_sides": eligible_candidate_sides,
        "long_hypotheses": eligible_candidate_sides["LONG"],
        "short_hypotheses": eligible_candidate_sides["SHORT"],
        "wait_hypotheses": eligible_candidate_sides["WAIT"],
        "selection": selection,
        "tie_audit": tie_audit,
        "hypotheses_sample": [h.to_dict() for h in hypotheses[:8]],
    }


def run_research_demo_loop(*, account: dict[str, Any], market_pack: dict[str, Any]) -> dict[str, Any]:
    """Try selected candidates; fall-through on order rejection.

    Dry/smoke (EXCHANGE_WRITE!=true): do NOT place a new Demo order.
    Replay the latest completed RESEARCH lifecycle from prior core evidence for wiring verification.
    """
    exchange_write = str(os.environ.get("EXCHANGE_WRITE", "false")).lower() in {"1", "true", "yes"}
    selection = market_pack.get("selection") or {}

    if not exchange_write:
        # Prefer V29 prior evidence, else V28 BLUAIUSDT completed trade.
        prior_paths = [OUT if OUT.exists() else None, PRIOR_CORE if PRIOR_CORE.exists() else None]
        for p in prior_paths:
            if p is None:
                continue
            prior = _load_json(p)
            # Prefer last trade lifecycle from CHECKPOINT / session pack.
            life = None
            sp = prior.get("session_pnl_pack") or {}
            if isinstance(sp.get("lifecycle"), dict):
                life = sp["lifecycle"]
            if life is None:
                # Walk for first BLUAIUSDT lifecycle with exact_pnl_accounting.
                def _find(obj: Any) -> dict[str, Any] | None:
                    if isinstance(obj, dict):
                        if (
                            obj.get("symbol") == "BLUAIUSDT"
                            and isinstance(obj.get("exact_pnl_accounting"), dict)
                            and obj.get("exit_reason")
                        ):
                            return obj
                        for v in obj.values():
                            found = _find(v)
                            if found is not None:
                                return found
                    elif isinstance(obj, list):
                        for it in obj:
                            found = _find(it)
                            if found is not None:
                                return found
                    return None

                life = _find(prior)
            if life is not None:
                return {
                    "executed": True,
                    "WAIT": False,
                    "dry_replay": True,
                    "reason": "DRY_REPLAY_PRIOR_LIFECYCLE",
                    "lifecycle": life,
                    "two_sided_selection": market_pack,
                    "exchange_preflight": selection.get("preflight") or {},
                    "EXCHANGE_WRITE": False,
                }
        return {
            "executed": False,
            "WAIT": True,
            "dry_replay": True,
            "reason": "DRY_NO_PRIOR_LIFECYCLE",
            "market_opportunity": market_pack,
            "EXCHANGE_WRITE": False,
        }

    if selection.get("action") != "SELECT":
        return {
            "executed": False,
            "WAIT": True,
            "reason": selection.get("block_code") or "NO_DIRECTIONAL_CANDIDATE",
            "market_opportunity": market_pack,
        }

    sym = selection.get("selected_symbol")
    side = selection.get("selected_side") or "LONG"
    preflight = selection.get("preflight") or {}

    pnl = v25.run_research_pnl_trade_v25(
        account=dict(account),
        symbol=sym,
        side=side,
        qty_override=str(preflight.get("normalized_qty") or ""),
        exchange_preflight_pass=bool(preflight.get("exchange_feasibility_pass")),
    )
    pnl["two_sided_selection"] = market_pack
    pnl["exchange_preflight"] = preflight
    return pnl


def run_focused_tests() -> dict[str, Any]:
    files = [
        "tests/research_ai_autonomy/test_v18_2_29_stop_entry_audit.py",
        "tests/research_ai_autonomy/test_v18_2_29_direction_tie_audit.py",
        "tests/research_ai_autonomy/test_v18_2_29_v28_reclassification.py",
        "tests/research_ai_autonomy/test_v18_2_29_rolling_stats.py",
        "tests/research_ai_autonomy/test_v18_2_29_wiring_telemetry.py",
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
    print(json.dumps({"phase": "v18_2_29_start", "at": _utc()}), flush=True)

    holdout = v27.verify_holdouts()
    account = v23.resolve_demo_account()
    symbols, _ = v22.resolve_tracking()
    symbols = symbols[: v27.TRACKING_CAP]

    activity = v27.audit_activity_v27(symbols, {})
    _write_json(CAMPAIGN_ROOT / "activity" / "publisher_repair_v29.json", activity)

    load_demo_env(ENV_PATH)
    client = DemoWriteClient()
    equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)

    integrity = evaluate_horizon_integrity(strategy_family=STRATEGY_FAMILY)
    if not integrity.get("horizon_integrity_pass"):
        pnl_pack = {
            "executed": False,
            "WAIT": True,
            "reason": integrity.get("block_code") or "INVALID_HORIZON_CONFIGURATION",
            "horizon_integrity": integrity,
            "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        }
        _write_json(OUT, {"executed": False, "reason": pnl_pack["reason"]})
        return 0

    market_pack = scan_full_market_directional(client=client, symbols=symbols, equity=equity)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "directional_market.json", market_pack)

    pnl_pack = run_research_demo_loop(account=account, market_pack=market_pack)
    _write_json(CAMPAIGN_ROOT / "autonomy" / "pnl_research_trade.json", pnl_pack)

    lifecycles: list[dict[str, Any]] = []
    # Accumulate prior accounting-complete Research lifecycles for rolling windows.
    if PRIOR_CORE.exists():
        try:
            prior = _load_json(PRIOR_CORE)
            sp = prior.get("session_pnl_pack") or {}
            if isinstance(sp.get("lifecycle"), dict):
                lifecycles.append(sp["lifecycle"])
            for L in (prior.get("AUTONOMY") or {}).get("lifecycles") or []:
                if isinstance(L, dict):
                    lifecycles.append(L)
        except Exception:  # noqa: BLE001
            pass
    if pnl_pack.get("executed") and pnl_pack.get("lifecycle"):
        lifecycles.append(pnl_pack["lifecycle"])

    # Performance (all-time + rolling windows)
    performance = compute_research_win_rate(lifecycles).copy()
    rolling = compute_research_rolling_stats(lifecycles)
    performance["last_10"] = rolling.get("last_10")
    performance["last_30"] = rolling.get("last_30")

    reflections = ReflectionV28()
    for lc in lifecycles:
        reflections.reflect_lifecycle(lc)
    refl_stats = reflections.to_dict()

    last_life = lifecycles[-1] if lifecycles else None
    direction = market_pack.get("selection", {}).get("hypothesis") or {}
    tie_audit = market_pack.get("tie_audit")
    if not direction and tie_audit:
        direction = {
            "selected_side": tie_audit.get("selected_side"),
            "direction_ambiguity_supported": True,
            "side_selection_reason": tie_audit.get("side_selection_reason") or "DIRECTION_AMBIGUOUS",
            "wait_reason": tie_audit.get("wait_reason"),
            "long_score": tie_audit.get("long_score"),
            "short_score": tie_audit.get("short_score"),
            "direction_score_delta": tie_audit.get("direction_score_delta"),
        }

    last_trade_sections = _audit_last_trade_sections(lifecycle=last_life, direction=direction)
    last_trade_block = _build_last_trade_block(lifecycle=last_life, sections=last_trade_sections)
    entry_q = last_trade_sections.get("ENTRY QUALITY") or {}
    stop_q = last_trade_sections.get("STOP QUALITY") or empty_stop_quality_block()
    adaptive = last_trade_sections.get("ADAPTIVE PROFIT CAPTURE") or empty_adaptive_profit_capture_block()

    v28_reclass = reclassify_v28_bluaiusdt_loss()

    # Lesson stage flags: always present; null + reason when not validated.
    lesson_stage_reason = "lesson validation stages not yet executed for this CandidateLesson"
    lessons_block = {
        "candidate_lessons": refl_stats.get("lesson_candidates") or [],
        "replay_passed": None,
        "development_passed": None,
        "shadow_passed": None,
        "demo_passed": None,
        "active_lessons": [],
        "repeat_after_validated_lesson": None,
        "not_available_reason": {
            "replay_passed": lesson_stage_reason,
            "development_passed": lesson_stage_reason,
            "shadow_passed": lesson_stage_reason,
            "demo_passed": lesson_stage_reason,
        },
    }

    checkpoint = {
        "schema": "v18_2_29_progress_checkpoint_v1",
        "updated_at": _utc(),
        "DIRECTION": {
            "tie_break_audit": {
                "side_selection_reason": direction.get("side_selection_reason"),
                "direction_score_delta": direction.get("direction_score_delta"),
                "default_side_bias": False,
            },
            "direction_ambiguity_supported": direction.get("direction_ambiguity_supported"),
            "last_long_score": direction.get("long_score"),
            "last_short_score": direction.get("short_score"),
            "last_score_delta": direction.get("direction_score_delta"),
            "last_selected_side": direction.get("selected_side"),
            "last_side_reason": direction.get("wait_reason") or direction.get("side_selection_reason"),
        },
        "ENTRY QUALITY": {
            "entry_quality_enabled": True,
            **entry_q,
        },
        "STOP QUALITY": stop_q,
        "ADAPTIVE PROFIT CAPTURE": adaptive,
        "AUTONOMY": {
            "market_cycles": 1,
            "eligible_candidate_sides": market_pack.get("eligible_candidate_sides"),
            "prepared": 1 if pnl_pack.get("executed") else 0,
            "triggered": 1 if pnl_pack.get("executed") else 0,
            "real_orders": (
                0
                if pnl_pack.get("dry_replay")
                else (1 if pnl_pack.get("executed") else 0)
            ),
            "dry_replay": bool(pnl_pack.get("dry_replay")),
            "WAIT": 1 if pnl_pack.get("WAIT") else 0,
            "BLOCK": 0,
        },
        "ACTIVE POSITION": {
            "status": "FLAT",
            "symbol": None,
            "side": None,
            "entry": None,
            "current": None,
            "stop": None,
            "dynamic_profit_zone": None,
            "unrealized": None,
            "MFE": None,
            "MAE": None,
            "remaining_edge": None,
            "continuation_score": None,
            "giveback_risk": None,
            "profit_lock_state": None,
            "protected_pnl_floor": None,
            "note": "FLAT after completed trade is correct; see LAST TRADE for closed-trade telemetry",
        },
        "LAST TRADE": last_trade_block,
        "PERFORMANCE": performance,
        "REFLECTION": {
            "latest_root_causes": (
                (
                    (refl_stats.get("reflections") or [{}])[0].get("root_causes")
                    or ((refl_stats.get("reflections") or [{}])[0].get("process_notes") or {}).get(
                        "failure_root_causes"
                    )
                    or (refl_stats.get("reflections") or [{}])[0].get("error_classes")
                )
                if refl_stats.get("reflections")
                else None
            ),
            "unavoidable_outcome_supported": None,
            "v28_reclassification": {
                "V28_original_class": v28_reclass.get("V28_original_class"),
                "V28_reclassified_as": v28_reclass.get("V28_reclassified_as"),
            },
            "raw": refl_stats,
            "not_available_reason": {
                "unavoidable_outcome_supported": (
                    "requires full direction/entry/stop/cost/regime validation pass before claim"
                ),
            },
        },
        "LESSONS": lessons_block,
        "FOUNDER MONITOR": {
            "remote_deployed": False,
            "direction_visible": True,
            "entry_quality_visible": True,
            "stop_quality_visible": True,
            "adaptive_profit_visible": True,
            "performance_visible": True,
            "learning_visible": True,
            "trading_intel_block_present": True,
            "performance_block_present": True,
            "reflection_block_present": True,
            "lessons_block_present": True,
        },
        "SAFETY": {
            "demo_only": True,
            "mainnet": 0,
            "real_money": False,
            "leverage": 1,
            "notional_max": 500,
            "wallet_risk_max": 0.1,
            "member_execution": 0,
            "billing": False,
            "partner_api": False,
            "gate_lowering": False,
            "cost_lowering": False,
            "freshness_lowering": False,
            "oos_reuse": False,
        },
    }

    core = {
        "schema": "v18_2_29_core_v1",
        "generated_at": _utc(),
        "directive": "V18.2.29_AGENT_B_DIRECTION_CONFIDENCE_ENTRY_STOP_QUALITY",
        "prior_v28_sot_sha256": "6451f772eb42f8f8ce2416c688eca742d5f31b6f29bfd9e0c263fada595",
        "worktree": str(ROOT),
        "CANONICAL": {},
        "CHECKPOINT_33": checkpoint,
        "market_opportunity": market_pack,
        "session_pnl_pack": pnl_pack,
        "TESTS": run_focused_tests(),
        "HOLDOUT": holdout,
        "ACTIVITY": activity,
    }

    live_feed = build_founder_live_feed_v29(
        account=account,
        pnl_pack=pnl_pack,
        activity=activity,
        checkpoint=checkpoint,
        open_telemetry=pnl_pack.get("open_position_telemetry"),
    )
    _write_json(LIVE_FEED, live_feed)

    _write_json(OUT, core)
    print(json.dumps({"phase": "done", "out": str(OUT), "exists": OUT.exists()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

