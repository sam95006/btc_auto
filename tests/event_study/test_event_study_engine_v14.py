"""V14-B Event Study Engine tests — fixtures + forensic RO, blocked real study."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_event_study import (
    ENGINE_STATUS,
    EVENT_DEFINITION_IDS,
    HARD_BANS,
    REAL_EVENT_STUDY_EXECUTION,
    REAL_EVENT_STUDY_STATUS,
    ForensicWriteAttemptError,
    build_synthetic_cohort,
    build_windows,
    classify_missing,
    definition_catalog,
    exclude_overlapping,
    filter_by_completeness,
    forensic_campaign_probe,
    list_definitions,
    multi_horizon_outcomes,
    prove_pit_excludes_future,
    refuse_write,
    run_blocked_fixture_study,
    summarize_groups,
    verify_deterministic_study,
)
from backend.nexus_event_study.adversarial import run_adversarial_pass
from backend.nexus_event_study.bootstrap import bootstrap_mean_ci
from backend.nexus_event_study.fixtures import make_study_event
from backend.nexus_event_study.forensic_ro import scan_owned_paths_for_write_apis
from backend.nexus_event_study.types import StudyEvent


ROOT = Path(__file__).resolve().parents[2]


def test_dual_status_contract() -> None:
    assert ENGINE_STATUS == "ENGINE_READY"
    assert REAL_EVENT_STUDY_STATUS == "REAL_EVENT_STUDY_BLOCKED"
    assert REAL_EVENT_STUDY_EXECUTION is False


def test_hard_bans_remain_false() -> None:
    assert HARD_BANS["pr27_merge"] is False
    assert HARD_BANS["deploy"] is False
    assert HARD_BANS["formal_walk_forward"] is False
    assert HARD_BANS["oos_execution"] is False
    assert HARD_BANS["demo_orders"] is False
    assert HARD_BANS["exchange_write"] is False
    assert HARD_BANS["mainnet"] is False
    assert HARD_BANS["real_money"] is False
    assert HARD_BANS["profitability_claims"] is False
    assert HARD_BANS["real_14d_event_study"] is False
    assert HARD_BANS["auto_integrate"] is False


def test_definition_catalog_complete() -> None:
    cat = definition_catalog()
    assert cat["definition_count"] == len(EVENT_DEFINITION_IDS)
    assert set(cat["event_ids"]) == set(EVENT_DEFINITION_IDS)
    assert cat["predictive_edge_claimed"] is False
    assert cat["real_event_study_execution"] is False
    for d in list_definitions():
        assert d.economic_rationale
        assert d.pre_window_bars > 0
        assert d.post_window_bars > 0
        assert d.control_window_bars > 0
        assert d.missing_policy == "EXCLUDE_WITH_REASON"


def test_synthetic_cohort_deterministic() -> None:
    a = build_synthetic_cohort(seed="det-1")
    b = build_synthetic_cohort(seed="det-1")
    assert a["fixture_checksum"] == b["fixture_checksum"]
    c = build_synthetic_cohort(seed="det-2")
    assert c["fixture_checksum"] != a["fixture_checksum"]


def test_windows_geometry() -> None:
    ev = make_study_event(
        event_id="aggressive_flow_burst",
        symbol="BTCUSDT",
        decision_ts_ms=1_720_000_000_000,
        seq=1,
    )
    wins = build_windows(ev, bar_ms=60_000, pre_bars=8, post_bars=16, control_bars=16)
    assert wins.pre.end_offset_bars == 0
    assert wins.post.start_offset_bars == 0
    assert wins.post.end_offset_bars == 16
    assert wins.control.end_offset_bars == -8
    assert wins.control.start_offset_bars == -24
    assert wins.pre.end_ts_ms == ev.decision_ts_ms
    assert wins.post.start_ts_ms == ev.decision_ts_ms
    # Control never uses future post outcomes
    assert wins.control.end_ts_ms <= wins.pre.start_ts_ms


def test_overlap_exclusion_keeps_earlier() -> None:
    base = 1_720_000_000_000
    a = make_study_event(
        event_id="spread_shock", symbol="BTCUSDT", decision_ts_ms=base, seq=1
    )
    b = make_study_event(
        event_id="spread_shock",
        symbol="BTCUSDT",
        decision_ts_ms=base + 3 * 60_000,
        seq=2,
    )
    result = exclude_overlapping([a, b], exclusion_bars=8)
    assert result["kept_count"] == 1
    assert result["excluded_count"] == 1
    assert result["kept"][0].observation_id == a.observation_id


def test_grouping_by_symbol_regime() -> None:
    cohort = build_synthetic_cohort(seed="group-1", include_future=False, include_incomplete=False)
    events = list(cohort["_events_objs"])
    summary = summarize_groups(events, min_events=1)
    assert summary["total_events"] == len(events)
    assert summary["symbol_groups"]
    assert summary["regime_groups"]


def test_cost_aware_multi_horizon_outcomes() -> None:
    ev = make_study_event(
        event_id="absorption_print",
        symbol="ETHUSDT",
        decision_ts_ms=1_720_000_000_000,
        seq=7,
        side="BUY",
        entry_price=100.0,
    )
    path = [100.0 + i * 0.1 for i in range(40)]
    outs = multi_horizon_outcomes(ev, path, horizons=(1, 4, 8), fee_bps=5.0, slip_bps=1.0)
    assert all(o.available for o in outs)
    for o in outs:
        assert o.cost is not None and o.cost > 0
        assert o.net_return is not None and o.gross_return is not None
        assert o.net_return == pytest.approx(o.gross_return - o.cost)
    short = multi_horizon_outcomes(ev, [100.0, 100.1], horizons=(1, 8))
    assert short[0].available is True
    assert short[1].available is False
    assert short[1].missing_reason == "insufficient_forward_path"


def test_bootstrap_ci_deterministic() -> None:
    values = [0.01, -0.02, 0.015, 0.0, -0.005, 0.008]
    a = bootstrap_mean_ci(values, seed=14, replicates=50, block=2)
    b = bootstrap_mean_ci(values, seed=14, replicates=50, block=2)
    assert a.point == b.point
    assert a.ci_low == b.ci_low
    assert a.ci_high == b.ci_high
    assert a.point is not None


def test_completeness_filter_drops_short_paths() -> None:
    ev = make_study_event(
        event_id="liquidity_withdrawal",
        symbol="SOLUSDT",
        decision_ts_ms=1_720_000_000_000,
        seq=3,
    )
    result = filter_by_completeness(
        [ev],
        {ev.observation_id: [100.0, 100.1]},
        required_horizon=16,
        min_completeness=0.85,
    )
    assert result["kept_count"] == 0
    assert result["dropped_count"] == 1


def test_pit_excludes_future() -> None:
    cohort = build_synthetic_cohort(seed="pit-1")
    events = list(cohort["_events_objs"])
    as_of = int(cohort["base_ts_ms"]) + 800 * 60_000
    proof = prove_pit_excludes_future(events, as_of_ms=as_of)
    assert proof["pit_holds"] is True
    assert proof["future_event_count"] >= 1


def test_missing_event_exclude_with_reason() -> None:
    broken = make_study_event(
        event_id="oi_step_change",
        symbol="BTCUSDT",
        decision_ts_ms=1_720_000_000_000,
        seq=11,
        payload={},
    )
    broken = StudyEvent(
        observation_id=broken.observation_id,
        event_id=broken.event_id,
        symbol=broken.symbol,
        regime=broken.regime,
        decision_ts_ms=broken.decision_ts_ms,
        exchange_ts_ms=broken.exchange_ts_ms,
        receive_ts_ms=broken.receive_ts_ms,
        side=broken.side,
        entry_price=broken.entry_price,
        source=broken.source,
        payload={},
        is_trade=False,
    )
    result = classify_missing([broken])
    assert result["valid_count"] == 0
    assert result["missing_count"] == 1
    assert result["silent_impute"] is False
    assert "missing_required_field" in result["missing"][0]["reasons"]


def test_blocked_fixture_study_and_replay() -> None:
    study = run_blocked_fixture_study(seed="study-1")
    assert study["engine_status"] == "ENGINE_READY"
    assert study["real_event_study_status"] == "REAL_EVENT_STUDY_BLOCKED"
    assert study["real_event_study_execution"] is False
    assert study["profitability_claimed"] is False
    assert study["hold_conditions_satisfied"] is False
    assert study["completeness"]["kept_count"] >= 1
    replay = verify_deterministic_study(seed="study-1")
    assert replay["match"] is True


def test_forensic_ro_probe_and_write_ban() -> None:
    probe = forensic_campaign_probe(ROOT)
    assert probe["mode"] == "READ_ONLY_FORENSIC"
    assert probe["raw_partitions_modified"] is False
    assert probe["write_attempt_count"] == 0
    with pytest.raises(ForensicWriteAttemptError):
        refuse_write(ROOT / "artifacts" / "ban_probe")
    owned = list((ROOT / "backend" / "nexus_event_study").rglob("*.py"))
    scan = scan_owned_paths_for_write_apis(owned)
    assert scan["ok"] is True


def test_adversarial_pass_ok() -> None:
    study = run_blocked_fixture_study(seed="adv-harness")
    pass1 = {
        "pit_holds": study["pit_proof"]["pit_holds"],
        "deterministic_replay": verify_deterministic_study(seed="adv-harness")["match"],
        "real_event_study_execution": False,
    }
    adv = run_adversarial_pass(pass1, repo_root=ROOT)
    assert adv["adversarial_ok"] is True
    assert adv["critical_count"] == 0
    assert adv["high_count"] == 0
