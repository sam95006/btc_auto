"""Foundation orchestration tests."""

from __future__ import annotations

from backend.nexus_public_mobile_notify.alerts import decision_status_alert, demo_lineage, risk_alert
from backend.nexus_public_mobile_notify.foundation import MobileNotificationFoundation
from backend.nexus_public_mobile_notify.preferences import InMemoryPreferenceStore
from backend.nexus_public_mobile_notify.push import DeviceRegistration, InMemoryMockPushProvider


def test_dispatch_respects_preferences_and_builds_widget_hint():
    prefs = InMemoryPreferenceStore()
    push = InMemoryMockPushProvider()
    foundation = MobileNotificationFoundation(push_provider=push, preferences=prefs)
    device = DeviceRegistration(
        device_id="ios_1",
        platform="ios",
        push_token="demo",
        app_environment="staging",
    )
    alert = decision_status_alert(
        decision_id="dec_7",
        status="ACTIVE",
        title="Active",
        body="Decision active",
        deep_link=foundation.attach_deep_link(kind="DECISION_STATUS", decision_id="dec_7"),
        lineage=demo_lineage(),
    )
    result = foundation.dispatch(member_id="m1", alert=alert, device=device)
    assert result.skipped_reason is None
    assert result.delivery is not None
    assert result.widget_hint is not None
    assert "ios_timeline" in result.widget_hint
    assert result.widget_hint["ios_live_activity"]["production_push_token_used"] is False

    prefs.update_channel("m1", "RISK", enabled=False)
    risk = risk_alert(
        decision_id="dec_7",
        risk_code="X",
        severity="HIGH",
        title="Risk",
        body="Risk",
        deep_link=foundation.attach_deep_link(kind="RISK", decision_id="dec_7"),
        lineage=demo_lineage(),
    )
    skipped = foundation.dispatch(member_id="m1", alert=risk, device=device)
    assert skipped.skipped_reason == "preference_suppressed"
    assert skipped.delivery is None


def test_android_dispatch_widget():
    foundation = MobileNotificationFoundation(push_provider=InMemoryMockPushProvider())
    device = DeviceRegistration(
        device_id="and_1",
        platform="android",
        push_token="demo",
        app_environment="local",
    )
    alert = decision_status_alert(
        decision_id="dec_8",
        status="REVIEW",
        title="Review",
        body="Review",
        deep_link="nexus://app/decision_detail?decision_id=dec_8",
        lineage=demo_lineage(),
    )
    result = foundation.dispatch(member_id="m2", alert=alert, device=device)
    assert "android_widget" in (result.widget_hint or {})
