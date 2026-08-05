"""Push provider stub/mock tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_mobile_notify.alerts import decision_status_alert, demo_lineage
from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation
from backend.nexus_public_mobile_notify.push import (
    DeviceRegistration,
    InMemoryMockPushProvider,
    create_push_provider,
)


def _alert():
    return decision_status_alert(
        decision_id="dec_42",
        status="MONITORING",
        title="Monitoring",
        body="Decision is being monitored.",
        deep_link="nexus://app/decision_detail?decision_id=dec_42",
        lineage=demo_lineage(),
    )


def test_stub_and_mock_providers(tmp_path: Path):
    device = DeviceRegistration(
        device_id="dev_1",
        platform="ios",
        push_token="local-demo-token",
        app_environment="local",
    )
    stub = create_push_provider("STUB")
    rec = stub.send(alert=_alert(), device=device)
    assert rec.status == "STUB_ACCEPTED"
    assert rec.provider_mode == "STUB"

    mock = InMemoryMockPushProvider()
    rec2 = mock.send(alert=_alert(), device=device)
    assert rec2.status == "MOCK_DELIVERED"
    assert len(mock.deliveries) == 1

    sink = create_push_provider("LOCAL_FILE_SINK", sink_dir=tmp_path)
    rec3 = sink.send(alert=_alert(), device=device)
    assert rec3.status == "FILE_SINK_WRITTEN"
    assert list(tmp_path.glob("*.json"))


def test_production_device_environment_refused():
    device = DeviceRegistration(
        device_id="dev_x",
        platform="android",
        push_token="tok",
        app_environment="production",
    )
    stub = create_push_provider("STUB")
    with pytest.raises(HardBanViolation, match="production"):
        stub.send(alert=_alert(), device=device)
