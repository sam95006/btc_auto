"""Notification preference controls (PUB-K)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_public_mobile_notify.constants import ALERT_KINDS, ALERT_PRIORITIES
from backend.nexus_public_mobile_notify.hard_bans import assert_no_private_fields


@dataclass
class ChannelPreference:
    enabled: bool = True
    min_priority: str = "NORMAL"


@dataclass
class NotificationPreferences:
    """Per-member notification preference document."""

    member_id: str
    push_enabled: bool = True
    quiet_hours_start_utc: str | None = None  # HH:MM
    quiet_hours_end_utc: str | None = None
    channels: dict[str, ChannelPreference] = field(default_factory=dict)
    deep_link_enabled: bool = True
    live_activity_enabled: bool = True
    ios_widgets_enabled: bool = True
    android_widgets_enabled: bool = True
    version: int = 1

    def __post_init__(self) -> None:
        if not self.channels:
            self.channels = {
                kind: ChannelPreference(enabled=True, min_priority="NORMAL")
                for kind in sorted(ALERT_KINDS)
            }
        for kind in self.channels:
            if kind not in ALERT_KINDS:
                raise ValueError(f"unknown alert channel: {kind}")
            pref = self.channels[kind]
            if pref.min_priority not in ALERT_PRIORITIES:
                raise ValueError(f"invalid min_priority for {kind}: {pref.min_priority}")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        assert_no_private_fields(d)
        return d

    def allows(self, *, kind: str, priority: str) -> bool:
        if not self.push_enabled:
            return False
        if kind not in self.channels:
            return False
        channel = self.channels[kind]
        if not channel.enabled:
            return False
        order = ["LOW", "NORMAL", "HIGH", "CRITICAL"]
        return order.index(priority) >= order.index(channel.min_priority)


class InMemoryPreferenceStore:
    """Local/staging preference store. Not a production customer database."""

    def __init__(self) -> None:
        self._by_member: dict[str, NotificationPreferences] = {}

    def get_or_default(self, member_id: str) -> NotificationPreferences:
        if member_id not in self._by_member:
            self._by_member[member_id] = NotificationPreferences(member_id=member_id)
        return deepcopy(self._by_member[member_id])

    def save(self, prefs: NotificationPreferences) -> NotificationPreferences:
        payload = prefs.to_dict()
        assert_no_private_fields(payload)
        stored = NotificationPreferences(
            member_id=prefs.member_id,
            push_enabled=prefs.push_enabled,
            quiet_hours_start_utc=prefs.quiet_hours_start_utc,
            quiet_hours_end_utc=prefs.quiet_hours_end_utc,
            channels=deepcopy(prefs.channels),
            deep_link_enabled=prefs.deep_link_enabled,
            live_activity_enabled=prefs.live_activity_enabled,
            ios_widgets_enabled=prefs.ios_widgets_enabled,
            android_widgets_enabled=prefs.android_widgets_enabled,
            version=prefs.version + 1,
        )
        self._by_member[prefs.member_id] = stored
        return deepcopy(stored)

    def update_channel(
        self,
        member_id: str,
        kind: str,
        *,
        enabled: bool | None = None,
        min_priority: str | None = None,
    ) -> NotificationPreferences:
        prefs = self.get_or_default(member_id)
        channel = prefs.channels[kind]
        if enabled is not None:
            channel.enabled = enabled
        if min_priority is not None:
            if min_priority not in ALERT_PRIORITIES:
                raise ValueError(f"invalid min_priority: {min_priority}")
            channel.min_priority = min_priority
        return self.save(prefs)
