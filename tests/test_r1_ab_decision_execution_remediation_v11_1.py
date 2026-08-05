"""TWO-PASS negative tests for FOUNDER R1 A/B Decision↔Execution remediation.

Each critical finding ID has Pass-1 focused + Pass-2 adversarial coverage.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from backend.nexus_decision import (
    DecisionExecutionBridge,
    DecisionExecutionBridgeError,
    DecisionLifecycleError,
    DecisionLifecycleOrchestrator,
    VALID_TRANSITIONS,
)
from backend.nexus_decision.evidence import hash_evidence_blob
from backend.nexus_decision.execution_bridge import (
    BRIDGE_MODULE,
    FORBIDDEN_DECISION_POSITION,
    assert_decision_position_compatible,
)
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_execution.risk_gates import FORBIDDEN_ACTIONS
from backend.nexus_strategy_engine import cost_semantics


REPO = Path(__file__).resolve().parents[1]
ORCH_PATH = REPO / "backend" / "nexus_decision" / "orchestrator.py"
BRIDGE_PATH = REPO / "backend" / "nexus_decision" / "execution_bridge.py"


def _fresh_evidence(n: int = 2, age: float = 10.0) -> dict:
    blobs = {f"ev_{i}": f"blob-{i}-payload" for i in range(n)}
    ids = list(blobs.keys())
    hashes = [hash_evidence_blob(blobs[i]) for i in ids]
    return {
        "evidence_ids": ids,
        "evidence_hashes": hashes,
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": age, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts"],
            "present_fields": ["mid", "spread", "ts"],
        },
    }


def _observe(orch: DecisionLifecycleOrchestrator, key: str = "obs", **overrides):
    ev = _fresh_evidence()
    return orch.observe(
        candidate_id=overrides.get("candidate_id", "cand_1"),
        market_context_id=overrides.get("market_context_id", "mctx_1"),
        point_in_time_timestamp=overrides.get("point_in_time_timestamp", "2026-08-05T00:00:00Z"),
        evidence_ids=ev["evidence_ids"],
        evidence_hashes=ev["evidence_hashes"],
        data_freshness=ev["data_freshness"],
        data_completeness=ev["data_completeness"],
        idempotency_key=key,
        evidence_blobs=ev.get("evidence_blobs"),
        decision_id=overrides.get("decision_id"),
    )


def _to_challenged(orch: DecisionLifecycleOrchestrator, did: str, prefix: str) -> None:
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key=f"{prefix}-u")
    orch.challenge(did, independent_critic_output={"verdict": "ok"}, idempotency_key=f"{prefix}-c")


# ---------------------------------------------------------------------------
# Pass 1 — focused negative / authority traps
# ---------------------------------------------------------------------------


def test_pass1_ci_trap_no_decorative_intent_or_position_mint() -> None:
    """AUTH_DECISION_MINTS_INTENT_ID / AUTH_DECISION_MINTS_POSITION_ID."""
    text = ORCH_PATH.read_text(encoding="utf-8")
    assert not re.search(r'intent_id\s*=\s*.*f["\']intent_', text)
    assert not re.search(r'intent_id\s*=\s*.*["\']intent_', text)
    assert not re.search(r'position_id\s*=\s*.*f["\']pos_', text)
    assert not re.search(r'position_id\s*=\s*.*["\']pos_', text)
    assert "intent_{" not in text
    assert "pos_{" not in text
    assert BRIDGE_PATH.is_file()
    assert "execution_bridge" in BRIDGE_PATH.name


def test_pass1_auth_no_decision_execution_bridge_module_exists() -> None:
    """AUTH_NO_DECISION_EXECUTION_BRIDGE."""
    assert BRIDGE_PATH.is_file()
    from backend.nexus_decision import execution_bridge as eb

    assert eb.BRIDGE_SCHEMA.startswith("nexus_decision_execution_bridge")
    assert "NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1" in eb.__doc__ or eb.ADAPTER_ID


def test_pass1_risk_bypass_forbidden_action_rejected(tmp_path: Path) -> None:
    """AUTH_DECISION_RISK_BYPASS — opaque allowed=True cannot bypass FORBIDDEN_ACTIONS."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="risk-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "risk")
    banned = sorted(FORBIDDEN_ACTIONS)[0]
    out = orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        execution_intent={
            "idempotency_key": "risk_forbidden_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
            "requested_actions": (banned,),
        },
        idempotency_key="risk-d",
    )
    assert out["status"] == "REJECTED"
    assert out["decision"]["intent_id"] is None


def test_pass1_cost_model_version_bound_on_approve(tmp_path: Path) -> None:
    """AUTH_COST_MODEL_VERSION_MISMATCH / AUTH_DECISION_NO_COST_VERSION_BIND."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="cost-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "cost")
    with pytest.raises(DecisionLifecycleError, match="cost_model_version_mismatch"):
        orch.decide(
            did,
            deterministic_risk_result={"allowed": True},
            cost_model_version="totally-invented-parallel-v9",
            idempotency_key="cost-bad",
        )
    # Fresh decision for happy bind (prior may be mid-flight).
    did2 = _observe(orch, key="cost-obs-2", candidate_id="cand_cost2")["decision"]["decision_id"]
    _to_challenged(orch, did2, "cost2")
    ok = orch.decide(
        did2,
        deterministic_risk_result={"allowed": True},
        cost_model_version=COST_MODEL_VERSION,
        idempotency_key="cost-ok",
    )
    assert ok["status"] == "APPROVED_SIMULATED"
    assert ok["decision"]["cost_model_version"] == COST_MODEL_VERSION
    assert cost_semantics.COST_MODEL_VERSION == COST_MODEL_VERSION


def test_pass1_vocab_monitoring_cannot_skip_exit(tmp_path: Path) -> None:
    """VOCAB_MONITORING_SKIP_EXIT."""
    assert "UNDER_REVIEW" not in VALID_TRANSITIONS["MONITORING"]
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="skip-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "skip")
    orch.decide(did, deterministic_risk_result={"allowed": True}, idempotency_key="skip-d")
    orch.record(did, idempotency_key="skip-r")
    with pytest.raises(DecisionLifecycleError):
        orch.review(did, idempotency_key="skip-rev")


def test_pass1_approved_twice_same_candidate_fail_closed(tmp_path: Path) -> None:
    """ADV_DECISION_APPROVED_TWICE."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    d1 = _observe(orch, key="ap1", candidate_id="SAME_CAND")["decision"]["decision_id"]
    d2 = _observe(orch, key="ap2", candidate_id="SAME_CAND")["decision"]["decision_id"]
    _to_challenged(orch, d1, "a1")
    _to_challenged(orch, d2, "a2")
    first = orch.decide(d1, deterministic_risk_result={"allowed": True}, idempotency_key="a1-d")
    assert first["status"] == "APPROVED_SIMULATED"
    with pytest.raises(DecisionLifecycleError, match="candidate_already_approved"):
        orch.decide(d2, deterministic_risk_result={"allowed": True}, idempotency_key="a2-d")


# ---------------------------------------------------------------------------
# Pass 2 — adversarial / cross-lane
# ---------------------------------------------------------------------------


def test_pass2_intent_replay_after_restart_bound_to_order_intent(tmp_path: Path) -> None:
    """ADV_INTENT_REPLAY_AFTER_RESTART."""
    root = tmp_path / "replay"
    orch = DecisionLifecycleOrchestrator(root)
    did = _observe(orch, key="ir-obs", decision_id="dec_intent_replay")["decision"]["decision_id"]
    _to_challenged(orch, did, "ir")
    approved = orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        execution_intent={
            "idempotency_key": "owned_intent_key_ir",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        idempotency_key="ir-d",
    )
    intent_before = approved["decision"]["intent_id"]
    assert intent_before == "owned_intent_key_ir"
    assert intent_before in orch.bridge.simulator.intent_owners

    orch2 = DecisionLifecycleOrchestrator(root)
    recovered = orch2.recover(did)
    assert recovered["decision"]["intent_id"] == intent_before
    replay = orch2.decide(
        did,
        deterministic_risk_result={"allowed": True},
        idempotency_key="ir-d",
    )
    assert replay["status"] == "APPROVED_SIMULATED"
    recorded = orch2.record(did, idempotency_key="ir-r")
    assert recorded["status"] == "MONITORING"
    assert intent_before in orch2.bridge.simulator.intent_owners
    assert recorded["decision"]["position_id"]
    assert recorded["decision"]["linkage_authority"] == BRIDGE_MODULE


def test_pass2_partial_fill_during_decision_transition_fail_closed(tmp_path: Path) -> None:
    """ADV_PARTIAL_FILL_DURING_DECISION_TRANSITION."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="pf-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "pf")
    orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        execution_intent={
            "idempotency_key": "pf_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        idempotency_key="pf-d",
    )
    binding = orch.bridge.binding_for(did)
    assert binding and binding.order_id
    # Force a partial fill on the bound order while still APPROVED_SIMULATED.
    fill = orch.bridge.adapter.try_fill(
        binding.order_id,
        market_bid=99.0,
        market_ask=101.0,
        last_price=100.0,
        path_low=98.0,
        path_high=102.0,
        partial_ratio=0.4,
    )
    assert fill.get("status") == "PARTIALLY_FILLED"
    blocked = orch.record(did, idempotency_key="pf-r")
    assert blocked["status"] == "BLOCKED_AMBIGUOUS"
    assert "partial_fill" in (blocked.get("blocked_reason") or "")


def test_pass2_position_closed_decision_monitoring_blocked(tmp_path: Path) -> None:
    """ADV_POSITION_CLOSED_DECISION_MONITORING."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="pcdm-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "pcdm")
    orch.decide(did, deterministic_risk_result={"allowed": True}, idempotency_key="pcdm-d")
    orch.record(did, idempotency_key="pcdm-r")
    binding = orch.bridge.binding_for(did)
    assert binding and binding.position_id
    pos = orch.bridge.simulator.positions[binding.position_id]
    pos.state = "CLOSED"
    pos.qty = Decimal("0")
    out = orch.monitor(did, exit=False, idempotency_key="pcdm-hb")
    assert out["status"] == "BLOCKED_AMBIGUOUS"


def test_pass2_decision_closed_position_open_blocked(tmp_path: Path) -> None:
    """ADV_DECISION_CLOSED_POSITION_OPEN."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="dcpo-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "dcpo")
    orch.decide(did, deterministic_risk_result={"allowed": True}, idempotency_key="dcpo-d")
    orch.record(did, idempotency_key="dcpo-r")
    # Cannot skip EXITED.
    with pytest.raises(DecisionLifecycleError):
        orch.review(did, idempotency_key="dcpo-rev")
    # Even with forced CLOSED probe while position open:
    with pytest.raises(DecisionExecutionBridgeError):
        assert_decision_position_compatible("CLOSED", "OPEN")
    assert ("CLOSED", "OPEN") in FORBIDDEN_DECISION_POSITION


def test_pass2_same_bar_stop_target_blocks_via_canonical_engine(tmp_path: Path) -> None:
    """ADV_SAME_BAR_STOP_TARGET."""
    orch = DecisionLifecycleOrchestrator(tmp_path)
    did = _observe(orch, key="sb-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "sb")
    orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        execution_intent={
            "idempotency_key": "sb_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        idempotency_key="sb-d",
    )
    probe = orch.bridge.apply_same_bar_probe(did, stop=95, target=105, mark_price=100)
    assert probe["blocked_ambiguous"] is True
    assert probe["status"] == "BLOCKED_AMBIGUOUS"
    # Decision must not advance to MONITORING after same-bar block on the bound order.
    out = orch.record(did, idempotency_key="sb-r")
    assert out["status"] == "BLOCKED_AMBIGUOUS"


def test_pass2_adv_cost_model_version_mismatch_reject(tmp_path: Path) -> None:
    """ADV_COST_MODEL_VERSION_MISMATCH."""
    bridge = DecisionExecutionBridge(tmp_path / "bridge")
    with pytest.raises(DecisionExecutionBridgeError, match="cost_model_version_mismatch"):
        bridge.approve_intent(
            decision_id="d1",
            candidate_id="c1",
            intent_req={
                "idempotency_key": "c_intent",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "MARKET",
                "qty": Decimal("0.1"),
            },
            cost_model_version="NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1_PARALLEL",
        )
    # Legacy proxy label migrates onto canonical (no parallel formula).
    binding = bridge.approve_intent(
        decision_id="d2",
        candidate_id="c2",
        intent_req={
            "idempotency_key": "c_intent2",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        cost_model_version="NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1",
    )
    assert binding.cost_model_version == COST_MODEL_VERSION
