"""End-to-end notification foundation facade (prototype orchestration)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_public_mobile_notify.alerts.models import PublicAlert, PublicAlertLineage
from backend.nexus_public_mobile_notify.deeplink.router import DeepLinkRouter
from backend.nexus_public_mobile_notify.preferences.store import (
    InMemoryPreferenceStore,
    NotificationPreferences,
)
from backend.nexus_public_mobile_notify.push.provider import (
    DeviceRegistration,
    PushDeliveryRecord,
    PushProvider,
    StubPushProvider,
)
from backend.nexus_public_mobile_notify.widgets.abstractions import (
    AndroidWidgetAbstraction,
    IOSLiveActivityAbstraction,
    IOSWidgetAbstraction,
    WidgetSnapshot,
    build_decision_widget_snapshot,
)


@dataclass
class NotificationDispatchResult:
    alert: PublicAlert
    delivery: PushDeliveryRecord | None
    skipped_reason: str | None
    widget_hint: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert": self.alert.to_dict(),
            "delivery": None
            if self.delivery is None
            else {
                "delivery_id": self.delivery.delivery_id,
                "status": self.delivery.status,
                "provider_mode": self.delivery.provider_mode,
                "device_id": self.delivery.device_id,
            },
            "skipped_reason": self.skipped_reason,
            "widget_hint": self.widget_hint,
        }


class MobileNotificationFoundation:
    """Coordinates preferences, deep links, push stubs, and widget hints."""

    def __init__(
        self,
        *,
        push_provider: PushProvider | None = None,
        preferences: InMemoryPreferenceStore | None = None,
        router: DeepLinkRouter | None = None,
    ) -> None:
        self.push = push_provider or StubPushProvider()
        self.preferences = preferences or InMemoryPreferenceStore()
        self.router = router or DeepLinkRouter()
        self.ios_live = IOSLiveActivityAbstraction()
        self.ios_widget = IOSWidgetAbstraction()
        self.android_widget = AndroidWidgetAbstraction()

    def dispatch(
        self,
        *,
        member_id: str,
        alert: PublicAlert,
        device: DeviceRegistration,
        update_widgets: bool = True,
    ) -> NotificationDispatchResult:
        prefs = self.preferences.get_or_default(member_id)
        if not prefs.allows(kind=alert.kind, priority=alert.priority):
            return NotificationDispatchResult(
                alert=alert,
                delivery=None,
                skipped_reason="preference_suppressed",
                widget_hint=None,
            )
        delivery = self.push.send(alert=alert, device=device)
        widget_hint = None
        if update_widgets and alert.decision_id:
            widget_hint = self._widget_hint(alert=alert, prefs=prefs, platform=device.platform)
        return NotificationDispatchResult(
            alert=alert,
            delivery=delivery,
            skipped_reason=None,
            widget_hint=widget_hint,
        )

    def _widget_hint(
        self,
        *,
        alert: PublicAlert,
        prefs: NotificationPreferences,
        platform: str,
    ) -> dict[str, Any]:
        snap = build_decision_widget_snapshot(
            platform_kind="IOS_HOME_SCREEN" if platform == "ios" else "ANDROID_HOME_SCREEN",
            decision_id=alert.decision_id or "unknown",
            status=str(alert.public_payload.get("decision_status") or alert.kind),
            title=alert.title,
            deep_link=alert.deep_link,
            as_of=alert.lineage.as_of,
            freshness=alert.lineage.freshness,
            mode=alert.lineage.mode,
        )
        out: dict[str, Any] = {"snapshot": snap.to_dict()}
        if platform == "ios" and prefs.ios_widgets_enabled:
            out["ios_timeline"] = self.ios_widget.timeline([snap])
            if prefs.live_activity_enabled:
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
                out["ios_live_activity"] = self.ios_live.start(live_snap)
        if platform == "android" and prefs.android_widgets_enabled:
            out["android_widget"] = self.android_widget.render(snap)
        return out

    def attach_deep_link(self, *, kind: str, decision_id: str | None = None) -> str:
        return self.router.for_alert(kind=kind, decision_id=decision_id).uri


def demo_lineage_bundle() -> PublicAlertLineage:
    from backend.nexus_public_mobile_notify.alerts.models import demo_lineage

    return demo_lineage()
