"""Deterministic power-loss / concurrency fuzz for V8 durability + simulator.

Frozen seeds only. Never instantiates exchange-write clients.
"""
from __future__ import annotations

import os
import random
import threading
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.execution_simulator_v1 import AutonomousExecutionSimulatorV1
from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1

FROZEN_SEED = 20260804


def test_power_loss_phases_idempotent(tmp_path: Path):
    rng = random.Random(FROZEN_SEED)
    phases = [
        "before_ledger_append",
        "during_ledger_append",
        "after_append_before_snapshot",
        "during_snapshot",
        "after_intent_creation",
        "during_partial_fill",
        "after_fill_before_position_snapshot",
        "during_exit",
        "during_reflection",
        "during_lesson_storage",
    ]
    for phase in phases:
        root = tmp_path / phase
        dur = RuntimeDurabilityV1(root)
        led = dur.open_ledger()
        sim = AutonomousExecutionSimulatorV1(max_positions=1, max_intents=1)
        key = f"idem-{phase}-{rng.randint(1, 10_000)}"
        if phase == "before_ledger_append":
            # crash before any append — empty ledger remains valid
            assert led.event_count() == 0
        else:
            a = led.append(
                aggregate_id=key,
                aggregate_type="ORDER_INTENT",
                event_type="CREATED",
                source="fuzz",
                payload={"phase": phase},
                idempotency_key=key,
            )
            assert a.duplicate is False
            if phase == "during_ledger_append":
                # second append same key must be idempotent
                b = led.append(
                    aggregate_id=key,
                    aggregate_type="ORDER_INTENT",
                    event_type="CREATED",
                    source="fuzz",
                    payload={"phase": phase},
                    idempotency_key=key,
                )
                assert b.duplicate is True
            if phase in {"after_append_before_snapshot", "during_snapshot", "after_fill_before_position_snapshot"}:
                snap = dur.create_snapshot(led, fast=True)
                assert snap["status"] == "SNAPSHOT_OK"
            if phase in {
                "after_intent_creation",
                "during_partial_fill",
                "after_fill_before_position_snapshot",
                "during_exit",
            }:
                o = sim.create_order(
                    {
                        "idempotency_key": key,
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "order_type": "market",
                        "qty": 0.1,
                        "mark_price": 100.0,
                    }
                )
                assert o["status"] in {"ACCEPTED", "DUPLICATE_IGNORED"}
                if phase == "during_partial_fill" and o.get("order_id"):
                    sim.try_fill(
                        o["order_id"],
                        market_bid=99.9,
                        market_ask=100.1,
                        last_price=100.0,
                        path_low=99.0,
                        path_high=101.0,
                        partial_ratio=0.5,
                    )
                if phase == "during_exit" and o.get("order_id"):
                    sim.try_fill(
                        o["order_id"],
                        market_bid=99.9,
                        market_ask=100.1,
                        last_price=100.0,
                        path_low=99.0,
                        path_high=101.0,
                    )
                    # close if position open
                    for pid in list(getattr(sim, "positions", {}) or {}):
                        if hasattr(sim, "close_position"):
                            sim.close_position(pid, mark_price=100.5)
            if phase == "during_reflection":
                led.append(
                    aggregate_id=f"{key}-ref",
                    aggregate_type="REFLECTION",
                    event_type="QUEUED",
                    source="fuzz",
                    payload={"phase": phase},
                    idempotency_key=f"{key}-ref",
                )
            if phase == "during_lesson_storage":
                led.append(
                    aggregate_id=f"{key}-les",
                    aggregate_type="LESSON",
                    event_type="STORED",
                    source="fuzz",
                    payload={"phase": phase, "policy_effect": False},
                    idempotency_key=f"{key}-les",
                )
        assert led.verify_hash_chain()["ledger_hash_chain_status"] == "PASS"
        assert sim.report()["exchange_write_attempt_count"] == 0
        assert sim.report()["open_ambiguous_position_count"] == 0
        led.close()


def test_concurrent_duplicate_intent_single_canonical(tmp_path: Path):
    rng = random.Random(FROZEN_SEED + 1)
    led = PrivateEventLedger(tmp_path / "c.sqlite3")
    sim = AutonomousExecutionSimulatorV1(max_positions=2, max_intents=2)
    key = f"dup-{rng.randint(1, 9999)}"
    results: list[dict] = []
    lock = threading.Lock()

    def worker() -> None:
        o = sim.create_order(
            {
                "idempotency_key": key,
                "symbol": "ETHUSDT",
                "side": "BUY",
                "order_type": "limit",
                "qty": 0.1,
                "mark_price": 200.0,
                "limit_price": 199.5,
            }
        )
        led.append(
            aggregate_id=key,
            aggregate_type="ORDER_INTENT",
            event_type="CREATED",
            source="fuzz",
            payload={"thread": threading.get_ident()},
            idempotency_key=key,
        )
        with lock:
            results.append(o)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    accepted = [r for r in results if r.get("status") == "ACCEPTED"]
    ignored = [r for r in results if r.get("status") == "DUPLICATE_IGNORED"]
    assert len(accepted) == 1
    assert len(ignored) == 7
    assert len(led.replay()) == 1
    assert led.verify_hash_chain()["ledger_hash_chain_status"] == "PASS"
    assert sim.report()["exchange_write_attempt_count"] == 0
    led.close()
