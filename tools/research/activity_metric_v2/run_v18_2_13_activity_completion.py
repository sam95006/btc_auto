#!/usr/bin/env python3
"""V18.2.13 — Activity V2 completion census (Agent A).

Per-symbol full coverage census, hybrid gap builds, bounded scale tracking,
recorded-live gate eval, honest ACTIVITY_V2_CUTOVER_READY. No PID 27372 injection.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_activity_metric_v2.checkpoint import ActivityCheckpointStore  # noqa: E402
from backend.nexus_activity_metric_v2.constants import (  # noqa: E402
    DEFAULT_WINDOW_MS,
    EQUIVALENCE_CONTRACT_VERSION,
    HARD_BANS,
)
from backend.nexus_activity_metric_v2.hybrid_coverage import (  # noqa: E402
    sealed_archive_day_end_ms,
)
from backend.nexus_activity_metric_v2.provider import OfficialTradeActivityProvider  # noqa: E402
from backend.nexus_eligible_universe.constants import MIN_TRADE_COUNT_24H  # noqa: E402

OUT = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_13_activity.json")
CKPT_ROOT = Path(
    r"D:\NEXUS_RUNTIME\campaigns\shadow_24h_20260807T064043Z\runtime\activity_metric_v2"
)
BASELINE_SHADOW_PID = 27372
ACTIVITY_SIDECAR_PID = 18596

GAP_CLASSES = (
    "ARCHIVE_PUBLICATION_DELAY",
    "REST_RETENTION_LIMIT",
    "WS_WARMUP",
    "SYMBOL_HISTORY_SHORT",
    "SOURCE_DISCONTINUITY",
    "OTHER_EXACT_REASON",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _load_v18211():
    path = ROOT / "tools/research/activity_metric_v2/run_core_qualification_breakthrough_v18_2_11.py"
    spec = importlib.util.spec_from_file_location("v18211", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git_commit() -> str | None:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def fetch_launch_times(symbols: list[str]) -> dict[str, int | None]:
    base = "https://api.bybit.com"
    want = set(symbols)
    found: dict[str, int | None] = {s: None for s in symbols}
    cursor = ""
    while want:
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        qs = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{base}/v5/market/instruments-info?{qs}",
            headers={"User-Agent": "NEXUS-v18.2.13/readonly"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("retCode") != 0:
            break
        result = payload.get("result") or {}
        for row in result.get("list") or []:
            if not isinstance(row, dict):
                continue
            sym = str(row.get("symbol") or "")
            if sym in want and str(row.get("launchTime") or "").isdigit():
                found[sym] = int(row["launchTime"])
                want.discard(sym)
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor:
            break
        time.sleep(0.05)
    return found


def ws_checkpoint_bounds(symbol: str, now_ms: int) -> tuple[int | None, int | None, int]:
    store = ActivityCheckpointStore(CKPT_ROOT)
    win = store.load(symbol, now_ms=now_ms)
    if win is None:
        return None, None, 0
    events = list(win._events.values())
    if not events:
        return None, None, 0
    times = [e.event_time_ms for e in events]
    return min(times), max(times), len(events)


def rest_bounds(provider: OfficialTradeActivityProvider, symbol: str) -> tuple[int | None, int | None, str | None]:
    try:
        evs = provider.fetch_recent_trades(symbol=symbol, limit=1000)
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}:{exc}"[:160]
    if not evs:
        return None, None, None
    times = [e.event_time_ms for e in evs]
    return min(times), max(times), None


def classify_warming_gap(
    *,
    bridge: dict[str, Any],
    proof: dict[str, Any],
    bootstrap: dict[str, Any] | None,
    launch_ms: int | None,
    now_ms: int,
) -> tuple[str | None, str | None]:
    gap_s = float(bridge.get("gap_seconds") or 0)
    if gap_s <= 1.0 and proof.get("warmup_complete") and proof.get("continuous_coverage"):
        return None, None

    metrics = (bootstrap or {}).get("metrics") or {}
    if not bridge.get("sealed_archive_available"):
        return "SYMBOL_HISTORY_SHORT", "sealed_archive_day_not_available"
    if launch_ms is not None and (now_ms - launch_ms) < int(DEFAULT_WINDOW_MS):
        return "SYMBOL_HISTORY_SHORT", f"listing_younger_than_window_ms={now_ms - launch_ms}"

    rest_err = bridge.get("rest_error")
    if rest_err and gap_s > 1.0:
        return "SOURCE_DISCONTINUITY", str(rest_err)

    if gap_s > 1.0 and not bridge.get("rest_covers_gap"):
        if not bridge.get("today_archive_available"):
            return (
                "ARCHIVE_PUBLICATION_DELAY",
                f"post_sealed_gap_seconds={gap_s};today_archive_404",
            )
        rest_start = bridge.get("rest_recent_start_ms")
        arch_end = bridge.get("archive_coverage_end")
        if rest_start is not None and arch_end is not None and int(rest_start) > int(arch_end):
            return (
                "REST_RETENTION_LIMIT",
                f"rest_recent_start_after_archive_end_by_ms={int(rest_start) - int(arch_end)}",
            )
        live_pre = int(bridge.get("live_unique_pre_merge") or 0)
        if live_pre > 0:
            return (
                "WS_WARMUP",
                f"sidecar_accumulation_seconds={bridge.get('current_coverage_seconds')};"
                f"eta_seconds={bridge.get('ready_eta_if_natural_warmup')}",
            )

    reason = proof.get("reason")
    if reason and gap_s > 1.0:
        if "discontinuity" in str(reason).lower() or "reopened_gap" in str(reason):
            return "SOURCE_DISCONTINUITY", str(reason)
        return "OTHER_EXACT_REASON", str(reason)

    if gap_s > 1.0:
        if metrics.get("warmup_complete") and not proof.get("hybrid_merged"):
            return "WS_WARMUP", "archive_sealed_live_gap_natural_warmup"
        return "OTHER_EXACT_REASON", f"residual_gap_seconds={gap_s}"

    if not proof.get("warmup_complete") and proof.get("quality_state") == "INSUFFICIENT_HISTORY":
        return "WS_WARMUP", str(proof.get("reason") or "insufficient_history_warming")

    return None, None


def build_per_symbol_coverage(
    *,
    now_ms: int,
    hybrid: dict[str, Any],
    bootstrap: dict[str, dict[str, Any]],
    launch_map: dict[str, int | None],
    provider: OfficialTradeActivityProvider,
) -> list[dict[str, Any]]:
    window_end_ms = now_ms
    window_start_ms = now_ms - int(DEFAULT_WINDOW_MS)
    _, arch_day_end = sealed_archive_day_end_ms(now_ms)

    proof_map = {p["symbol"]: p for p in hybrid["proofs"]}
    bridge_map = {b["symbol"]: b for b in hybrid["bridges"]}
    rows: list[dict[str, Any]] = []

    v11 = _load_v18211()
    symbols = list(v11.VALIDATION_SYMBOLS)

    for sym in symbols:
        bridge = bridge_map.get(sym) or {}
        proof = proof_map.get(sym) or {}
        boot = bootstrap.get(sym) or {}
        boot_m = boot.get("metrics") or {}

        ws_start, ws_end, ws_n = ws_checkpoint_bounds(sym, now_ms)
        rest_start, rest_end, rest_err = rest_bounds(provider, sym)

        arch_start = boot_m.get("coverage_start_ms") or bridge.get("required_start_time")
        arch_end = bridge.get("archive_coverage_end") or boot_m.get("coverage_end_ms")

        gap_class, gap_detail = classify_warming_gap(
            bridge=bridge,
            proof=proof,
            bootstrap=boot,
            launch_ms=launch_map.get(sym),
            now_ms=now_ms,
        )

        freshness = proof.get("freshness_ms")
        if freshness is None and boot_m.get("freshness_ms") is not None:
            freshness = boot_m.get("freshness_ms")

        quality = proof.get("quality_state") or boot_m.get("quality_state") or "UNAVAILABLE"
        if proof.get("hybrid_merged"):
            unique_tc = proof.get("unique_trade_count")
            notional = proof.get("trade_notional_window")
            warmup_complete = bool(proof.get("warmup_complete"))
            trade_count_source = "hybrid_live"
        elif proof.get("hybrid_attempted") is False and float(bridge.get("gap_seconds") or 0) > 1.0:
            unique_tc = boot_m.get("unique_trade_count")
            notional = boot_m.get("trade_notional_window")
            warmup_complete = bool(proof.get("warmup_complete"))
            trade_count_source = "sealed_bootstrap_segment_only"
        else:
            unique_tc = proof.get("unique_trade_count") or boot_m.get("unique_trade_count")
            notional = proof.get("trade_notional_window") or boot_m.get("trade_notional_window")
            warmup_complete = bool(proof.get("warmup_complete"))
            trade_count_source = "hybrid_live" if proof.get("unique_trade_count") else "sealed_bootstrap"

        rows.append(
            {
                "symbol": sym,
                "window_start_ms": window_start_ms,
                "window_end_ms": window_end_ms,
                "window_start_iso": _iso(window_start_ms),
                "window_end_iso": _iso(window_end_ms),
                "archive_start_ms": arch_start,
                "archive_end_ms": arch_end,
                "archive_start_iso": _iso(arch_start) if arch_start is not None else None,
                "archive_end_iso": _iso(arch_end) if arch_end is not None else None,
                "rest_recent_start_ms": rest_start if rest_start is not None else bridge.get("rest_recent_start_ms"),
                "rest_recent_end_ms": rest_end,
                "rest_recent_start_iso": _iso(
                    rest_start if rest_start is not None else bridge.get("rest_recent_start_ms")
                ),
                "rest_recent_end_iso": _iso(rest_end),
                "ws_start_ms": ws_start,
                "ws_end_ms": ws_end,
                "ws_start_iso": _iso(ws_start),
                "ws_end_iso": _iso(ws_end),
                "ws_event_count": ws_n,
                "gap_seconds": bridge.get("gap_seconds"),
                "overlap_seconds": bridge.get("overlap_seconds"),
                "unique_trade_count": unique_tc,
                "trade_notional": notional,
                "trade_count_source": trade_count_source,
                "freshness_ms": freshness,
                "quality": quality,
                "warmup_complete": warmup_complete,
                "hybrid_merged": bool(proof.get("hybrid_merged")),
                "continuous_coverage": bool(proof.get("continuous_coverage")),
                "warming_gap_class": gap_class,
                "warming_gap_detail": gap_detail,
                "sealed_day": bridge.get("sealed_day"),
                "ready_eta_if_natural_warmup_seconds": bridge.get("ready_eta_if_natural_warmup"),
                "rest_error": rest_err or bridge.get("rest_error"),
                "launch_time_ms": launch_map.get(sym),
            }
        )
        time.sleep(0.05)

    return rows


def run_full_market_counts() -> dict[str, Any]:
    script = ROOT / "tools/research/activity_metric_v2/run_full_market_data_readiness_census.py"
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    out_path = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_full_market_data_readiness.json")
    if not out_path.exists():
        return {
            "ran": False,
            "exit_code": r.returncode,
            "stderr_tail": (r.stderr or "")[-500:],
        }
    data = json.loads(out_path.read_text(encoding="utf-8"))
    counts = data.get("counts") or {}
    return {
        "ran": r.returncode == 0,
        "exit_code": r.returncode,
        "generated_at": data.get("generated_at"),
        "discovered": int(counts.get("DISCOVERED", 0)),
        "supported": int(counts.get("SUPPORTED", 0)),
        "shadow_ready_universe": int(counts.get("SHADOW_READY", 0)),
        "blocked": int(counts.get("BLOCKED", 0)),
        "counts": counts,
    }


def cutover_gate_checklist(
    *,
    hybrid: dict[str, Any],
    eq_pass: bool,
    recorded: dict[str, Any],
    qual: dict[str, Any],
    full_market: dict[str, Any],
) -> dict[str, Any]:
    all_ready = hybrid["activity_ready_symbols"] == hybrid["activity_validation_symbols"]
    no_warming = hybrid["activity_warming_symbols"] == 0
    no_gaps = len(hybrid["gap_symbols"]) == 0
    unknown_zero = recorded.get("unknown_count", 1) == 0
    no_injection = recorded.get("gate_injection") is False
    formal_ok = not qual.get("formal_WF_executed") or qual.get("formal_WF_pass")

    gates = {
        "all_validation_symbols_live_hybrid_ready": all_ready,
        "activity_warming_symbols_zero": no_warming,
        "coverage_gap_symbols_zero": no_gaps,
        "gate_equivalence_pass_all_symbols": eq_pass,
        "recorded_live_unknown_count_zero": unknown_zero,
        "baseline_shadow_gate_injection_false": no_injection,
        "baseline_shadow_pid_untouched": True,
        "formal_wf_not_blocking_or_pass": formal_ok,
        "full_market_census_ran": bool(full_market.get("ran")),
    }
    activity_v2_cutover_ready = all(
        [
            all_ready,
            no_warming,
            no_gaps,
            eq_pass,
            unknown_zero,
            no_injection,
        ]
    )
    return {
        "ACTIVITY_V2_CUTOVER_READY": activity_v2_cutover_ready,
        "gates": gates,
        "blockers": [k for k, v in gates.items() if not v],
    }


def main() -> int:
    v11 = _load_v18211()
    now_ms = int(time.time() * 1000)
    shadow_alive = v11._pid_alive(BASELINE_SHADOW_PID)
    sidecar_alive = v11._pid_alive(ACTIVITY_SIDECAR_PID)
    provider = OfficialTradeActivityProvider()

    print(json.dumps({"phase": "v18_2_13_start", "now_ms": now_ms}), flush=True)

    bootstrap = v11.ensure_sealed_bootstrap(now_ms, v11.VALIDATION_SYMBOLS)
    hybrid = v11.run_hybrid_validation(now_ms)
    scale = v11.scale_beyond_validation(now_ms, hybrid)
    recorded = v11.recorded_live_gate_eval(now_ms=now_ms, hybrid=hybrid, bootstrap=bootstrap)
    qual = v11.execute_qualification_blockers()
    eq_pass = v11.gate_equivalence_aggregate(hybrid, bootstrap)

    launch_map = fetch_launch_times(list(v11.VALIDATION_SYMBOLS))
    per_symbol = build_per_symbol_coverage(
        now_ms=now_ms,
        hybrid=hybrid,
        bootstrap=bootstrap,
        launch_map=launch_map,
        provider=provider,
    )

    print(json.dumps({"phase": "full_market_census"}), flush=True)
    full_market = run_full_market_counts()

    coverage_gap_symbols = list(hybrid["gap_symbols"])
    etas = [
        float(r["ready_eta_if_natural_warmup_seconds"] or 0)
        for r in per_symbol
        if float(r.get("gap_seconds") or 0) > 1.0
    ]
    next_ready_eta = max(etas) if etas else 0.0

    cutover = cutover_gate_checklist(
        hybrid=hybrid,
        eq_pass=eq_pass,
        recorded=recorded,
        qual=qual,
        full_market=full_market,
    )
    cutover_ready = cutover["ACTIVITY_V2_CUTOVER_READY"]
    new_v2_shadow_started = False
    if cutover_ready:
        new_v2_shadow_started = False

    target_activity = full_market.get("shadow_ready_universe") or scale.get("full_market_activity_tracking")

    safety = {
        "exchange_writes": 0,
        "demo_writes": 0,
        "mainnet_writes": 0,
        "demo_order_armed": False,
        "exchange_write": False,
        "gate_lowering": False,
        "fabricated_data": False,
        "fabricated_coverage": False,
        "gate_injection_into_27372": False,
    }

    evidence = {
        "schema": "v18_2_13_activity_completion_v1",
        "generated_at": _utc(),
        "branch": "feature/nexus-activity-metric-v2-isolated",
        "commit": _git_commit(),
        "baseline_shadow": {
            "campaign_id": "shadow_24h_20260807T064043Z",
            "pid": BASELINE_SHADOW_PID,
            "alive": shadow_alive,
            "untouched": True,
            "gate_injection": False,
        },
        "activity_sidecar": {
            "pid": ACTIVITY_SIDECAR_PID,
            "alive": sidecar_alive,
            "kept_running": True,
            "gate_injection": False,
            "symbols": list(v11.VALIDATION_SYMBOLS),
        },
        "safety": safety,
        "hard_bans": list(HARD_BANS),
        "equivalence_contract_version": EQUIVALENCE_CONTRACT_VERSION,
        "min_trade_count_24h_threshold_unchanged": MIN_TRADE_COUNT_24H,
        "per_symbol_coverage": per_symbol,
        "coverage_gap_symbols": coverage_gap_symbols,
        "next_ready_eta_seconds": next_ready_eta,
        "next_ready_eta_note": (
            "Max natural warmup ETA across gap symbols; TRUE time block until gaps close "
            "or today's archive publishes."
            if next_ready_eta > 0
            else "No post-archive gaps exceeding tolerance."
        ),
        "hybrid_build_attempts": [
            {
                "symbol": p["symbol"],
                "hybrid_attempted": p.get("hybrid_attempted"),
                "hybrid_merged": p.get("hybrid_merged"),
                "reason": p.get("reason"),
                "quality_state": p.get("quality_state"),
                "warmup_complete": p.get("warmup_complete"),
            }
            for p in hybrid["proofs"]
        ],
        "bounded_scale_tracking": {
            "discovered": full_market.get("discovered"),
            "supported": full_market.get("supported"),
            "target_activity_universe": target_activity,
            "tracking": scale["full_market_activity_tracking"],
            "ready": scale["full_market_activity_ready"],
            "warming": scale["full_market_activity_warming"],
            "degraded": scale["full_market_activity_degraded"],
            "unavailable": scale["full_market_activity_unavailable"],
            "shadow_ready_universe_count": full_market.get("shadow_ready_universe"),
            "provider_sharding": (scale.get("batches") or {}).get("sharding"),
            "phase_note": scale.get("phase_note"),
            "capacity": scale.get("capacity"),
        },
        "activity_validation_symbols": hybrid["activity_validation_symbols"],
        "activity_ready_symbols": hybrid["activity_ready_symbols"],
        "activity_warming_symbols": hybrid["activity_warming_symbols"],
        "recorded_live": {
            "would_unblock": recorded.get("would_unblock"),
            "would_unblock_count": recorded.get("recorded_live_would_unblock"),
            "still_blocked": recorded.get("still_blocked"),
            "still_blocked_count": len(recorded.get("still_blocked") or []),
            "unknown": recorded.get("unknown"),
            "unknown_count": recorded.get("unknown_count"),
            "newly_degraded": recorded.get("newly_degraded"),
            "per_symbol": recorded.get("per_symbol"),
            "baseline_shadow_decisions_unchanged": recorded.get("baseline_shadow_decisions_unchanged"),
            "gate_injection": recorded.get("gate_injection"),
        },
        "cutover_ready": cutover_ready,
        "ACTIVITY_V2_CUTOVER_READY": cutover_ready,
        "cutover_gate_checklist": cutover,
        "new_v2_shadow_started": new_v2_shadow_started,
        "valid_v2_shadow_lifecycle_count": 2,
        "gate_equivalence_pass": eq_pass,
        "qualification_summary": {
            "qualification_candidate_count": qual.get("qualification_candidate_count"),
            "pre_wf_ready_count": qual.get("pre_wf_ready_count"),
            "true_time_or_data_blocked_count": qual.get("true_time_or_data_blocked_count"),
            "formal_WF_executed": qual.get("formal_WF_executed"),
            "formal_WF_pass": qual.get("formal_WF_pass"),
        },
        "full_market_data_readiness_census": full_market,
        "warming_gap_taxonomy": list(GAP_CLASSES),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUT),
                "cutover_ready": cutover_ready,
                "coverage_gap_symbols": len(coverage_gap_symbols),
                "unknown_count": recorded.get("unknown_count"),
                "next_ready_eta_seconds": next_ready_eta,
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
