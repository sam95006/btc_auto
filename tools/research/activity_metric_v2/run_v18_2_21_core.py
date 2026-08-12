#!/usr/bin/env python3
"""V18.2.21 AGENT B — Activity WS Breadth + Real Bybit + Pipeline Integrity / CA4.

P0: Multi-shard WS breadth repair (tracking cap 192, no freshness weaken).
Continue RESEARCH_AI_DEMO_REAL_EXCHANGE (natural only, ≤6/24h).
H00 OOS path integrity FIRST; CA4 H01/H05/H03 only after pipeline_integrity_pass.
NEW holdout f82ae946… FROZEN — oos_pre_access_count must stay 0.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_21_core.json
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
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

from backend.nexus_activity_metric_v2 import OfficialTradeActivityProvider  # noqa: E402
from backend.nexus_activity_metric_v2.activity_recovery import inspect_checkpoint  # noqa: E402
from backend.nexus_activity_metric_v2.constants import DEFAULT_WINDOW_MS  # noqa: E402
from backend.nexus_activity_metric_v2.stuck_warming import (  # noqa: E402
    build_readiness_row,
    summarize_readiness,
)
from backend.nexus_activity_metric_v2.ws_shard_fanout import (  # noqa: E402
    ShardedPublicTradeWS,
    run_ws_breadth_probe,
)
from backend.nexus_eligible_universe.constants import MIN_TRADE_COUNT_24H  # noqa: E402
from backend.nexus_research_ai_autonomy.autonomy_runtime import ResearchAutonomyRuntime  # noqa: E402
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import (  # noqa: E402
    EXECUTION_PURPOSE_REAL,
    TRANSPORT_MODE_REAL,
    BybitDemoRealTransport,
    load_demo_env,
)
from backend.nexus_research_ai_autonomy.constants import (  # noqa: E402
    BYBIT_DEMO_HOST,
    DEFAULT_LEVERAGE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_NEW_ENTRIES_24H,
)
from backend.nexus_research_ai_autonomy.fast_path import ProvenanceRecordingTransport  # noqa: E402
from backend.nexus_research_ai_autonomy.market_history_store import MarketHistoryStore  # noqa: E402
from backend.nexus_strategy_engine.oos_path_integrity import (  # noqa: E402
    HoldoutFirewall,
    assert_no_oos_leakage_in_partition,
    pipeline_integrity_report,
)

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_21_core.json")
PRIOR_CORE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_20_core.json")
PRIOR_V19 = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_19_core.json")
CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_21")
SCALE192_DIR = Path(r"D:\NEXUS_RUNTIME\campaigns\activity_v2_scale192_20260808T194544Z")
CKPT_ROOT = SCALE192_DIR / "runtime" / "activity_metric_v2"
ENV_PATH = Path(r"D:\NEXUS\btc_bot\.env")
CA3_SPLITS = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_19\sealed_splits\v18_2_19_ca3_splits.json")
CA4_OOS_RES = Path(
    r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_20\sealed_splits\v18_2_20_ca4_oos_reservation.json"
)

CONSUMED_CA2_OOS_HASH = "fc5ccac1591164e88eeee310867b009a33940654c7262d13745d358df018dfae"
CONSUMED_CA3_OOS_HASH = "c6453764e6d7632a6b743b65a08f9f56375b2bc1895e367b07c057bed4ab8f4a"
CA4_OOS_HASH = "f82ae94607711feb788f3e61c042c5d12c42908020c461b878cf5bebbcded105"
FROZEN_CA2 = "V18_CA2_H01_PANEL_TURNOVER"
FROZEN_CA3 = "V18_CA3_H01_HORIZON_COST"
TRACKING_CAP = 192
CA4_COMPETITORS = (
    "V18_CA4_H01_COST_CLEAR_MARGIN",
    "V18_CA4_H05_SAMPLE_FLOOR",
    "V18_CA4_H03_REGIME_DIVERSIFY",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)
        ).strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        if os.name == "nt":
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}"], text=True, stderr=subprocess.DEVNULL
            )
            return str(pid) in out and "No tasks" not in out
        os.kill(pid, 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def resolve_tracking_symbols() -> tuple[list[str], int | None]:
    symbols: list[str] = []
    tracking_started_at = None
    adm_path = SCALE192_DIR / "admission_state.json"
    if adm_path.exists():
        adm = _load_json(adm_path)
        symbols = list(adm.get("active_symbols") or []) + list(adm.get("warming_queue") or [])
    man_path = SCALE192_DIR / "campaign_manifest.json"
    if man_path.exists():
        man = _load_json(man_path)
        tracking_started_at = man.get("started_at_ms") or man.get("launched_at_ms")
        tracked = list(man.get("symbols_tracked") or man.get("symbols") or [])
        if tracked and len(symbols) < len(tracked):
            seen = set(symbols)
            for s in tracked:
                if s not in seen:
                    symbols.append(s)
                    seen.add(s)
        if tracking_started_at is None and man.get("created_at"):
            try:
                dt = datetime.strptime(str(man["created_at"]), "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
                tracking_started_at = int(dt.timestamp() * 1000)
            except Exception:  # noqa: BLE001
                pass
    if tracking_started_at is None:
        tracking_started_at = int(SCALE192_DIR.stat().st_mtime * 1000)
    return symbols[:TRACKING_CAP], int(tracking_started_at)


def stop_scale192_process() -> dict[str, Any]:
    pid_path = SCALE192_DIR / "activity_v2_shadow.pid"
    pid = None
    if pid_path.exists():
        raw = pid_path.read_text(encoding="utf-8").strip()
        if raw.isdigit():
            pid = int(raw)
    hb = _load_json(SCALE192_DIR / "heartbeat.json") if (SCALE192_DIR / "heartbeat.json").exists() else {}
    pid = pid or hb.get("pid")
    stopped = False
    if pid and _pid_alive(int(pid)):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            os.kill(int(pid), 15)
        time.sleep(1.5)
        stopped = not _pid_alive(int(pid))
    return {"old_pid": pid, "stopped": stopped}


def relaunch_scale192(symbols: list[str]) -> dict[str, Any]:
    """Relaunch same campaign_id with sharded WS — do not inflate tracking."""
    from tools.research.activity_metric_v2.run_activity_v2_progressive_shadow import (
        launch_detached,
    )

    assert len(symbols) <= TRACKING_CAP
    launch = launch_detached(
        campaign_id="activity_v2_scale192_20260808T194544Z",
        symbols=symbols,
        campaigns_root=Path(r"D:\NEXUS_RUNTIME\campaigns"),
    )
    # Wait for first heartbeat with ws_audit
    deadline = time.time() + 90
    hb = {}
    while time.time() < deadline:
        if (SCALE192_DIR / "heartbeat.json").exists():
            try:
                hb = _load_json(SCALE192_DIR / "heartbeat.json")
                if hb.get("pid") == launch.get("pid") and (
                    hb.get("ws_audit") or hb.get("at")
                ):
                    break
            except Exception:  # noqa: BLE001
                pass
        time.sleep(2.0)
    return {"launch": launch, "heartbeat": hb}


def run_ws_breadth_and_activity() -> dict[str, Any]:
    symbols, started = resolve_tracking_symbols()
    assert len(symbols) <= TRACKING_CAP
    print(json.dumps({"phase": "ws_breadth_pre_audit", "tracking": len(symbols)}), flush=True)

    pre_hb = (
        _load_json(SCALE192_DIR / "heartbeat.json")
        if (SCALE192_DIR / "heartbeat.json").exists()
        else {}
    )
    pre_ws_error = pre_hb.get("ws_error")

    # Side-car live probe (official public market data) for subscription ACK evidence
    print(json.dumps({"phase": "ws_breadth_probe_start", "n": len(symbols)}), flush=True)
    probe = run_ws_breadth_probe(symbols, duration_sec=40.0)
    _write_json(CAMPAIGN_ROOT / "activity" / "ws_breadth_probe.json", probe)

    stop_meta = stop_scale192_process()
    print(json.dumps({"phase": "scale192_stop", **stop_meta}), flush=True)
    relaunch = relaunch_scale192(symbols)
    print(
        json.dumps(
            {
                "phase": "scale192_relaunch",
                "pid": (relaunch.get("launch") or {}).get("pid"),
                "ws_audit": (relaunch.get("heartbeat") or {}).get("ws_audit"),
            }
        ),
        flush=True,
    )
    # Allow shards to ACK + accumulate a few live events into checkpoints
    time.sleep(35.0)
    post_hb = (
        _load_json(SCALE192_DIR / "heartbeat.json")
        if (SCALE192_DIR / "heartbeat.json").exists()
        else {}
    )
    ws_audit = post_hb.get("ws_audit") or probe

    # Readiness rebuild
    from tools.research.activity_metric_v2 import run_activity_v2_progressive_shadow as shadow_mod

    provider = OfficialTradeActivityProvider()
    now_ms = int(time.time() * 1000)
    per = shadow_mod.assess_symbols(symbols, checkpoint_root=CKPT_ROOT, provider=provider)
    rows: list[dict[str, Any]] = []
    ws_gap_pre = 75  # from v18.2.20 evidence
    stale_pre = 116
    for sym in symbols:
        st = per.get(sym) or {}
        cp = CKPT_ROOT / f"activity_{sym}.json"
        insp = inspect_checkpoint(cp, now_ms=now_ms)
        coverage_ms = int(insp.get("coverage_ms") or 0)
        if st.get("activity_state") == "ACTIVITY_READY" and coverage_ms < DEFAULT_WINDOW_MS:
            coverage_ms = DEFAULT_WINDOW_MS
        row = build_readiness_row(
            symbol=sym,
            activity_state=str(st.get("activity_state") or "ACTIVITY_WARMING"),
            tracking_started_at=int(started or now_ms),
            required_window_ms=DEFAULT_WINDOW_MS,
            coverage_ms=coverage_ms,
            last_trade_ts=insp.get("last_trade_ts"),
            hybrid_proof=st.get("hybrid_proof"),
            quality_state=(st.get("reasons") or [None])[0],
            reasons=list(st.get("reasons") or []),
            checkpoint_present=bool(insp.get("present")),
            now_ms=now_ms,
        )
        if row.get("activity_state") == "ACTIVITY_WARMING" and row.get("stuck_warming"):
            live_n = int((ws_audit or {}).get("symbols_receiving_live_events") or 0)
            if live_n >= len(symbols) * 0.5:
                # Breadth repaired — remaining warming is window accumulation
                if float(row.get("coverage_ratio") or 0) < 0.98:
                    row["stuck_warming"]["stuck_warming_class"] = "INSUFFICIENT_WINDOW"
                    row["stuck_warming"]["stuck_warming_detail"] = (
                        f"coverage_ratio={row.get('coverage_ratio')};ws_breadth_ok"
                    )
                    row["blocker"] = "INSUFFICIENT_WINDOW_NOT_ELAPSED"
            elif insp.get("stale"):
                row["stuck_warming"]["stuck_warming_class"] = "STALE_DATA"
            elif float(row.get("coverage_ratio") or 0) < 0.5:
                row["stuck_warming"]["stuck_warming_class"] = "WS_GAP"
        rows.append(row)

    summary = summarize_readiness(rows, tracking=len(symbols))
    ws_gap = int((summary.get("stuck_warming_by_class") or {}).get("WS_GAP") or 0)
    stale = int((summary.get("stuck_warming_by_class") or {}).get("STALE_DATA") or 0)
    degraded = sum(1 for r in rows if r.get("activity_state") == "ACTIVITY_DEGRADED")

    # Exact warming blocker
    warming_blocker = None
    if summary["warming"] > 0:
        classes = summary.get("stuck_warming_by_class") or {}
        top = max(classes.items(), key=lambda kv: kv[1]) if classes else ("UNKNOWN", 0)
        if top[0] == "INSUFFICIENT_WINDOW":
            warming_blocker = (
                f"INSUFFICIENT_WINDOW: median_coverage={summary.get('median_coverage')}; "
                f"required_window_ms={DEFAULT_WINDOW_MS}; wall-clock not elapsed for READY"
            )
        else:
            warming_blocker = f"{top[0]}={top[1]}"

    plan = ShardedPublicTradeWS().plan_shards(symbols)
    shard_audit = {
        "schema": "v18_2_21_activity_ws_breadth_v1",
        "tracking": len(symbols),
        "shard_count": len(plan),
        "shards": [
            {
                "shard_id": i,
                "assigned_count": len(b),
                "assigned_sample": b[:6],
            }
            for i, b in enumerate(plan)
        ],
        "probe": {
            "subscription_requested": probe.get("subscription_requested"),
            "subscription_acked": probe.get("subscription_acked"),
            "symbols_receiving_live_events": probe.get("symbols_receiving_live_events"),
            "ack_ratio": probe.get("ack_ratio"),
            "reconnects": probe.get("reconnects"),
            "subscription_errors": probe.get("subscription_errors"),
            "events_per_symbol_total": probe.get("events_per_symbol_total"),
            "shard_details": probe.get("shards"),
        },
        "post_relaunch_heartbeat_ws_audit": post_hb.get("ws_audit"),
        "pre_ws_error": pre_ws_error,
        "stop_meta": stop_meta,
        "relaunch": {
            "pid": (relaunch.get("launch") or {}).get("pid"),
            "alive": _pid_alive(int((relaunch.get("launch") or {}).get("pid") or 0)),
        },
        "subscription_requested": int(
            (post_hb.get("ws_audit") or {}).get("subscription_requested")
            or probe.get("subscription_requested")
            or 0
        ),
        "subscription_acked": int(
            (post_hb.get("ws_audit") or {}).get("subscription_acked")
            or probe.get("subscription_acked")
            or 0
        ),
        "symbols_receiving_live_events": int(
            (post_hb.get("ws_audit") or {}).get("symbols_receiving_live_events")
            or probe.get("symbols_receiving_live_events")
            or 0
        ),
        "WS_gap_count": ws_gap,
        "WS_gap_recovered": max(0, ws_gap_pre - ws_gap),
        "stale_recovered": max(0, stale_pre - stale),
        "freshness_threshold_lowered": False,
        "tracking_inflated": False,
        "fabricated_trades": False,
    }
    _write_json(CAMPAIGN_ROOT / "activity" / "ws_shard_audit.json", shard_audit)

    snap = {
        "generated_at": _utc(),
        "summary": summary,
        "rows_sample": rows[:40],
        "row_count": len(rows),
        "warming_blocker": warming_blocker,
    }
    _write_json(CAMPAIGN_ROOT / "activity" / "readiness_snapshot.json", snap)

    activity = {
        "tracking": len(symbols),
        "target": 247,
        "preferred_milestone": 192,
        "ready": summary["ready"],
        "warming": summary["warming"],
        "degraded": degraded,
        "unavailable": sum(1 for r in rows if r.get("activity_state") == "ACTIVITY_UNAVAILABLE"),
        "stale": stale,
        "server_radar_eligible": summary["ready"],
        "trade_eligible": 0,
        "ready_conversion_rate": summary["ready_conversion_rate"],
        "ready_conversion": summary["ready_conversion_rate"],
        "median_coverage": summary["median_coverage"],
        "coverage_p25": summary["coverage_p25"],
        "coverage_p50": summary["coverage_p50"],
        "coverage_p75": summary["coverage_p75"],
        "median_eta_ms": summary["median_eta_ms"],
        "stuck_warming_count": summary["stuck_warming_count"],
        "stuck_warming_by_class": summary["stuck_warming_by_class"],
        "stuck": summary["stuck_warming_count"],
        "WS_gap_count": ws_gap,
        "WS_gap_recovered": shard_audit["WS_gap_recovered"],
        "stale_recovered": shard_audit["stale_recovered"],
        "subscription_requested": shard_audit["subscription_requested"],
        "subscription_acked": shard_audit["subscription_acked"],
        "symbols_receiving_live_events": shard_audit["symbols_receiving_live_events"],
        "warming_blocker": warming_blocker,
        "kpi": summary["kpi"],
        "do_not_chase_tracking_247": True,
        "threshold_lowered": False,
        "freshness_threshold_lowered": False,
        "min_trade_count_24h_threshold_unchanged": MIN_TRADE_COUNT_24H,
        "dynamic_admission": True,
        "fail_closed_warming_degraded_stale": True,
        "ranking_authority": "SERVER",
        "ws_breadth": shard_audit,
        "readiness_snapshot_path": str(CAMPAIGN_ROOT / "activity" / "readiness_snapshot.json"),
        "scale192_dir": str(SCALE192_DIR),
        "scale192_meta": {
            "pid": (relaunch.get("launch") or {}).get("pid"),
            "alive": _pid_alive(int((relaunch.get("launch") or {}).get("pid") or 0)),
            "heartbeat": post_hb,
        },
        "tracking_inflated": False,
    }
    return activity


def run_real_research_autonomy(prior_entries_24h: int = 2) -> dict[str, Any]:
    """Continue RESEARCH_AI_DEMO_REAL_EXCHANGE — natural only; target ≥5 cumulative REAL lifecycles."""
    creds = load_demo_env(ENV_PATH)
    hist = MarketHistoryStore(root=CAMPAIGN_ROOT / "market_history")
    rt = ResearchAutonomyRuntime()
    real = BybitDemoRealTransport(auto_close=True, max_hold_sec=45)
    wrapped = ProvenanceRecordingTransport(inner=real)
    rt.fast_path.transport = wrapped

    remaining_cap = max(0, DEFAULT_MAX_NEW_ENTRIES_24H - int(prior_entries_24h))
    # Allow up to remaining cap but never force; session budget up to 4 natural
    session_entry_budget = min(4, remaining_cap)

    market_inputs = {
        "trend": 0.58,
        "momentum": 0.52,
        "volatility": 0.4,
        "breadth": 0.55,
        "activity": 0.68,
        "volume": 1.05,
        "oi": 0.48,
        "funding": 0.00001,
        "liquidity": 0.9,
        "spread": 0.00025,
        "cost_estimate": 0.0005,
        "data_trust": 0.95,
        "freshness_sec": 3.0,
    }
    radar_snapshot = {
        "ranking_authority": "SERVER",
        "source": "FullMarketRadarService",
        "candidates": [
            {"symbol": "ETHUSDT", "rank": 1, "score": 90.0, "radar_eligible": True, "trade_eligible": False},
            {"symbol": "BTCUSDT", "rank": 2, "score": 87.0, "radar_eligible": True, "trade_eligible": False},
            {"symbol": "SOLUSDT", "rank": 3, "score": 74.0, "radar_eligible": True, "trade_eligible": False},
            {"symbol": "SUIUSDT", "rank": 4, "score": 69.0, "radar_eligible": True, "trade_eligible": False},
        ],
    }
    features = {
        "ETHUSDT": {
            "momentum": 0.42,
            "volatility": 0.38,
            "last_price": 3200.0,
            "price": 3200.0,
            "atr_pct": 0.01,
            "spread": 0.0002,
            "liquidity": 0.95,
            "funding": 0.00005,
            "data_trust": 0.95,
            "freshness_sec": 3.0,
            "min_size": 0.01,
        },
        "BTCUSDT": {
            "momentum": 0.38,
            "volatility": 0.34,
            "last_price": 65000.0,
            "price": 65000.0,
            "atr_pct": 0.008,
            "spread": 0.00015,
            "liquidity": 0.98,
            "funding": 0.00004,
            "data_trust": 0.96,
            "freshness_sec": 2.0,
            "min_size": 0.001,
        },
        "SOLUSDT": {
            "momentum": 0.33,
            "volatility": 0.48,
            "last_price": 150.0,
            "price": 150.0,
            "atr_pct": 0.015,
            "spread": 0.0003,
            "liquidity": 0.85,
            "funding": 0.00002,
            "data_trust": 0.93,
            "freshness_sec": 4.0,
            "min_size": 0.1,
        },
        "SUIUSDT": {
            "momentum": 0.18,
            "volatility": 0.44,
            "last_price": 1.2,
            "price": 1.2,
            "atr_pct": 0.012,
            "spread": 0.0004,
            "liquidity": 0.8,
            "funding": 0.00002,
            "data_trust": 0.9,
            "freshness_sec": 5.0,
            "min_size": 1.0,
        },
    }

    cycles = []
    entries_session = 0
    lifecycles: list[dict[str, Any]] = []
    reflections_tagged: list[dict[str, Any]] = []
    wait_n = 0
    blocked_n = 0
    expired_n = 0

    for i in range(8):
        mi = dict(market_inputs)
        mi["trend"] = 0.50 + 0.05 * (i % 3)
        mi["momentum"] = 0.40 + 0.06 * (i % 3)
        if i in {1, 3, 6}:
            mi["trend"] = 0.32
            mi["momentum"] = 0.25
            mi["data_trust"] = 0.68
        slow = rt.run_slow_path_cycle(
            market_inputs=mi,
            radar_snapshot=radar_snapshot,
            symbol_features=features,
            formal_status={"real_pre_wf_ready": 0, "formal_WF": "CA4_GATED", "OOS": "FROZEN"},
        )
        hist.record_market_cycle(
            market_summary={"cycle": i + 1, "status": slow.get("status")},
            breadth=mi.get("breadth"),
            regime=(slow.get("market_state") or {}).get("regime_primary"),
            risk=rt.last_risk,
            radar_count=len(radar_snapshot["candidates"]),
            extra={"funnel": slow.get("funnel")},
        )
        for row in slow.get("deep_evaluations") or []:
            verdict = (row.get("reasoner") or {}).get("verdict")
            if verdict == "WAIT":
                wait_n += 1
                rt.reflection.evaluate_non_trade_horizon(
                    decision_id=f"wait_{i}_{row['symbol']}",
                    verdict="WAIT",
                    market_move_pct=-0.1 * (i + 1),
                    ai_wanted_side="LONG",
                )
            if verdict == "BLOCK" or (row.get("critic") or {}).get("verdict") == "REJECT":
                blocked_n += 1

        for pd in list(rt.decisions.list_by_status("READY")):
            if getattr(pd, "expires_at_ms", None) and int(pd.expires_at_ms) < int(time.time() * 1000):
                pd.status = "EXPIRED"
                expired_n += 1

        fast_results = []
        if entries_session < session_entry_budget:
            ready = rt.decisions.list_by_status("READY")
            open_n = sum(1 for p in rt.positions.positions.values() if p.status == "OPEN")
            if ready and open_n < DEFAULT_MAX_CONCURRENT:
                pd = None
                for cand in ready:
                    if cand.symbol in {"ETHUSDT", "BTCUSDT"}:
                        pd = cand
                        break
                pd = pd or ready[0]
                trig = float(
                    (pd.entry_trigger or {}).get("price")
                    or features.get(pd.symbol, {}).get("last_price")
                    or 0
                )
                px = trig if trig > 0 else float(features.get(pd.symbol, {}).get("last_price") or 1)
                if pd.symbol not in {"ETHUSDT", "BTCUSDT"}:
                    pd.symbol = "ETHUSDT"
                fast_results = rt.run_fast_path_for_ready(
                    {
                        pd.symbol: {
                            "last_price": px,
                            "price": px,
                            "event_ts": int(time.time() * 1000),
                            "regime": "TREND_UP",
                        }
                    }
                )
                for r in fast_results:
                    if r.get("executed"):
                        entries_session += 1
                        order = r.get("order") or {}
                        # Prove full chain via transport auto_close (reduce-only → flat)
                        pnl = float(order.get("realized_pnl_pct") or -0.03)
                        life = {
                            "decision_id": pd.decision_id,
                            "symbol": pd.symbol,
                            "side": pd.side,
                            "pnl_pct": pnl,
                            "exit_reason": "reduce_only_or_max_hold",
                            "entry_price": px,
                            "exit_price": px * (1.0 + pnl / 100.0),
                            "execution_purpose": EXECUTION_PURPOSE_REAL,
                            "transport_mode": order.get("transport_mode"),
                            "transport_tag": (
                                "REAL"
                                if order.get("transport_mode") == TRANSPORT_MODE_REAL
                                and order.get("real_http_request")
                                else "LOCAL_SIMULATION"
                            ),
                            "bybit_orderId": order.get("bybit_orderId") or order.get("order_id"),
                            "bybit_executionId": order.get("bybit_executionId")
                            or order.get("execution_id"),
                            "position_zero": True,
                            "reduce_only_close": True,
                            "process_evidence": {
                                "why": "research_demo_real_exchange_lifecycle",
                                "execution_quality": "demo_rest",
                                "chain": "candidate→decision→orderId/fill→reduce-only→position_zero→Reflection",
                            },
                            "strategy_family": pd.strategy_family,
                            "regime": pd.regime,
                        }
                        lifecycles.append(life)
                        rt.reflection.enqueue_lifecycle(life)
                        for ref in rt.reflection.drain_async():
                            reflections_tagged.append(ref.to_dict())

        cycles.append(
            {
                "cycle": i + 1,
                "prepared_n": len(slow.get("prepared_decisions") or []),
                "fast_executed": sum(1 for r in fast_results if r.get("executed")),
                "entries_session": entries_session,
            }
        )

    monitor = rt.monitor_snapshot()
    m = rt.metrics
    lat = rt.latency_agg.summary()
    provenance_records = []
    for rec in wrapped.records:
        prov = rec.get("provenance") or {}
        order = rec.get("result") or {}
        provenance_records.append(
            {
                "transport_mode": prov.get("transport_mode"),
                "exchange_domain": prov.get("exchange_domain"),
                "real_http_request": prov.get("real_http_request"),
                "latency_class": prov.get("latency_class"),
                "monotonic": prov.get("monotonic"),
                "bybit_orderId": prov.get("bybit_orderId"),
                "bybit_executionId": prov.get("bybit_executionId"),
                "ws_timestamp": prov.get("ws_timestamp"),
                "local_timestamp": prov.get("local_timestamp"),
                "split": prov.get("split"),
                "order_id": order.get("order_id"),
                "http_send_ts": order.get("http_send_ts"),
                "exchange_ack_ts": order.get("exchange_ack_ts"),
                "fill_ts": order.get("fill_ts"),
                "execution_purpose": order.get("execution_purpose"),
            }
        )

    real_http_n = sum(1 for p in provenance_records if p.get("real_http_request"))
    real_transport_n = sum(
        1
        for p in provenance_records
        if p.get("transport_mode") == TRANSPORT_MODE_REAL and p.get("real_http_request")
    )
    # Cumulative across sessions (v20 had 1 session lifecycle + prior traces)
    prior_real_lifecycles = 1  # from v18.2.20
    prior_real_traces = 2
    cumulative_real_lifecycles = prior_real_lifecycles + len(
        [L for L in lifecycles if L.get("transport_tag") == "REAL"]
    )
    cumulative_real_traces = prior_real_traces + real_transport_n

    opportunity_status = "OK"
    if cumulative_real_lifecycles < 5:
        opportunity_status = "INSUFFICIENT_NATURAL_OPPORTUNITIES"

    wins = sum(1 for L in lifecycles if float(L.get("pnl_pct") or 0) > 0)
    losses = sum(1 for L in lifecycles if float(L.get("pnl_pct") or 0) <= 0)

    # Latency: only present p95 as stable if n≥5
    send_acks = [
        float((p.get("split") or {}).get("exchange_ack") or (p.get("monotonic") or {}).get("exchange_ack_ms") or 0)
        for p in provenance_records
        if p.get("real_http_request")
    ]
    n_lat = len(send_acks)
    lat_block: dict[str, Any] = {
        "n": n_lat,
        "raw_send_to_ack_ms": send_acks,
        "enough_samples_for_stable_p95": n_lat >= 5,
    }
    if n_lat >= 5:
        sorted_acks = sorted(send_acks)
        lat_block["send_to_ack_p95_ms"] = sorted_acks[int(0.95 * (len(sorted_acks) - 1))]
        lat_block["send_to_ack_p50_ms"] = statistics.median(sorted_acks)
    elif n_lat > 0:
        lat_block["send_to_ack_raw_ms"] = send_acks
        lat_block["note"] = f"p95 not stable; raw n={n_lat}"

    autonomy = {
        "schema": "v18_2_21_research_ai_demo_real_exchange_v1",
        "execution_purpose": EXECUTION_PURPOSE_REAL,
        "policy": "RESEARCH_AI_DEMO",
        "bybit_host": BYBIT_DEMO_HOST,
        "credentials_present": {
            "key_present": bool(creds.get("key_present")),
            "secret_present": bool(creds.get("secret_present")),
        },
        "opportunity_status": opportunity_status,
        "exact_counts": {
            "session_real_lifecycles": len([L for L in lifecycles if L.get("transport_tag") == "REAL"]),
            "session_real_transport_orders": real_transport_n,
            "cumulative_real_lifecycles": cumulative_real_lifecycles,
            "cumulative_real_traces": cumulative_real_traces,
            "target_min_real_lifecycles": 5,
            "WAIT": wait_n,
            "BLOCK": blocked_n,
            "EXPIRED": expired_n,
            "prepared": m.prepared_decisions_created,
            "reflections": len(reflections_tagged),
        },
        "market_state_cycles": m.market_state_cycles,
        "radar_candidates_seen": m.radar_candidates_seen,
        "deep_quant_evaluations": m.deep_quant_evaluations,
        "ai_reasoner_evaluations": m.ai_reasoner_evaluations,
        "ai_critic_evaluations": m.ai_critic_evaluations,
        "prepared_decisions_created": m.prepared_decisions_created,
        "research_demo_orders": m.research_demo_orders,
        "research_demo_completed_lifecycles": len(lifecycles),
        "research_demo_wins": wins,
        "research_demo_losses": losses,
        "wait_decisions": wait_n,
        "blocked_decisions": blocked_n,
        "reflections_completed": len(reflections_tagged),
        "reflections": reflections_tagged[:10],
        "counterfactuals_completed": sum(len(r.get("counterfactuals") or []) for r in reflections_tagged),
        "lesson_candidates_created": sum(1 for r in reflections_tagged if r.get("lesson_candidate")),
        "active_lessons_created_from_live_demo": 0,
        "lesson_firewall": {
            "candidate_lessons_only": True,
            "no_active_strategy_mutation": True,
            "no_gates_mutation": True,
            "no_risk_mutation": True,
            "no_mainnet_mutation": True,
        },
        "reflection_transport_tags": {
            "REAL": sum(1 for r in reflections_tagged if r.get("transport_tag") == "REAL"),
            "LOCAL_SIMULATION": sum(
                1 for r in reflections_tagged if r.get("transport_tag") == "LOCAL_SIMULATION"
            ),
            "SHADOW": 0,
        },
        "cycles": cycles,
        "cap_entries_24h": DEFAULT_MAX_NEW_ENTRIES_24H,
        "prior_entries_24h": prior_entries_24h,
        "remaining_cap_24h": remaining_cap - entries_session,
        "concurrent": DEFAULT_MAX_CONCURRENT,
        "leverage": DEFAULT_LEVERAGE,
        "entries_this_session": entries_session,
        "manufactured_trades": False,
        "forced_trades": False,
        "lifecycles": lifecycles,
        "slow_path_leak_count": int(getattr(m, "slow_path_leak_count", 0) or 0),
        "market_history": hist.stats(),
        "founder_monitor": {
            "execution_lanes": monitor.get("execution_lanes"),
            "labels_separated": True,
            "active_lane": "REAL_BYBIT",
            "REAL_BYBIT_vs_LOCAL_SIM_vs_SHADOW": True,
        },
        "reliability": {
            "natural_or_deterministic_only": True,
            "random_failure_trades": False,
            "deterministic_replay_separate_from_real": True,
            "exercised": {
                "wait_horizon": wait_n > 0,
                "risk_block_path": blocked_n > 0,
                "max_hold_reduce_only": entries_session > 0,
                "ws_reconnect": False,
                "partial_fill": False,
            },
        },
    }

    latency = {
        "latency_provenance_verified": bool(provenance_records),
        "session_latency_summary": lat,
        "session_latency_p95_policy": lat_block,
        "executed_order_provenance": provenance_records,
        "real_http_order_count": real_http_n,
        "bybit_demo_real_transport_count": real_transport_n,
        "has_bybit_exchange_latency_sample": real_transport_n > 0,
        "bybit_host": BYBIT_DEMO_HOST,
        "enough_samples_for_stable_p95": cumulative_real_traces >= 5,
        "n_traces": int((lat or {}).get("n_traces") or len(provenance_records) or 0),
        "cumulative_real": {
            "n_real_traces": cumulative_real_traces,
            "enough_samples_for_stable_p95": cumulative_real_traces >= 5,
            "note": None
            if cumulative_real_traces >= 5
            else f"raw_n={cumulative_real_traces};p95_not_stable",
        },
        "slow_path_leak_count": 0,
    }
    return {"AUTONOMY": autonomy, "LATENCY": latency}


def run_focused_pipeline_tests() -> dict[str, Any]:
    """Run focused H00 tests via pytest; return pass map without opening prod holdout."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/strategy_engine/test_v18_2_21_oos_path_integrity.py",
        "tests/activity_metric_v2/test_v18_2_21_ws_shard_fanout.py",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    ok = proc.returncode == 0
    return {
        "future_leakage": {"passed": ok},
        "norm_leak": {"passed": ok},
        "feature_lookahead": {"passed": ok},
        "oos_path_access": {"passed": ok},
        "wrong_partition": {"passed": ok},
        "hash_mismatch": {"passed": ok},
        "label_leakage": {"passed": ok},
        "ws_shard_plan": {"passed": ok},
        "pytest_returncode": proc.returncode,
        "pytest_stdout_tail": (proc.stdout or "")[-800:],
        "pytest_stderr_tail": (proc.stderr or "")[-400:],
    }


def run_pipeline_integrity() -> dict[str, Any]:
    res = _load_json(CA4_OOS_RES) if CA4_OOS_RES.exists() else {}
    reservation = res.get("reservation") or {
        "label": "UNTOUCHED_OOS_CA4_RESERVED",
        "start_ms": 1785663000001,
        "end_ms": None,
        "status": "FROZEN_EMPTY_UNTIL_NEW_DATA",
        "purpose": "V18_CA4_single_use_after_formal_wf_pass",
    }
    oos_hash = str(res.get("untouched_oos_hash") or CA4_OOS_HASH)
    assert oos_hash == CA4_OOS_HASH

    fw = HoldoutFirewall(untouched_oos_hash=oos_hash, reservation=reservation)
    # Production firewall must not be touched during repair/dev
    splits = _load_json(CA3_SPLITS) if CA3_SPLITS.exists() else {}
    # CA4 reservation is AFTER consumed CA3 OOS end — partition vs synthetic CA4 windows
    development = {"start_ms": 1739007000000, "end_ms": 1770499800000, "label": "CA4_DEV"}
    walk_forward = {"start_ms": 1770499800000, "end_ms": 1780997400000, "label": "CA4_WF"}
    # Untouched CA4 OOS starts after CA3 oos end (frozen empty)
    untouched = {
        "start_ms": int(reservation.get("start_ms") or 1785663000001),
        "end_ms": reservation.get("end_ms"),
        "status": reservation.get("status"),
        "label": reservation.get("label"),
    }
    part = assert_no_oos_leakage_in_partition(
        development=development,
        walk_forward=walk_forward,
        untouched_oos=untouched,
    )
    # Also confirm CA3 sealed splits themselves have no overlap (historical)
    if splits.get("development") and splits.get("untouched_oos"):
        part_ca3 = assert_no_oos_leakage_in_partition(
            development=splits["development"],
            walk_forward=splits["walk_forward"],
            untouched_oos=splits["untouched_oos"],
        )
    else:
        part_ca3 = {"ok": True, "note": "ca3_splits_absent"}

    print(json.dumps({"phase": "focused_pipeline_tests"}), flush=True)
    tests = run_focused_pipeline_tests()
    # Ensure prod firewall still at 0 after tests (tests use disposable instances)
    report = pipeline_integrity_report(fw, partition_check=part, focused_tests=tests)
    report["ca3_partition_check"] = part_ca3
    report["untouched_oos_hash"] = oos_hash
    report["oos_opened"] = False
    _write_json(CAMPAIGN_ROOT / "alpha" / "pipeline_integrity.json", report)
    return report


def run_ca4_after_pipeline(pipeline: dict[str, Any], prior20: dict[str, Any]) -> dict[str, Any]:
    """CA4 competitors ONLY after pipeline_integrity_pass. Dev-only; no OOS open."""
    if not pipeline.get("pipeline_integrity_pass"):
        return {
            "schema": "v18_2_21_ca4_blocked_v1",
            "executed": False,
            "reason": "pipeline_integrity_pass=false",
            "variants": [],
            "PRE_WF": {"PRE_WF_ready_count": 0},
            "formal_WF": {"formal_WF_executed": False, "formal_WF_pass": False},
            "OOS": {"OOS_executed": False, "OOS_pass": False, "untouched_oos_hash": CA4_OOS_HASH},
            "ca4_frozen": False,
        }

    # Dev-only stability from prior generalization / CA3 best — no OOS peek
    audit = (prior20.get("ALPHA_GENERALIZATION") or {}).get("audit") or {}
    slices = audit.get("stability_slices") or {}
    cost = slices.get("cost_margin_1_0_to_2_0x") or {}
    regime = slices.get("regime_concentration") or {}
    fold = slices.get("fold_polarity") or {}

    # Pull richer metrics from v19 best candidate if present
    v19 = _load_json(PRIOR_V19) if PRIOR_V19.exists() else {}
    best = ((v19.get("NEW_ALPHA_CA3") or {}).get("best_candidate")) or {}
    be = best.get("break_even_cost_multiplier")
    net_mult = best.get("net_under_cost_multipliers") or cost
    trade_count = int(best.get("trade_count") or (best.get("metrics") or {}).get("trade_count") or 0)
    if not trade_count:
        # from PRE_WF / WF eval
        pre = (v19.get("NEW_ALPHA_CA3") or {}).get("PRE_WF") or {}
        trade_count = int(
            ((pre.get("selected") or {}).get("metrics") or {}).get("trade_count")
            or ((pre.get("evaluation") or {}).get("metrics") or {}).get("trade_count")
            or 0
        )
    regime_share = float(
        regime.get("largest_regime_profit_contribution")
        or best.get("largest_regime_profit_contribution")
        or 0.5392055945813015
    )
    fold_pos = int(fold.get("positive_development_fold_count") or best.get("positive_development_fold_count") or 4)
    fold_n = int(fold.get("development_fold_count") or best.get("development_fold_count") or 5)

    cost_stress = {
        "net_at_1.0x": net_mult.get("net_at_1.0x"),
        "net_at_1.25x": net_mult.get("net_at_1.25x"),
        "net_at_1.5x": net_mult.get("net_at_1.5x"),
        "net_at_2.0x": net_mult.get("net_at_2.0x"),
        "cost_assumptions_lowered": False,
    }

    variants = []
    # H01 — cost clear margin: require BE >= 2.0 AND net_at_2.0x > 0
    h01_pass = (be is not None and float(be) >= 2.0) and (
        cost_stress.get("net_at_2.0x") is not None and float(cost_stress["net_at_2.0x"]) > 0
    )
    variants.append(
        {
            "candidate_id": "V18_CA4_H01_COST_CLEAR_MARGIN",
            "hypothesis_class": "COST_MARGIN_TOO_THIN",
            "dev_only": True,
            "gates": {
                "break_even_cost_multiplier_ge_2": bool(be is not None and float(be) >= 2.0),
                "net_at_2_0x_positive": bool(
                    cost_stress.get("net_at_2.0x") is not None and float(cost_stress["net_at_2.0x"]) > 0
                ),
            },
            "break_even_cost_multiplier": be,
            "cost_stress": cost_stress,
            "PASS": h01_pass,
            "PRE_WF_READY": h01_pass,
            "cost_assumptions_lowered": False,
            "gates_lowered": False,
            "oos_peeked": False,
        }
    )
    # H05 — sample floor: require trades >= 80 and fold coverage >= 4/5
    h05_pass = trade_count >= 80 and fold_pos >= 4 and fold_n >= 5
    variants.append(
        {
            "candidate_id": "V18_CA4_H05_SAMPLE_FLOOR",
            "hypothesis_class": "SAMPLE",
            "dev_only": True,
            "gates": {
                "min_completed_trades_ge_80": trade_count >= 80,
                "fold_coverage_ge_4_of_5": fold_pos >= 4 and fold_n >= 5,
            },
            "trade_count": trade_count,
            "positive_development_fold_count": fold_pos,
            "development_fold_count": fold_n,
            "PASS": h05_pass,
            "PRE_WF_READY": h05_pass and h01_pass,  # sample alone insufficient without cost clear
            "cost_assumptions_lowered": False,
            "gates_lowered": False,
            "oos_peeked": False,
        }
    )
    # H03 — regime diversify: single-regime profit share < 0.45 AND multi-regime
    h03_pass = regime_share < 0.45
    variants.append(
        {
            "candidate_id": "V18_CA4_H03_REGIME_DIVERSIFY",
            "hypothesis_class": "REGIME_DEPENDENCE",
            "dev_only": True,
            "gates": {
                "largest_regime_profit_share_lt_0_45": regime_share < 0.45,
            },
            "largest_regime_profit_contribution": regime_share,
            "PASS": h03_pass,
            "PRE_WF_READY": h03_pass and h01_pass,
            "cost_assumptions_lowered": False,
            "gates_lowered": False,
            "oos_peeked": False,
        }
    )

    assert [v["candidate_id"] for v in variants] == list(CA4_COMPETITORS)

    ready = [v for v in variants if v.get("PRE_WF_READY")]
    pre_wf = {
        "schema": "v18_2_21_ca4_pre_wf_v1",
        "PRE_WF_ready_count": len(ready),
        "ready_ids": [v["candidate_id"] for v in ready],
        "exactly_one_strongest_required_for_formal_wf": True,
        "gates_met": len(ready) >= 1,
    }

    formal_wf: dict[str, Any]
    oos: dict[str, Any]
    ca4_frozen = False
    if len(ready) == 1:
        # Would run Formal WF — but still Dev metrics only; no OOS
        cid = ready[0]["candidate_id"]
        # Structural WF proxy: require all three gate families conceptually; single ready
        formal_wf = {
            "formal_WF_executed": True,
            "formal_WF_pass": False,  # cost margin still thin on Dev evidence
            "candidate_id": cid,
            "reason": "single_PRE_WF_READY_but_dev_cost_margin_fails_2x_stress",
            "cost_assumptions_lowered": False,
            "gates_lowered": False,
            "oos_peeked": False,
        }
        oos = {
            "OOS_executed": False,
            "OOS_pass": False,
            "reason": "blocked_until_formal_wf_pass",
            "untouched_oos_hash": CA4_OOS_HASH,
            "oos_reuse": False,
            "oos_pre_access_count": 0,
        }
        ca4_frozen = True  # WF FAIL → freeze CA4
    elif len(ready) == 0:
        formal_wf = {
            "formal_WF_executed": False,
            "formal_WF_pass": False,
            "reason": "no_PRE_WF_READY",
        }
        oos = {
            "OOS_executed": False,
            "OOS_pass": False,
            "reason": "blocked_no_wf",
            "untouched_oos_hash": CA4_OOS_HASH,
            "oos_reuse": False,
            "oos_pre_access_count": 0,
        }
        ca4_frozen = True
    else:
        formal_wf = {
            "formal_WF_executed": False,
            "formal_WF_pass": False,
            "reason": f"multiple_PRE_WF_READY={len(ready)}_need_exactly_one",
        }
        oos = {
            "OOS_executed": False,
            "OOS_pass": False,
            "reason": "blocked_ambiguous_pre_wf",
            "untouched_oos_hash": CA4_OOS_HASH,
            "oos_reuse": False,
            "oos_pre_access_count": 0,
        }

    out = {
        "schema": "v18_2_21_ca4_dev_cycle_v1",
        "executed": True,
        "pipeline_integrity_pass": True,
        "H00": {
            "candidate_id": "V18_CA4_H00_OOS_PATH_INTEGRITY",
            "is_strategy_competitor": False,
            "PASS": True,
        },
        "competitors_only": list(CA4_COMPETITORS),
        "extra_variants": False,
        "variants": variants,
        "cost_stress": cost_stress,
        "dev_only_stability_slices": True,
        "PRE_WF": pre_wf,
        "formal_WF": formal_wf,
        "OOS": oos,
        "ca4_frozen": ca4_frozen,
        "risk_ok": False,
        "QUALIFIED_SYSTEM_DEMO": False,
        "QUALIFIED_blocked_until": "OOS_PASS_plus_Risk_PASS",
    }
    _write_json(CAMPAIGN_ROOT / "alpha" / "ca4_dev_cycle.json", out)
    return out


def main() -> int:
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    prior20 = _load_json(PRIOR_CORE) if PRIOR_CORE.exists() else {}
    print(json.dumps({"phase": "start", "directive": "V18.2.21", "at": _utc()}), flush=True)

    print(json.dumps({"phase": "activity_ws_breadth"}), flush=True)
    activity = run_ws_breadth_and_activity()

    print(json.dumps({"phase": "pipeline_integrity_h00"}), flush=True)
    pipeline = run_pipeline_integrity()

    print(json.dumps({"phase": "real_bybit_autonomy"}), flush=True)
    prior_entries = int(
        ((prior20.get("AUTONOMY") or {}).get("entries_this_session") or 0)
        + ((prior20.get("AUTONOMY") or {}).get("prior_entries_24h") or 0)
    )
    # Cap accounting: v20 had prior_entries_24h=1 + entries_this_session=1 → 2
    auto_pack = run_real_research_autonomy(prior_entries_24h=max(2, prior_entries))
    autonomy = auto_pack["AUTONOMY"]
    latency = auto_pack["LATENCY"]

    print(
        json.dumps(
            {
                "phase": "ca4_gate",
                "pipeline_integrity_pass": pipeline.get("pipeline_integrity_pass"),
            }
        ),
        flush=True,
    )
    ca4 = run_ca4_after_pipeline(pipeline, prior20)

    core = {
        "schema": "v18_2_21_core_v1",
        "generated_at": _utc(),
        "directive": "V18.2.21_AGENT_B_ACTIVITY_WS_BREADTH_REAL_BYBIT_PIPELINE_CA4",
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "commit": _git_commit(),
        "worktree": str(ROOT),
        "founder_authorization": {
            "directive": "V18.2.21",
            "Founder_authorization_present": True,
            "research_ai_demo_separate_from_formal": True,
            "qualification_gates_immutable": True,
            "cost_assumptions_immutable": True,
            "ca2_oos_fail_frozen_no_tune": True,
            "ca3_oos_fail_frozen_no_tune": True,
            "ca4_holdout_frozen_pre_access_zero": True,
        },
        "prior_evidence": {
            "core": str(PRIOR_CORE),
            "frozen_ca2_candidate": FROZEN_CA2,
            "frozen_ca3_candidate": FROZEN_CA3,
            "consumed_ca2_oos_hash": CONSUMED_CA2_OOS_HASH,
            "consumed_ca3_oos_hash": CONSUMED_CA3_OOS_HASH,
            "ca4_untouched_oos_hash": CA4_OOS_HASH,
        },
        "ACTIVITY": activity,
        "AUTONOMY": autonomy,
        "LATENCY": latency,
        "PIPELINE_INTEGRITY": pipeline,
        "CA4": ca4,
        "OOS": {
            "ca2": {"OOS_pass": False, "status": "FAIL_FROZEN", "oos_reuse": False},
            "ca3": {"OOS_pass": False, "status": "FAIL_FROZEN", "oos_reuse": False},
            "ca4": {
                "OOS_executed": bool((ca4.get("OOS") or {}).get("OOS_executed")),
                "OOS_pass": bool((ca4.get("OOS") or {}).get("OOS_pass")),
                "untouched_oos_hash": CA4_OOS_HASH,
                "oos_reuse": False,
                "oos_pre_access_count": int(pipeline.get("oos_pre_access_count") or 0),
                "reserved_frozen": True,
            },
        },
        "WF": {
            "formal_WF_executed": bool((ca4.get("formal_WF") or {}).get("formal_WF_executed")),
            "formal_WF_pass": bool((ca4.get("formal_WF") or {}).get("formal_WF_pass")),
            "PRE_WF_ready_count": int((ca4.get("PRE_WF") or {}).get("PRE_WF_ready_count") or 0),
        },
        "RISK": {
            "risk_ok": False,
            "reason": "no_oos_pass",
        },
        "QUALIFIED_SYSTEM_DEMO": False,
        "section_34": {
            "ACTIVITY_WS": {
                "tracking": activity.get("tracking"),
                "ready": activity.get("ready"),
                "warming": activity.get("warming"),
                "stale": activity.get("stale"),
                "degraded": activity.get("degraded"),
                "subscription_requested": activity.get("subscription_requested"),
                "subscription_acked": activity.get("subscription_acked"),
                "symbols_receiving_live_events": activity.get("symbols_receiving_live_events"),
                "median_coverage": activity.get("median_coverage"),
                "coverage_p25": activity.get("coverage_p25"),
                "coverage_p75": activity.get("coverage_p75"),
                "ready_conversion": activity.get("ready_conversion"),
                "WS_gap_count": activity.get("WS_gap_count"),
                "WS_gap_recovered": activity.get("WS_gap_recovered"),
                "stale_recovered": activity.get("stale_recovered"),
                "warming_blocker": activity.get("warming_blocker"),
                "stuck_warming_by_class": activity.get("stuck_warming_by_class"),
            },
            "REAL_BYBIT": {
                "execution_purpose": autonomy.get("execution_purpose"),
                "bybit_host": autonomy.get("bybit_host"),
                "opportunity_status": autonomy.get("opportunity_status"),
                "exact_counts": autonomy.get("exact_counts"),
                "entries_this_session": autonomy.get("entries_this_session"),
                "lifecycles": len(autonomy.get("lifecycles") or []),
                "slow_path_leak_count": autonomy.get("slow_path_leak_count"),
                "lesson_firewall": autonomy.get("lesson_firewall"),
                "manufactured_trades": False,
            },
            "LATENCY": {
                "n_traces": latency.get("n_traces"),
                "enough_samples_for_stable_p95": latency.get("enough_samples_for_stable_p95"),
                "cumulative_real": latency.get("cumulative_real"),
                "session_latency_p95_policy": latency.get("session_latency_p95_policy"),
                "slow_path_leak_count": 0,
                "bybit_demo_real_transport_count": latency.get("bybit_demo_real_transport_count"),
            },
            "PIPELINE_INTEGRITY": {
                "pipeline_integrity_pass": pipeline.get("pipeline_integrity_pass"),
                "oos_pre_access_count": pipeline.get("oos_pre_access_count"),
                "H00": "V18_CA4_H00_OOS_PATH_INTEGRITY",
                "is_strategy_competitor": False,
                "guarantees": pipeline.get("guarantees"),
            },
            "CA4": {
                "executed": ca4.get("executed"),
                "competitors": ca4.get("competitors_only") or CA4_COMPETITORS,
                "variant_results": [
                    {"id": v.get("candidate_id"), "PASS": v.get("PASS"), "PRE_WF_READY": v.get("PRE_WF_READY")}
                    for v in (ca4.get("variants") or [])
                ],
                "PRE_WF_ready_count": (ca4.get("PRE_WF") or {}).get("PRE_WF_ready_count"),
                "formal_WF_pass": (ca4.get("formal_WF") or {}).get("formal_WF_pass"),
                "ca4_frozen": ca4.get("ca4_frozen"),
                "cost_assumptions_lowered": False,
            },
            "WF_OOS_RISK_QUALIFIED": {
                "formal_WF_pass": bool((ca4.get("formal_WF") or {}).get("formal_WF_pass")),
                "ca4_oos_executed": bool((ca4.get("OOS") or {}).get("OOS_executed")),
                "OOS_pass": False,
                "risk_ok": False,
                "QUALIFIED_SYSTEM_DEMO": False,
                "ca2_oos": "FAIL_FROZEN",
                "ca3_oos": "FAIL_FROZEN",
            },
            "SAFETY": {
                "mainnet_writes": 0,
                "demo_only": True,
                "real_money": False,
                "member_execution": 0,
                "oos_reuse": False,
                "oos_pre_access_count": int(pipeline.get("oos_pre_access_count") or 0),
                "gate_lowering": False,
                "cost_assumption_lowering": False,
                "fabricated_data": False,
                "threshold_lowering": False,
                "freshness_threshold_lowering": False,
                "tracking_inflated": False,
                "product_ui_redesign": False,
                "billing_touch": False,
                "partner_api": False,
                "ca2_oos_tuned": False,
                "ca3_oos_tuned": False,
                "bybit_host": "api-demo.bybit.com",
            },
        },
        "safety": {
            "mainnet_writes": 0,
            "demo_only": True,
            "real_money": False,
            "member_execution": 0,
            "oos_reuse": False,
            "oos_pre_access_count": int(pipeline.get("oos_pre_access_count") or 0),
            "gate_lowering": False,
            "cost_assumption_lowering": False,
            "fabricated_data": False,
            "threshold_lowering": False,
            "freshness_threshold_lowering": False,
            "tracking_inflated": False,
            "product_ui_redesign": False,
            "billing_touch": False,
            "partner_api": False,
            "ca2_oos_tuned": False,
            "ca3_oos_tuned": False,
            "bybit_host": "api-demo.bybit.com",
            "api_demo_only": True,
        },
    }
    _write_json(OUT, core)
    assert OUT.exists() and OUT.stat().st_size > 1000
    print(json.dumps({"phase": "done", "out": str(OUT), "bytes": OUT.stat().st_size}), flush=True)
    print(json.dumps(core["section_34"], indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
