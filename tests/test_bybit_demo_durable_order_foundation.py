from decimal import Decimal

from backend.nexus_demo_execution.durable_order_ledger import make_order_link_id
from backend.nexus_demo_execution.order_reconciliation import exchange_state


def test_order_link_id_is_deterministic_and_bybit_safe():
    one = make_order_link_id("campaign-a", "decision-a", "intent-a")
    two = make_order_link_id("campaign-a", "decision-a", "intent-a")
    assert one == two
    assert len(one) <= 36
    assert one.startswith("nx-")


def test_exchange_state_uses_actual_partial_quantity():
    state, exchange = exchange_state(
        {"orderStatus": "PartiallyFilled", "qty": "10", "cumExecQty": "4", "avgPrice": "100"}
    )
    assert state == "PARTIALLY_FILLED"
    assert exchange["filled_qty"] == Decimal("4")
    assert exchange["remaining_qty"] == Decimal("6")


def test_exchange_state_does_not_treat_ack_as_fill():
    state, exchange = exchange_state({"orderStatus": "New", "qty": "10", "cumExecQty": "0"})
    assert state == "NEW"
    assert exchange["filled_qty"] == Decimal("0")
