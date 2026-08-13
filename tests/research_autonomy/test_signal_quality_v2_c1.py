"""Focused tests for Signal Quality V2-C1 Shadow Challenger."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.nexus_research_ai_autonomy.regime_provenance_v1 import (
    MAPPING_VERSION,
    attach_regime_provenance,
)
from backend.nexus_research_ai_autonomy.shadow_v2_challenger_v1 import (
    EVIDENCE_GENERATION,
    build_shadow_v2_challenger_report,
    load_v2_c1_shadow_signals,
    persist_v2_evidence,
    run_v2_c1_shadow_challenger,
)
from backend.nexus_research_ai_autonomy.signal_quality_v2_c1 import (
    CHALLENGER_VERSION,
    EPISODE_WINDOW_SEC,
    FEE_RT,
    materialize_v2_evidence,
    rank_by_score,
    select_v2_c1_for_episode,
)


def _enrichment(*, sym: str = "APRUSDT", ts: int | None = None) -> dict[str, Any]:
    return {
        "symbol": sym,
        "timestamp_ms": ts or int(time.time() * 1000),
        "price": 1.0,
        "turnover": 20_000_000,
        "spread_bps": 3.0,
        "estimated_slippage": 0.0003,
        "activity_score": 0.72,
        "activity_source": "TURNOVER_LOG",
        "activity_fallback": False,
        "momentum_1m": {"return": 0.05, "velocity": 0.02, "acceleration": 0.01},
        "momentum_5m": {"return": 0.12, "velocity": 0.04, "acceleration": 0.02},
        "momentum_15m": {"return": 0.08, "velocity": 0.03, "acceleration": 0.01},
        "volatility": 0.35,
        "open_interest": 1000.0,
        "oi_delta_short": 0.02,
        "funding_rate": 0.0001,
        "data_freshness_ms": 50,
    }


def _regime_info() -> dict[str, Any]:
    return {
        "market_structure": "TREND_UP",
        "regime": "TREND_UP",
        "regime_confidence": 0.7,
    }


def _ranked_row(
    *,
    sym: str,
    ts: int,
    gate_pass: bool = True,
    snapshot_action: str = "WATCH",
) -> dict[str, Any]:
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
        build_evidence_lists,
        compute_entry_quality,
        compute_expected_net_edge,
    )

    enrichment = _enrichment(sym=sym, ts=ts)
    regime_info = _regime_info()
    edge = compute_expected_net_edge(enrichment=enrichment, side="LONG", notional=350.0)
    eq = compute_entry_quality(
        enrichment, side="LONG", structure="TREND_UP", regime="TREND_UP", edge=edge
    )
    support, contradict = build_evidence_lists(
        enrichment, side="LONG", structure="TREND_UP", regime="TREND_UP", edge=edge
    )
    return {
        "symbol": sym,
        "side": "LONG",
        "entry_quality_score": eq.get("entry_quality_score"),
        "expected_net_edge": edge.get("expected_net_edge"),
        "final_action": snapshot_action,
        "snapshot": {
            "final_action": snapshot_action,
            "rank": 1,
            "entry_quality_score": eq.get("entry_quality_score"),
            "expected_net_edge": edge.get("expected_net_edge"),
            "supporting_evidence": support,
            "contradicting_evidence": contradict,
        },
        "enrichment": enrichment,
        "regime_info": regime_info,
        "gate_pass": gate_pass,
        "timestamp_ms": ts,
    }


def test_v1_output_unchanged_with_v2_enabled(tmp_path: Path) -> None:
    """V2 hook must not alter V1 ranking or snapshot fields."""
    from backend.nexus_research_ai_autonomy.signal_quality_cycle_v1 import run_signal_quality_shadow_cycle

    tickers = [{"symbol": "APRUSDT", "last_price": 1.0}, {"symbol": "BTCUSDT", "last_price": 50000.0}]
    market_pack = {"tickers": tickers, "hypotheses_sample": []}
    client = MagicMock()
    client.public_get.return_value = {"result": {"list": []}}

    with patch(
        "backend.nexus_research_ai_autonomy.signal_quality_cycle_v1.enrich_symbol",
        side_effect=lambda _c, symbol=..., ticker_row=..., now_ms=...: _enrichment(sym=str(symbol), ts=now_ms),
    ), patch(
        "backend.nexus_research_ai_autonomy.signal_quality_cycle_v1.evaluate_regime",
        return_value=_regime_info(),
    ), patch(
        "backend.nexus_research_ai_autonomy.signal_quality_cycle_v1.run_v2_c1_shadow_challenger",
        return_value={"v2_evidence_persisted": 0},
    ) as mock_v2:
        result = run_signal_quality_shadow_cycle(
            client=client, market_pack=market_pack, campaign_root_path=tmp_path
        )

    mock_v2.assert_called_once()
    assert result["schema"] == "v30_signal_quality_shadow_cycle_v1"
    assert "v2_challenger" in result
    ranking = result["ranking"]
    assert len(ranking) == 2
    # V1 still ranks by expected_net_edge then entry_quality_score
    edges = [r["expected_net_edge"] for r in ranking]
    assert edges == sorted(edges, reverse=True)


def test_v2_uses_same_pit_snapshot_inputs() -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="AUSDT", ts=ts), _ranked_row(sym="BUSDT", ts=ts)]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    assert sel["episode_window_sec"] == EPISODE_WINDOW_SEC
    assert sel["long_top1"] is not None
    assert sel["long_top1"]["detected_at_ms"] == ts


def test_no_future_fields_in_ranking() -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc_test", now_ms=ts)
    banned = {"MFE", "MAE", "post_cost_hypothetical", "target_before_stop", "stop_before_target"}
    for ev in evidence:
        assert ev.get("no_hindsight") is True
        assert banned.isdisjoint(set(ev.keys()))


def test_max_one_long_top1_per_episode() -> None:
    ts = int(time.time() * 1000)
    rows = [
        _ranked_row(sym=f"SYM{i}USDT", ts=ts) for i in range(5)
    ]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    long_rows = [e for e in evidence if e.get("lane") == "LONG_TOP1"]
    assert len(long_rows) == 1
    assert sel["long_top1"]["v2_rank"] == 1


def test_zero_ready_episode_allowed() -> None:
    ts = int(time.time() * 1000)
    row = _ranked_row(sym="APRUSDT", ts=ts, gate_pass=False)
    sel = select_v2_c1_for_episode([row], campaign_root=Path("/tmp/unused"), now_ms=ts)
    assert sel["long_top1"]["v2_action"] in {"WAIT", "BLOCK", "WATCH"}


def test_short_never_ready_in_v2_c1() -> None:
    ts = int(time.time() * 1000)
    from backend.nexus_research_ai_autonomy.signal_quality_v1 import (
        build_evidence_lists,
        compute_entry_quality,
        compute_expected_net_edge,
    )

    enrichment = _enrichment(sym="SHORTUSDT", ts=ts)
    enrichment["momentum_5m"] = {"return": -0.5, "velocity": -0.2, "acceleration": -0.1}
    enrichment["momentum_15m"] = {"return": -0.4, "velocity": -0.15, "acceleration": -0.05}
    regime_info = {"market_structure": "TREND_DOWN", "regime": "TREND_DOWN", "regime_confidence": 0.9}
    edge = compute_expected_net_edge(enrichment=enrichment, side="SHORT", notional=350.0)
    eq = compute_entry_quality(
        enrichment, side="SHORT", structure="TREND_DOWN", regime="TREND_DOWN", edge=edge
    )
    row = {
        "symbol": "SHORTUSDT",
        "enrichment": enrichment,
        "regime_info": regime_info,
        "gate_pass": True,
        "timestamp_ms": ts,
        "snapshot": {"final_action": "SELECT", "rank": 1, "entry_quality_score": eq.get("entry_quality_score")},
    }
    sel = select_v2_c1_for_episode([row], campaign_root=Path("/tmp/unused"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    short = next(e for e in evidence if e.get("lane") == "SHORT_SHADOW_RESEARCH")
    assert short["action"] != "READY"
    assert short["lane"] == "SHORT_SHADOW_RESEARCH"


def test_short_still_produces_research_evidence() -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    short = [e for e in evidence if e.get("lane") == "SHORT_SHADOW_RESEARCH"]
    assert len(short) == 1
    assert short[0].get("expected_net_edge") is not None
    assert short[0].get("supporting_evidence") is not None


def test_fee_baseline_remains_0_0011() -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    for ev in evidence:
        assert ev.get("fee_baseline_rt") == FEE_RT == 0.0011


def test_expected_edge_not_primary_ranker() -> None:
    ts = int(time.time() * 1000)
    low_edge_high_score = _ranked_row(sym="HIGHUSDT", ts=ts)
    high_edge_low_score = _ranked_row(sym="LOWUSDT", ts=ts)
    # Force score inversion vs edge by patching scores on built rows
    low_edge_high_score["entry_quality_score"] = 0.95
    high_edge_low_score["entry_quality_score"] = 0.1
    pool = [
        {"entry_quality_score": 0.95, "expected_net_edge": 0.01},
        {"entry_quality_score": 0.1, "expected_net_edge": 0.5},
    ]
    ranked = rank_by_score(pool)
    assert ranked[0]["entry_quality_score"] == 0.95
    evidence = materialize_v2_evidence(
        {"episode_id": 1, "episode_started_at_ms": ts, "long_top1": ranked[0], "short_research_top1": None},
        cycle_id="cyc",
        now_ms=ts,
    )
    assert evidence[0]["primary_ranker"] == "SCORE"


def test_calibrated_probability_null() -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    evidence = materialize_v2_evidence(sel, cycle_id="cyc", now_ms=ts)
    for ev in evidence:
        assert ev.get("calibrated_probability") is None
        assert ev.get("calibration_status") == "UNVALIDATED"


def test_regime_provenance_mapping() -> None:
    enrichment = _enrichment()
    prov = attach_regime_provenance(_regime_info(), enrichment=enrichment)
    assert prov["engine_regime"] == "TREND_UP"
    assert prov["market_structure"] == "TREND_UP"
    assert prov["regime"] == prov["engine_regime"]
    assert prov["regime_source"] == "MarketStateEngine"
    assert prov["mapping_version"] == MAPPING_VERSION
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    sel = select_v2_c1_for_episode(rows, campaign_root=Path("/tmp/unused"), now_ms=ts)
    rp = (sel["long_top1"] or {}).get("regime_provenance") or {}
    assert rp.get("engine_regime") is not None
    assert rp.get("mapping_version") == MAPPING_VERSION


def test_post_v2_freeze_evidence_namespace(tmp_path: Path) -> None:
    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    run_v2_c1_shadow_challenger(
        campaign_root=tmp_path, cycle_id="cyc_ns", now_ms=ts, ranked_rows=rows
    )
    loaded = load_v2_c1_shadow_signals(tmp_path)
    assert len(loaded) >= 1
    for row in loaded:
        assert row.get("evidence_generation") == EVIDENCE_GENERATION
        assert row.get("challenger_version") == CHALLENGER_VERSION


def test_v2_outcomes_use_shared_lifecycle(tmp_path: Path) -> None:
    from backend.nexus_research_ai_autonomy.shadow_signal_v1 import load_signal_state

    ts = int(time.time() * 1000)
    rows = [_ranked_row(sym="APRUSDT", ts=ts)]
    run_v2_c1_shadow_challenger(
        campaign_root=tmp_path, cycle_id="cyc_lc", now_ms=ts, ranked_rows=rows
    )
    state = load_signal_state(tmp_path)
    v2 = load_v2_c1_shadow_signals(tmp_path)
    assert v2
    sid = str(v2[0]["signal_id"])
    assert sid in (state.get("signals") or {})


def test_demo_write_remains_false() -> None:
    report = build_shadow_v2_challenger_report(Path("/nonexistent"))
    assert report.get("ready_for_demo_reenable") is False
    assert report.get("promotion_auto_enable") is False
