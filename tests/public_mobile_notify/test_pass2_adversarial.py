"""Pass-2 adversarial / negative tests for PUB-K."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.nexus_public_mobile_notify.alerts import (
    PublicAlertLineage,
    build_alert,
    decision_status_alert,
    demo_lineage,
    risk_alert,
)
from backend.nexus_public_mobile_notify.foundation import MobileNotificationFoundation
from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation
from backend.nexus_public_mobile_notify.preferences import InMemoryPreferenceStore, in_quiet_hours
from backend.nexus_public_mobile_notify.push import DeviceRegistration, InMemoryMockPushProvider
from backend.nexus_public_mobile_notify.security.invariants import collect_security_invariants

ROOT = Path(__file__).resolve().parents[2]


def _device(**kwargs):
    base = dict(
        device_id="dev",
        platform="ios",
        push_token="demo",
        app_environment="local",
    )
    base.update(kwargs)
    return DeviceRegistration(**base)


def test_dispatch_refuses_private_deep_link():
    foundation = MobileNotificationFoundation(push_provider=InMemoryMockPushProvider())
    alert = decision_status_alert(
        decision_id="dec_x",
        status="ACTIVE",
        title="x",
        body="y",
        deep_link="nexus://app/wallet",
        lineage=demo_lineage(),
    )
    with pytest.raises(HardBanViolation, match="private deep-link"):
        foundation.dispatch(member_id="m", alert=alert, device=_device())


def test_quiet_hours_suppress_non_critical(monkeypatch):
    store = InMemoryPreferenceStore()
    prefs = store.get_or_default("m_q")
    prefs.quiet_hours_start_utc = "00:00"
    prefs.quiet_hours_end_utc = "23:59"
    store.save(prefs)
    foundation = MobileNotificationFoundation(
        push_provider=InMemoryMockPushProvider(),
        preferences=store,
    )
    now = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    assert in_quiet_hours(start_utc="00:00", end_utc="23:59", now_utc=now) is True
    alert = risk_alert(
        decision_id="dec_q",
        risk_code="X",
        severity="HIGH",
        title="Risk",
        body="Risk",
        deep_link="nexus://app/risks?decision_id=dec_q",
        lineage=demo_lineage(),
        priority="HIGH",
    )
    result = foundation.dispatch(member_id="m_q", alert=alert, device=_device(), now_utc=now)
    assert result.skipped_reason == "quiet_hours_suppressed"
    assert result.delivery is None

    critical = risk_alert(
        decision_id="dec_q",
        risk_code="X",
        severity="CRITICAL",
        title="Critical risk",
        body="Critical",
        deep_link="nexus://app/risks?decision_id=dec_q",
        lineage=demo_lineage(),
        priority="CRITICAL",
    )
    ok = foundation.dispatch(member_id="m_q", alert=critical, device=_device(), now_utc=now)
    assert ok.skipped_reason is None
    assert ok.delivery is not None


def test_live_empty_source_refused_as_fabrication():
    lineage = PublicAlertLineage(
        source_system="",
        source_endpoint="/v1/x",
        as_of="2026-08-05T00:00:00Z",
        retrieved_at="2026-08-05T00:00:00Z",
        freshness="FRESH",
        completeness="COMPLETE",
        lineage_id="x",
        mode="LIVE",
    )
    with pytest.raises(HardBanViolation, match="fabricated live alert"):
        build_alert(
            kind="DECISION_STATUS",
            title="t",
            body="b",
            deep_link="nexus://app/alerts",
            lineage=lineage,
        )


def test_prod_and_live_device_aliases_refused():
    foundation = MobileNotificationFoundation(push_provider=InMemoryMockPushProvider())
    alert = decision_status_alert(
        decision_id="dec_1",
        status="ACTIVE",
        title="t",
        body="b",
        deep_link="nexus://app/decision_detail?decision_id=dec_1",
        lineage=demo_lineage(),
    )
    for env in ("prod", "live", "PRODUCTION"):
        with pytest.raises(HardBanViolation):
            foundation.dispatch(
                member_id="m",
                alert=alert,
                device=_device(app_environment=env),
            )


def test_security_invariants_pass():
    report = collect_security_invariants(ROOT)
    assert report["ok"] is True, report
    assert report["exchange_write_capability_count"] == 0
    assert report["lane_status_json_count"] == 0
    assert report["public_private_import_violation_count"] == 0
    assert report["production_credential_hit_count"] == 0


def test_stub_status_never_claims_production_ack():
    foundation = MobileNotificationFoundation()
    alert = decision_status_alert(
        decision_id="dec_2",
        status="ACTIVE",
        title="t",
        body="b",
        deep_link="nexus://app/decision_detail?decision_id=dec_2",
        lineage=demo_lineage(),
    )
    result = foundation.dispatch(member_id="m", alert=alert, device=_device())
    assert result.delivery is not None
    assert result.delivery.status == "STUB_ACCEPTED"
    assert result.delivery.provider_mode == "STUB"
    assert "PRODUCTION" not in result.delivery.status
