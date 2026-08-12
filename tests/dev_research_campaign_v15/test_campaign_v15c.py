"""V15-C Real Development Research Campaign tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_dev_research_campaign_v15.constants import ALLOWED_LABELS, DEV_END_MS, DEV_START_MS
from backend.nexus_dev_research_campaign_v15.data import _fixture_panel, load_development_panel
from backend.nexus_dev_research_campaign_v15.hard_bans import (
    HardBanViolation,
    assert_interval_not_oos,
    assert_no_status_json,
    refuse_auto_integrate,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_oos_consume,
)
from backend.nexus_dev_research_campaign_v15.labeling import assert_label_allowed, assign_label
from backend.nexus_dev_research_campaign_v15.campaign import run_campaign
from backend.nexus_dev_research_campaign_v15.adversarial import run_adversarial_review
from backend.nexus_dev_research_campaign_v15.artifacts import write_immutable_artifacts


ROOT = Path(__file__).resolve().parents[2]


def test_allowed_labels_cover_founder_set() -> None:
    expected = {
        "REJECTED",
        "DATA_BLOCKED",
        "SAMPLE_BLOCKED",
        "COST_DESTROYED",
        "REGIME_FRAGILE",
        "MULTIPLE_TESTING_REJECTED",
        "DEVELOPMENT_REVIEW",
        "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
    }
    assert ALLOWED_LABELS == expected


def test_qualified_label_rejected() -> None:
    with pytest.raises(ValueError):
        assert_label_allowed("QUALIFIED")


def test_promising_not_qualified_allowed() -> None:
    assert assert_label_allowed("DEVELOPMENT_PROMISING_NOT_QUALIFIED")


def test_hard_ban_refuse_apis() -> None:
    for fn in (
        refuse_oos_consume,
        refuse_formal_walk_forward,
        refuse_exchange_write,
        refuse_auto_integrate,
    ):
        with pytest.raises(HardBanViolation):
            fn()


def test_oos_interval_blocked() -> None:
    with pytest.raises(HardBanViolation):
        assert_interval_not_oos(DEV_END_MS, DEV_END_MS + 10_000_000)


def test_fixture_never_called_real() -> None:
    panel = _fixture_panel(
        symbols=["BTCUSDT", "ETHUSDT"],
        start_ms=DEV_START_MS,
        end_ms=DEV_END_MS,
        interval="60",
    )
    assert panel.classification == "FIXTURE_NOT_REAL"
    assert panel.fixture_used is True
    assert panel.is_real is False


def test_campaign_fixture_two_pass(tmp_path: Path) -> None:
    # Use repo root so imports/artifacts paths resolve; panel forced fixture.
    panel = _fixture_panel(
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        start_ms=DEV_START_MS,
        end_ms=min(DEV_END_MS, DEV_START_MS + 60 * 3_600_000 * 200),
        interval="60",
    )
    r1 = run_campaign(root=ROOT, panel=panel, pass_id=1, use_network=False)
    a1 = run_adversarial_review(r1, root=ROOT, pass_name="pass_1")
    r2 = run_campaign(root=ROOT, panel=panel, pass_id=2, use_network=False)
    a2 = run_adversarial_review(r2, root=ROOT, pass_name="pass_2")
    assert r2["mechanism_count"] >= 40
    assert r2["qualification_ready_count"] == 0
    assert r2["oos_consumed"] is False
    assert r2["data_lineage"] == "FIXTURE_NOT_REAL"
    assert set(r2["label_histogram"]) <= ALLOWED_LABELS
    assert "QUALIFIED" not in r2["label_histogram"]
    assert a1["adversarial_ok"]
    assert a2["adversarial_ok"]
    paths = write_immutable_artifacts(r2, [a1, a2], root=ROOT)
    assert "campaign_report" in paths
    # No status.json
    art = ROOT / "artifacts/readiness/immutable/v15_c_real_development_research_campaign"
    scan = assert_no_status_json(art)
    assert scan["ok"]
    assert not list(art.glob("*status.json"))


def test_assign_label_priority_data_blocked() -> None:
    info = assign_label(
        data_blocked=True,
        sample_blocked=True,
        multiple_testing_rejected=True,
        cost_destroyed=True,
        regime_fragile=True,
        development_promising=True,
        rejected=True,
    )
    assert info["label"] == "DATA_BLOCKED"
    assert info["qualification_claim"] is False
