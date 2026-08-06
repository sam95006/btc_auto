"""Tests — full deep license/inference campaign."""
from __future__ import annotations

from backend.nexus_deep_license_inference.campaign import run_campaign, write_campaign_artifacts
from backend.nexus_deep_license_inference.constants import COVERAGE_AREAS, HARD_BANS
from backend.nexus_deep_license_inference.hard_bans import (
    HardBanViolation,
    hard_ban_inventory,
    refuse_pr26_merge,
    refuse_pr27_merge,
)
import pytest


def test_campaign_survivors_zero() -> None:
    report = run_campaign()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["attack_count"] >= 12
    for area in COVERAGE_AREAS:
        assert area in report["coverage_areas"]


def test_campaign_writes_artifacts(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # write into temp by pointing parents — use explicit root
    report = run_campaign()
    path = write_campaign_artifacts(report, root=tmp_path)
    assert path.is_file()
    assert (tmp_path / "artifacts/readiness/immutable/v17_deep_license_inference/deep_license_inference_summary.json").is_file()


def test_hard_bans_inventory() -> None:
    inv = hard_ban_inventory()
    assert inv["exchange_write"] is False
    assert inv["mainnet"] is False
    assert inv["pr26_merged"] is False
    assert inv["pr27_merged"] is False
    for ban in (
        "no_restricted_license_as_live",
        "inference_attack_survivors_must_be_0",
        "no_pr26_merge",
        "no_pr27_merge",
    ):
        assert ban in HARD_BANS


def test_refuse_pr_merges() -> None:
    with pytest.raises(HardBanViolation):
        refuse_pr26_merge()
    with pytest.raises(HardBanViolation):
        refuse_pr27_merge()
