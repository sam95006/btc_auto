"""V18-F Shadow Decision Ledger and Learning Bridge — focused tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_lesson_compiler.fixtures import REFLECTION_FIXTURES
from backend.nexus_shadow_decision_ledger.artifacts import (
    build_summary_payload,
    write_immutable_artifacts,
)
from backend.nexus_shadow_decision_ledger.constants import (
    HARD_BANS,
    LIFECYCLE_STATES,
    PUBLIC_FIELD_INVARIANTS,
)
from backend.nexus_shadow_decision_ledger.contracts import (
    ShadowDecisionContractError,
    build_empty_record,
)
from backend.nexus_shadow_decision_ledger.ledger import ShadowDecisionLedger, ShadowLedgerError
from backend.nexus_shadow_decision_ledger.learning_bridge import (
    LearningBridgeError,
    ShadowLearningBridge,
)
from backend.nexus_shadow_decision_ledger.lifecycle import InvalidShadowTransitionError


def _populate(rec, *, kind: str = "WAIT") -> None:
    rec.market_snapshot = {
        "symbol": "BTCUSDT",
        "mark_price": 65000.0,
        "data_quality_status": "OK",
        "data_class": "FIXTURE",
    }
    rec.universe_decision = {"eligible": True, "reason": "fixture_universe"}
    rec.candidate = {"symbol": "BTCUSDT", "score": 0.42, "side_bias": "NEUTRAL"}
    rec.ai_suggestion = {"kind": kind, "confidence": 0.51, "rationale": "fixture"}
    rec.critic = {"verdict": "CAUTION", "notes": ["fixture_critic"]}
    rec.deterministic_risk = {"status": "PASS", "max_leverage": 0, "blocks": []}
    rec.final_shadow_decision = {
        "kind": kind,
        "entry_price": 65000.0,
        "stop_price": 64000.0,
        "target_price": 67000.0,
    }
    rec.subsequent_outcome = None
    rec.costs = {"estimated_fee_bps": 2.0, "cost_gate_status": "PASS"}
    rec.invalidation = None
    rec.process_classification = None


def test_lifecycle_happy_path_and_shadow_opened_virtual_only() -> None:
    ledger = ShadowDecisionLedger()
    rec = build_empty_record("SD-001")
    _populate(rec)
    ledger.create(rec)
    lc = ledger.lifecycle("SD-001")
    lc.advance_full_happy_path(prefix="t1")
    assert lc.state == "REFLECTED"
    assert set(LIFECYCLE_STATES) == {
        "OBSERVED",
        "CANDIDATE",
        "REVIEWED",
        "SHADOW_READY",
        "SHADOW_OPENED",
        "SHADOW_MANAGING",
        "SHADOW_CLOSED",
        "OUTCOME_PENDING",
        "OUTCOME_RECORDED",
        "REFLECTION_PENDING",
        "REFLECTED",
    }
    opened = ledger.get("SD-001")
    assert opened.virtual_research_position is True
    assert opened.actual_ordered is False
    assert opened.actual_filled is False
    assert opened.exchange_order_id is None
    pub = opened.public_view()
    assert pub["actual_ordered"] is False
    assert pub["actual_filled"] is False
    assert pub["exchange_order_id"] is None


def test_invalid_transition_fail_closed() -> None:
    ledger = ShadowDecisionLedger()
    rec = build_empty_record("SD-002")
    _populate(rec)
    ledger.create(rec)
    lc = ledger.lifecycle("SD-002")
    with pytest.raises(InvalidShadowTransitionError):
        lc.transition("SHADOW_OPENED", reason="skip", idempotency_key="bad")


def test_public_invariants_reject_order_truth() -> None:
    ledger = ShadowDecisionLedger()
    rec = build_empty_record("SD-003")
    _populate(rec)
    ledger.create(rec)
    with pytest.raises(ShadowDecisionContractError):
        ledger.attempt_set_actual_ordered("SD-003", True)
    with pytest.raises(ShadowLedgerError):
        ledger.attempt_exchange_order(symbol="BTCUSDT")
    counts = ledger.counts()
    assert counts["actual_ordered_count"] == 0
    assert counts["exchange_write_attempt_count"] == 0
    assert ledger.get("SD-003").actual_ordered is False


def test_persist_all_required_fields_and_seal_immutability(tmp_path: Path) -> None:
    path = tmp_path / "shadow_ledger.jsonl"
    ledger = ShadowDecisionLedger(storage_path=path)
    rec = build_empty_record("SD-004")
    _populate(rec, kind="ABSTAIN")
    ledger.create(rec)
    lc = ledger.lifecycle("SD-004")
    # Advance to SHADOW_OPENED then fill outcome path fields before seal.
    for i, nxt in enumerate(
        [
            "CANDIDATE",
            "REVIEWED",
            "SHADOW_READY",
            "SHADOW_OPENED",
            "SHADOW_MANAGING",
            "SHADOW_CLOSED",
            "OUTCOME_PENDING",
        ]
    ):
        lc.transition(nxt, reason=nxt, idempotency_key=f"p:{i}")
    ledger.update_fields(
        "SD-004",
        subsequent_outcome={"net_pnl": -12.5, "is_real_performance": False},
        invalidation={"occurred": False},
        costs={"estimated_fee_bps": 2.5, "cost_gate_status": "PASS"},
    )
    lc.transition("OUTCOME_RECORDED", reason="outcome", idempotency_key="p:out")
    lc.transition("REFLECTION_PENDING", reason="refl", idempotency_key="p:rp")
    lc.transition("REFLECTED", reason="done", idempotency_key="p:rf")
    sealed = ledger.seal("SD-004")
    assert sealed.sealed is True
    assert sealed.content_hash
    ledger.assert_immutable("SD-004")
    with pytest.raises(ShadowLedgerError):
        ledger.update_fields("SD-004", critic={"verdict": "REWRITE"})
    # Reload from JSONL
    ledger2 = ShadowDecisionLedger(storage_path=path)
    assert "SD-004" in {r.shadow_decision_id for r in ledger2.list_records()}


def test_learning_bridge_candidate_only_and_counters() -> None:
    ledger = ShadowDecisionLedger()
    rec = build_empty_record("SD-005")
    _populate(rec, kind="LONG")
    ledger.create(rec)
    lc = ledger.lifecycle("SD-005")
    for i, nxt in enumerate(["CANDIDATE", "REVIEWED", "SHADOW_READY", "SHADOW_OPENED"]):
        lc.transition(nxt, reason=nxt, idempotency_key=f"b:{i}")
    ledger.update_fields(
        "SD-005",
        subsequent_outcome={"net_pnl": -8.0, "is_real_performance": False},
        costs={"estimated_fee_bps": 3.0, "cost_gate_status": "PASS"},
    )
    bridge = ShadowLearningBridge(ledger)
    classification = bridge.classify_process(
        "SD-005",
        packet={
            "entry_price": 65000.0,
            "stop_price": 64000.0,
            "target_price": 67000.0,
            "cost_gate_status": "PASS",
            "data_quality_status": "OK",
            "net_pnl": -8.0,
        },
    )
    assert "process_class" in classification
    refs = bridge.attach_counterfactual_ref(
        "SD-005",
        counterfactual_id="CF-SHADOW-001",
        outcome={"pnl": 10.0, "is_counterfactual": True, "is_real_performance": False},
    )
    assert "CF-SHADOW-001" in refs
    lesson = bridge.compile_lesson_candidate("SD-005", reflection=REFLECTION_FIXTURES[0])
    assert lesson["status"] == "CANDIDATE"
    assert lesson["active"] is False
    assert ledger.get("SD-005").lesson_candidate_refs
    bridge.refuse_active_lesson("SD-005", REFLECTION_FIXTURES[1])
    mem = bridge.seal_memory_nodes("SD-005", as_of_ms=1_700_000_000_000)
    assert mem["decision_node_id"]
    counts = ledger.counts()
    assert counts["active_lesson_count"] == 0
    assert bridge.active_lesson_count == 0
    assert bridge.candidate_lesson_count >= 1
    # No successful actual orders
    assert counts["actual_ordered_count"] == 0


def test_learning_bridge_rejects_active_status() -> None:
    ledger = ShadowDecisionLedger()
    rec = build_empty_record("SD-006")
    _populate(rec)
    ledger.create(rec)
    bridge = ShadowLearningBridge(ledger)
    with pytest.raises(LearningBridgeError):
        bridge.compile_lesson_candidate(
            "SD-006",
            reflection=REFLECTION_FIXTURES[0],
            forced_status="ACTIVE",
        )
    assert ledger.counts()["active_lesson_count"] == 0


def test_hard_bans_and_artifacts(tmp_path: Path) -> None:
    assert "no_active_lessons" in HARD_BANS
    assert "no_exchange_write" in HARD_BANS
    assert "no_demo_orders" in HARD_BANS
    assert PUBLIC_FIELD_INVARIANTS["exchange_order_id"] is None
    payload = build_summary_payload(
        tip_sha="deadbeef",
        counts={
            "active_lesson_count": 0,
            "actual_ordered_count": 0,
            "actual_filled_count": 0,
            "exchange_write_attempt_count": 0,
            "shadow_decision_count": 1,
        },
        tests={"passed": 1, "failed": 0},
    )
    assert payload["active_lesson_count"] == 0
    assert payload["actual_ordered_count"] == 0
    # Write under tmp as repo root stand-in
    out = write_immutable_artifacts(tmp_path, payload)
    assert out.exists()
