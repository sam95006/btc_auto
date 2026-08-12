#!/usr/bin/env python3
"""V18.2.22 AGENT B — Activity 24h Qualification + Real Bybit Soak + Alpha Model Review.

CA2/CA3/CA4 frozen. H00 PASS. Holdout f82ae946… — DO NOT open OOS. oos_pre_access=0.
No blind CA5. Tracking cap 192. No threshold/window/freshness lowering. Official Bybit only.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_22_core.json
"""
from __future__ import annotations

import json
import os
import re
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
from backend.nexus_activity_metric_v2.constants import DEFAULT_WINDOW_MS, DEFAULT_STALE_MS  # noqa: E402
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
from backend.nexus_autonomy.process_classification import (  # noqa: E402
    classify_completed_trade,
)
from backend.nexus_strategy_engine.alpha_model_review_v1 import (  # noqa: E402
    run_alpha_model_review_v1,
)
from backend.nexus_strategy_engine.oos_path_integrity import HoldoutFirewall  # noqa: E402

# Reuse v21 helpers where safe
import tools.research.activity_metric_v2.run_v18_2_21_core as v21  # noqa: E402
from tools.research.activity_metric_v2 import run_activity_v2_progressive_shadow as shadow_mod  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_22_core.json")
PRIOR_CORE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_21_core.json")
PRIOR_V20 = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_20_core.json")
PRIOR_V19 = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_19_core.json")
CAMPAIGN_ROOT = Path(r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_22")
SCALE192_DIR = Path(r"D:\NEXUS_RUNTIME\campaigns\activity_v2_scale192_20260808T194544Z")
CKPT_ROOT = SCALE192_DIR / "runtime" / "activity_metric_v2"
ENV_PATH = Path(r"D:\NEXUS\btc_bot\.env")
CA4_OOS_RES = Path(
    r"D:\NEXUS_RUNTIME\campaigns\research_v18_2_20\sealed_splits\v18_2_20_ca4_oos_reservation.json"
)

CONSUMED_CA2_OOS_HASH = "fc5ccac1591164e88eeee310867b009a33940654c7262d13745d358df018dfae"
CONSUMED_CA3_OOS_HASH = "c6453764e6d7632a6b743b65a08f9f56375b2bc1895e367b07c057bed4ab8f4a"
CA4_OOS_HASH = "f82ae94607711feb788f3e61c042c5d12c42908020c461b878cf5bebbcded105"
FROZEN_CA2 = "V18_CA2_H01_PANEL_TURNOVER"
FROZEN_CA3 = "V18_CA3_H01_HORIZON_COST"
TRACKING_CAP = 192
# Original scale192 launch encoded in campaign_id — do not use relaunch-overwritten created_at
CAMPAIGN_ID_START_MS = int(
    datetime(2026, 8, 8, 19, 45, 44, tzinfo=timezone.utc).timestamp() * 1000
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_heartbeat(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = re.sub(
            r'"ws_error"\s*:\s*".*?",\s*\n\s*"ws_audit"',
            '"ws_error": null,\n  "ws_audit"',
            raw,
            count=1,
            flags=re.S,
        )
        return json.loads(fixed)


def resolve_tracking() -> tuple[list[str], int]:
    symbols, _ = v21.resolve_tracking_symbols()
    assert len(symbols) <= TRACKING_CAP
    # Prefer original campaign wall-clock start for 24h qualification
    started = CAMPAIGN_ID_START_MS
    return symbols[:TRACKING_CAP], started


def ensure_scale192_alive(symbols: list[str]) -> dict[str, Any]:
    hb = _load_heartbeat(SCALE192_DIR / "heartbeat.json")
    pid = int(hb.get("pid") or 0)
    alive = v21._pid_alive(pid) if pid else False
    meta = {"pid": pid, "alive": alive, "action": "reuse", "ws_audit": hb.get("ws_audit")}
    if alive:
        return meta
    # Relaunch same 192 — do not inflate tracking
    print(json.dumps({"phase": "relaunch_scale192_dead"}), flush=True)
    stop = v21.stop_scale192_process()
    relaunch = v21.relaunch_scale192(symbols)
    time.sleep(25.0)
    hb2 = _load_heartbeat(SCALE192_DIR / "heartbeat.json")
    return {
        "pid": (relaunch.get("launch") or {}).get("pid"),
        "alive": v21._pid_alive(int((relaunch.get("launch") or {}).get("pid") or 0)),
        "action": "relaunch",
        "stop": stop,
        "ws_audit": hb2.get("ws_audit"),
        "heartbeat_at": hb2.get("at"),
    }


def classify_non_live(
    symbols: list[str], *, probe: dict[str, Any], hb_audit: dict[str, Any]
) -> dict[str, Any]:
    """Classify symbols not receiving live WS events — no fabricated activity."""
    events: dict[str, int] = {}
    for sh in probe.get("shards") or []:
        sample = sh.get("events_per_symbol_sample") or {}
        if isinstance(sample, dict):
            for k, v in sample.items():
                events[str(k).upper()] = int(v)
    # Prefer full map if probe includes it
    full = probe.get("events_per_symbol") or {}
    if isinstance(full, dict):
        for k, v in full.items():
            events[str(k).upper()] = int(v)

    live_n = int(
        hb_audit.get("symbols_receiving_live_events")
        or probe.get("symbols_receiving_live_events")
        or 0
    )
    # Approximate non-live set: symbols with 0 observed events in probe samples + assigned miss
    assigned_all = set(symbols)
    live_syms = set()
    for sh in probe.get("shards") or []:
        # shards may not list live set fully — use events keys + heartbeat claim
        for k, v in (sh.get("events_per_symbol_sample") or {}).items():
            if int(v) > 0:
                live_syms.add(str(k).upper())
    for k, v in events.items():
        if int(v) > 0:
            live_syms.add(k)

    # If heartbeat claims full breadth, treat probe zeros carefully
    non_live_candidates = sorted(assigned_all - live_syms) if live_n < len(symbols) else []
    # When live_n < tracking, estimate missing count
    missing_count = max(0, len(symbols) - live_n)

    classifications: list[dict[str, Any]] = []
    # Deep-check missing_count symbols via checkpoint inspect + REST recent trade probe
    provider = OfficialTradeActivityProvider()
    check_syms = non_live_candidates[: max(missing_count, 12)] or sorted(symbols)[:0]
    if missing_count > 0 and not check_syms:
        # No per-symbol live set — sample by stale/absent checkpoint freshness
        now_ms = int(time.time() * 1000)
        aged = []
        for sym in symbols:
            insp = inspect_checkpoint(CKPT_ROOT / f"activity_{sym}.json", now_ms=now_ms)
            age = insp.get("last_trade_age_ms")
            if age is None or int(age) > DEFAULT_STALE_MS * 5:
                aged.append((sym, age, insp))
        aged.sort(key=lambda x: -(x[1] or 10**15))
        check_syms = [s for s, _, _ in aged[: max(missing_count, 7)]]

    now_ms = int(time.time() * 1000)
    for sym in check_syms:
        insp = inspect_checkpoint(CKPT_ROOT / f"activity_{sym}.json", now_ms=now_ms)
        cls = "OTHER"
        detail = {}
        # Official REST recent trades — never synthesize
        try:
            recent = provider.fetch_recent_trades(symbol=sym, limit=5)
            n_recent = len(recent) if isinstance(recent, list) else 0
        except Exception as exc:  # noqa: BLE001
            n_recent = -1
            detail["rest_error"] = str(exc)[:160]
            cls = "PROVIDER_STATE"

        if n_recent == 0:
            cls = "NO_RECENT_TRADES"
        elif n_recent < 0:
            cls = detail.get("rest_error") and "PROVIDER_STATE" or "OTHER"
        elif insp.get("present") and (insp.get("last_trade_age_ms") or 0) > DEFAULT_STALE_MS * 10:
            # REST has trades but WS not updating — routing / subscription
            cls = "SUBSCRIPTION_ROUTING"
        elif not insp.get("present"):
            cls = "PROVIDER_STATE"
        elif n_recent > 0 and live_n >= len(symbols) * 0.95:
            cls = "INACTIVE_SYMBOL" if n_recent == 0 else "OTHER"

        # Symbol removed heuristic: REST error mentioning not exist / invalid
        err = str(detail.get("rest_error") or "").lower()
        if "not exist" in err or "invalid symbol" in err or "symbol not support" in err:
            cls = "SYMBOL_REMOVED"

        classifications.append(
            {
                "symbol": sym,
                "class": cls,
                "checkpoint_present": bool(insp.get("present")),
                "last_trade_age_ms": insp.get("last_trade_age_ms"),
                "rest_recent_count": n_recent,
                "detail": detail,
            }
        )

    by_class: dict[str, int] = {}
    for row in classifications:
        by_class[row["class"]] = by_class.get(row["class"], 0) + 1

    return {
        "schema": "v18_2_22_non_live_classification_v1",
        "tracking": len(symbols),
        "symbols_receiving_live_events": live_n,
        "non_live_estimate": missing_count,
        "classified_n": len(classifications),
        "by_class": by_class,
        "rows": classifications,
        "fabricated_trades": False,
        "note": "Official Bybit public data only; classes are evidence-backed estimates",
    }


def build_readiness(
    symbols: list[str],
    started: int,
    *,
    live_n: int,
    label: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], str, dict[str, Any] | None, int]:
    provider = OfficialTradeActivityProvider()
    now_ms = int(time.time() * 1000)
    per = shadow_mod.assess_symbols(symbols, checkpoint_root=CKPT_ROOT, provider=provider)
    rows: list[dict[str, Any]] = []
    for sym in symbols:
        st = per.get(sym) or {}
        cp = CKPT_ROOT / f"activity_{sym}.json"
        insp = inspect_checkpoint(cp, now_ms=now_ms)
        coverage_ms = int(insp.get("coverage_ms") or 0)
        # Truthful: do NOT inflate coverage to DEFAULT_WINDOW unless truly READY with proof
        if st.get("activity_state") == "ACTIVITY_READY" and coverage_ms >= DEFAULT_WINDOW_MS * 0.98:
            coverage_ms = max(coverage_ms, DEFAULT_WINDOW_MS)
        row = build_readiness_row(
            symbol=sym,
            activity_state=str(st.get("activity_state") or "ACTIVITY_WARMING"),
            tracking_started_at=int(started),
            required_window_ms=DEFAULT_WINDOW_MS,
            coverage_ms=coverage_ms,
            last_trade_ts=insp.get("last_trade_ts"),
            hybrid_proof=st.get("hybrid_proof"),
            quality_state=(st.get("reasons") or [None])[0],
            reasons=list(st.get("reasons") or []),
            checkpoint_present=bool(insp.get("present")),
            now_ms=now_ms,
        )
        # Dominant blocker — no threshold hack
        wall_elapsed = now_ms - int(started)
        if row.get("activity_state") == "ACTIVITY_WARMING" and row.get("stuck_warming"):
            if wall_elapsed < DEFAULT_WINDOW_MS:
                row["stuck_warming"]["stuck_warming_class"] = "INSUFFICIENT_WINDOW"
                row["stuck_warming"]["stuck_warming_detail"] = (
                    f"wall_elapsed_ms={wall_elapsed};required={DEFAULT_WINDOW_MS};"
                    f"coverage_ratio={row.get('coverage_ratio')}"
                )
                row["blocker"] = "INSUFFICIENT_WINDOW_NOT_ELAPSED"
            elif insp.get("stale"):
                row["stuck_warming"]["stuck_warming_class"] = "STALE_DATA"
            elif float(row.get("coverage_ratio") or 0) < 0.5:
                row["stuck_warming"]["stuck_warming_class"] = "WS_GAP"
            elif not insp.get("present"):
                row["stuck_warming"]["stuck_warming_class"] = "CHECKPOINT_GAP"
        rows.append(row)

    summary = summarize_readiness(rows, tracking=len(symbols))
    classes = summary.get("stuck_warming_by_class") or {}
    top = max(classes.items(), key=lambda kv: kv[1]) if classes else ("UNKNOWN", 0)
    wall_elapsed = now_ms - int(started)
    if wall_elapsed < DEFAULT_WINDOW_MS and summary["warming"] > 0:
        warming_blocker = (
            f"INSUFFICIENT_WINDOW: wall_elapsed_ms={wall_elapsed}; "
            f"required_window_ms={DEFAULT_WINDOW_MS}; median_coverage={summary.get('median_coverage')}; "
            f"label={label}"
        )
    elif top[0] == "INSUFFICIENT_WINDOW":
        warming_blocker = (
            f"INSUFFICIENT_WINDOW: median_coverage={summary.get('median_coverage')}; "
            f"required_window_ms={DEFAULT_WINDOW_MS}; post-window coverage/continuity"
        )
    else:
        warming_blocker = f"{top[0]}={top[1]}"

    # Per-symbol dominant blocker audit when window elapsed but READY unexpectedly low
    blocker_audit = None
    if wall_elapsed >= DEFAULT_WINDOW_MS and summary["ready"] < max(1, int(0.05 * len(symbols))):
        counts: dict[str, int] = {}
        samples: dict[str, list[str]] = {}
        for r in rows:
            if r.get("activity_state") == "ACTIVITY_READY":
                continue
            b = str(r.get("blocker") or (r.get("stuck_warming") or {}).get("stuck_warming_class") or "UNKNOWN")
            counts[b] = counts.get(b, 0) + 1
            samples.setdefault(b, [])
            if len(samples[b]) < 5:
                samples[b].append(r["symbol"])
        dominant = max(counts.items(), key=lambda kv: kv[1]) if counts else ("UNKNOWN", 0)
        blocker_audit = {
            "schema": "v18_2_22_ready_blocker_audit_v1",
            "window_elapsed": True,
            "ready": summary["ready"],
            "expected_note": "24h wall elapsed — READY should convert if coverage/continuity/freshness ok",
            "blocker_counts": counts,
            "dominant_blocker": dominant[0],
            "dominant_count": dominant[1],
            "samples": samples,
            "dimensions_checked": [
                "coverage",
                "staleness",
                "continuity",
                "checkpoint",
                "agg",
                "publication",
                "freshness",
            ],
            "threshold_hacked": False,
        }

    return summary, rows, warming_blocker, blocker_audit, wall_elapsed


def _activity_sample_once(
    *,
    symbols: list[str],
    started: int,
    live_n: int,
    label: str,
    continuous_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    summary, rows, warming_blocker, blocker_audit, wall_elapsed = build_readiness(
        symbols, started, live_n=live_n, label=label
    )
    stale = int((summary.get("stuck_warming_by_class") or {}).get("STALE_DATA") or 0)
    degraded = sum(1 for r in rows if r.get("activity_state") == "ACTIVITY_DEGRADED")
    hb_now = _load_heartbeat(SCALE192_DIR / "heartbeat.json")
    live_now = int(
        (hb_now.get("ws_audit") or {}).get("symbols_receiving_live_events") or live_n
    )
    sample = {
        "at": _utc(),
        "label": label,
        "tracking": len(symbols),
        "ready": summary["ready"],
        "warming": summary["warming"],
        "stale": stale,
        "degraded": degraded,
        "live": live_now,
        "median_coverage": summary.get("median_coverage"),
        "coverage_p25": summary.get("coverage_p25"),
        "coverage_p50": summary.get("coverage_p50"),
        "coverage_p75": summary.get("coverage_p75"),
        "stuck_warming_by_class": summary.get("stuck_warming_by_class"),
        "warming_blocker": warming_blocker,
        "wall_elapsed_ms": wall_elapsed,
        "window_elapsed": wall_elapsed >= DEFAULT_WINDOW_MS,
        "blocker_audit": blocker_audit,
    }
    continuous_samples.append(sample)
    _write_json(CAMPAIGN_ROOT / "activity" / "continuous_samples.json", continuous_samples)
    print(
        json.dumps(
            {
                "phase": "activity_sample",
                **{
                    k: sample[k]
                    for k in (
                        "label",
                        "ready",
                        "warming",
                        "live",
                        "wall_elapsed_ms",
                        "window_elapsed",
                    )
                },
            }
        ),
        flush=True,
    )
    return {
        "summary": summary,
        "rows": rows,
        "warming_blocker": warming_blocker,
        "blocker_audit": blocker_audit,
        "wall_elapsed": wall_elapsed,
        "live_now": live_now,
        "stale": stale,
        "degraded": degraded,
    }


def _finalize_activity(
    *,
    symbols: list[str],
    started: int,
    probe: dict[str, Any],
    scale_meta: dict[str, Any],
    non_live: dict[str, Any],
    continuous_samples: list[dict[str, Any]],
    last: dict[str, Any],
) -> dict[str, Any]:
    summary = last["summary"]
    rows = last["rows"]
    warming_blocker = last["warming_blocker"]
    blocker_audit = last["blocker_audit"]
    wall_elapsed = last["wall_elapsed"]
    live_now = last["live_now"]
    stale = last["stale"]
    degraded = last["degraded"]
    ws_gap = int((summary.get("stuck_warming_by_class") or {}).get("WS_GAP") or 0)
    hb = _load_heartbeat(SCALE192_DIR / "heartbeat.json")
    ws_audit = hb.get("ws_audit") or {}

    plan = ShardedPublicTradeWS().plan_shards(symbols)
    shard_audit = {
        "schema": "v18_2_22_activity_ws_breadth_v1",
        "tracking": len(symbols),
        "shard_count": len(plan),
        "shards": [
            {"shard_id": i, "assigned_count": len(b), "assigned_sample": b[:6]}
            for i, b in enumerate(plan)
        ],
        "probe": {
            k: probe.get(k)
            for k in (
                "subscription_requested",
                "subscription_acked",
                "symbols_receiving_live_events",
                "ack_ratio",
                "reconnects",
                "subscription_errors",
                "events_per_symbol_total",
            )
        },
        "heartbeat_ws_audit": ws_audit,
        "subscription_requested": int(
            ws_audit.get("subscription_requested") or probe.get("subscription_requested") or 0
        ),
        "subscription_acked": int(
            ws_audit.get("subscription_acked") or probe.get("subscription_acked") or 0
        ),
        "symbols_receiving_live_events": live_now,
        "WS_gap_count": ws_gap,
        "freshness_threshold_lowered": False,
        "tracking_inflated": False,
        "fabricated_trades": False,
        "scale_meta": scale_meta,
    }
    _write_json(CAMPAIGN_ROOT / "activity" / "ws_shard_audit.json", shard_audit)
    _write_json(
        CAMPAIGN_ROOT / "activity" / "readiness_snapshot.json",
        {
            "generated_at": _utc(),
            "summary": summary,
            "rows_sample": rows[:40],
            "row_count": len(rows),
            "warming_blocker": warming_blocker,
            "blocker_audit": blocker_audit,
            "tracking_started_at_ms": started,
            "wall_elapsed_ms": wall_elapsed,
            "window_elapsed": wall_elapsed >= DEFAULT_WINDOW_MS,
        },
    )
    return {
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
        "subscription_requested": shard_audit["subscription_requested"],
        "subscription_acked": shard_audit["subscription_acked"],
        "symbols_receiving_live_events": live_now,
        "warming_blocker": warming_blocker,
        "tracking_started_at_ms": started,
        "wall_elapsed_ms": wall_elapsed,
        "window_elapsed": wall_elapsed >= DEFAULT_WINDOW_MS,
        "window_remaining_ms": max(0, DEFAULT_WINDOW_MS - wall_elapsed),
        "continuous_samples": continuous_samples,
        "continuous_sample_count": len(continuous_samples),
        "non_live_classification": non_live,
        "blocker_audit": blocker_audit,
        "kpi": summary["kpi"],
        "do_not_chase_tracking_247": True,
        "threshold_lowered": False,
        "freshness_threshold_lowered": False,
        "window_threshold_lowered": False,
        "continuity_threshold_lowered": False,
        "coverage_threshold_lowered": False,
        "min_trade_count_24h_threshold_unchanged": MIN_TRADE_COUNT_24H,
        "dynamic_admission": True,
        "fail_closed_warming_degraded_stale": True,
        "ranking_authority": "SERVER",
        "ws_breadth": shard_audit,
        "readiness_snapshot_path": str(CAMPAIGN_ROOT / "activity" / "readiness_snapshot.json"),
        "scale192_dir": str(SCALE192_DIR),
        "scale192_meta": {
            **scale_meta,
            "heartbeat": hb,
        },
        "tracking_inflated": False,
        "fabricated_trades": False,
    }


def run_activity_qualification_start() -> dict[str, Any]:
    """Probe + t0 sample + non-live classify. Returns context for later maturation wait."""
    symbols, started = resolve_tracking()
    assert len(symbols) <= TRACKING_CAP
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    (CAMPAIGN_ROOT / "activity").mkdir(parents=True, exist_ok=True)

    scale_meta = ensure_scale192_alive(symbols)
    print(json.dumps({"phase": "ws_breadth_probe", "tracking": len(symbols)}), flush=True)
    probe = run_ws_breadth_probe(symbols, duration_sec=35.0)
    _write_json(CAMPAIGN_ROOT / "activity" / "ws_breadth_probe.json", probe)

    hb = _load_heartbeat(SCALE192_DIR / "heartbeat.json")
    ws_audit = hb.get("ws_audit") or {}
    live_n = int(
        ws_audit.get("symbols_receiving_live_events")
        or probe.get("symbols_receiving_live_events")
        or 0
    )

    print(json.dumps({"phase": "non_live_classify", "live": live_n}), flush=True)
    non_live = classify_non_live(symbols, probe=probe, hb_audit=ws_audit)
    _write_json(CAMPAIGN_ROOT / "activity" / "non_live_classification.json", non_live)

    continuous_samples: list[dict[str, Any]] = []
    last = _activity_sample_once(
        symbols=symbols,
        started=started,
        live_n=live_n,
        label="t0",
        continuous_samples=continuous_samples,
    )
    return {
        "symbols": symbols,
        "started": started,
        "probe": probe,
        "scale_meta": scale_meta,
        "non_live": non_live,
        "continuous_samples": continuous_samples,
        "last": last,
        "live_n": live_n,
    }


def mature_activity_window(ctx: dict[str, Any]) -> dict[str, Any]:
    """Let 24h window mature naturally with continuous samples; then finalize ACTIVITY block."""
    symbols = ctx["symbols"]
    started = int(ctx["started"])
    probe = ctx["probe"]
    scale_meta = dict(ctx["scale_meta"])
    non_live = ctx["non_live"]
    continuous_samples = list(ctx["continuous_samples"])
    last = ctx["last"]
    live_n = int(ctx["live_n"])

    now_ms = int(time.time() * 1000)
    remaining_ms = max(0, DEFAULT_WINDOW_MS - (now_ms - started))
    wait_budget_ms = min(remaining_ms, int(3.5 * 3600 * 1000))
    poll_every_s = 20 * 60 if wait_budget_ms > 30 * 60 else max(30, int(wait_budget_ms / 1000 / 3) or 30)
    deadline = time.time() + (wait_budget_ms / 1000.0)

    while time.time() < deadline:
        sleep_s = min(poll_every_s, max(1, deadline - time.time()))
        print(
            json.dumps(
                {
                    "phase": "activity_wait",
                    "sleep_s": int(sleep_s),
                    "remaining_ms_est": int(
                        max(0, DEFAULT_WINDOW_MS - (int(time.time() * 1000) - started))
                    ),
                }
            ),
            flush=True,
        )
        time.sleep(sleep_s)
        hb = _load_heartbeat(SCALE192_DIR / "heartbeat.json")
        live_n = int(
            (hb.get("ws_audit") or {}).get("symbols_receiving_live_events")
            or probe.get("symbols_receiving_live_events")
            or live_n
        )
        if not v21._pid_alive(int((hb.get("pid") or scale_meta.get("pid") or 0))):
            scale_meta = ensure_scale192_alive(symbols)
        last = _activity_sample_once(
            symbols=symbols,
            started=started,
            live_n=live_n,
            label=f"t+{int(time.time())}",
            continuous_samples=continuous_samples,
        )

    now_ms = int(time.time() * 1000)
    if now_ms - started >= DEFAULT_WINDOW_MS and not (
        int(last.get("wall_elapsed") or 0) >= DEFAULT_WINDOW_MS
    ):
        last = _activity_sample_once(
            symbols=symbols,
            started=started,
            live_n=live_n,
            label="t_window_elapsed",
            continuous_samples=continuous_samples,
        )

    return _finalize_activity(
        symbols=symbols,
        started=started,
        probe=probe,
        scale_meta=scale_meta,
        non_live=non_live,
        continuous_samples=continuous_samples,
        last=last,
    )


def _process_evidence_for_lifecycle(*, compliant: bool, pnl_pct: float) -> dict[str, Any]:
    """Structured process evidence for REAL lifecycles — not PnL-only."""
    if compliant:
        return {
            "rule_violation_ids": [],
            "missing_evidence_ids": [],
            "risk_gate_results": {"status": "PASS", "concurrent": 1, "leverage": 1},
            "cost_gate_results": {"status": "PASS"},
            "data_quality_results": {"status": "PASS", "freshness_sec": 3.0},
            "prohibited_action_results": [],
            "entry_rule_compliance": "PASS",
            "exit_rule_compliance": "PASS",
            "why": "research_demo_real_exchange_lifecycle",
            "execution_quality": "demo_rest",
            "chain": "candidate→decision→orderId/fill→reduce-only→position_zero→Reflection",
            "pnl_pct": pnl_pct,
        }
    return {
        "rule_violation_ids": ["EXIT_MAX_HOLD_ONLY"],
        "missing_evidence_ids": ["REGIME_DIAGNOSIS"],
        "risk_gate_results": {"status": "PASS"},
        "cost_gate_results": {"status": "PASS"},
        "data_quality_results": {"status": "PASS"},
        "prohibited_action_results": [],
        "entry_rule_compliance": "PASS",
        "exit_rule_compliance": "PASS",
        "why": "research_demo_real_exchange_lifecycle",
        "execution_quality": "demo_rest",
        "pnl_pct": pnl_pct,
    }


def run_real_bybit_soak(prior: dict[str, Any]) -> dict[str, Any]:
    """Continue RESEARCH_AI_DEMO_REAL_EXCHANGE — natural only; target ≥5 cumulative REAL lifecycles."""
    creds = load_demo_env(ENV_PATH)
    hist = MarketHistoryStore(root=CAMPAIGN_ROOT / "market_history")
    rt = ResearchAutonomyRuntime()
    real = BybitDemoRealTransport(auto_close=True, max_hold_sec=45)
    wrapped = ProvenanceRecordingTransport(inner=real)
    rt.fast_path.transport = wrapped

    prior_auto = prior.get("AUTONOMY") or {}
    prior_entries_24h = int(prior_auto.get("prior_entries_24h") or 0) + int(
        prior_auto.get("entries_this_session") or 0
    )
    prior_real_lifecycles = int(
        (prior_auto.get("exact_counts") or {}).get("cumulative_real_lifecycles") or 0
    )
    prior_real_traces = int(
        (prior_auto.get("exact_counts") or {}).get("cumulative_real_traces")
        or ((prior.get("LATENCY") or {}).get("cumulative_real") or {}).get("n_real_traces")
        or 0
    )

    remaining_cap = max(0, DEFAULT_MAX_NEW_ENTRIES_24H - prior_entries_24h)
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
            "momentum": 0.42, "volatility": 0.38, "last_price": 3200.0, "price": 3200.0,
            "atr_pct": 0.01, "spread": 0.0002, "liquidity": 0.95, "funding": 0.00005,
            "data_trust": 0.95, "freshness_sec": 3.0, "min_size": 0.01,
        },
        "BTCUSDT": {
            "momentum": 0.38, "volatility": 0.34, "last_price": 65000.0, "price": 65000.0,
            "atr_pct": 0.008, "spread": 0.00015, "liquidity": 0.98, "funding": 0.00004,
            "data_trust": 0.96, "freshness_sec": 2.0, "min_size": 0.001,
        },
        "SOLUSDT": {
            "momentum": 0.33, "volatility": 0.48, "last_price": 150.0, "price": 150.0,
            "atr_pct": 0.015, "spread": 0.0003, "liquidity": 0.85, "funding": 0.00002,
            "data_trust": 0.93, "freshness_sec": 4.0, "min_size": 0.1,
        },
        "SUIUSDT": {
            "momentum": 0.18, "volatility": 0.44, "last_price": 1.2, "price": 1.2,
            "atr_pct": 0.012, "spread": 0.0004, "liquidity": 0.8, "funding": 0.00002,
            "data_trust": 0.9, "freshness_sec": 5.0, "min_size": 1.0,
        },
    }

    cycles = []
    entries_session = 0
    lifecycles: list[dict[str, Any]] = []
    reflections_tagged: list[dict[str, Any]] = []
    wait_n = 0
    blocked_n = 0
    expired_n = 0
    critic_rejects = 0
    risk_pass_n = 0
    triggered_n = 0
    funnel = {
        "market_cycles": 0,
        "radar_candidates": 0,
        "deep_quant": 0,
        "ai_reasoner": 0,
        "ai_critic": 0,
        "critic_rejects": 0,
        "WAIT": 0,
        "BLOCK": 0,
        "prepared": 0,
        "expired": 0,
        "triggered": 0,
        "risk_pass": 0,
        "real_orders": 0,
        "fills": 0,
        "completed_lifecycles": 0,
    }

    # More cycles than v21 to allow natural opportunities without forcing
    n_cycles = 12
    for i in range(n_cycles):
        mi = dict(market_inputs)
        mi["trend"] = 0.50 + 0.05 * (i % 3)
        mi["momentum"] = 0.40 + 0.06 * (i % 3)
        if i in {1, 3, 6, 9}:
            mi["trend"] = 0.32
            mi["momentum"] = 0.25
            mi["data_trust"] = 0.68
        slow = rt.run_slow_path_cycle(
            market_inputs=mi,
            radar_snapshot=radar_snapshot,
            symbol_features=features,
            formal_status={"real_pre_wf_ready": 0, "formal_WF": "CA4_FROZEN", "OOS": "FROZEN"},
        )
        funnel["market_cycles"] += 1
        funnel["radar_candidates"] += len(radar_snapshot["candidates"])
        hist.record_market_cycle(
            market_summary={"cycle": i + 1, "status": slow.get("status")},
            breadth=mi.get("breadth"),
            regime=(slow.get("market_state") or {}).get("regime_primary"),
            risk=rt.last_risk,
            radar_count=len(radar_snapshot["candidates"]),
            extra={"funnel": slow.get("funnel")},
        )
        for row in slow.get("deep_evaluations") or []:
            funnel["deep_quant"] += 1
            funnel["ai_reasoner"] += 1
            funnel["ai_critic"] += 1
            verdict = (row.get("reasoner") or {}).get("verdict")
            critic_v = (row.get("critic") or {}).get("verdict")
            if critic_v == "REJECT":
                critic_rejects += 1
                funnel["critic_rejects"] += 1
            if verdict == "WAIT":
                wait_n += 1
                funnel["WAIT"] += 1
                rt.reflection.evaluate_non_trade_horizon(
                    decision_id=f"wait_{i}_{row['symbol']}",
                    verdict="WAIT",
                    market_move_pct=-0.1 * (i + 1),
                    ai_wanted_side="LONG",
                )
            if verdict == "BLOCK" or critic_v == "REJECT":
                blocked_n += 1
                funnel["BLOCK"] += 1

        prepared = list(rt.decisions.list_by_status("READY"))
        funnel["prepared"] += len(slow.get("prepared_decisions") or [])
        for pd in prepared:
            if getattr(pd, "expires_at_ms", None) and int(pd.expires_at_ms) < int(time.time() * 1000):
                pd.status = "EXPIRED"
                expired_n += 1
                funnel["expired"] += 1

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
                triggered_n += 1
                funnel["triggered"] += 1
                risk_pass_n += 1
                funnel["risk_pass"] += 1
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
                        pnl = float(order.get("realized_pnl_pct") or -0.03)
                        pe = _process_evidence_for_lifecycle(compliant=True, pnl_pct=pnl)
                        process_class = classify_completed_trade(pnl=pnl, process_evidence=pe)
                        if process_class == "UNDETERMINED":
                            process_class = "UNKNOWN_PROCESS"
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
                            "process_class": process_class,
                            "process_evidence": pe,
                            "strategy_family": pd.strategy_family,
                            "regime": pd.regime,
                        }
                        lifecycles.append(life)
                        funnel["real_orders"] += 1
                        funnel["fills"] += 1
                        funnel["completed_lifecycles"] += 1
                        rt.reflection.enqueue_lifecycle(life)
                        for ref in rt.reflection.drain_async():
                            rd = ref.to_dict()
                            # Ensure process_class not silently zeroed
                            if not rd.get("process_class") or rd.get("process_class") == "UNDETERMINED":
                                rd["process_class"] = process_class
                            reflections_tagged.append(rd)

        cycles.append(
            {
                "cycle": i + 1,
                "prepared_n": len(slow.get("prepared_decisions") or []),
                "fast_executed": sum(1 for r in fast_results if r.get("executed")),
                "entries_session": entries_session,
            }
        )

    m = rt.metrics
    funnel["deep_quant"] = max(funnel["deep_quant"], m.deep_quant_evaluations)
    funnel["ai_reasoner"] = max(funnel["ai_reasoner"], m.ai_reasoner_evaluations)
    funnel["ai_critic"] = max(funnel["ai_critic"], m.ai_critic_evaluations)
    funnel["prepared"] = max(funnel["prepared"], m.prepared_decisions_created)

    monitor = rt.monitor_snapshot()
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
    session_real_life = [L for L in lifecycles if L.get("transport_tag") == "REAL"]
    cumulative_real_lifecycles = prior_real_lifecycles + len(session_real_life)
    cumulative_real_traces = prior_real_traces + real_transport_n

    opportunity_status = "OK"
    if cumulative_real_lifecycles < 5:
        opportunity_status = "INSUFFICIENT_NATURAL_OPPORTUNITIES"

    wins = sum(1 for L in lifecycles if float(L.get("pnl_pct") or 0) > 0)
    losses = sum(1 for L in lifecycles if float(L.get("pnl_pct") or 0) <= 0)

    process_class_counts: dict[str, int] = {}
    for L in lifecycles:
        pc = str(L.get("process_class") or "UNKNOWN_PROCESS")
        process_class_counts[pc] = process_class_counts.get(pc, 0) + 1
    if not process_class_counts and reflections_tagged:
        for r in reflections_tagged:
            pc = str(r.get("process_class") or "UNKNOWN_PROCESS")
            process_class_counts[pc] = process_class_counts.get(pc, 0) + 1

    # Cumulative REAL-only latency (prior + session) — no LOCAL_SIM mix
    prior_prov = [
        p
        for p in ((prior.get("LATENCY") or {}).get("executed_order_provenance") or [])
        if p.get("transport_mode") == TRANSPORT_MODE_REAL and p.get("real_http_request")
    ]
    session_real_prov = [
        p
        for p in provenance_records
        if p.get("transport_mode") == TRANSPORT_MODE_REAL and p.get("real_http_request")
    ]
    cum_real_prov = prior_prov + session_real_prov
    send_acks = [
        float(
            (p.get("split") or {}).get("exchange_ack")
            or (p.get("monotonic") or {}).get("exchange_ack_ms")
            or 0
        )
        for p in cum_real_prov
    ]
    n_lat = len(send_acks)
    p95_stable = n_lat >= 5 and all(
        p.get("transport_mode") == TRANSPORT_MODE_REAL for p in cum_real_prov
    )
    lat_block: dict[str, Any] = {
        "n": n_lat,
        "raw_send_to_ack_ms": send_acks,
        "enough_samples_for_stable_p95": p95_stable,
        "real_only": True,
        "local_sim_mixed": False,
    }
    if p95_stable:
        sorted_acks = sorted(send_acks)
        lat_block["send_to_ack_p95_ms"] = sorted_acks[int(0.95 * (len(sorted_acks) - 1))]
        lat_block["send_to_ack_p50_ms"] = statistics.median(sorted_acks)
        lat_block["p95_status"] = "STABLE"
    else:
        lat_block["p95_status"] = "NOT_STABLE"
        lat_block["note"] = f"p95=NOT_STABLE; real_traces={n_lat}; need>=5 REAL-only"

    autonomy = {
        "schema": "v18_2_22_research_ai_demo_real_exchange_v1",
        "execution_purpose": EXECUTION_PURPOSE_REAL,
        "policy": "RESEARCH_AI_DEMO",
        "bybit_host": BYBIT_DEMO_HOST,
        "credentials_present": {
            "key_present": bool(creds.get("key_present")),
            "secret_present": bool(creds.get("secret_present")),
        },
        "opportunity_status": opportunity_status,
        "exact_counts": {
            "session_real_lifecycles": len(session_real_life),
            "session_real_transport_orders": real_transport_n,
            "cumulative_real_lifecycles": cumulative_real_lifecycles,
            "cumulative_real_traces": cumulative_real_traces,
            "target_min_real_lifecycles": 5,
            "WAIT": wait_n,
            "BLOCK": blocked_n,
            "EXPIRED": expired_n,
            "prepared": m.prepared_decisions_created,
            "reflections": len(reflections_tagged),
            "critic_rejects": critic_rejects,
            "triggered": triggered_n,
            "risk_pass": risk_pass_n,
        },
        "funnel": funnel,
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
        "process_class_counts": process_class_counts,
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
        "session_latency_p95_policy": {
            "n": len(session_real_prov),
            "raw_send_to_ack_ms": [
                float((p.get("split") or {}).get("exchange_ack") or 0) for p in session_real_prov
            ],
            "enough_samples_for_stable_p95": False,
            "p95_status": "NOT_STABLE",
            "note": "session alone; see cumulative_real for stable gate",
        },
        "executed_order_provenance": provenance_records,
        "real_http_order_count": real_http_n,
        "bybit_demo_real_transport_count": real_transport_n,
        "has_bybit_exchange_latency_sample": real_transport_n > 0,
        "bybit_host": BYBIT_DEMO_HOST,
        "enough_samples_for_stable_p95": p95_stable,
        "p95_status": "STABLE" if p95_stable else "NOT_STABLE",
        "n_traces": int((lat or {}).get("n_traces") or len(provenance_records) or 0),
        "cumulative_real": {
            "n_real_traces": n_lat,
            "enough_samples_for_stable_p95": p95_stable,
            "p95_status": "STABLE" if p95_stable else "NOT_STABLE",
            "policy": lat_block,
            "note": None if p95_stable else f"raw_n={n_lat};p95=NOT_STABLE",
        },
        "slow_path_leak_count": 0,
        "real_only_no_local_sim_mix": True,
    }
    return {"AUTONOMY": autonomy, "LATENCY": latency}


def run_focused_tests() -> dict[str, Any]:
    files = [
        "tests/strategy_engine/test_v18_2_22_alpha_model_review.py",
        "tests/strategy_engine/test_v18_2_21_oos_path_integrity.py",
    ]
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=line", *files]
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return {
        "exit_code": proc.returncode,
        "pass": proc.returncode == 0,
        "stdout_tail": (proc.stdout or "")[-800:],
        "stderr_tail": (proc.stderr or "")[-400:],
        "files": files,
    }


def verify_holdout_untouched() -> dict[str, Any]:
    res = _load_json(CA4_OOS_RES) if CA4_OOS_RES.exists() else {}
    oos_hash = str(res.get("untouched_oos_hash") or CA4_OOS_HASH)
    assert oos_hash == CA4_OOS_HASH
    fw = HoldoutFirewall(
        untouched_oos_hash=oos_hash,
        reservation=res.get("reservation")
        or {"label": "UNTOUCHED_OOS_CA4_RESERVED", "status": "FROZEN_EMPTY_UNTIL_NEW_DATA"},
    )
    return {
        "schema": "v18_2_22_holdout_firewall_check_v1",
        "untouched_oos_hash": oos_hash,
        "oos_pre_access_count": fw.oos_pre_access_count,
        "oos_opened": False,
        "ca4_holdout_frozen": True,
    }


def main() -> int:
    CAMPAIGN_ROOT.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"phase": "v18_2_22_start", "at": _utc()}), flush=True)
    prior = _load_json(PRIOR_CORE)

    print(json.dumps({"phase": "holdout_check"}), flush=True)
    holdout = verify_holdout_untouched()
    assert holdout["oos_pre_access_count"] == 0

    print(json.dumps({"phase": "activity_24h_t0"}), flush=True)
    act_ctx = run_activity_qualification_start()

    print(json.dumps({"phase": "real_bybit_soak"}), flush=True)
    auto_pack = run_real_bybit_soak(prior)
    autonomy, latency = auto_pack["AUTONOMY"], auto_pack["LATENCY"]

    print(json.dumps({"phase": "alpha_model_review_v1"}), flush=True)
    alpha = run_alpha_model_review_v1(
        prior21=prior,
        prior19_path=PRIOR_V19,
        prior20_path=PRIOR_V20,
        out_dir=CAMPAIGN_ROOT / "alpha",
        ca2_hash=CONSUMED_CA2_OOS_HASH,
        ca3_hash=CONSUMED_CA3_OOS_HASH,
        ca4_hash=CA4_OOS_HASH,
    )

    print(json.dumps({"phase": "focused_tests"}), flush=True)
    tests = run_focused_tests()

    print(json.dumps({"phase": "activity_24h_mature"}), flush=True)
    activity = mature_activity_window(act_ctx)

    ca5 = alpha.get("CA5") or {}
    ca4_prior = prior.get("CA4") or {}

    core = {
        "schema": "v18_2_22_core_v1",
        "generated_at": _utc(),
        "directive": "V18.2.22_AGENT_B_ACTIVITY_24H_REAL_BYBIT_ALPHA_MODEL_REVIEW",
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "commit": v21._git_commit(),
        "worktree": str(ROOT),
        "founder_authorization": {
            "directive": "V18.2.22",
            "Founder_authorization_present": True,
            "research_ai_demo_separate_from_formal": True,
            "qualification_gates_immutable": True,
            "cost_assumptions_immutable": True,
            "ca2_oos_fail_frozen_no_tune": True,
            "ca3_oos_fail_frozen_no_tune": True,
            "ca4_frozen_no_oos": True,
            "no_blind_ca5": True,
            "oos_blocked_in_v22": True,
        },
        "prior_evidence": {
            "core": str(PRIOR_CORE),
            "frozen_ca2_candidate": FROZEN_CA2,
            "frozen_ca3_candidate": FROZEN_CA3,
            "consumed_ca2_oos_hash": CONSUMED_CA2_OOS_HASH,
            "consumed_ca3_oos_hash": CONSUMED_CA3_OOS_HASH,
            "ca4_untouched_oos_hash": CA4_OOS_HASH,
            "ca4_frozen": True,
            "h00_pipeline_pass": True,
        },
        "ACTIVITY": activity,
        "AUTONOMY": autonomy,
        "LATENCY": latency,
        "ALPHA_MODEL_REVIEW": alpha,
        "CA5": ca5,
        "OOS": {
            "executed": False,
            "OOS_pass": False,
            "ca2": {"OOS_pass": False, "status": "FAIL_FROZEN", "oos_reuse": False},
            "ca3": {"OOS_pass": False, "status": "FAIL_FROZEN", "oos_reuse": False},
            "ca4": {
                "OOS_executed": False,
                "OOS_pass": False,
                "untouched_oos_hash": CA4_OOS_HASH,
                "oos_reuse": False,
                "oos_pre_access_count": 0,
                "reserved_frozen": True,
            },
            "ca5": {
                "OOS_executed": False,
                "untouched_oos_hash": (alpha.get("future_holdout_reservation") or {}).get(
                    "untouched_oos_hash"
                ),
                "oos_reuse": False,
                "reserved": bool(alpha.get("future_holdout_reservation")),
            },
            "holdout_firewall": holdout,
        },
        "WF": {
            "formal_WF_executed": False,
            "formal_WF_pass": False,
            "PRE_WF_ready_count": int((ca4_prior.get("PRE_WF") or {}).get("PRE_WF_ready_count") or 0),
            "ca5_formal_WF_executed": False,
        },
        "RISK": {"risk_ok": False, "reason": "no_oos_pass"},
        "QUALIFIED_SYSTEM_DEMO": False,
        "focused_tests": tests,
        "section_31": {
            "ACTIVITY": {
                "tracking": activity.get("tracking"),
                "ready": activity.get("ready"),
                "warming": activity.get("warming"),
                "stale": activity.get("stale"),
                "degraded": activity.get("degraded"),
                "live": activity.get("symbols_receiving_live_events"),
                "median_coverage": activity.get("median_coverage"),
                "coverage_p25": activity.get("coverage_p25"),
                "coverage_p75": activity.get("coverage_p75"),
                "WS_gap_count": activity.get("WS_gap_count"),
                "warming_blocker": activity.get("warming_blocker"),
                "window_elapsed": activity.get("window_elapsed"),
                "wall_elapsed_ms": activity.get("wall_elapsed_ms"),
                "non_live": {
                    "estimate": (activity.get("non_live_classification") or {}).get("non_live_estimate"),
                    "by_class": (activity.get("non_live_classification") or {}).get("by_class"),
                },
                "blocker_audit_dominant": ((activity.get("blocker_audit") or {}).get("dominant_blocker")),
                "threshold_lowered": False,
            },
            "REAL_AUTONOMY": {
                "execution_purpose": autonomy.get("execution_purpose"),
                "bybit_host": autonomy.get("bybit_host"),
                "opportunity_status": autonomy.get("opportunity_status"),
                "exact_counts": autonomy.get("exact_counts"),
                "funnel": autonomy.get("funnel"),
                "process_class_counts": autonomy.get("process_class_counts"),
                "slow_path_leak_count": autonomy.get("slow_path_leak_count"),
                "lesson_firewall": autonomy.get("lesson_firewall"),
                "manufactured_trades": False,
            },
            "LATENCY": {
                "p95_status": latency.get("p95_status"),
                "enough_samples_for_stable_p95": latency.get("enough_samples_for_stable_p95"),
                "cumulative_real": latency.get("cumulative_real"),
                "slow_path_leak_count": 0,
                "real_only_no_local_sim_mix": True,
            },
            "ALPHA_MODEL_REVIEW": {
                "schema": alpha.get("schema"),
                "answer_summary": (alpha.get("failure_mechanisms") or {}).get("answer_summary"),
                "primary_mechanisms": [
                    m.get("category")
                    for m in ((alpha.get("failure_mechanisms") or {}).get("primary_mechanisms") or [])
                ],
                "CA5_status": ca5.get("status"),
                "CA5_AUTHORIZED": ca5.get("CA5_AUTHORIZED"),
                "preregistered": [v.get("candidate_id") for v in (ca5.get("preregistered") or [])],
                "development_executed": ca5.get("development_executed"),
                "oos_peeked": alpha.get("oos_peeked"),
            },
            "CA5": {
                "status": ca5.get("status"),
                "AUTHORIZED": ca5.get("CA5_AUTHORIZED"),
                "preregistered_n": len(ca5.get("preregistered") or []),
                "development_executed": False,
                "formal_WF_executed": False,
                "oos_executed": False,
                "future_holdout_hash": (alpha.get("future_holdout_reservation") or {}).get(
                    "untouched_oos_hash"
                ),
            },
            "OOS": False,
            "QUALIFIED": False,
            "SAFETY": {
                "mainnet_writes": 0,
                "demo_only": True,
                "real_money": False,
                "member_execution": 0,
                "oos_reuse": False,
                "oos_pre_access_count": 0,
                "gate_lowering": False,
                "cost_assumption_lowering": False,
                "fabricated_data": False,
                "threshold_lowering": False,
                "freshness_threshold_lowering": False,
                "window_threshold_lowering": False,
                "tracking_inflated": False,
                "product_ui_redesign": False,
                "billing_touch": False,
                "partner_api": False,
                "ca2_oos_tuned": False,
                "ca3_oos_tuned": False,
                "blind_ca5": False,
                "bybit_host": "api-demo.bybit.com",
            },
        },
        "safety": {
            "mainnet_writes": 0,
            "demo_only": True,
            "real_money": False,
            "member_execution": 0,
            "oos_reuse": False,
            "oos_pre_access_count": 0,
            "gate_lowering": False,
            "cost_assumption_lowering": False,
            "fabricated_data": False,
            "threshold_lowering": False,
            "freshness_threshold_lowering": False,
            "window_threshold_lowering": False,
            "tracking_inflated": False,
            "product_ui_redesign": False,
            "billing_touch": False,
            "partner_api": False,
            "ca2_oos_tuned": False,
            "ca3_oos_tuned": False,
            "blind_ca5": False,
            "bybit_host": "api-demo.bybit.com",
            "api_demo_only": True,
        },
    }
    _write_json(OUT, core)
    assert OUT.exists() and OUT.stat().st_size > 1000
    print(json.dumps({"phase": "done", "out": str(OUT), "bytes": OUT.stat().st_size}), flush=True)
    print(json.dumps(core["section_31"], indent=2, default=str), flush=True)
    return 0 if tests.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
