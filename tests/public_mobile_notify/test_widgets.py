"""Widget and Live Activity abstraction tests."""

from __future__ import annotations

import pytest

from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation
from backend.nexus_public_mobile_notify.widgets import (
    AndroidWidgetAbstraction,
    IOSLiveActivityAbstraction,
    IOSWidgetAbstraction,
    WidgetSnapshot,
    build_decision_widget_snapshot,
)


def test_ios_live_activity_and_widget_prototypes():
    snap = build_decision_widget_snapshot(
        platform_kind="IOS_HOME_SCREEN",
        decision_id="dec_1",
        status="ACTIVE",
        title="Decision active",
        deep_link="nexus://app/decision_detail?decision_id=dec_1",
        as_of="2026-08-05T12:00:00Z",
        freshness="DEMO_DATA",
        mode="DEMO_DATA",
    )
    ios_w = IOSWidgetAbstraction()
    timeline = ios_w.timeline([snap])
    assert timeline["entry_count"] == 1
    assert "WidgetKit not invoked" in timeline["note"]

    live = IOSLiveActivityAbstraction()
    live_snap = WidgetSnapshot(
        widget_kind="IOS_LIVE_ACTIVITY",
        headline=snap.headline,
        subtitle=snap.subtitle,
        status_chip=snap.status_chip,
        deep_link=snap.deep_link,
        as_of=snap.as_of,
        freshness=snap.freshness,
        mode=snap.mode,
        fields=dict(snap.fields),
    )
    started = live.start(live_snap)
    assert started["production_push_token_used"] is False
    assert started["action"] == "START"
    ended = live.end(started["activity_id"])
    assert ended["action"] == "END"


def test_android_widget_prototype():
    snap = build_decision_widget_snapshot(
        platform_kind="ANDROID_HOME_SCREEN",
        decision_id="dec_2",
        status="REVIEW",
        title="Review",
        deep_link="nexus://app/decision_detail?decision_id=dec_2",
        as_of="2026-08-05T12:00:00Z",
        freshness="DEMO_DATA",
    )
    rendered = AndroidWidgetAbstraction().render(snap)
    assert rendered["platform"] == "android"
    assert rendered["remote_views"]["click_deep_link"].startswith("nexus://")


def test_widget_rejects_private_fields():
    with pytest.raises(HardBanViolation):
        WidgetSnapshot(
            widget_kind="IOS_HOME_SCREEN",
            headline="x",
            subtitle="y",
            status_chip="z",
            deep_link="nexus://app/home",
            as_of="2026-08-05T12:00:00Z",
            freshness="DEMO_DATA",
            mode="DEMO_DATA",
            fields={"strategy_id": "nope"},
        ).to_dict()
