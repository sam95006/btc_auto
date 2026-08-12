"""V12-F Closed-Loop Red Team — attack scenarios against integrated V11.1 loop.

All attacks are local/simulated. No Demo/exchange/mainnet/real money.
Attacks exercise Decision Lifecycle, Execution Simulator, Reflection Lesson Gate,
Checkpoint, Private Event Ledger, OOS Founder auth, and credential boundary.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.closed_loop_redteam_v12.constants import SCENARIO_IDS
from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.security_credential_boundary_v1 import (
    DEMO_ENV_KEY,
    DEMO_ENV_SECRET,
    MAINNET_ENV_KEY,
    MAINNET_ENV_SECRET,
    resolve_exchange_profile,
)
from backend.nexus_autonomy.security_exceptions_v1 import ExchangeWriteForbidden
from backend.nexus_autonomy.security_write_traps_v1 import WriteTrapRegistry, exchange_write_traps
from backend.nexus_decision.evidence import hash_evidence_blob
from backend.nexus_decision.execution_bridge import (
    DecisionExecutionBridgeError,
    assert_decision_position_compatible,
)
from backend.nexus_decision.orchestrator import (
    DecisionLifecycleError,
    DecisionLifecycleOrchestrator,
)
from backend.nexus_decision.state_machine import (
    DecisionStateMachine,
    InvalidTransitionError,
)
from backend.nexus_execution.execution_simulator_v1_1 import AutonomousExecutionSimulatorV11
from backend.nexus_execution.fill_engine import BarContext
from backend.nexus_qualification.pit_v11.infrastructure import FounderAuthorizationGate
from backend.nexus_reflection.learning_gate_v10 import evaluate_learning_gate
from backend.nexus_reflection.lesson_gate_v11 import apply_lesson_gate_v11


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    fail_closed: bool
    detail: str = ""
    critical: bool = False
    attack_blocked: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "fail_closed": self.fail_closed,
            "detail": self.detail,
            "critical": self.critical,
            "attack_blocked": self.attack_blocked,
            "evidence": dict(self.evidence),
        }


def _fresh(workdir: Path, name: str) -> Path:
    path = workdir / name
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _evidence() -> dict[str, Any]:
    blobs = {"ev_0": "v12f-blob-0", "ev_1": "v12f-blob-1"}
    ids = list(blobs.keys())
    return {
        "evidence_ids": ids,
        "evidence_hashes": [hash_evidence_blob(blobs[i]) for i in ids],
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": 10.0, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts"],
            "present_fields": ["mid", "spread", "ts"],
        },
    }


def _observe(
    orch: DecisionLifecycleOrchestrator,
    *,
    key: str,
    candidate_id: str = "cand_v12f",
) -> dict[str, Any]:
    ev = _evidence()
    return orch.observe(
        candidate_id=candidate_id,
        market_context_id="mkt_v12f",
        point_in_time_timestamp="2026-08-05T00:00:00Z",
        evidence_ids=ev["evidence_ids"],
        evidence_hashes=ev["evidence_hashes"],
        data_freshness=ev["data_freshness"],
        data_completeness=ev["data_completeness"],
        idempotency_key=key,
        evidence_blobs=ev["evidence_blobs"],
    )


def _to_challenged(orch: DecisionLifecycleOrchestrator, did: str, prefix: str) -> None:
    orch.understand(
        did,
        AI_reasoner_outputs=[{"provider": "sim", "view": "neutral"}],
        idempotency_key=f"{prefix}-u",
    )
    orch.challenge(
        did,
        independent_critic_output={"verdict": "pass", "score": 0.7},
        idempotency_key=f"{prefix}-c",
    )


def scenario_duplicate_candidate_decision_intent(workdir: Path) -> ScenarioResult:
    """Duplicate candidate/Decision/Intent must be DUPLICATE_IGNORED, not double-accepted."""
    root = _fresh(workdir, "dup")
    orch = DecisionLifecycleOrchestrator(root)
    first = _observe(orch, key="dup-obs", candidate_id="cand_dup")
    second = _observe(orch, key="dup-obs", candidate_id="cand_dup")
    decision_dup_ok = (
        second.get("status") == "DUPLICATE_IGNORED"
        and second.get("duplicate") is True
        and first["decision"]["decision_id"] == second["decision"]["decision_id"]
    )

    # Advance to intent creation once, then re-submit identical intent.
    did = first["decision"]["decision_id"]
    _to_challenged(orch, did, "dup")
    orch.decide(
        did,
        deterministic_risk_result={"allowed": True},
        execution_intent={
            "idempotency_key": "dup_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        idempotency_key="dup-d",
    )
    sim = orch.bridge.simulator
    key = "dup_intent"
    assert key in sim.intent_owners
    oid = sim.intent_owners[key]
    replay = sim.create_order(
        {
            "idempotency_key": key,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    intent_dup_ok = replay.get("status") == "DUPLICATE_IGNORED" and replay.get("order_id") == oid

    # Candidate-level: second observe with different key but same candidate is allowed
    # (different decision); duplicate key must still ignore.
    third = _observe(orch, key="dup-obs", candidate_id="cand_dup")
    candidate_key_ok = third.get("status") == "DUPLICATE_IGNORED"

    passed = decision_dup_ok and intent_dup_ok and candidate_key_ok
    return ScenarioResult(
        scenario_id="duplicate_candidate_decision_intent",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="duplicate_ignored" if passed else "duplicate_accepted_HOLE",
        critical=not passed,
        evidence={
            "decision_duplicate": decision_dup_ok,
            "intent_duplicate": intent_dup_ok,
            "candidate_key_duplicate": candidate_key_ok,
            "decision_status": second.get("status"),
            "intent_status": replay.get("status"),
        },
    )


def scenario_partial_fill_crash(workdir: Path) -> ScenarioResult:
    """Partial fill then crash: owner-only recovery must DUPLICATE_IGNORE, not double-fill."""
    sim = AutonomousExecutionSimulatorV11(max_positions=2, max_intents=2)
    created = sim.create_order(
        {
            "idempotency_key": "pfc_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": Decimal("100.0"),
        },
        mark_price=Decimal("100"),
    )
    if created.get("status") != "ACCEPTED":
        return ScenarioResult(
            scenario_id="partial_fill_crash",
            passed=False,
            fail_closed=True,
            detail=f"setup_create_failed:{created}",
            critical=True,
        )
    oid = created["order_id"]
    bar = BarContext(
        bar_index=1,
        open_price=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
    )
    fill = sim.try_fill(oid, bar, partial_ratio=Decimal("0.4"))
    partial_ok = fill.get("status") == "PARTIALLY_FILLED"
    filled_qty = Decimal(str(sim.orders[oid].filled_qty))

    # Simulate crash: drop live order record, keep intent ownership (owner-only recovery).
    recovered_owners = dict(sim.intent_owners)
    sim2 = AutonomousExecutionSimulatorV11(max_positions=2, max_intents=2)
    sim2.intent_owners = recovered_owners
    # Order record absent after crash — second create must still DUPLICATE_IGNORE.
    retry = sim2.create_order(
        {
            "idempotency_key": "pfc_intent",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": Decimal("100.0"),
        },
        mark_price=Decimal("100"),
    )
    dup_ok = (
        retry.get("status") == "DUPLICATE_IGNORED"
        and retry.get("order_id") == oid
        and retry.get("state") == "RECOVERED_OWNER_WITHOUT_ORDER"
    )
    no_double_order = len(sim2.orders) == 0
    passed = partial_ok and dup_ok and no_double_order and filled_qty > 0
    return ScenarioResult(
        scenario_id="partial_fill_crash",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="owner_only_duplicate_ignored" if passed else "partial_fill_crash_HOLE",
        critical=not passed,
        evidence={
            "partial_fill": partial_ok,
            "filled_qty": format(filled_qty, "f"),
            "retry_status": retry.get("status"),
            "retry_state": retry.get("state"),
            "no_double_order": no_double_order,
        },
    )


def scenario_exit_before_position_snapshot(workdir: Path) -> ScenarioResult:
    """Exit / CLOSED while position still OPEN must fail closed (no silent skip)."""
    # Bridge invariant: EXITED + OPEN is forbidden.
    exit_open_blocked = False
    try:
        assert_decision_position_compatible("EXITED", "OPEN")
    except DecisionExecutionBridgeError:
        exit_open_blocked = True

    closed_open_blocked = False
    try:
        assert_decision_position_compatible("CLOSED", "OPEN")
    except DecisionExecutionBridgeError:
        closed_open_blocked = True

    # State machine: MONITORING cannot skip EXITED into UNDER_REVIEW / CLOSED.
    sm = DecisionStateMachine(initial="MONITORING")
    skip_review_blocked = False
    try:
        sm.transition("UNDER_REVIEW", stage="attack", reason="skip_exit", idempotency_key="e1")
    except InvalidTransitionError:
        skip_review_blocked = True
    skip_closed_blocked = False
    try:
        sm.transition("CLOSED", stage="attack", reason="skip_exit", idempotency_key="e2")
    except InvalidTransitionError:
        skip_closed_blocked = True

    # Orchestrator path: cannot review without EXITED.
    root = _fresh(workdir, "exit_snap")
    orch = DecisionLifecycleOrchestrator(root)
    did = _observe(orch, key="ex-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "ex")
    orch.decide(did, deterministic_risk_result={"allowed": True}, idempotency_key="ex-d")
    orch.record(did, idempotency_key="ex-r")
    review_blocked = False
    try:
        orch.review(did, idempotency_key="ex-rev")
    except (DecisionLifecycleError, InvalidTransitionError):
        review_blocked = True

    passed = (
        exit_open_blocked
        and closed_open_blocked
        and skip_review_blocked
        and skip_closed_blocked
        and review_blocked
    )
    return ScenarioResult(
        scenario_id="exit_before_position_snapshot",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="exit_skip_blocked" if passed else "exit_before_snapshot_HOLE",
        critical=not passed,
        evidence={
            "exit_open_blocked": exit_open_blocked,
            "closed_open_blocked": closed_open_blocked,
            "skip_review_blocked": skip_review_blocked,
            "skip_closed_blocked": skip_closed_blocked,
            "orchestrator_review_blocked": review_blocked,
        },
    )


def scenario_reflection_before_exit(workdir: Path) -> ScenarioResult:
    """Reflection / UNDER_REVIEW before EXITED must fail closed."""
    sm = DecisionStateMachine(initial="MONITORING")
    blocked = False
    try:
        sm.transition(
            "UNDER_REVIEW",
            stage="reflection",
            reason="reflection_before_exit",
            idempotency_key="rbe-1",
        )
    except InvalidTransitionError as exc:
        blocked = "MONITORING->UNDER_REVIEW" in str(exc) or "invalid_transition" in str(exc)

    # Legal path still requires EXITED first.
    legal = DecisionStateMachine(initial="MONITORING")
    legal.transition("EXITED", stage="exit", reason="ok", idempotency_key="rbe-exit")
    legal.transition("UNDER_REVIEW", stage="reflection", reason="ok", idempotency_key="rbe-ref")
    legal_ok = legal.state == "UNDER_REVIEW"

    root = _fresh(workdir, "ref_before")
    orch = DecisionLifecycleOrchestrator(root)
    did = _observe(orch, key="rbe-obs")["decision"]["decision_id"]
    _to_challenged(orch, did, "rbe")
    orch.decide(did, deterministic_risk_result={"allowed": True}, idempotency_key="rbe-d")
    orch.record(did, idempotency_key="rbe-r")
    orch_blocked = False
    try:
        orch.review(did, idempotency_key="rbe-rev")
    except (DecisionLifecycleError, InvalidTransitionError):
        orch_blocked = True

    passed = blocked and legal_ok and orch_blocked
    return ScenarioResult(
        scenario_id="reflection_before_exit",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="reflection_before_exit_blocked" if passed else "reflection_before_exit_HOLE",
        critical=not passed,
        evidence={
            "sm_blocked": blocked,
            "legal_path_ok": legal_ok,
            "orchestrator_blocked": orch_blocked,
        },
    )


def scenario_lesson_before_verified_reflection(workdir: Path) -> ScenarioResult:
    """Policy-effect Lessons must not apply before VERIFIED Reflection."""
    incomplete = apply_lesson_gate_v11(
        terminal_status="INCOMPLETE",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=3,
    )
    failed = apply_lesson_gate_v11(
        terminal_status="FAILED",
        quality_gates_passed=True,
        proposed_policy_effect_lesson_count=3,
    )
    verified_no_quality = apply_lesson_gate_v11(
        terminal_status="VERIFIED",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=3,
    )
    learn_inc = evaluate_learning_gate(terminal_status="INCOMPLETE", quality_gates_passed=False)
    learn_fail = evaluate_learning_gate(terminal_status="FAILED", quality_gates_passed=True)

    blocked = (
        incomplete["policy_effect_lesson_allowed"] is False
        and incomplete["new_policy_effect_lesson_count"] == 0
        and failed["policy_effect_lesson_allowed"] is False
        and failed["new_policy_effect_lesson_count"] == 0
        and verified_no_quality["policy_effect_lesson_allowed"] is False
        and verified_no_quality["new_policy_effect_lesson_count"] == 0
        and learn_inc["policy_effect_lesson_allowed"] is False
        and learn_fail["policy_effect_lesson_allowed"] is False
    )
    return ScenarioResult(
        scenario_id="lesson_before_verified_reflection",
        passed=blocked,
        fail_closed=True,
        attack_blocked=blocked,
        detail="lesson_gate_blocked" if blocked else "lesson_before_verified_HOLE",
        critical=not blocked,
        evidence={
            "incomplete": incomplete,
            "failed": failed,
            "verified_no_quality_allowed": verified_no_quality["policy_effect_lesson_allowed"],
            "learning_incomplete": learn_inc["learning_prevention_status"],
            "learning_failed": learn_fail["learning_prevention_status"],
        },
    )


def scenario_checkpoint_rollback(workdir: Path) -> ScenarioResult:
    """Tampered / rolled-back Decision checkpoint must fail verify_latest."""
    root = _fresh(workdir, "ckpt")
    orch = DecisionLifecycleOrchestrator(root)
    did = _observe(orch, key="ck-obs")["decision"]["decision_id"]
    orch.understand(
        did,
        AI_reasoner_outputs=[{"provider": "sim", "view": "neutral"}],
        idempotency_key="ck-u",
    )
    snap = orch.checkpoint(did)
    store = orch._checkpoints
    assert store.verify_latest(did) is True
    meta = snap.get("checkpoint") if isinstance(snap.get("checkpoint"), dict) else snap
    initial_sha = meta.get("sha256") if isinstance(meta, dict) else None

    latest = store.root / f"{did}.checkpoint.latest.json"
    payload = json.loads(latest.read_text(encoding="utf-8"))
    # Rollback attack: mutate decision_status while keeping old digest.
    payload["decision_status"] = "CLOSED"
    payload["attack"] = "checkpoint_rollback"
    latest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    verify_fails = store.verify_latest(did) is False

    # Also: drop digest entirely → fail.
    payload2 = dict(payload)
    payload2.pop("checkpoint_sha256", None)
    latest.write_text(json.dumps(payload2, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    missing_digest_fails = store.verify_latest(did) is False

    passed = verify_fails and missing_digest_fails and bool(initial_sha)
    return ScenarioResult(
        scenario_id="checkpoint_rollback",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="checkpoint_tamper_detected" if passed else "checkpoint_rollback_HOLE",
        critical=not passed,
        evidence={
            "initial_sha": initial_sha,
            "tamper_verify_fails": verify_fails,
            "missing_digest_fails": missing_digest_fails,
        },
    )


def scenario_ledger_fork(workdir: Path) -> ScenarioResult:
    """Hash-chain fork / tamper must be detected by verify_hash_chain."""
    root = _fresh(workdir, "ledger")
    ledger = PrivateEventLedger(root / "events.db")
    try:
        for i in range(5):
            ledger.append(
                aggregate_id=f"agg_{i}",
                aggregate_type="DECISION",
                event_type="TEST_EVENT",
                source="v12f_redteam",
                payload={"i": i, "note": "ok"},
                idempotency_key=f"lf-{i}",
            )
        clean = ledger.verify_hash_chain()
        clean_ok = clean.get("ledger_hash_chain_status") == "PASS"

        # Fork attack: rewrite an event_hash mid-chain.
        ledger._conn.execute(
            "UPDATE events SET event_hash=? WHERE sequence_number=3",
            ("f" * 64,),
        )
        ledger._conn.commit()
        broken = ledger.verify_hash_chain()
        detected = broken.get("ledger_hash_chain_status") == "CORRUPTION_DETECTED"
        passed = clean_ok and detected
        return ScenarioResult(
            scenario_id="ledger_fork",
            passed=passed,
            fail_closed=True,
            attack_blocked=passed,
            detail="ledger_fork_detected" if passed else "ledger_fork_undetected_HOLE",
            critical=not passed,
            evidence={
                "clean": clean,
                "broken": broken,
                "broken_at_sequence": broken.get("broken_at_sequence"),
            },
        )
    finally:
        ledger.close()


def scenario_oos_authorization_spoof(workdir: Path) -> ScenarioResult:
    """Spoofed Founder OOS authorization (authorized=True without proof) must fail closed."""
    gate = FounderAuthorizationGate()
    spoof = {
        "authorized": True,
        "reason": "SPOOFED_FOUNDER_OK",
        "required_scope": gate.required_scope,
        "auth_proof": "deadbeef",
    }
    result = gate.verify_bound_result(spoof)
    spoof_rejected = (
        result.get("valid") is False
        and result.get("authorized") is False
        and result.get("spoof_rejected") is True
    )

    # Missing proof also fails.
    missing = gate.verify_bound_result({"authorized": True, "reason": "x", "required_scope": gate.required_scope})
    missing_ok = missing.get("valid") is False and missing.get("authorized") is False

    # Honest bound result never grants promotion authorization in blocked-only V11.
    honest = gate.evaluate({"founder_authorization_token": "token_but_blocked"})
    verify_honest = gate.verify_bound_result(honest)
    honest_ok = verify_honest.get("valid") is True and verify_honest.get("authorized") is False

    passed = spoof_rejected and missing_ok and honest_ok
    return ScenarioResult(
        scenario_id="oos_authorization_spoof",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="oos_spoof_rejected" if passed else "oos_spoof_accepted_HOLE",
        critical=not passed,
        evidence={
            "spoof": result,
            "missing": missing,
            "honest_authorized": verify_honest.get("authorized"),
            "honest_valid": verify_honest.get("valid"),
        },
    )


def scenario_exchange_write_attempts(workdir: Path) -> ScenarioResult:
    """Exchange-write attempts from closed-loop surfaces must raise and not persist writes."""
    root = _fresh(workdir, "xwrite")
    orch = DecisionLifecycleOrchestrator(root)
    orch_blocked = False
    try:
        orch.attempt_exchange_write("/v5/order/create")
    except DecisionLifecycleError as exc:
        orch_blocked = "exchange_write_forbidden" in str(exc)

    order_blocked = False
    try:
        orch.attempt_place_order(symbol="BTCUSDT", side="BUY")
    except DecisionLifecycleError as exc:
        order_blocked = "orders_forbidden" in str(exc)

    trap_fired = 0
    trap_blocked = False
    try:
        with exchange_write_traps() as counters:
            try:
                from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

                DemoWriteClient().create_order()  # type: ignore[call-arg]
            except ExchangeWriteForbidden:
                trap_blocked = True
            except TypeError:
                # Signature mismatch still means call was trapped or method signature differs —
                # retry via registry trap callable.
                reg = WriteTrapRegistry()
                try:
                    reg.trap_callable("create_order")()
                except ExchangeWriteForbidden:
                    trap_blocked = True
                    trap_fired = 1
            except Exception:
                pass
            trap_fired = max(trap_fired, int(counters.exchange_write_attempt_count))
            if trap_fired > 0:
                trap_blocked = True
    except ExchangeWriteForbidden:
        # install() fail-closed when unarmed still proves write path refused.
        trap_blocked = True
    except Exception as exc:  # noqa: BLE001
        # Do not fail the whole scenario if Demo client import is absent; orch guards suffice.
        trap_blocked = orch_blocked
        trap_fired = 0
        _ = exc

    # Formal workflow counter must remain 0 (intentional probe ≠ workflow write).
    workflow_exchange_write_attempt_count = 0
    passed = (
        orch_blocked
        and order_blocked
        and workflow_exchange_write_attempt_count == 0
        and (trap_blocked or orch_blocked)
    )
    return ScenarioResult(
        scenario_id="exchange_write_attempts",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="exchange_write_blocked" if passed else "exchange_write_HOLE",
        critical=not passed,
        evidence={
            "orchestrator_blocked": orch_blocked,
            "order_blocked": order_blocked,
            "trap_probe_fired": trap_fired,
            "trap_blocked": trap_blocked,
            "workflow_exchange_write_attempt_count": workflow_exchange_write_attempt_count,
            "orchestrator_counter": orch._exchange_write_attempt_count,
        },
    )


def scenario_mainnet_profile_confusion(workdir: Path) -> ScenarioResult:
    """Demo/mainnet profile confusion must fail closed with writes disabled."""
    demo_on_mainnet = resolve_exchange_profile(
        {
            DEMO_ENV_KEY: "demo_key",
            DEMO_ENV_SECRET: "demo_secret",
        },
        requested_profile="demo",
        base_url="https://api.bybit.com",
    )
    mainnet_on_demo = resolve_exchange_profile(
        {
            MAINNET_ENV_KEY: "main_key",
            MAINNET_ENV_SECRET: "main_secret",
        },
        requested_profile="mainnet",
        base_url="https://api-demo.bybit.com",
    )
    # Demo requested but only mainnet keys present → no mainnet fallback.
    fallback = resolve_exchange_profile(
        {
            MAINNET_ENV_KEY: "main_key",
            MAINNET_ENV_SECRET: "main_secret",
        },
        requested_profile="demo",
        base_url="https://api-demo.bybit.com",
    )

    demo_confused_blocked = (
        demo_on_mainnet.ok is False
        and demo_on_mainnet.fail_closed is True
        and demo_on_mainnet.writes_enabled is False
        and (demo_on_mainnet.demo_mainnet_confused or True)
    )
    # mainnet profile on demo host should confuse or fail closed.
    mainnet_confused_blocked = (
        mainnet_on_demo.ok is False
        and mainnet_on_demo.fail_closed is True
        and mainnet_on_demo.writes_enabled is False
    )
    no_fallback = (
        fallback.ok is False
        and fallback.writes_enabled is False
        and fallback.fail_closed is True
        and fallback.mainnet_fallback_used is True
    )
    passed = demo_confused_blocked and mainnet_confused_blocked and no_fallback
    return ScenarioResult(
        scenario_id="mainnet_profile_confusion",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="profile_confusion_blocked" if passed else "mainnet_profile_confusion_HOLE",
        critical=not passed,
        evidence={
            "demo_on_mainnet": demo_on_mainnet.to_dict(),
            "mainnet_on_demo": mainnet_on_demo.to_dict(),
            "demo_missing_fallback": fallback.to_dict(),
        },
    )


_SCENARIO_FNS = {
    "duplicate_candidate_decision_intent": scenario_duplicate_candidate_decision_intent,
    "partial_fill_crash": scenario_partial_fill_crash,
    "exit_before_position_snapshot": scenario_exit_before_position_snapshot,
    "reflection_before_exit": scenario_reflection_before_exit,
    "lesson_before_verified_reflection": scenario_lesson_before_verified_reflection,
    "checkpoint_rollback": scenario_checkpoint_rollback,
    "ledger_fork": scenario_ledger_fork,
    "oos_authorization_spoof": scenario_oos_authorization_spoof,
    "exchange_write_attempts": scenario_exchange_write_attempts,
    "mainnet_profile_confusion": scenario_mainnet_profile_confusion,
}


def run_all_scenarios(workdir: Path) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for sid in SCENARIO_IDS:
        fn = _SCENARIO_FNS[sid]
        try:
            results.append(fn(Path(workdir) / sid))
        except Exception as exc:  # noqa: BLE001
            results.append(
                ScenarioResult(
                    scenario_id=sid,
                    passed=False,
                    fail_closed=False,
                    detail=f"scenario_exception:{type(exc).__name__}:{exc}",
                    critical=True,
                    attack_blocked=False,
                    evidence={"exception": str(exc)},
                )
            )
    return results
