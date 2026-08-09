"""V18.2.20 paid-beta retention foundation tests."""
from __future__ import annotations

from backend.nexus_paid_beta_retention.alert_events import (
    build_alert_event,
    get_anti_spam,
    normalize_event_type,
)
from backend.nexus_paid_beta_retention.auth_census import auth_commercial_census
from backend.nexus_paid_beta_retention.auth_gate import auth_required_body
from backend.nexus_paid_beta_retention.billing_readiness import billing_readiness
from backend.nexus_paid_beta_retention.constants import (
    ALERT_EVENT_TYPES,
    AUTH_REQUIRED_BLOCKER,
    MARKER,
    ONBOARDING_STEPS,
)
from backend.nexus_paid_beta_retention.service import foundation_status, ingest_alert
from backend.nexus_paid_beta_retention.watchlist_store import WatchlistStore


def test_marker_and_event_types():
    assert MARKER == "PUBLIC_V18_2_20_PAID_BETA_RETENTION_HEAD"
    assert "RADAR_NEW" in ALERT_EVENT_TYPES
    assert "WATCHLIST_EVENT" in ALERT_EVENT_TYPES
    assert len(ONBOARDING_STEPS) == 3


def test_auth_required_blocker_no_fake_identity():
    body = auth_required_body()
    assert body["error"] == AUTH_REQUIRED_BLOCKER
    assert body["fake_identity"] is False
    assert body["member_execution"] == 0


def test_watchlist_server_authority():
    store = WatchlistStore()
    out = store.add("acct_1", "BTCUSDT")
    assert out["authority"] == "SERVER"
    assert out["canonical"] is True
    assert out["items"][0]["symbol"] == "BTCUSDT"
    out2 = store.remove("acct_1", "BTCUSDT")
    assert out2["items"] == []


def test_anti_spam_dedup():
    spam = get_anti_spam()
    ok1, _ = spam.allow(
        "acct_spam",
        event_type="RADAR_UP",
        symbol="ETHUSDT",
        severity="HIGH",
        dedup_key="k1",
    )
    ok2, reason = spam.allow(
        "acct_spam",
        event_type="RADAR_UP",
        symbol="ETHUSDT",
        severity="HIGH",
        dedup_key="k1",
    )
    assert ok1 is True
    assert ok2 is False
    assert reason in {"dedup", "cooldown"}


def test_normalize_and_build_event():
    assert normalize_event_type("UP") == "RADAR_UP"
    evt = build_alert_event(
        event_type="RADAR_NEW",
        symbol="solusdt",
        severity="MEDIUM",
        headline="SOL entered radar",
    )
    assert evt["type"] == "RADAR_NEW"
    assert evt["symbol"] == "SOLUSDT"
    assert evt["link"].endswith("SOLUSDT")


def test_ingest_to_notification_center():
    r1 = ingest_alert(
        "acct_n1",
        event_type="STATE_CHANGE",
        symbol="BTCUSDT",
        severity="MEDIUM",
        headline="BTC state change",
        metric={"dedup": "unique-state-1"},
    )
    assert r1["ok"] is True
    assert r1["notification"]["read"] is False


def test_auth_census_and_billing():
    census = auth_commercial_census()
    assert "paid_beta_auth_blockers" in census
    assert census["census"]["entitlement"] == "READY"
    bill = billing_readiness()
    assert bill["production_billing_activated"] is False
    assert bill["frontend_only_paid_authority"] is False
    assert bill["member_execution"] == 0


def test_foundation_status():
    st = foundation_status()
    assert st["marker"] == MARKER
    assert st["delivery"]["in_app"] is True
    assert st["web_push_foundation"] is False
    assert st["production_billing"] is False
