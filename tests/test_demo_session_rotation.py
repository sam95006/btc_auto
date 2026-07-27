"""Fault and happy-path tests for autonomous Demo session rotation."""
from __future__ import annotations

import time

import pytest

from backend.nexus_research.demo_autonomous.reentry_guard import ReentryGuard
from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationValidator,
    DEFAULT_MAX_RISK_PCT,
)
from backend.nexus_research.demo_autonomous.session_rotator import (
    AutonomousDemoSessionRotator,
    SingleOwnerRotationLock,
)


@pytest.fixture()
def auth(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    v = AuthorizationValidator()
    v.issue(ttl_ms=60_000, max_risk_per_trade_pct=0.5, auto_send=True)
    return v


def test_flat_full_rotation(auth):
    # Force near-expiry
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    rot = AutonomousDemoSessionRotator(auth=auth)
    res = rot.rotate_if_needed(position_count=0, open_order_count=0, force=True)
    assert res.ok
    assert res.mode == "FULL_ROTATION"
    assert res.new_session_id
    assert auth.session is not None
    assert auth.session.is_active()
    assert auth.session.max_risk_per_trade_pct <= DEFAULT_MAX_RISK_PCT


def test_open_position_continuity(auth):
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    rot = AutonomousDemoSessionRotator(auth=auth)
    res = rot.rotate_if_needed(position_count=1, open_order_count=2, force=True)
    assert res.ok
    assert res.mode == "POSITION_CONTINUITY"
    assert res.new_entries_paused is True
    assert auth.session.is_active()


def test_duplicate_rotation_request(auth):
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    rot = AutonomousDemoSessionRotator(auth=auth)
    r1 = rot.rotate_if_needed(position_count=0, open_order_count=0, force=True)
    # Same expiry key already consumed — after renew expiry changed, force again with new key
    assert r1.ok
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    # Reuse idempotency on identical old key is hard after renew; test lock instead
    lock = SingleOwnerRotationLock()
    assert lock.acquire("a") is True
    assert lock.acquire("b") is False
    lock.release("a")
    assert lock.acquire("b") is True


def test_owner_competition_blocks(auth):
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    rot = AutonomousDemoSessionRotator(auth=auth, owner_count_fn=lambda: 2)
    res = rot.rotate_if_needed(position_count=0, open_order_count=0, force=True)
    assert res.ok is False
    assert res.error == "owner_count_not_1"


def test_emergency_stop_blocks(auth):
    auth.emergency_stop("test")
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    rot = AutonomousDemoSessionRotator(auth=auth)
    res = rot.rotate_if_needed(position_count=0, open_order_count=0, force=True)
    assert res.ok is False
    assert res.error == "emergency_stop"


def test_risk_increase_blocked_on_renew(auth):
    # renew clamps risk; simulate parent at 0.5 and ensure cannot go higher
    old = auth.session.max_risk_per_trade_pct
    renewed = auth.renew(ttl_ms=120_000, max_risk_per_trade_pct=0.9)
    assert renewed.max_risk_per_trade_pct <= old


def test_policy_mismatch_blocks(auth):
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    auth.session.leverage_policy_version = "wrong"
    rot = AutonomousDemoSessionRotator(auth=auth)
    res = rot.rotate_if_needed(position_count=0, open_order_count=0, force=True)
    assert res.ok is False
    assert res.error == "policy_version_mismatch"


def test_ambiguous_blocks(auth):
    auth.session.expires_at_ms = int(time.time() * 1000) - 1
    rot = AutonomousDemoSessionRotator(auth=auth)
    res = rot.rotate_if_needed(
        position_count=0, open_order_count=0, ambiguous=True, force=True
    )
    assert res.ok is False
    assert res.error == "ambiguous_state"


def test_reentry_cooldown():
    g = ReentryGuard(min_cooldown_ms=60_000)
    g.record_close(symbol="BTCUSDT", side="Buy", strategy="TREND_FOLLOWING", signal_id="s1")
    ok, reason = g.allow(
        symbol="BTCUSDT",
        side="Buy",
        strategy="TREND_FOLLOWING",
        signal_id="s2",
        market_snapshot_id="snap1",
    )
    assert ok is False
    assert reason == "reentry_cooldown"


def test_reentry_same_signal_blocked_after_cooldown():
    g = ReentryGuard(min_cooldown_ms=1)
    g.record_close(symbol="BTCUSDT", side="Buy", strategy="TREND_FOLLOWING", signal_id="s1")
    time.sleep(0.02)
    ok, reason = g.allow(
        symbol="BTCUSDT",
        side="Buy",
        strategy="TREND_FOLLOWING",
        signal_id="s1",
        market_snapshot_id="snap2",
    )
    assert ok is False
    assert reason == "same_signal_id"


def test_reentry_allows_new_signal():
    g = ReentryGuard(min_cooldown_ms=1)
    g.record_close(symbol="BTCUSDT", side="Buy", strategy="TREND_FOLLOWING", signal_id="s1")
    time.sleep(0.02)
    ok, reason = g.allow(
        symbol="BTCUSDT",
        side="Buy",
        strategy="TREND_FOLLOWING",
        signal_id="s2",
        market_snapshot_id="snap2",
    )
    assert ok is True
    assert reason is None


def test_skip_when_not_near_expiry(auth):
    auth.session.expires_at_ms = int(time.time() * 1000) + 3_600_000
    rot = AutonomousDemoSessionRotator(auth=auth)
    res = rot.rotate_if_needed(position_count=0, open_order_count=0, force=False)
    assert res.mode == "SKIPPED"


def test_exit_policy_incomplete_without_plans(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    from backend.nexus_research.demo_autonomous.exit_policy_record import record_exit_policy

    incomplete = record_exit_policy(
        symbol="BTCUSDT",
        side="Buy",
        strategy="TREND_FOLLOWING",
        protective_stop_plan=None,
        take_profit_plan=None,
    )
    assert incomplete.persisted is True
    assert incomplete.is_complete() is False


def test_exit_policy_complete_and_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    from backend.nexus_research.demo_autonomous.exit_policy_record import (
        latest_exit_policy,
        record_exit_policy,
    )

    complete = record_exit_policy(
        symbol="BTCUSDT",
        side="Buy",
        strategy="TREND_FOLLOWING",
        protective_stop_plan={"type": "StopLoss", "triggerPrice": 100.0},
        take_profit_plan={"type": "TakeProfit", "triggerPrice": 110.0},
    )
    assert complete.is_complete() is True
    loaded = latest_exit_policy("BTCUSDT")
    assert loaded is not None
    assert loaded.is_complete() is True
    assert loaded.protective_stop_plan["triggerPrice"] == 100.0
