"""Write-path repair tests: Demo allowlist, stage classification, qty rounding."""
from __future__ import annotations

import pytest

from backend.nexus_research.demo_autonomous.account_mode import DemoMarginModeCompatibility
from backend.nexus_research.demo_autonomous.session_authorization import AuthorizationValidator
from backend.nexus_research.demo_autonomous.write_adapter import (
    AutonomousDemoOrderAdapter,
    round_qty_to_step,
)
from backend.nexus_research.demo_autonomous.write_trace import (
    DEMO_UNSUPPORTED_WRITE_PATHS,
    BybitDemoErrorClassifier,
    WriteFailureClass,
    WriteStage,
)
from backend.nexus_research.demo_autonomous.write_transport import (
    DEMO_BLOCKED_CLASSIC_PATHS,
    DemoWriteTransport,
)
from backend.nexus_research.demo_exchange.errors import WriteForbiddenError
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner
from backend.nexus_research.demo_execution.intent import DemoOrderIntent


def test_switch_isolated_not_on_demo_allowlist():
    assert "/v5/position/switch-isolated" in DEMO_UNSUPPORTED_WRITE_PATHS
    assert "/v5/position/switch-isolated" in DEMO_BLOCKED_CLASSIC_PATHS


def test_transport_blocks_switch_isolated():
    auth = AuthorizationValidator()
    auth.issue(ttl_ms=60_000)
    t = DemoWriteTransport(signer=DemoRequestSigner("k", "s"), auth=auth, dry_run=True)
    with pytest.raises(WriteForbiddenError):
        t.post("/v5/position/switch-isolated", {"symbol": "BTCUSDT", "tradeMode": 1})


def test_classifier_marks_switch_isolated_as_demo_unsupported():
    c = BybitDemoErrorClassifier()
    cls = c.classify(
        stage=WriteStage.STEP_2_VERIFY_OR_SET_MARGIN_MODE,
        endpoint_path="/v5/position/switch-isolated",
        ret_code=10005,
        ret_msg="Permission denied",
        account_type="UNIFIED",
    )
    assert cls == WriteFailureClass.ENDPOINT_NOT_ON_DEMO_ALLOWLIST


def test_ensure_isolated_skips_classic_path_dry_run():
    auth = AuthorizationValidator()
    auth.issue(ttl_ms=60_000)
    t = DemoWriteTransport(signer=DemoRequestSigner("k", "s"), auth=auth, dry_run=True)
    ad = AutonomousDemoOrderAdapter(t, auth=auth)
    # Without get_json, margin unknown → calls set-margin-mode (demo supported)
    res = ad.ensure_isolated("BTCUSDT", 25)
    assert res.path == "/v5/account/set-margin-mode"
    assert res.ok
    assert any(
        s.endpoint_path == "/v5/position/switch-isolated" and s.ret_msg and "SKIPPED" in s.ret_msg
        for s in ad.last_trace.stages
    )


def test_qty_round_btc():
    assert round_qty_to_step(0.025822, 0.001, 0.001) == 0.025
    assert round_qty_to_step(0.0004, 0.001, 0.001) == 0.0


def test_margin_compat():
    m = DemoMarginModeCompatibility()
    assert m.already_isolated("ISOLATED_MARGIN", None) is True
    assert m.needs_switch("REGULAR_MARGIN") is True


def test_place_order_omits_reduce_only_false():
    auth = AuthorizationValidator()
    auth.issue(ttl_ms=60_000)
    posted: list[dict] = []

    class Capturing(DemoWriteTransport):
        def post(self, path, body):  # type: ignore[override]
            posted.append(dict(body))
            return super().post(path, body)

    t = Capturing(signer=DemoRequestSigner("k", "s"), auth=auth, dry_run=True)
    ad = AutonomousDemoOrderAdapter(t, auth=auth)
    intent = DemoOrderIntent(
        intent_id="t1",
        symbol="BTCUSDT",
        side="Buy",
        qty=0.001,
        leverage=25,
        entry_price=100000,
        stop_loss_price=98500,
        take_profit_price=103000,
        risk_tier="VALIDATION",
        client_order_id="nxa-testlinkid000001",
        source="test",
    )
    ad.place_order(intent, reduce_only=False)
    assert posted and "reduceOnly" not in posted[0]
    assert posted[0]["positionIdx"] == 0
