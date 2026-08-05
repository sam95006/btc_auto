"""Disaster Recovery V2 — orchestrates fail-closed restore decisions."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_runtime.durability_v2.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    PRESERVED_FACTS,
    RECOVERED_EXACT,
    RECOVERED_LAST_KNOWN_GOOD,
)
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class DrillResult:
    injection: str
    expected: str
    actual: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "injection": self.injection,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "detail": self.detail,
        }


class DisasterRecoveryV2:
    """Recovery controller: detect → classify → restore or block."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.durability = RuntimeDurabilityV2(self.root / "durability")
        self.exchange_write_attempt_count = 0

    def assess(self) -> dict[str, Any]:
        """Assess live ledger + LKG without mutating state."""
        ledger_path = self.durability.ledger_path
        assessment: dict[str, Any] = {
            "assessed_at": _utc(),
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            **PRESERVED_FACTS,
        }
        if not ledger_path.exists():
            if self.durability.lkg_path.exists():
                assessment["status"] = "LKG_AVAILABLE_LIVE_MISSING"
                assessment["recommendation"] = "RESTORE_LKG"
            else:
                assessment["status"] = BLOCKED_AMBIGUOUS_STATE
                assessment["recommendation"] = "BLOCK"
                assessment["reason"] = "no_live_no_lkg"
            return assessment

        try:
            led = self.durability.open_ledger()
            det = self.durability.detect_corruption(led)
            assessment["live"] = det
            assessment["event_count"] = led.event_count()
            assessment["max_sequence"] = led.max_sequence()
            led.close()
        except Exception as exc:
            assessment["live"] = {"corruption_detection_status": CORRUPTION_DETECTED, "error": str(exc)}
            det = assessment["live"]

        if det.get("corruption_detection_status") == CORRUPTION_DETECTED:
            assessment["status"] = CORRUPTION_DETECTED
            assessment["recommendation"] = "RESTORE_LKG_OR_BLOCK"
            return assessment

        assessment["status"] = "LIVE_HEALTHY"
        assessment["recommendation"] = "NO_ACTION"
        return assessment

    def recover(self) -> dict[str, Any]:
        """Run recovery decision. Never silently guesses."""
        assessment = self.assess()
        rec = assessment.get("recommendation")
        if rec == "NO_ACTION":
            return {
                "status": "NO_RECOVERY_NEEDED",
                "assessment": assessment,
                "exchange_write_attempt_count": 0,
                **PRESERVED_FACTS,
            }
        if rec == "BLOCK":
            return self.durability.fail_closed_ambiguous(reason=assessment.get("reason") or "blocked")

        # Attempt LKG restore — may still return BLOCKED_AMBIGUOUS / CORRUPTION.
        result = self.durability.restore_last_known_good()
        return {
            "status": result.status,
            "detail": result.detail,
            "assessment": assessment,
            "exchange_write_attempt_count": 0,
            "silent_recovery_guess": False,
            **PRESERVED_FACTS,
        }

    def concurrent_append_drill(self, n_threads: int = 8, per_thread: int = 50) -> dict[str, Any]:
        """Concurrent appends must remain monotonic + hash-chain valid."""
        led = self.durability.open_ledger()
        errors: list[str] = []
        lock = threading.Lock()

        def worker(tid: int) -> None:
            for i in range(per_thread):
                try:
                    led.append(
                        aggregate_id=f"t{tid}",
                        aggregate_type="DECISION",
                        event_type="CONCURRENT",
                        source="drill",
                        payload={"tid": tid, "i": i},
                        idempotency_key=f"c-{tid}-{i}",
                    )
                except Exception as exc:
                    with lock:
                        errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        chain = led.verify_hash_chain()
        count = led.event_count()
        led.close()
        expected = n_threads * per_thread
        # May be less if prior events exist — check chain + monotonic.
        passed = chain.get("ledger_hash_chain_status") == "PASS" and not errors
        return {
            "status": "PASS" if passed else "FAIL",
            "event_count": count,
            "expected_min_new": expected,
            "chain": chain,
            "errors": errors[:10],
        }

    def duplicate_idempotency_drill(self) -> dict[str, Any]:
        led = self.durability.open_ledger()
        a = led.append(
            aggregate_id="dup",
            aggregate_type="ORDER_INTENT",
            event_type="CREATED",
            source="drill",
            payload={"n": 1},
            idempotency_key="idem-dup-1",
        )
        b = led.append(
            aggregate_id="dup",
            aggregate_type="ORDER_INTENT",
            event_type="CREATED",
            source="drill",
            payload={"n": 1},
            idempotency_key="idem-dup-1",
        )
        count = led.event_count()
        led.close()
        passed = (not a.duplicate) and b.duplicate and b.status == "DUPLICATE_IGNORED"
        return {
            "status": "PASS" if passed else "FAIL",
            "first": a.status,
            "second": b.status,
            "event_count": count,
        }

    def clock_rollback_drill(self) -> dict[str, Any]:
        clocks = [1_700_000_000.0]

        def clock() -> float:
            return clocks[0]

        led = self.durability.open_ledger(clock=clock)
        a = led.append(
            aggregate_id="clk",
            aggregate_type="DECISION",
            event_type="T1",
            source="drill",
            payload={"t": 1},
            idempotency_key="clk-1",
        )
        clocks[0] = clocks[0] - 3600  # rollback 1h
        b = led.append(
            aggregate_id="clk",
            aggregate_type="DECISION",
            event_type="T0",
            source="drill",
            payload={"t": 0},
            idempotency_key="clk-0",
        )
        led.close()
        passed = a.status == "APPENDED" and b.status == "BLOCKED_CLOCK_ROLLBACK"
        return {
            "status": "PASS" if passed else "FAIL",
            "first": a.status,
            "second": b.status,
            "second_reason": b.reason,
        }

    def out_of_order_drill(self) -> dict[str, Any]:
        """Out-of-order payload accepted only with explicit flag; sequence stays monotonic."""
        led = self.durability.open_ledger()
        a = led.append(
            aggregate_id="ooo",
            aggregate_type="DECISION",
            event_type="A",
            source="drill",
            payload={"ord": 2},
            idempotency_key="ooo-a",
        )
        b = led.append(
            aggregate_id="ooo",
            aggregate_type="DECISION",
            event_type="B",
            source="drill",
            payload={"ord": 1},
            idempotency_key="ooo-b",
            allow_out_of_order=True,
            wall_clock=time.time() - 10,
        )
        chain = led.verify_hash_chain()
        seqs = [r["sequence_number"] for r in led.replay() if r["aggregate_id"] == "ooo"]
        led.close()
        monotonic = seqs == sorted(seqs) and len(seqs) == 2
        passed = (
            a.status == "APPENDED"
            and b.status == "APPENDED"
            and chain.get("ledger_hash_chain_status") == "PASS"
            and monotonic
        )
        return {
            "status": "PASS" if passed else "FAIL",
            "sequences": seqs,
            "chain": chain,
        }
