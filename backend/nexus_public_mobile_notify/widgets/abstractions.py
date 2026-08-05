"""iOS / Android widget and Live Activity abstractions (PUB-K prototypes)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from backend.nexus_public_mobile_notify.constants import WIDGET_KINDS
from backend.nexus_public_mobile_notify.hard_bans import assert_no_private_fields


@dataclass(frozen=True)
class WidgetSnapshot:
    """Public-safe snapshot rendered by home/lock widgets or Live Activities."""

    widget_kind: str
    headline: str
    subtitle: str
    status_chip: str
    deep_link: str
    as_of: str
    freshness: str
    mode: str  # LIVE | DEMO_DATA | MOCK_IN_MEMORY
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        if self.widget_kind not in WIDGET_KINDS:
            raise ValueError(f"unsupported widget kind: {self.widget_kind}")
        d = asdict(self)
        assert_no_private_fields(d)
        return d


class IOSLiveActivityAbstraction:
    """Architecture-only Live Activity controller. No ActivityKit network."""

    kind = "IOS_LIVE_ACTIVITY"

    def start(self, snapshot: WidgetSnapshot) -> dict[str, Any]:
        payload = snapshot.to_dict()
        return {
            "action": "START",
            "platform": "ios",
            "activity_id": f"la_{hash(payload['headline']) & 0xFFFFFFFF:08x}",
            "snapshot": payload,
            "production_push_token_used": False,
            "note": "prototype only; ActivityKit not invoked",
        }

    def update(self, activity_id: str, snapshot: WidgetSnapshot) -> dict[str, Any]:
        return {
            "action": "UPDATE",
            "platform": "ios",
            "activity_id": activity_id,
            "snapshot": snapshot.to_dict(),
            "production_push_token_used": False,
        }

    def end(self, activity_id: str, *, reason: str = "completed") -> dict[str, Any]:
        return {
            "action": "END",
            "platform": "ios",
            "activity_id": activity_id,
            "reason": reason,
            "production_push_token_used": False,
        }


class IOSWidgetAbstraction:
    """Home / lock-screen widget timeline builder (no WidgetKit invocation)."""

    def timeline(self, snapshots: list[WidgetSnapshot]) -> dict[str, Any]:
        entries = []
        for snap in snapshots:
            if snap.widget_kind not in {"IOS_HOME_SCREEN", "IOS_LOCK_SCREEN"}:
                raise ValueError(f"iOS widget refuses kind {snap.widget_kind}")
            entries.append(snap.to_dict())
        return {
            "platform": "ios",
            "entry_count": len(entries),
            "entries": entries,
            "reload_policy": "ON_ALERT_OR_MANUAL",
            "note": "prototype timeline; WidgetKit not invoked",
        }


class AndroidWidgetAbstraction:
    """Android App Widget remote-views model (no AppWidgetManager invocation)."""

    def render(self, snapshot: WidgetSnapshot) -> dict[str, Any]:
        if snapshot.widget_kind not in {"ANDROID_HOME_SCREEN", "ANDROID_LOCK_SCREEN_GLANCE"}:
            raise ValueError(f"Android widget refuses kind {snapshot.widget_kind}")
        payload = snapshot.to_dict()
        return {
            "platform": "android",
            "remote_views": {
                "headline": payload["headline"],
                "subtitle": payload["subtitle"],
                "status_chip": payload["status_chip"],
                "click_deep_link": payload["deep_link"],
                "freshness": payload["freshness"],
            },
            "update_period_ms": 0,  # event-driven only in foundation
            "note": "prototype only; AppWidgetManager not invoked",
        }


def build_decision_widget_snapshot(
    *,
    platform_kind: str,
    decision_id: str,
    status: str,
    title: str,
    deep_link: str,
    as_of: str,
    freshness: str,
    mode: str = "DEMO_DATA",
    extra: Mapping[str, Any] | None = None,
) -> WidgetSnapshot:
    fields = {"decision_id": decision_id, "decision_status": status}
    if extra:
        fields.update(dict(extra))
    return WidgetSnapshot(
        widget_kind=platform_kind,
        headline=title,
        subtitle=f"Decision {decision_id}",
        status_chip=status,
        deep_link=deep_link,
        as_of=as_of,
        freshness=freshness,
        mode=mode,
        fields=fields,
    )
