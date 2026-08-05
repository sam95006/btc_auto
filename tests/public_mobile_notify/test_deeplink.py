"""Deep-link routing tests."""

from __future__ import annotations

import pytest

from backend.nexus_public_mobile_notify.deeplink import DeepLinkRouter
from backend.nexus_public_mobile_notify.hard_bans import HardBanViolation


def test_build_parse_roundtrip():
    router = DeepLinkRouter()
    target = router.build("decision_detail", decision_id="dec_9")
    assert target.uri == "nexus://app/decision_detail?decision_id=dec_9"
    parsed = router.parse(target.uri)
    assert parsed.route == "decision_detail"
    assert parsed.params["decision_id"] == "dec_9"


def test_for_alert_routing():
    router = DeepLinkRouter()
    assert router.for_alert(kind="DECISION_STATUS", decision_id="d1").route == "decision_detail"
    assert router.for_alert(kind="RISK").route == "risks"
    assert router.for_alert(kind="DATA_STALE").params["focus"] == "stale"
    assert router.for_alert(kind="THESIS_INVALIDATED", decision_id="d1").route == "thesis_monitor"
    assert router.for_alert(kind="MARKET_ANOMALY").route == "markets"


def test_private_routes_refused():
    router = DeepLinkRouter()
    with pytest.raises(HardBanViolation):
        router.parse("nexus://app/founder")
    with pytest.raises(HardBanViolation):
        router.parse("nexus://app/wallet")
    with pytest.raises(ValueError):
        router.build("not_a_route")


def test_private_param_keys_refused():
    router = DeepLinkRouter()
    with pytest.raises(HardBanViolation):
        router.build("alerts", strategy_id="s1")
