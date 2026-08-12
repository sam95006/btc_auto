"""Expanded future-leakage redteam — survivors must remain 0."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_deep_pit_survivorship.campaign import run_campaign, write_artifacts  # noqa: E402
from backend.nexus_deep_pit_survivorship.constants import (  # noqa: E402
    COVERAGE_AREAS,
    EXPECTED_EXPANDED_LEAKAGE_ATTACKS,
    HARD_BANS,
)
from backend.nexus_deep_pit_survivorship.future_leakage_expand import (  # noqa: E402
    run_expanded_future_leakage_redteam,
)
from backend.nexus_pit_revision_v17.redteam import run_future_leakage_redteam  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_expanded_future_leakage_zero_survivors():
    report = run_expanded_future_leakage_redteam()
    assert report["pass"] is True
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["expanded"]["attack_count"] >= EXPECTED_EXPANDED_LEAKAGE_ATTACKS
    assert report["base"]["survivor_count"] == 0


def test_base_future_leakage_still_clean():
    base = run_future_leakage_redteam()
    assert base["pass"] is True
    assert base["survivor_count"] == 0
    assert base["attack_count"] == 12


def test_campaign_pass_and_coverage():
    report = run_campaign(repo_root=ROOT)
    assert report["passed"] is True
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert set(COVERAGE_AREAS).issubset(set(report["coverage_areas"]))
    assert "no_collapse_cross_exchange_symbols" in HARD_BANS
    assert "no_leap_second_aware_claim" in HARD_BANS
    paths = write_artifacts(report, repo_root=ROOT)
    assert (ROOT / "artifacts/readiness/immutable/v17_deep_pit_survivorship/campaign.json").is_file()
    assert "campaign.json" in paths


def test_hard_bans_forbid_wf_oos_exchange():
    required = {
        "no_formal_walk_forward",
        "no_untouched_oos",
        "no_exchange_write",
        "no_mainnet",
        "no_pr26_merge",
        "no_pr27_merge",
        "no_acceleration_report_edit",
    }
    assert required.issubset(set(HARD_BANS))
