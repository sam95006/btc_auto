"""Push notification provider abstractions — stub/mock only (PUB-K)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from backend.nexus_public_mobile_notify.alerts.models import PublicAlert
from backend.nexus_public_mobile_notify.constants import ALLOWED_PUSH_PROVIDER_MODES
from backend.nexus_public_mobile_notify.hard_bans import (
    HardBanViolation,
    assert_no_private_fields,
    assert_no_production_credential_material,
    refuse_apns_production_key,
    refuse_fcm_production_server_key,
    refuse_production_notification_credentials,
)


@dataclass(frozen=True)
class DeviceRegistration:
    """Public device token registration (no production secrets)."""

    device_id: str
    platform: str  # ios | android
    push_token: str
    app_environment: str  # local | staging | demo — never production
    locale: str = "en"


@dataclass
class PushDeliveryRecord:
    delivery_id: str
    alert_id: str
    device_id: str
    status: str
    provider_mode: str
    detail: dict[str, Any] = field(default_factory=dict)


class PushProvider(Protocol):
    mode: str

    def send(self, *, alert: PublicAlert, device: DeviceRegistration) -> PushDeliveryRecord: ...


def validate_provider_mode(mode: str) -> str:
    if mode in {"PRODUCTION_APNS_REFUSED", "PRODUCTION_FCM_REFUSED", "PRODUCTION"}:
        refuse_production_notification_credentials(mode)
    if mode not in ALLOWED_PUSH_PROVIDER_MODES:
        raise HardBanViolation(f"HARD BAN: push provider mode '{mode}' refused in PUB-K")
    return mode


def validate_device_registration(device: DeviceRegistration) -> None:
    if device.app_environment.lower() in {"production", "prod", "live"}:
        refuse_production_notification_credentials("device.app_environment=production")
    assert_no_production_credential_material(
        {
            "push_token": device.push_token,
            "device_id": device.device_id,
            "platform": device.platform,
        }
    )


class StubPushProvider:
    """No-op provider for architecture wiring."""

    mode = "STUB"

    def send(self, *, alert: PublicAlert, device: DeviceRegistration) -> PushDeliveryRecord:
        validate_provider_mode(self.mode)
        validate_device_registration(device)
        payload = alert.to_dict()
        assert_no_private_fields(payload)
        return PushDeliveryRecord(
            delivery_id=f"stub_{uuid4().hex[:12]}",
            alert_id=alert.alert_id,
            device_id=device.device_id,
            status="STUB_ACCEPTED",
            provider_mode=self.mode,
            detail={"note": "no network call; architecture prototype only"},
        )


class InMemoryMockPushProvider:
    """Records deliveries in-process for tests and local demos."""

    mode = "MOCK_IN_MEMORY"

    def __init__(self) -> None:
        self.deliveries: list[PushDeliveryRecord] = []

    def send(self, *, alert: PublicAlert, device: DeviceRegistration) -> PushDeliveryRecord:
        validate_provider_mode(self.mode)
        validate_device_registration(device)
        assert_no_private_fields(alert.to_dict())
        record = PushDeliveryRecord(
            delivery_id=f"mock_{uuid4().hex[:12]}",
            alert_id=alert.alert_id,
            device_id=device.device_id,
            status="MOCK_DELIVERED",
            provider_mode=self.mode,
            detail={"title": alert.title, "kind": alert.kind},
        )
        self.deliveries.append(record)
        return record


class LocalFileSinkPushProvider:
    """Writes delivery envelopes to a local directory (never production APNs/FCM)."""

    mode = "LOCAL_FILE_SINK"

    def __init__(self, sink_dir: Path) -> None:
        self.sink_dir = Path(sink_dir)
        self.sink_dir.mkdir(parents=True, exist_ok=True)

    def send(self, *, alert: PublicAlert, device: DeviceRegistration) -> PushDeliveryRecord:
        validate_provider_mode(self.mode)
        validate_device_registration(device)
        payload = alert.to_dict()
        assert_no_private_fields(payload)
        delivery_id = f"file_{uuid4().hex[:12]}"
        out = self.sink_dir / f"{delivery_id}.json"
        import json

        out.write_text(
            json.dumps(
                {
                    "delivery_id": delivery_id,
                    "device_id": device.device_id,
                    "platform": device.platform,
                    "alert": payload,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return PushDeliveryRecord(
            delivery_id=delivery_id,
            alert_id=alert.alert_id,
            device_id=device.device_id,
            status="FILE_SINK_WRITTEN",
            provider_mode=self.mode,
            detail={"path": str(out)},
        )


def create_push_provider(mode: str, *, sink_dir: Path | None = None) -> PushProvider:
    validate_provider_mode(mode)
    if mode == "STUB":
        return StubPushProvider()
    if mode == "MOCK_IN_MEMORY":
        return InMemoryMockPushProvider()
    if mode == "LOCAL_FILE_SINK":
        if sink_dir is None:
            raise ValueError("LOCAL_FILE_SINK requires sink_dir")
        return LocalFileSinkPushProvider(sink_dir)
    refuse_production_notification_credentials(mode)
    raise AssertionError("unreachable")


def refuse_apns_config(config: dict[str, Any]) -> None:
    """Explicit trap for production APNs wiring attempts."""
    assert_no_production_credential_material(config)
    keys = {str(k).upper() for k in config}
    if keys & {"KEY_ID", "TEAM_ID", "AUTH_KEY", "P8", "PRODUCTION"}:
        refuse_apns_production_key()
    refuse_apns_production_key()


def refuse_fcm_config(config: dict[str, Any]) -> None:
    """Explicit trap for production FCM wiring attempts."""
    assert_no_production_credential_material(config)
    refuse_fcm_production_server_key()
