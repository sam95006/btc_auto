"""Tests for Founder V17-D Point-in-Time and Revision Control."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_pit_revision_v17.constants import (
    HARD_BANS,
    LANE,
    TIME_AXES,
)
from backend.nexus_pit_revision_v17.fixtures import DAY, T0, build_revision_catalog
from backend.nexus_pit_revision_v17.hard_bans import (
    MissingAsKnownAtError,
    TodayRevisionForPastBacktestError,
    UnavailableAtTimeError,
    hard_ban_probe_matrix,
    require_as_known_at_in_signature,
    scan_owned_paths_for_banned_claims,
)
from backend.nexus_pit_revision_v17.harness import evaluate_pit_revision_control, run_pit_revision_lab
from backend.nexus_pit_revision_v17.redteam import run_future_leakage_redteam
from backend.nexus_pit_revision_v17.store import (
    PitRevisionStore,
    prove_pit_visibility,
    research_query,
)
from backend.nexus_pit_revision_v17.types import DualTimeStamp, ResearchQuery, RevisionRecord


REPO_ROOT = Path(__file__).resolve().parents[2]


def _store() -> PitRevisionStore:
    s = PitRevisionStore()
    s.ingest_many(build_revision_catalog())
    return s


def test_dual_time_axes_contract() -> None:
    assert TIME_AXES == (
        "event_time",
        "available_time",
        "revision_time",
        "ingest_time",
    )
    assert LANE == "V17-D"


def test_research_query_requires_as_known_at_signature() -> None:
    assert require_as_known_at_in_signature(research_query)


def test_missing_as_known_at_rejected() -> None:
    store = _store()
    with pytest.raises(MissingAsKnownAtError):
        research_query(store, {"series_id": "SYNTH.BTCUSDT.CLOSE"})  # type: ignore[arg-type]
    with pytest.raises(MissingAsKnownAtError):
        research_query(store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=None)


def test_as_known_at_selects_historical_revision_not_today() -> None:
    store = _store()
    past = research_query(
        store,
        series_id="SYNTH.BTCUSDT.CLOSE",
        as_known_at=T0 + 3 * DAY,
    )
    assert past.status == "AVAILABLE"
    assert past.revision_id == "OBS_BTC_CLOSE_R1"
    assert past.value == 42000.0

    mid = research_query(
        store,
        series_id="SYNTH.BTCUSDT.CLOSE",
        as_known_at=T0 + 6 * DAY,
    )
    assert mid.revision_id == "OBS_BTC_CLOSE_R2"
    assert mid.value == 41950.0

    tip = research_query(
        store,
        series_id="SYNTH.BTCUSDT.CLOSE",
        as_known_at=T0 + 40 * DAY,
    )
    assert tip.revision_id == "OBS_BTC_CLOSE_R3_TODAY"


def test_today_revision_banned_for_past_backtest() -> None:
    store = _store()
    with pytest.raises(TodayRevisionForPastBacktestError):
        research_query(
            store,
            ResearchQuery(
                series_id="SYNTH.BTCUSDT.CLOSE",
                as_known_at=T0 + 3 * DAY,
                allow_latest_revision=True,
            ),
        )


def test_revision_lineage() -> None:
    store = _store()
    lineage = store.revision_lineage("OBS_BTC_CLOSE_R3_TODAY")
    ids = [r.revision_id for r in lineage]
    assert ids == [
        "OBS_BTC_CLOSE_R1",
        "OBS_BTC_CLOSE_R2",
        "OBS_BTC_CLOSE_R3_TODAY",
    ]
    mid = research_query(
        store,
        series_id="SYNTH.BTCUSDT.CLOSE",
        as_known_at=T0 + 6 * DAY,
    )
    visible_ids = [r["revision_id"] for r in mid.lineage]
    assert "OBS_BTC_CLOSE_R3_TODAY" not in visible_ids
    assert "OBS_BTC_CLOSE_R2" in visible_ids


def test_late_arriving_unavailable_at_time_guard() -> None:
    store = _store()
    early = research_query(
        store,
        series_id="SYNTH.ETHUSDT.CLOSE",
        as_known_at=T0 + 4 * DAY,
    )
    assert early.status == "UNAVAILABLE_AT_TIME"
    assert early.value is None
    assert early.leakage_blocked is True

    later = research_query(
        store,
        series_id="SYNTH.ETHUSDT.CLOSE",
        as_known_at=T0 + 8 * DAY,
    )
    assert later.status == "AVAILABLE"
    assert later.value == 2200.0


def test_backfill_gated_by_available_time() -> None:
    store = _store()
    before = research_query(
        store,
        series_id="SYNTH.SOLUSDT.CLOSE",
        as_known_at=T0 + 5 * DAY,
    )
    assert before.status == "UNAVAILABLE_AT_TIME"
    after = research_query(
        store,
        series_id="SYNTH.SOLUSDT.CLOSE",
        as_known_at=T0 + 11 * DAY,
    )
    assert after.status == "AVAILABLE"
    assert after.value == 95.5


def test_label_revision() -> None:
    store = _store()
    early = research_query(
        store,
        series_id="SYNTH.BTCUSDT.REGIME_LABEL",
        as_known_at=T0 + 5 * DAY,
        label_name="regime_v1",
    )
    late = research_query(
        store,
        series_id="SYNTH.BTCUSDT.REGIME_LABEL",
        as_known_at=T0 + 15 * DAY,
        label_name="regime_v1",
    )
    assert early.value == "TREND_UP"
    assert late.value == "RANGE"


def test_unavailable_raise_path() -> None:
    store = _store()
    with pytest.raises(UnavailableAtTimeError):
        research_query(
            store,
            series_id="SYNTH.MISSING",
            as_known_at=T0 + 3 * DAY,
            raise_on_unavailable=True,
        )


def test_dual_time_stamp_validation() -> None:
    with pytest.raises(ValueError):
        DualTimeStamp(
            event_time=100,
            available_time=50,
            revision_time=60,
            ingest_time=70,
        ).validate()
    with pytest.raises(ValueError):
        DualTimeStamp(
            event_time=100,
            available_time=100,
            revision_time=120,
            ingest_time=110,
        ).validate()


def test_pit_visibility_proof_holds() -> None:
    store = _store()
    proof = prove_pit_visibility(
        store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=T0 + 3 * DAY
    )
    assert proof["pit_holds"] is True
    assert proof["leaked_revision_ids"] == []
    assert proof["visible_count"] == 1


def test_future_leakage_redteam_zero_survivors() -> None:
    report = run_future_leakage_redteam()
    assert report["attack_count"] >= 10
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["pass"] is True
    for finding in report["findings"]:
        assert finding["survivor"] is False
        assert finding["blocked"] is True


def test_hard_bans_include_founder_constraints() -> None:
    for ban in (
        "no_today_revision_for_past_backtest",
        "no_research_query_without_as_known_at",
        "no_future_leakage",
        "no_acceleration_report_edit",
        "no_exchange_write",
        "no_formal_wf",
        "no_oos_claims",
        "no_pr26_merge",
        "no_pr27_merge",
    ):
        assert ban in HARD_BANS
    probe = hard_ban_probe_matrix()
    assert probe["env_ok"] is True
    assert probe["exchange_write"]["allowed"] is False
    assert probe["report_edit"]["allowed"] is False


def test_banned_claim_scan_clean() -> None:
    result = scan_owned_paths_for_banned_claims(REPO_ROOT)
    assert result["ok"] is True
    assert result["hits"] == []


def test_evaluate_and_lab_pass() -> None:
    summary = evaluate_pit_revision_control(repo_root=REPO_ROOT)
    assert summary["status"] == "PASS"
    assert summary["future_leakage_redteam"]["survivor_count"] == 0
    assert summary["formal_wf_executed"] is False
    assert summary["oos_claimed"] is False
    assert summary["real_market_data"] is False

    lab = run_pit_revision_lab(repo_root=REPO_ROOT)
    assert lab["status"] == "PASS"
    assert lab["survivor_count"] == 0
    art = REPO_ROOT / "artifacts" / "readiness" / "immutable" / "v17_pit_revision"
    assert (art / "pit_revision_summary.json").is_file()
    assert (art / "future_leakage_redteam.json").is_file()
    assert (art / "pit_revision_contract.json").is_file()


def test_ingest_rejects_unknown_parent() -> None:
    store = PitRevisionStore()
    with pytest.raises(ValueError, match="missing parent"):
        store.ingest(
            RevisionRecord(
                revision_id="X",
                series_id="S",
                kind="OBSERVATION",
                value=1,
                times=DualTimeStamp(
                    event_time=T0,
                    available_time=T0 + DAY,
                    revision_time=T0 + DAY,
                    ingest_time=T0 + DAY,
                ),
                parent_revision_id="MISSING",
            )
        )
