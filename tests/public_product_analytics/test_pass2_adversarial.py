"""PUB2-I Pass 2: adversarial fabrication / privacy / hard-ban attacks."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_product_analytics.hard_bans import (
    HardBanViolation,
    refuse_fabrication,
    refuse_status_json_emission,
    run_hard_ban_pass,
)
from backend.nexus_public_product_analytics.store import LocalAnalyticsStore
from backend.nexus_public_product_analytics.three_pass import pass2_adversarial
from backend.nexus_public_product_analytics.tracker import ProductAnalyticsTracker

ROOT = Path(__file__).resolve().parents[2]


def test_refuse_fabricated_subject():
    tracker = ProductAnalyticsTracker()
    tracker.grant_consent("fake_wau_user")
    with pytest.raises(HardBanViolation):
        tracker.track("session_active", raw_subject_id="fake_wau_user", props={"surface": "web"})


def test_refuse_pii_props():
    tracker = ProductAnalyticsTracker()
    tracker.grant_consent("member_x")
    with pytest.raises(HardBanViolation):
        tracker.track(
            "upgrade_intent",
            raw_subject_id="member_x",
            props={"intent_kind": "stated", "email": "x@y.com"},
        )


def test_refuse_production_db_and_status_json():
    with pytest.raises(HardBanViolation):
        LocalAnalyticsStore(production_customer_database=True)
    with pytest.raises(HardBanViolation):
        refuse_status_json_emission("artifacts/pub2_i_lane_status.json")
    with pytest.raises(HardBanViolation):
        refuse_fabrication("dummy_wau")


def test_hard_ban_pass_clean():
    result = run_hard_ban_pass(ROOT)
    assert result["ok"] is True
    assert result["status_json"]["ok"] is True


def test_pass2_runner_zero_survivors():
    result = pass2_adversarial(ROOT)
    assert result["ok"] is True
    assert result["survivor_count"] == 0
