"""Alert builder and lineage tests."""

from __future__ import annotations

import pytest

from backend.nexus_public_mobile_notify.alerts import (
    PublicAlertLineage,
    data_stale_alert,
    decision_status_alert,
    demo_lineage,
    market_anomaly_alert,
    risk_alert,
    thesis_invalidated_alert,
)
from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation


def test_all_alert_kinds_build_with_demo_lineage():
    lineage = demo_lineage()
    decision = decision_status_alert(
        decision_id="dec_1",
        status="RECORDED",
        title="Decision recorded",
        body="Your decision was recorded.",
        deep_link="nexus://app/decision_detail?decision_id=dec_1",
        lineage=lineage,
    )
    assert decision.kind == "DECISION_STATUS"
    assert decision.lineage.mode == "DEMO_DATA"
    assert "strategy_id" not in decision.to_dict()["public_payload"]

    risk = risk_alert(
        decision_id="dec_1",
        risk_code="CONCENTRATION",
        severity="HIGH",
        title="Risk elevated",
        body="Concentration risk elevated.",
        deep_link="nexus://app/risks?decision_id=dec_1",
        lineage=lineage,
    )
    assert risk.kind == "RISK"

    stale = data_stale_alert(
        dataset="market_overview",
        stale_age_seconds=900,
        title="Data stale",
        body="Market overview is stale.",
        deep_link="nexus://app/alerts?focus=stale",
        lineage=lineage,
    )
    assert stale.kind == "DATA_STALE"

    thesis = thesis_invalidated_alert(
        decision_id="dec_1",
        thesis_id="th_9",
        reason_code="COUNTER_EVIDENCE",
        title="Thesis invalidated",
        body="Counter-evidence crossed threshold.",
        deep_link="nexus://app/thesis_monitor?decision_id=dec_1",
        lineage=lineage,
    )
    assert thesis.kind == "THESIS_INVALIDATED"

    anomaly = market_anomaly_alert(
        symbol="BTCUSDT",
        anomaly_code="VOLUME_SPIKE",
        title="Market anomaly",
        body="Volume spike detected.",
        deep_link="nexus://app/markets",
        lineage=lineage,
    )
    assert anomaly.kind == "MARKET_ANOMALY"


def test_private_field_in_payload_refused():
    from backend.nexus_public_mobile_notify.alerts.models import build_alert

    lineage = demo_lineage()
    with pytest.raises(HardBanViolation, match="strategy_id"):
        build_alert(
            kind="DECISION_STATUS",
            title="x",
            body="y",
            deep_link="nexus://app/alerts",
            lineage=lineage,
            public_payload={"strategy_id": "secret"},
        )


def test_live_fabricated_demo_freshness_refused():
    from backend.nexus_public_mobile_notify.alerts.models import build_alert

    bad = PublicAlertLineage(
        source_system="DEMO_PREVIEW",
        source_endpoint="demo://x",
        as_of="2026-08-05T00:00:00Z",
        retrieved_at="2026-08-05T00:00:00Z",
        freshness="DEMO_DATA",
        completeness="DEMO_DATA",
        lineage_id="bad",
        mode="LIVE",
    )
    with pytest.raises(HardBanViolation, match="fabricated live alert"):
        build_alert(
            kind="RISK",
            title="x",
            body="y",
            deep_link="nexus://app/risks",
            lineage=bad,
        )


def test_data_stale_requires_stale_freshness_in_live():
    live_fresh = PublicAlertLineage(
        source_system="public_decision_cloud",
        source_endpoint="/v1/freshness",
        as_of="2026-08-05T00:00:00Z",
        retrieved_at="2026-08-05T00:00:00Z",
        freshness="FRESH",
        completeness="COMPLETE",
        lineage_id="live_1",
        mode="LIVE",
    )
    with pytest.raises(HardBanViolation, match="DATA_STALE"):
        data_stale_alert(
            dataset="markets",
            stale_age_seconds=10,
            title="stale",
            body="stale",
            deep_link="nexus://app/alerts",
            lineage=live_fresh,
        )
