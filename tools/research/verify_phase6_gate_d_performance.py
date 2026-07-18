#!/usr/bin/env python3
"""Phase 6 Gate D Verification — Performance Service & Soak Framework.

Verifies:
  T01  PERF_SERVICE_IMPORT: performance_service module importable
  T02  PERF_SERVICE_SINGLETON: get_performance_service() returns singleton
  T03  PERF_SUMMARY_SHAPE: summary() returns required keys
  T04  PERF_STREAM_SEPARATION: all 4 streams present and NOT merged
  T05  PERF_STREAM_RESEARCH_ONLY: all stream summaries have researchOnly=true
  T06  PERF_METRICS_INGEST: ingest a closed position and verify metrics update
  T07  PERF_WIN_RATE: win rate computed correctly
  T08  PERF_MAX_DRAWDOWN: drawdown computed from equity curve
  T09  PERF_UNCERTAINTY_LABEL: sample size → uncertainty label mapping
  T10  PERF_PROFIT_FACTOR: profit factor computed correctly
  T11  PERF_BY_SECTOR: by_sector() returns per-stream sector breakdown
  T12  PERF_BY_REGIME: by_regime() returns per-stream regime breakdown
  T13  PERF_BY_SIDE: by_side() returns per-stream side breakdown
  T14  PERF_RISK_BLOCKS: risk_blocks() returns per-stream block metrics
  T15  PERF_CALIBRATION: calibration() returns per-stream calibration
  T16  LIVE_SOAK_IMPORT: live_soak module importable
  T17  LIVE_SOAK_SINGLETON: get_live_soak_framework() returns singleton
  T18  LIVE_SOAK_RUN: smoke_30m runs and produces LiveSoakReport
  T19  LIVE_SOAK_CHECKLIST: report contains all 5 checklist items
  T20  LIVE_SOAK_PHASED_MARKERS: 4 phased markers present (smoke/6h/24h/72h)
  T21  LIVE_SOAK_WALL_CLOCK: wall-clock budget ≤ 60s
  T22  SOAK_NO_PRIVATE_API: no private API refs in soak errors
  T23  PERF_NO_PRIVATE_DATA: performance summary contains no private fields
  T24  STREAMS_NEVER_MERGED: streams in summary are independent dicts

VERDICT=PASS if all pass, VERDICT=FAIL otherwise.

Usage:
  python tools/research/verify_phase6_gate_d_performance.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_PASS = "PASS"
_FAIL = "FAIL"
_SKIP = "SKIP"

_results: list[dict] = []


def _test(name: str, fn) -> dict:
    start = time.time()
    try:
        fn()
        elapsed = time.time() - start
        result = {"test": name, "verdict": _PASS, "elapsedMs": round(elapsed * 1000)}
        print(f"  [PASS] {name}  ({elapsed * 1000:.0f}ms)")
    except Exception as exc:  # noqa: BLE001
        elapsed = time.time() - start
        result = {"test": name, "verdict": _FAIL, "error": str(exc), "elapsedMs": round(elapsed * 1000)}
        print(f"  [FAIL] {name}  ({elapsed * 1000:.0f}ms)")
        print(f"         {exc}")
    _results.append(result)
    return result


# ── T01: Import ────────────────────────────────────────────────────────────────

def t01_import():
    from backend.nexus_research.performance_service import ResearchPerformanceService  # noqa: F401


# ── T02: Singleton ─────────────────────────────────────────────────────────────

def t02_singleton():
    from backend.nexus_research.performance_service import get_performance_service
    a = get_performance_service()
    b = get_performance_service()
    assert a is b, "get_performance_service() must return the same singleton"


# ── T03: Summary shape ────────────────────────────────────────────────────────

def t03_summary_shape():
    from backend.nexus_research.performance_service import get_performance_service
    summary = get_performance_service().summary()
    required = {"ok", "researchOnly", "privateApi", "streams", "streamIds", "generatedAt"}
    missing = required - set(summary.keys())
    assert not missing, f"summary missing keys: {missing}"
    assert summary["ok"] is True
    assert summary["researchOnly"] is True
    assert summary["privateApi"] is False


# ── T04: Stream separation ────────────────────────────────────────────────────

def t04_stream_separation():
    from backend.nexus_research.performance_service import (
        get_performance_service,
        STREAM_LIVE_PAPER, STREAM_SHADOW, STREAM_REPLAY, STREAM_MANUAL_VALIDATION,
    )
    summary = get_performance_service().summary()
    streams = summary["streams"]
    required = {STREAM_LIVE_PAPER, STREAM_SHADOW, STREAM_REPLAY, STREAM_MANUAL_VALIDATION}
    missing = required - set(streams.keys())
    assert not missing, f"missing streams: {missing}"
    # Verify they are separate dict instances
    stream_list = list(streams.values())
    for i, s1 in enumerate(stream_list):
        for j, s2 in enumerate(stream_list):
            if i != j:
                assert s1 is not s2, "stream dicts must be independent"


# ── T05: researchOnly ─────────────────────────────────────────────────────────

def t05_research_only():
    from backend.nexus_research.performance_service import get_performance_service
    summary = get_performance_service().summary()
    for sid, s in summary["streams"].items():
        assert s.get("researchOnly") is True, f"stream {sid} missing researchOnly=true"
        assert s.get("privateApi") is False, f"stream {sid} missing privateApi=false"


# ── T06: Ingest + update ──────────────────────────────────────────────────────

def t06_metrics_ingest():
    from backend.nexus_research.performance_service import StreamMetrics, STREAM_LIVE_PAPER
    sm = StreamMetrics(STREAM_LIVE_PAPER)
    sm.ingest_closed_position(pnl_gross=100.0, fees=5.0, hold_ms=3_600_000.0)
    assert sm.closed_positions == 1
    assert sm.total_fees == 5.0
    assert sm.pnl_gross == 100.0
    assert sm.pnl_net == 95.0  # 100 - 5


# ── T07: Win rate ─────────────────────────────────────────────────────────────

def t07_win_rate():
    from backend.nexus_research.performance_service import StreamMetrics, STREAM_LIVE_PAPER
    sm = StreamMetrics(STREAM_LIVE_PAPER)
    sm.ingest_closed_position(50.0)
    sm.ingest_closed_position(-20.0)
    sm.ingest_closed_position(30.0)
    wr = sm.win_rate
    assert abs(wr - 2 / 3) < 0.001, f"expected win_rate=0.667 got {wr}"


# ── T08: Max drawdown ─────────────────────────────────────────────────────────

def t08_max_drawdown():
    from backend.nexus_research.performance_service import StreamMetrics, STREAM_LIVE_PAPER
    sm = StreamMetrics(STREAM_LIVE_PAPER)
    # Equity curve: 10000 → 10100 → 10050 → 10080 (peak=10100, low=10050 → dd=0.5%)
    sm.equity_curve = [10_000.0, 10_100.0, 10_050.0, 10_080.0]
    dd = sm._max_drawdown()
    assert dd > 0, "expected positive drawdown"
    assert dd < 0.01, f"drawdown too large: {dd:.4f}"


# ── T09: Uncertainty label ─────────────────────────────────────────────────────

def t09_uncertainty_label():
    from backend.nexus_research.performance_service import _uncertainty_label
    assert _uncertainty_label(0) == "INSUFFICIENT"
    assert _uncertainty_label(9) == "INSUFFICIENT"
    assert _uncertainty_label(10) == "LOW"
    assert _uncertainty_label(29) == "LOW"
    assert _uncertainty_label(30) == "MODERATE"
    assert _uncertainty_label(99) == "MODERATE"
    assert _uncertainty_label(100) == "ADEQUATE"


# ── T10: Profit factor ────────────────────────────────────────────────────────

def t10_profit_factor():
    from backend.nexus_research.performance_service import StreamMetrics, STREAM_LIVE_PAPER
    sm = StreamMetrics(STREAM_LIVE_PAPER)
    sm.ingest_closed_position(200.0)
    sm.ingest_closed_position(-100.0)
    pf = sm.profit_factor
    assert abs(pf - 2.0) < 0.001, f"expected PF=2.0 got {pf}"


# ── T11-T15: API methods ──────────────────────────────────────────────────────

def t11_by_sector():
    from backend.nexus_research.performance_service import get_performance_service
    data = get_performance_service().by_sector()
    assert data.get("ok") is True
    assert "bySector" in data
    assert data.get("researchOnly") is True


def t12_by_regime():
    from backend.nexus_research.performance_service import get_performance_service
    data = get_performance_service().by_regime()
    assert data.get("ok") is True
    assert "byRegime" in data


def t13_by_side():
    from backend.nexus_research.performance_service import get_performance_service
    data = get_performance_service().by_side()
    assert data.get("ok") is True
    assert "bySide" in data


def t14_risk_blocks():
    from backend.nexus_research.performance_service import get_performance_service
    data = get_performance_service().risk_blocks()
    assert data.get("ok") is True
    assert "riskBlocks" in data
    for sid, rb in data["riskBlocks"].items():
        assert "blockRate" in rb, f"stream {sid} missing blockRate"
        assert "uncertaintyLabel" in rb


def t15_calibration():
    from backend.nexus_research.performance_service import get_performance_service
    data = get_performance_service().calibration()
    assert data.get("ok") is True
    assert "calibration" in data
    for sid, c in data["calibration"].items():
        assert "winRate" in c, f"stream {sid} missing winRate"
        assert "uncertaintyLabel" in c


# ── T16-T24: Live Soak ────────────────────────────────────────────────────────

def t16_live_soak_import():
    from backend.nexus_research.live_soak import LiveSoakFramework  # noqa: F401


def t17_live_soak_singleton():
    from backend.nexus_research.live_soak import get_live_soak_framework
    a = get_live_soak_framework()
    b = get_live_soak_framework()
    assert a is b, "must return singleton"


def t18_live_soak_run():
    from backend.nexus_research.live_soak import get_live_soak_framework
    fw = get_live_soak_framework()
    report = fw.run_smoke_30m()
    assert report is not None
    d = report.to_dict()
    assert "overallVerdict" in d
    assert "checklist" in d
    assert d.get("researchOnly") is True


def t19_live_soak_checklist():
    from backend.nexus_research.live_soak import (
        get_live_soak_framework,
        CHECK_SIM_STACK_ALIVE, CHECK_RISK_ENGINE_ACTIVE,
        CHECK_LEDGER_CONSISTENT, CHECK_EXIT_POLICIES_FIRE, CHECK_NO_PRIVATE_API,
    )
    fw = get_live_soak_framework()
    reports = fw.list_reports(limit=1)
    assert reports, "expected at least one report after running smoke"
    r = reports[0]
    checklist = r["checklist"]
    for item in [CHECK_SIM_STACK_ALIVE, CHECK_RISK_ENGINE_ACTIVE,
                 CHECK_LEDGER_CONSISTENT, CHECK_EXIT_POLICIES_FIRE, CHECK_NO_PRIVATE_API]:
        assert item in checklist, f"missing checklist item: {item}"


def t20_phased_markers():
    from backend.nexus_research.live_soak import get_live_soak_framework
    status = get_live_soak_framework().status()
    markers = status.get("phasedMarkers", {})
    required = {"smoke_30m", "6h", "24h", "72h"}
    missing = required - set(markers.keys())
    assert not missing, f"missing phased markers: {missing}"


def t21_wall_clock_budget():
    from backend.nexus_research.live_soak import get_live_soak_framework
    fw = get_live_soak_framework()
    reports = fw.list_reports(limit=1)
    assert reports, "need at least one report"
    wc = reports[0].get("wallClockMs", 0)
    assert wc <= 60_000, f"wall-clock {wc}ms exceeds 60s budget"


def t22_no_private_api():
    from backend.nexus_research.live_soak import get_live_soak_framework
    fw = get_live_soak_framework()
    reports = fw.list_reports(limit=5)
    for r in reports:
        soak = r.get("soakResult", {})
        errors = soak.get("errors", [])
        private_refs = [
            e for e in errors
            if any(kw in str(e).lower() for kw in ("private", "api_key", "secret", "real_order"))
        ]
        assert not private_refs, f"private API refs in errors: {private_refs}"


def t23_no_private_data():
    from backend.nexus_research.performance_service import get_performance_service
    summary = get_performance_service().summary()
    forbidden_keys = {"api_key", "secret", "password", "token", "private_key"}
    raw = str(summary)
    for fk in forbidden_keys:
        assert fk not in raw.lower(), f"private data key found in summary: {fk}"


def t24_streams_never_merged():
    from backend.nexus_research.performance_service import get_performance_service
    summary = get_performance_service().summary()
    streams = summary["streams"]
    # Each stream must have its own 'stream' field matching the key
    for sid, s in streams.items():
        assert s["stream"] == sid, f"stream field mismatch: key={sid} stream={s['stream']}"


# ── Runner ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 6 Gate D — Performance Verification")
    print("=" * 60)

    tests = [
        ("T01_PERF_SERVICE_IMPORT", t01_import),
        ("T02_PERF_SERVICE_SINGLETON", t02_singleton),
        ("T03_PERF_SUMMARY_SHAPE", t03_summary_shape),
        ("T04_PERF_STREAM_SEPARATION", t04_stream_separation),
        ("T05_PERF_STREAM_RESEARCH_ONLY", t05_research_only),
        ("T06_PERF_METRICS_INGEST", t06_metrics_ingest),
        ("T07_PERF_WIN_RATE", t07_win_rate),
        ("T08_PERF_MAX_DRAWDOWN", t08_max_drawdown),
        ("T09_PERF_UNCERTAINTY_LABEL", t09_uncertainty_label),
        ("T10_PERF_PROFIT_FACTOR", t10_profit_factor),
        ("T11_PERF_BY_SECTOR", t11_by_sector),
        ("T12_PERF_BY_REGIME", t12_by_regime),
        ("T13_PERF_BY_SIDE", t13_by_side),
        ("T14_PERF_RISK_BLOCKS", t14_risk_blocks),
        ("T15_PERF_CALIBRATION", t15_calibration),
        ("T16_LIVE_SOAK_IMPORT", t16_live_soak_import),
        ("T17_LIVE_SOAK_SINGLETON", t17_live_soak_singleton),
        ("T18_LIVE_SOAK_RUN", t18_live_soak_run),
        ("T19_LIVE_SOAK_CHECKLIST", t19_live_soak_checklist),
        ("T20_LIVE_SOAK_PHASED_MARKERS", t20_phased_markers),
        ("T21_LIVE_SOAK_WALL_CLOCK", t21_wall_clock_budget),
        ("T22_SOAK_NO_PRIVATE_API", t22_no_private_api),
        ("T23_PERF_NO_PRIVATE_DATA", t23_no_private_data),
        ("T24_STREAMS_NEVER_MERGED", t24_streams_never_merged),
    ]

    for name, fn in tests:
        _test(name, fn)

    print()
    print("=" * 60)
    passes = sum(1 for r in _results if r["verdict"] == _PASS)
    fails = sum(1 for r in _results if r["verdict"] == _FAIL)
    skips = sum(1 for r in _results if r["verdict"] == _SKIP)
    total = len(_results)
    verdict = _PASS if fails == 0 else _FAIL
    print(f"TOTAL={total}  PASS={passes}  FAIL={fails}  SKIP={skips}")
    print(f"VERDICT={verdict}")
    print("=" * 60)

    if fails > 0:
        print("\nFailed tests:")
        for r in _results:
            if r["verdict"] == _FAIL:
                print(f"  {r['test']}: {r.get('error', '')}")

    sys.exit(0 if verdict == _PASS else 1)


if __name__ == "__main__":
    main()
