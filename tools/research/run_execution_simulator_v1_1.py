#!/usr/bin/env python3
"""Smoke + status package writer for NEXUS Autonomous Execution Simulator V1.1."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.execution_models_v1_1 import FILL_POLICY_DOC
from backend.nexus_autonomy.execution_simulator_v1_1 import AutonomousExecutionSimulatorV1_1

OUT = ROOT / "artifacts/readiness/immutable/autonomous_execution_simulator_v1_1"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> dict:
    sim = AutonomousExecutionSimulatorV1_1(max_positions=1, max_intents=1, leverage=25, margin_usdt=20.0)
    sim.assert_no_exchange_write_api()
    create = sim.create_order(
        {
            "idempotency_key": "v11-smoke",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "index_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    fill = sim.try_fill(
        create["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=100,
        index_price=100,
    )
    dup = sim.create_order(
        {
            "idempotency_key": "v11-smoke",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "market",
            "qty": 0.1,
            "mark_price": 100,
            "margin_mode": "ISOLATED",
        }
    )
    amb = AutonomousExecutionSimulatorV1_1(max_positions=1, max_intents=1)
    ao = amb.create_order(
        {
            "idempotency_key": "amb",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "stop-market",
            "qty": 0.1,
            "mark_price": 100,
            "stop_price": 99.5,
            "margin_mode": "ISOLATED",
        }
    )
    ambiguous = amb.try_fill(
        ao["order_id"],
        market_bid=99.4,
        market_ask=100.1,
        last_price=100,
        path_low=99,
        path_high=101,
        mark_price=99.4,
        index_price=99.4,
        same_bar_stop=99.5,
        same_bar_target=100.5,
    )
    # touch ≠ fill
    lim = AutonomousExecutionSimulatorV1_1(max_positions=1, max_intents=1)
    lo = lim.create_order(
        {
            "idempotency_key": "touch",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "limit",
            "qty": 0.1,
            "price": 100.0,
            "mark_price": 100.5,
            "margin_mode": "ISOLATED",
        }
    )
    touch = lim.try_fill(
        lo["order_id"],
        market_bid=99.9,
        market_ask=100.1,
        last_price=100.0,
        path_low=100.0,
        path_high=100.2,
        mark_price=100.0,
        index_price=100.0,
    )
    report = sim.report()
    ok = (
        create.get("status") == "ACCEPTED"
        and fill.get("status") == "FILLED"
        and dup.get("status") == "DUPLICATE_IGNORED"
        and ambiguous.get("status") == "BLOCKED_AMBIGUOUS"
        and touch.get("status") == "UNFILLED"
        and report["exchange_write_attempt_count"] == 0
    )
    status = {
        "schema": "autonomous_execution_simulator_v1_1",
        "Execution_V1_1_status": "PASS" if ok else "IMPLEMENTATION_INVALID",
        "execution_status": "NEXUS_AUTONOMOUS_EXECUTION_SIMULATOR_V1_1_PASS" if ok else "FAIL",
        "fill_policy": FILL_POLICY_DOC,
        "immutable_risk": {
            "max_positions_default": 2,
            "max_intents_default": 2,
            "bounded": {"max_positions": 1, "max_intents": 1, "margin_usdt": 20},
            "leverage": 25,
            "margin_mode": "ISOLATED",
            "ceiling": 50,
            "forbidden": ["100x", "cross", "martingale", "averaging_down", "stop_widening"],
        },
        "smoke": {
            "create": create,
            "fill": fill,
            "dup": dup,
            "ambiguous": ambiguous,
            "touch_alone": touch,
        },
        "report": report,
        "created_at": _utc(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "execution_status.json"
    path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(path), "Execution_V1_1_status": status["Execution_V1_1_status"]}, indent=2))
    return status


if __name__ == "__main__":
    main()
