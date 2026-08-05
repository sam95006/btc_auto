"""Adversarial cross-lane scenarios for FOUNDER R1 Decision + Execution review."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from tools.review.r1_decision_execution.lane_loader import LaneImportContext, LaneRoots, resolve_lane_roots


@dataclass
class ScenarioResult:
    scenario_id: str
    title: str
    expected_fail_closed: bool
    observed_fail_closed: bool
    lane_a_covered: bool
    lane_b_covered: bool
    cross_lane_invariant_enforced: bool
    false_pass: bool
    missing_negative_test: bool
    severity: str  # critical | high | medium | info
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "expected_fail_closed": self.expected_fail_closed,
            "observed_fail_closed": self.observed_fail_closed,
            "lane_a_covered": self.lane_a_covered,
            "lane_b_covered": self.lane_b_covered,
            "cross_lane_invariant_enforced": self.cross_lane_invariant_enforced,
            "false_pass": self.false_pass,
            "missing_negative_test": self.missing_negative_test,
            "severity": self.severity,
            "detail": self.detail,
            "evidence": self.evidence,
        }


def _fresh_evidence(n: int = 2, age: float = 10.0) -> dict[str, Any]:
    from backend.nexus_decision.evidence import hash_evidence_blob

    blobs = {f"ev{i}": f"blob-{i}-payload".encode("utf-8") for i in range(n)}
    ids = list(blobs)
    hashes = [hash_evidence_blob(blobs[i]) for i in ids]
    return {
        "evidence_ids": ids,
        "evidence_hashes": hashes,
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": age, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mark", "index"],
            "present_fields": ["mark", "index"],
        },
    }


def _observe(orch: Any, key: str = "obs", **overrides: Any) -> dict[str, Any]:
    ev = _fresh_evidence()
    ev.update(overrides.pop("evidence", {}))
    return orch.observe(
        candidate_id=overrides.pop("candidate_id", "cand_r1"),
        market_context_id=overrides.pop("market_context_id", "mkt_r1"),
        point_in_time_timestamp=overrides.pop("point_in_time_timestamp", "2026-08-05T00:00:00Z"),
        evidence_ids=ev["evidence_ids"],
        evidence_hashes=ev["evidence_hashes"],
        data_freshness=ev["data_freshness"],
        data_completeness=ev["data_completeness"],
        idempotency_key=key,
        evidence_blobs=ev.get("evidence_blobs"),
        decision_id=overrides.pop("decision_id", None),
        **overrides,
    )


def _to_approved(orch: Any, did: str, prefix: str) -> dict[str, Any]:
    orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key=f"{prefix}-u")
    orch.challenge(did, independent_critic_output={"verdict": "ok"}, idempotency_key=f"{prefix}-c")
    return orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        idempotency_key=f"{prefix}-d",
    )


def _lane_a_test_names(roots: LaneRoots) -> set[str]:
    path = roots.lane_a / "tests" / "test_decision_lifecycle_v11.py"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return set(__import__("re").findall(r"def (test_\w+)", text))


def _lane_b_test_names(roots: LaneRoots) -> set[str]:
    path = roots.lane_b / "tests" / "test_execution_microstructure_realism_v11.py"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return set(__import__("re").findall(r"def (test_\w+)", text))


def scenario_decision_approved_twice(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_decision.orchestrator import DecisionLifecycleError, DecisionLifecycleOrchestrator

    orch = DecisionLifecycleOrchestrator(tmp / "appr2")
    out = _observe(orch, key="ap2-obs")
    did = out["decision"]["decision_id"]
    first = _to_approved(orch, did, "ap2a")
    assert first["status"] == "APPROVED_SIMULATED"
    # Same decide key → idempotent (fail-closed against double mutation).
    again_same = orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        idempotency_key="ap2a-d",
    )
    same_ok = again_same["status"] == "APPROVED_SIMULATED"
    # Different key must not re-approve / mint a second intent.
    second_key_blocked = False
    try:
        orch.decide(
            did,
            deterministic_risk_result={"allowed": True},
            idempotency_key="ap2b-d",
        )
    except DecisionLifecycleError:
        second_key_blocked = True
    intent_ids = {orch.get(did)["decision"]["intent_id"]}
    # Candidate-level double observe (different keys) creates two approvals for same candidate.
    orch2 = DecisionLifecycleOrchestrator(tmp / "appr2b")
    d1 = _observe(orch2, key="cand-dup-1", candidate_id="SAME_CAND")["decision"]["decision_id"]
    d2 = _observe(orch2, key="cand-dup-2", candidate_id="SAME_CAND")["decision"]["decision_id"]
    _to_approved(orch2, d1, "cd1")
    _to_approved(orch2, d2, "cd2")
    two_approvals_same_candidate = d1 != d2 and len(
        {
            orch2.get(d1)["decision"]["intent_id"],
            orch2.get(d2)["decision"]["intent_id"],
        }
    ) == 2

    observed = same_ok and second_key_blocked
    # Gap: no candidate uniqueness → dual approval path is a false-PASS for "approved twice".
    false_pass = two_approvals_same_candidate
    covered = "test_idempotent_transition_replay" in a_tests
    missing = "approved_twice_same_candidate" not in " ".join(a_tests)
    return ScenarioResult(
        scenario_id="ADV_DECISION_APPROVED_TWICE",
        title="Decision approved twice",
        expected_fail_closed=True,
        observed_fail_closed=observed and not two_approvals_same_candidate,
        lane_a_covered=covered,
        lane_b_covered=False,
        cross_lane_invariant_enforced=False,
        false_pass=false_pass,
        missing_negative_test=missing,
        severity="critical" if false_pass else "high",
        detail=(
            "Per-decision idempotency blocks re-approve with a new key, but nothing prevents "
            "two Decision Objects approving the same candidate_id with distinct intent_ids."
        ),
        evidence={
            "same_key_idempotent": same_ok,
            "different_key_blocked": second_key_blocked,
            "intent_ids_single_decision": list(intent_ids),
            "two_approvals_same_candidate": two_approvals_same_candidate,
        },
    )


def scenario_reopened_after_close(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_decision.orchestrator import DecisionLifecycleError, DecisionLifecycleOrchestrator

    orch = DecisionLifecycleOrchestrator(tmp / "reopen")
    out = _observe(orch, key="re-obs")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "re")
    orch.record(did, idempotency_key="re-r")
    orch.monitor(did, exit=True, idempotency_key="re-m")
    orch.review(did, idempotency_key="re-rev")
    orch.calibrate(did, lesson_ids=["L1"], idempotency_key="re-cal")
    orch.improve(did, idempotency_key="re-imp")
    assert orch.get(did)["state"] == "CLOSED"
    blocked = False
    try:
        orch.understand(did, AI_reasoner_outputs=[{"v": 1}], idempotency_key="reopen-u")
    except DecisionLifecycleError:
        blocked = True
    # No reopen API; CLOSED transitions empty.
    return ScenarioResult(
        scenario_id="ADV_DECISION_REOPENED_AFTER_CLOSE",
        title="Decision reopened after close",
        expected_fail_closed=True,
        observed_fail_closed=blocked,
        lane_a_covered="test_invalid_transition_fail_closed" in a_tests
        or "test_property_transition_closure" in a_tests,
        lane_b_covered=False,
        cross_lane_invariant_enforced=False,
        false_pass=not blocked,
        missing_negative_test="reopen" not in " ".join(a_tests).lower(),
        severity="info" if blocked else "critical",
        detail="CLOSED is terminal; reopen attempts fail closed. Explicit reopen negative test still missing.",
        evidence={"reopen_blocked": blocked, "final_state": orch.get(did)["state"]},
    )


def scenario_intent_replay_after_restart(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_decision.orchestrator import DecisionLifecycleOrchestrator

    root = tmp / "intent_replay"
    orch = DecisionLifecycleOrchestrator(root)
    out = _observe(orch, key="ir-obs", decision_id="dec_intent_replay")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "ir")
    intent_before = orch.get(did)["decision"]["intent_id"]
    orch2 = DecisionLifecycleOrchestrator(root)
    recovered = orch2.recover(did)
    intent_after = recovered["decision"]["intent_id"]
    # Replay decide with same key.
    replay = orch2.decide(
        did,
        deterministic_risk_result={"allowed": True},
        idempotency_key="ir-d",
    )
    # Record advances and mints position_id — Intent never bound to OrderIntent.
    recorded = orch2.record(did, idempotency_key="ir-r")
    from backend.nexus_execution.execution_simulator_v1_1 import build_default_simulator

    sim = build_default_simulator()
    # Decision intent_id is not an OrderIntent.idempotency_key in the simulator.
    exec_has_intent = any(
        o.intent.idempotency_key == intent_after for o in sim.orders.values()
    )

    bound = intent_before == intent_after and intent_after is not None
    cross = bound and exec_has_intent
    return ScenarioResult(
        scenario_id="ADV_INTENT_REPLAY_AFTER_RESTART",
        title="Intent replay after restart",
        expected_fail_closed=True,
        observed_fail_closed=bound and replay["status"] == "APPROVED_SIMULATED",
        lane_a_covered="test_checkpoint_and_restart_recovery" in a_tests,
        lane_b_covered="duplicate_intent" in " ".join(b_tests),
        cross_lane_invariant_enforced=cross,
        false_pass=bound and not exec_has_intent,
        missing_negative_test=True,
        severity="critical",
        detail=(
            "Decision intent_id survives restart and decide replay is idempotent, but the Intent "
            "is a string token unbound to OrderIntent.idempotency_key — execution has zero knowledge of it."
        ),
        evidence={
            "intent_before": intent_before,
            "intent_after": intent_after,
            "replay_status": replay["status"],
            "position_id": recorded["decision"].get("position_id"),
            "execution_has_matching_order_intent": exec_has_intent,
        },
    )


def scenario_partial_fill_during_transition(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    """Partial fill while Decision is mid-transition — no coupling exists."""
    from backend.nexus_decision.orchestrator import DecisionLifecycleOrchestrator
    from backend.nexus_execution.book_model_v11 import generate_synthetic_book
    from backend.nexus_execution.microstructure_realism_v11.adapter import MicrostructureExecutionAdapterV11

    orch = DecisionLifecycleOrchestrator(tmp / "pf")
    out = _observe(orch, key="pf-obs")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "pf")
    # Mid transition: APPROVED_SIMULATED, not yet MONITORING.
    adapter = MicrostructureExecutionAdapterV11()
    created = adapter.create_order(
        {
            "idempotency_key": "exec_intent_pf",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    book = generate_synthetic_book(
        symbol="BTCUSDT",
        mid=Decimal("100"),
        tick=Decimal("0.1"),
        seed=42,
        age_ms=10,
    )
    fill = adapter.try_fill_with_book(
        created["order_id"],
        book,
        apply_impact=True,
        partial_ratio=Decimal("0.4"),
    )
    decision_state = orch.get(did)["state"]
    decision_aware = orch.get(did)["decision"].get("intent_id") == "exec_intent_pf"
    # Invariant should block Decision advancing while partial fill in-flight — not enforced.
    advanced = orch.record(did, idempotency_key="pf-r")
    return ScenarioResult(
        scenario_id="ADV_PARTIAL_FILL_DURING_DECISION_TRANSITION",
        title="Partial fill during Decision transition",
        expected_fail_closed=True,
        observed_fail_closed=False,
        lane_a_covered=False,
        lane_b_covered="partial_fill" in " ".join(b_tests).lower()
        or "test_scenario_kinds_cover_contracts" in b_tests,
        cross_lane_invariant_enforced=False,
        false_pass=True,
        missing_negative_test=True,
        severity="critical",
        detail=(
            "Lane B can partially fill while Decision sits in APPROVED_SIMULATED; Decision freely "
            "advances to MONITORING and mints an unrelated position_id. No joint lock."
        ),
        evidence={
            "decision_state_before_record": decision_state,
            "decision_state_after_record": advanced["status"],
            "fill_status": fill.get("status"),
            "decision_bound_to_exec_intent": decision_aware,
            "decision_position_id": advanced["decision"].get("position_id"),
            "exec_order_id": created.get("order_id"),
        },
    )


def scenario_same_bar_stop_target(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_execution.fill_engine import BarContext
    from backend.nexus_execution.fill_engine import try_fill as fill_try
    from backend.nexus_execution.execution_simulator_v1_1 import build_default_simulator
    from backend.nexus_decision.orchestrator import DecisionLifecycleOrchestrator

    sim = build_default_simulator()
    created = sim.create_order(
        {
            "idempotency_key": "sb_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    assert created.get("status") == "ACCEPTED", created
    order = sim.orders[created["order_id"]]
    spec = sim.instruments[order.intent.symbol]
    bar = BarContext(
        bar_index=1,
        open_price=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        mark_price_age_ms=1,
        same_bar_stop=Decimal("95"),
        same_bar_target=Decimal("105"),
    )
    outcome = fill_try(order, spec, bar)
    blocked = outcome.status == "BLOCKED_AMBIGUOUS"
    # Decision MONITORING has no awareness of same-bar block.
    orch = DecisionLifecycleOrchestrator(tmp / "sb")
    out = _observe(orch, key="sb-obs")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "sb")
    orch.record(did, idempotency_key="sb-r")
    hb = orch.monitor(did, exit=False, idempotency_key="sb-hb")
    decision_continues = hb["status"] == "MONITORING"
    return ScenarioResult(
        scenario_id="ADV_SAME_BAR_STOP_TARGET",
        title="Same-bar stop/target",
        expected_fail_closed=True,
        observed_fail_closed=blocked and not decision_continues,  # joint fail-closed desired
        lane_a_covered=False,
        lane_b_covered="same_bar" in " ".join(b_tests).lower()
        or "test_scenario_kinds_cover_contracts" in b_tests,
        cross_lane_invariant_enforced=False,
        false_pass=blocked and decision_continues,
        missing_negative_test=True,
        severity="high",
        detail=(
            "Fill engine blocks same-bar stop/target (adverse-first), but Decision MONITORING "
            "heartbeat proceeds with no linkage to the blocked order."
        ),
        evidence={
            "fill_status": outcome.status,
            "fill_reason": outcome.reject_reason,
            "decision_monitoring": decision_continues,
        },
    )


def scenario_cost_model_version_mismatch(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_execution.cost_model import COST_MODEL_VERSION
    from backend.nexus_decision.orchestrator import DecisionLifecycleOrchestrator

    # Probe strategy proxy version on review base if present.
    review_root = Path(__file__).resolve().parents[3]
    other_versions: list[str] = []
    for path in review_root.joinpath("backend").rglob("*.py"):
        if "nexus_execution" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "NEXUS_CONSERVATIVE_EXECUTION_PROXY" in text:
            import re

            for m in re.finditer(r'"(NEXUS_CONSERVATIVE_EXECUTION_PROXY[^"]*)"', text):
                other_versions.append(m.group(1))
            for m in re.finditer(r'COST_MODEL_VERSION\s*=\s*"([^"]+)"', text):
                other_versions.append(m.group(1))
    other_versions = sorted(set(other_versions) - {COST_MODEL_VERSION})
    mismatch = len(other_versions) > 0

    orch = DecisionLifecycleOrchestrator(tmp / "cost")
    out = _observe(orch, key="cost-obs")
    did = out["decision"]["decision_id"]
    # Approval succeeds without cost version binding — false PASS if mismatch exists.
    approved = _to_approved(orch, did, "cost")
    binds = "cost_model_version" in json.dumps(approved["decision"])
    return ScenarioResult(
        scenario_id="ADV_COST_MODEL_VERSION_MISMATCH",
        title="Cost model version mismatch",
        expected_fail_closed=True,
        observed_fail_closed=False if mismatch else (not mismatch),
        lane_a_covered=False,
        lane_b_covered=False,
        cross_lane_invariant_enforced=False,
        false_pass=mismatch and not binds,
        missing_negative_test=True,
        severity="critical" if mismatch else "high",
        detail=(
            f"Canonical COST_MODEL_VERSION={COST_MODEL_VERSION}; divergent versions={other_versions}. "
            "Decision approval does not bind or reject on cost version."
        ),
        evidence={
            "canonical_cost_model_version": COST_MODEL_VERSION,
            "divergent_versions": other_versions,
            "decision_binds_cost_version": binds,
            "approval_status": approved["status"],
        },
    )


def scenario_position_closed_decision_monitoring(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_decision.orchestrator import DecisionLifecycleOrchestrator
    from backend.nexus_execution.contracts import PositionRecord

    orch = DecisionLifecycleOrchestrator(tmp / "pc_dm")
    out = _observe(orch, key="pcdm-obs")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "pcdm")
    orch.record(did, idempotency_key="pcdm-r")
    decision_pos = orch.get(did)["decision"]["position_id"]
    # Simulate independent position close under execution authority.
    pos = PositionRecord(
        position_id=str(decision_pos),
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("0"),
        avg_entry_price=Decimal("100"),
        leverage=1,
        margin_usdt=Decimal("0"),
        state="CLOSED",
    )
    # Decision still MONITORING — no check against PositionRecord.
    hb = orch.monitor(did, exit=False, idempotency_key="pcdm-hb")
    illegal = hb["status"] == "MONITORING" and pos.state == "CLOSED"
    return ScenarioResult(
        scenario_id="ADV_POSITION_CLOSED_DECISION_MONITORING",
        title="Position closed but Decision still monitoring",
        expected_fail_closed=True,
        observed_fail_closed=False,
        lane_a_covered=False,
        lane_b_covered=False,
        cross_lane_invariant_enforced=False,
        false_pass=illegal,
        missing_negative_test=True,
        severity="critical",
        detail=(
            "Forbidden combination Position CLOSED + Decision MONITORING is constructible because "
            "Decision position_id is a decorative string, not a PositionRecord reference."
        ),
        evidence={
            "decision_state": hb["status"],
            "position_state": pos.state,
            "position_id": decision_pos,
        },
    )


def scenario_decision_closed_position_open(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_decision.orchestrator import DecisionLifecycleOrchestrator
    from backend.nexus_execution.contracts import PositionRecord

    orch = DecisionLifecycleOrchestrator(tmp / "dc_po")
    out = _observe(orch, key="dcpo-obs")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "dcpo")
    orch.record(did, idempotency_key="dcpo-r")
    # Skip EXITED: MONITORING → UNDER_REVIEW → CLOSED
    orch.review(did, idempotency_key="dcpo-rev")
    orch.improve(did, idempotency_key="dcpo-imp")  # UNDER_REVIEW → CLOSED allowed
    assert orch.get(did)["state"] == "CLOSED"
    decision_pos = orch.get(did)["decision"]["position_id"]
    pos = PositionRecord(
        position_id=str(decision_pos),
        symbol="BTCUSDT",
        side="LONG",
        qty=Decimal("1"),
        avg_entry_price=Decimal("100"),
        leverage=5,
        margin_usdt=Decimal("20"),
        state="OPEN",
    )
    illegal = orch.get(did)["state"] == "CLOSED" and pos.state == "OPEN" and pos.qty > 0
    return ScenarioResult(
        scenario_id="ADV_DECISION_CLOSED_POSITION_OPEN",
        title="Decision closed while position remains open",
        expected_fail_closed=True,
        observed_fail_closed=False,
        lane_a_covered=False,
        lane_b_covered=False,
        cross_lane_invariant_enforced=False,
        false_pass=illegal,
        missing_negative_test=True,
        severity="critical",
        detail=(
            "Decision MONITORING→UNDER_REVIEW→CLOSED skips EXITED; synthetic position_id can "
            "remain OPEN with qty>0. Critical cross-lifecycle invariant absent."
        ),
        evidence={
            "decision_state": orch.get(did)["state"],
            "decision_exit_id": orch.get(did)["decision"].get("exit_id"),
            "position_state": pos.state,
            "position_qty": str(pos.qty),
            "skipped_exited": orch.get(did)["decision"].get("exit_id") is None,
        },
    )


def scenario_evidence_tamper_after_approval(tmp: Path, roots: LaneRoots, a_tests: set[str], b_tests: set[str]) -> ScenarioResult:
    from backend.nexus_decision.orchestrator import DecisionLifecycleError, DecisionLifecycleOrchestrator

    orch = DecisionLifecycleOrchestrator(tmp / "tamp")
    out = _observe(orch, key="tamp-obs")
    did = out["decision"]["decision_id"]
    _to_approved(orch, did, "tamp")
    obj = orch._decisions[did]  # noqa: SLF001 — adversarial mutate
    obj.evidence_hashes = ["a" * 64] * len(obj.evidence_hashes)
    blocked = False
    try:
        orch.record(did, idempotency_key="tamp-r")
    except DecisionLifecycleError as exc:
        blocked = "evidence" in str(exc).lower() or "binding" in str(exc).lower()
    covered = "test_evidence_hash_tamper_binding_fail_closed" in a_tests
    return ScenarioResult(
        scenario_id="ADV_EVIDENCE_TAMPER_AFTER_APPROVAL",
        title="Evidence tamper after approval",
        expected_fail_closed=True,
        observed_fail_closed=blocked,
        lane_a_covered=covered,
        lane_b_covered=False,
        cross_lane_invariant_enforced=False,  # no exec evidence link
        false_pass=not blocked,
        missing_negative_test=not covered,
        severity="info" if blocked else "critical",
        detail=(
            "Lane A binding hash blocks post-approval evidence tamper on stage advance. "
            "No cross-lane evidence binding into execution OrderIntent."
        ),
        evidence={"blocked": blocked},
    )


SCENARIO_RUNNERS: tuple[Callable[..., ScenarioResult], ...] = (
    scenario_decision_approved_twice,
    scenario_reopened_after_close,
    scenario_intent_replay_after_restart,
    scenario_partial_fill_during_transition,
    scenario_same_bar_stop_target,
    scenario_cost_model_version_mismatch,
    scenario_position_closed_decision_monitoring,
    scenario_decision_closed_position_open,
    scenario_evidence_tamper_after_approval,
)


def run_adversarial_suite(tmp: Path, roots: LaneRoots | None = None) -> dict[str, Any]:
    roots = roots or resolve_lane_roots()
    a_tests = _lane_a_test_names(roots)
    b_tests = _lane_b_test_names(roots)
    results: list[ScenarioResult] = []
    with LaneImportContext(roots):
        for runner in SCENARIO_RUNNERS:
            results.append(runner(tmp, roots, a_tests, b_tests))
    false_passes = [r for r in results if r.false_pass]
    missing = [r for r in results if r.missing_negative_test]
    return {
        "scenario_count": len(results),
        "scenarios": [r.as_dict() for r in results],
        "false_PASS_count": len(false_passes),
        "missing_negative_test_count": len(missing),
        "lane_a_test_count": len(a_tests),
        "lane_b_test_count": len(b_tests),
        "lane_a_tests": sorted(a_tests),
        "lane_b_tests": sorted(b_tests),
    }
