"""Timestamp boundary / DST / UTC / leap-second guard tests."""
from __future__ import annotations

import os

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_deep_pit_survivorship.constants import LEAP_SECOND_POLICY  # noqa: E402
from backend.nexus_deep_pit_survivorship.hard_bans import (  # noqa: E402
    HardBanViolation,
    refuse_leap_second_aware_claim,
)
from backend.nexus_deep_pit_survivorship.timestamp_edges import (  # noqa: E402
    attack_dst_wallclock_collision,
    attack_leap_second_aware_claim,
    attack_local_tz_as_known_at,
    attack_spring_forward_gap_query,
    attack_utc_midnight_revision_boundary,
    dst_transition_instants,
    run_timestamp_edge_attacks,
    utc_midnight_boundaries,
)


def test_timestamp_edge_campaign_zero_survivors():
    report = run_timestamp_edge_attacks()
    assert report["pass"] is True
    assert report["survivor_count"] == 0
    assert report["leap_second_policy"] == LEAP_SECOND_POLICY


def test_leap_second_claim_refused():
    result = attack_leap_second_aware_claim()
    assert result["blocked"] is True
    assert result["survivor"] is False
    with pytest.raises(HardBanViolation):
        refuse_leap_second_aware_claim(claimed=True)


def test_leap_second_policy_documented():
    assert "UTC_CONTINUOUS" in LEAP_SECOND_POLICY
    assert "NO_LEAP_SECOND_TABLE" in LEAP_SECOND_POLICY


def test_local_tz_as_known_at_blocked():
    result = attack_local_tz_as_known_at()
    assert result["blocked"] is True
    assert result["survivor"] is False


def test_dst_fall_back_utc_distinct():
    result = attack_dst_wallclock_collision()
    assert result["blocked"] is True
    edges = dst_transition_instants()["fall_back_2024"]
    assert edges[0]["utc_ms"] != edges[1]["utc_ms"]


def test_utc_midnight_boundaries_no_leak():
    result = attack_utc_midnight_revision_boundary()
    assert result["blocked"] is True
    assert result["survivor"] is False
    assert len(utc_midnight_boundaries()) >= 5


def test_spring_forward_gap_query_safe():
    result = attack_spring_forward_gap_query()
    assert result["blocked"] is True
    assert result["evidence"]["gap_ms"] > 0
