"""Read-only protection order observability + verdict tests."""
from __future__ import annotations

from backend.nexus_research.demo_autonomous.protection_evidence import (
    classify_protection_orders,
)
from backend.nexus_research.demo_exchange.readers import (
    _parse_order,
    normalize_order_status,
)


def _pos(**kwargs):
    base = {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "size": 0.026,
        "positionIdx": 0,
        "avgPrice": 63392.3,
    }
    base.update(kwargs)
    return base


def _ord(**kwargs):
    base = {
        "orderId": "o1",
        "orderLinkId": "l1",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "qty": 0.026,
        "orderStatus": "Untriggered",
        "status": "Untriggered",
        "reduceOnly": True,
        "closeOnTrigger": True,
        "positionIdx": 0,
        "triggerPrice": 62439.6,
        "triggerBy": "MarkPrice",
        "stopOrderType": "StopLoss",
    }
    base.update(kwargs)
    return base


def test_orderview_retains_protection_fields():
    row = {
        "orderId": "abc",
        "orderLinkId": "lnk",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "orderType": "Market",
        "stopOrderType": "TakeProfit",
        "triggerPrice": "64816.7",
        "triggerDirection": "1",
        "triggerBy": "MarkPrice",
        "qty": "0.026",
        "leavesQty": "0.026",
        "cumExecQty": "0",
        "avgPrice": "0",
        "reduceOnly": True,
        "closeOnTrigger": True,
        "positionIdx": 0,
        "orderStatus": "Untriggered",
        "createdTime": "1",
        "updatedTime": "2",
        "takeProfit": "64816.7",
        "stopLoss": "",
        "tpTriggerBy": "MarkPrice",
        "slTriggerBy": "",
        "tpslMode": "Full",
    }
    view = _parse_order(row)
    d = view.to_dict()
    assert d["stopOrderType"] == "TakeProfit"
    assert d["triggerPrice"] == 64816.7
    assert d["reduceOnly"] is True
    assert d["closeOnTrigger"] is True
    assert d["positionIdx"] == 0
    assert d["orderType"] == "Market"
    assert d["triggerBy"] == "MarkPrice"
    assert d["normalizedOrderStatus"] == "Untriggered"
    assert d["stopLoss"] is None  # missing → null, not fake 0
    assert d["leavesQty"] == 0.026
    assert d["cumExecQty"] == 0.0


def test_status_and_orderstatus_normalization():
    assert normalize_order_status("Untriggered") == "Untriggered"
    assert normalize_order_status(None, "Untriggered") == "Untriggered"
    assert normalize_order_status("New") == "New"
    assert normalize_order_status("Cancelled") == "Cancelled"
    assert normalize_order_status("canceled") == "Cancelled"
    assert normalize_order_status("Filled") == "Filled"
    assert normalize_order_status("") == "UNKNOWN"
    assert normalize_order_status("???") == "UNKNOWN"


def test_api_like_open_orders_all_exposed_and_current_compatible():
    orders = [
        _ord(orderId="sl", stopOrderType="StopLoss", triggerPrice=62439.6),
        _ord(orderId="tp", stopOrderType="TakeProfit", triggerPrice=64816.7),
    ]
    model = classify_protection_orders(orders, [_pos()])
    assert len(model["openOrders"]) == 2
    assert model["openOrders"][0]["orderId"] == "sl"
    # currentOrder compatibility is ops_status concern; group must see both
    assert model["protectionGroups"][0]["stopLossOrder"]["orderId"] == "sl"
    assert model["protectionGroups"][0]["takeProfitOrder"]["orderId"] == "tp"
    assert model["protectionVerdict"] == "PROTECTED_VERIFIED"


def test_two_conditional_orders_form_tp_sl_group():
    model = classify_protection_orders(
        [
            _ord(orderId="tp", stopOrderType="TakeProfitStopOrder", triggerPrice=64816.7),
            _ord(orderId="sl", stopOrderType="StopLoss", triggerPrice=62439.6),
        ],
        [_pos()],
    )
    g = model["protectionGroups"][0]
    assert g["takeProfitOrder"] is not None
    assert g["stopLossOrder"] is not None
    assert g["coverageComplete"] is True
    assert model["protectionVerdict"] == "PROTECTED_VERIFIED"


def test_bybit_trading_stop_aggregate_mode():
    model = classify_protection_orders(
        [],
        [_pos(takeProfit=64816.7, stopLoss=62439.6)],
    )
    assert model["protectionGroups"][0]["tradingStopMode"] is True
    assert model["protectionVerdict"] == "PROTECTED_VERIFIED"


def test_full_qty_coverage_protected_verified():
    model = classify_protection_orders(
        [
            _ord(stopOrderType="TakeProfit", qty=0.026, triggerPrice=64816.7),
            _ord(orderId="sl", stopOrderType="StopLoss", qty=0.026, triggerPrice=62439.6),
        ],
        [_pos(size=0.026)],
    )
    assert model["protectionVerdict"] == "PROTECTED_VERIFIED"


def test_only_sl_partial():
    model = classify_protection_orders(
        [_ord(stopOrderType="StopLoss", triggerPrice=62439.6)],
        [_pos()],
    )
    assert model["protectionVerdict"] == "PARTIALLY_PROTECTED"


def test_only_tp_partial():
    model = classify_protection_orders(
        [_ord(stopOrderType="TakeProfit", triggerPrice=64816.7)],
        [_pos()],
    )
    assert model["protectionVerdict"] == "PARTIALLY_PROTECTED"


def test_qty_insufficient_partial():
    model = classify_protection_orders(
        [
            _ord(stopOrderType="TakeProfit", qty=0.01, closeOnTrigger=False, triggerPrice=64816.7),
            _ord(orderId="sl", stopOrderType="StopLoss", qty=0.01, closeOnTrigger=False, triggerPrice=62439.6),
        ],
        [_pos(size=0.026)],
    )
    assert model["protectionVerdict"] == "PARTIALLY_PROTECTED"
    assert model["protectionGroups"][0]["coverageComplete"] is False


def test_missing_reduce_only_ambiguous():
    model = classify_protection_orders(
        [
            _ord(
                stopOrderType="TakeProfit",
                reduceOnly=None,
                closeOnTrigger=None,
                triggerPrice=64816.7,
            ),
            _ord(
                orderId="sl",
                stopOrderType="StopLoss",
                reduceOnly=None,
                closeOnTrigger=None,
                triggerPrice=62439.6,
            ),
        ],
        [_pos()],
    )
    assert model["protectionVerdict"] == "AMBIGUOUS"


def test_cancelled_not_protection():
    model = classify_protection_orders(
        [
            _ord(stopOrderType="TakeProfit", orderStatus="Cancelled", status="Cancelled", triggerPrice=64816.7),
            _ord(orderId="sl", stopOrderType="StopLoss", orderStatus="Cancelled", status="Cancelled", triggerPrice=62439.6),
        ],
        [_pos()],
    )
    assert model["protectionVerdict"] == "UNPROTECTED"


def test_reverse_side_not_protection():
    model = classify_protection_orders(
        [
            _ord(side="Buy", stopOrderType="TakeProfit", triggerPrice=64816.7),
            _ord(orderId="sl", side="Buy", stopOrderType="StopLoss", triggerPrice=62439.6),
        ],
        [_pos(side="Buy")],
    )
    assert model["protectionVerdict"] == "AMBIGUOUS"
    assert model["protectionGroups"][0]["reverseExposureRisk"] is True


def test_flat_not_applicable():
    model = classify_protection_orders([_ord()], [])
    assert model["protectionVerdict"] == "FLAT_NOT_APPLICABLE"
    assert model["protectionStatus"] == "NONE"


def test_status_key_alone_detects_untriggered():
    """Regression: DTO used status while old checker looked at orderStatus."""
    model = classify_protection_orders(
        [
            {
                "orderId": "tp",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "qty": 0.026,
                "status": "Untriggered",
                "stopOrderType": "TakeProfit",
                "triggerPrice": 64816.7,
                "reduceOnly": True,
                "closeOnTrigger": True,
                "positionIdx": 0,
            },
            {
                "orderId": "sl",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "qty": 0.026,
                "status": "Untriggered",
                "stopOrderType": "StopLoss",
                "triggerPrice": 62439.6,
                "reduceOnly": True,
                "closeOnTrigger": True,
                "positionIdx": 0,
            },
        ],
        [_pos()],
    )
    assert model["protectionVerdict"] == "PROTECTED_VERIFIED"


def test_ops_status_exposes_all_open_orders(monkeypatch):
    from backend.nexus_research.demo_autonomous import ops_status as osmod

    class _Snap:
        def to_dict(self):
            return {
                "status": "SNAPSHOT_OK",
                "positions": [_pos()],
                "open_orders": [
                    _ord(orderId="sl", stopOrderType="StopLoss", triggerPrice=62439.6),
                    _ord(orderId="tp", stopOrderType="TakeProfit", triggerPrice=64816.7),
                ],
                "total_equity": 5000,
                "available_balance": 5000,
                "fingerprint": "abcd",
                "review_flags": [],
            }

    monkeypatch.setattr(
        "backend.nexus_research.demo_exchange.account_snapshot.capture_account_snapshot",
        lambda: _Snap(),
    )
    monkeypatch.setattr(osmod, "get_ops_store", lambda: osmod.AutonomousOpsStore())
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.controller.get_autonomous_controller",
        lambda: type(
            "C",
            (),
            {
                "to_dict": lambda self: {
                    "running": True,
                    "health": {},
                    "currentCycleId": "c1",
                    "lastCycleProgressAtMs": 1,
                }
            },
        )(),
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.session_authorization.get_authorization_validator",
        lambda: type("A", (), {"session": None})(),
    )
    monkeypatch.setattr(
        "backend.nexus_research.demo_autonomous.session_authorization.autonomous_enabled_from_env",
        lambda: False,
    )
    st = osmod.build_operations_status(include_snapshot=True)
    assert st["openOrderCount"] == 2
    assert len(st["openOrders"]) == 2
    assert st["currentOrder"]["orderId"] == "sl"
    assert st["protectionVerdict"] == "PROTECTED_VERIFIED"
    assert len(st["protectionGroups"]) == 1
