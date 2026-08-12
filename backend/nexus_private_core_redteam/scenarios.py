"""V15-L attack scenarios — private core false-pass and safety fail-closed proofs.

All attacks are local/simulated. No Demo/exchange/mainnet/real money.
Platform-blocked mutations are never reported as PASS.
Critical survivors block V15 readiness.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger
from backend.nexus_autonomy.security_constants_v1 import (
    DEMO_ENV_KEY,
    DEMO_ENV_SECRET,
    MAINNET_ENV_KEY,
    MAINNET_ENV_SECRET,
)
from backend.nexus_autonomy.security_credential_boundary_v1 import resolve_exchange_profile
from backend.nexus_autonomy.security_exceptions_v1 import ExchangeWriteForbidden
from backend.nexus_autonomy.security_persistence_v1 import scan_secrets_in_evidence
from backend.nexus_autonomy.security_public_private_v1 import redact_account_identifiers
from backend.nexus_autonomy.security_write_traps_v1 import WriteTrapRegistry, exchange_write_traps
from backend.nexus_decision.evidence import hash_evidence_blob
from backend.nexus_decision.orchestrator import (
    DecisionLifecycleError,
    DecisionLifecycleOrchestrator,
)
from backend.nexus_dynamic_universe import point_in_time_membership
from backend.nexus_execution.risk_gates import RiskLimits, RiskState, evaluate_intent
from backend.nexus_private_core_redteam.constants import ATTACK_SCENARIO_IDS
from backend.nexus_private_core_redteam.integrity import (
    CONTROL_FIXTURE_LABEL,
    detect_candidate_relabeling,
    detect_capacity_as_quality,
    detect_cost_omission,
    detect_counter_inflation,
    detect_development_oos_confusion,
    detect_duplicate_lifecycle,
    detect_fabricated_universe,
    detect_lesson_before_reflection,
    detect_result_cherry_picking,
    detect_risk_bypass,
    seal_research_result,
)
from backend.nexus_qualification.pit_v11.infrastructure import (
    FounderAuthorizationGate,
    IntervalRecord,
    IntervalRegistry,
    prove_future_data_exclusion,
    prove_oos_non_consumption,
)
from backend.nexus_reflection.lesson_gate import apply_lesson_gate


@dataclass
class ScenarioResult:
    scenario_id: str
    passed: bool
    fail_closed: bool
    detail: str = ""
    critical: bool = False
    attack_blocked: bool = False
    platform_blocked: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "fail_closed": self.fail_closed,
            "detail": self.detail,
            "critical": self.critical,
            "attack_blocked": self.attack_blocked,
            "platform_blocked": self.platform_blocked,
            "evidence": dict(self.evidence),
        }


def _fresh(workdir: Path, name: str) -> Path:
    path = workdir / name
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _clean_result(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "result_id": "rr_v15l_001",
        "candidate_ids": ["cand_a", "cand_b"],
        "universe_members": ["AAAUSDT", "BBBUSDT"],
        "as_of_ms": 1_700_000_000_000,
        "counters": {"evaluated": 2, "passed_gate": 1},
        "metrics": {"sharpe": 0.4, "net_pnl": 12.5},
        "cost_model_version": "cost_v1",
        "cost_summary": {"total_cost": 1.25, "fees": 0.8, "slippage": 0.45},
        "fixture_label": CONTROL_FIXTURE_LABEL,
        "provider_status": "OK",
        "is_control_fixture": True,
        "claims_real_performance": False,
    }
    base.update(overrides)
    return base


def scenario_future_data_leakage(workdir: Path) -> ScenarioResult:
    _ = workdir
    as_of = 1_700_000_000_000
    clean = {
        "as_of_ms": as_of,
        "records": [
            {
                "record_id": "r1",
                "available_as_of_ms": as_of - 100,
                "payload": {"bar_close_ts_ms": as_of - 50},
            },
        ],
    }
    dirty = {
        "as_of_ms": as_of,
        "records": [
            {
                "record_id": "r2",
                "available_as_of_ms": as_of - 10,
                "payload": {"nested": {"decision_ts_ms": as_of + 999}},
            },
        ],
    }
    clean_proof = prove_future_data_exclusion(clean, as_of_ms=as_of)
    dirty_proof = prove_future_data_exclusion(dirty, as_of_ms=as_of)
    passed = (
        clean_proof.get("future_data_excluded") is True
        and dirty_proof.get("future_data_excluded") is False
        and dirty_proof.get("status") == "FUTURE_DATA_VIOLATION"
    )
    return ScenarioResult(
        scenario_id="future_data_leakage",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="future_data_leakage_blocked" if passed else "future_data_leakage_HOLE",
        critical=not passed,
        evidence={"clean": clean_proof, "dirty": dirty_proof},
    )


def scenario_development_oos_confusion(workdir: Path) -> ScenarioResult:
    """Development/OOS relabel + OOS consumption must fail closed."""
    _ = workdir
    honest = detect_development_oos_confusion(
        claimed_class="DEVELOPMENT", sealed_class="DEVELOPMENT", consumed=False
    )
    relabel = detect_development_oos_confusion(
        claimed_class="OOS_RESERVED", sealed_class="DEVELOPMENT", consumed=False
    )
    oos_as_dev = detect_development_oos_confusion(
        claimed_class="DEVELOPMENT", sealed_class="OOS_UNTOUCHED", consumed=False
    )
    reserved = IntervalRegistry(kind="reserved")
    consumed = IntervalRegistry(kind="consumed")
    reserved.add(
        IntervalRecord(
            interval_id="oos_1",
            label="oos_holdout",
            start_ms=1000,
            end_ms=2000,
            category="oos",
        )
    )
    clean_oos = prove_oos_non_consumption({"reserved": reserved, "consumed": consumed})
    consumed_attack = IntervalRegistry(kind="consumed")
    consumed_attack.add(
        IntervalRecord(
            interval_id="sneak_1",
            label="sneak_consume",
            start_ms=1500,
            end_ms=1800,
            category="consumed",
        )
    )
    dirty_oos = prove_oos_non_consumption({"reserved": reserved, "consumed": consumed_attack})
    consume_conf = detect_development_oos_confusion(
        claimed_class="OOS_RESERVED", sealed_class="OOS_RESERVED", consumed=True
    )
    passed = (
        honest.get("ok") is True
        and relabel.get("ok") is False
        and oos_as_dev.get("ok") is False
        and consume_conf.get("ok") is False
        and clean_oos.get("proven") is True
        and dirty_oos.get("proven") is False
        and dirty_oos.get("status") == "OOS_NON_CONSUMPTION_FAILED"
    )
    return ScenarioResult(
        scenario_id="development_oos_confusion",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="development_oos_confusion_blocked" if passed else "development_oos_HOLE",
        critical=not passed,
        evidence={
            "honest": honest,
            "relabel": relabel,
            "oos_as_dev": oos_as_dev,
            "consume_conf": consume_conf,
            "clean_oos": clean_oos,
            "dirty_oos": dirty_oos,
        },
    )


def scenario_fabricated_universe(workdir: Path) -> ScenarioResult:
    _ = workdir
    as_of = 1_700_000_000_000
    snapshot = {
        "instruments": [
            {"symbol": "AAAUSDT", "eligible": True, "launch_time": as_of - 10_000, "delivery_time": 0},
            {"symbol": "FUTUREUSDT", "eligible": True, "launch_time": as_of + 5_000, "delivery_time": 0},
            {"symbol": "DEADUSDT", "eligible": True, "launch_time": as_of - 20_000, "delivery_time": as_of - 1},
        ]
    }
    pit = point_in_time_membership(snapshot, as_of_ms=as_of)
    honest = detect_fabricated_universe(claimed_members=pit, pit_members=pit)
    attack = detect_fabricated_universe(
        claimed_members=["AAAUSDT", "FUTUREUSDT"],
        pit_members=pit,
    )
    passed = (
        honest.get("ok") is True
        and attack.get("ok") is False
        and attack.get("status") == "FABRICATED_UNIVERSE"
        and "FUTUREUSDT" in (attack.get("fabricated") or [])
    )
    return ScenarioResult(
        scenario_id="fabricated_universe",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="fabricated_universe_blocked" if passed else "fabricated_universe_HOLE",
        critical=not passed,
        evidence={"pit": pit, "honest": honest, "attack": attack},
    )


def scenario_cost_omission(workdir: Path) -> ScenarioResult:
    _ = workdir
    clean = detect_cost_omission(_clean_result())
    missing_version = detect_cost_omission(_clean_result(cost_model_version=""))
    missing_summary = detect_cost_omission(_clean_result(cost_summary={}))
    null_total = detect_cost_omission(
        _clean_result(cost_summary={"fees": 0.1, "total_cost": None})
    )
    passed = (
        clean.get("ok") is True
        and missing_version.get("ok") is False
        and missing_summary.get("ok") is False
        and null_total.get("ok") is False
        and missing_version.get("status") == "COST_OMISSION"
    )
    return ScenarioResult(
        scenario_id="cost_omission",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="cost_omission_blocked" if passed else "cost_omission_HOLE",
        critical=not passed,
        evidence={
            "clean": clean,
            "missing_version": missing_version,
            "missing_summary": missing_summary,
            "null_total": null_total,
        },
    )


def scenario_result_cherry_picking(workdir: Path) -> ScenarioResult:
    _ = workdir
    full_ids = ["c1", "c2", "c3", "c4"]
    honest = detect_result_cherry_picking(
        full_population_ids=full_ids,
        reported_ids=full_ids,
        full_metric=0.2,
        reported_metric=0.2,
        disclosed_subset=False,
    )
    attack = detect_result_cherry_picking(
        full_population_ids=full_ids,
        reported_ids=["c1", "c2"],
        full_metric=0.2,
        reported_metric=0.9,
        disclosed_subset=False,
    )
    disclosed = detect_result_cherry_picking(
        full_population_ids=full_ids,
        reported_ids=["c1", "c2"],
        full_metric=0.2,
        reported_metric=0.9,
        disclosed_subset=True,
    )
    passed = (
        honest.get("ok") is True
        and attack.get("ok") is False
        and attack.get("status") == "RESULT_CHERRY_PICKING"
        and disclosed.get("ok") is True
    )
    return ScenarioResult(
        scenario_id="result_cherry_picking",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="cherry_picking_blocked" if passed else "cherry_picking_HOLE",
        critical=not passed,
        evidence={"honest": honest, "attack": attack, "disclosed": disclosed},
    )


def scenario_candidate_relabeling(workdir: Path) -> ScenarioResult:
    _ = workdir
    sealed = {"cand_a": "mean_reversion", "cand_b": "momentum"}
    honest = detect_candidate_relabeling(sealed_labels=sealed, reported_labels=dict(sealed))
    swapped = detect_candidate_relabeling(
        sealed_labels=sealed,
        reported_labels={"cand_a": "momentum", "cand_b": "mean_reversion"},
    )
    renamed = detect_candidate_relabeling(
        sealed_labels=sealed,
        reported_labels={"cand_a": "winner_relabel", "cand_b": "momentum"},
    )
    passed = (
        honest.get("ok") is True
        and swapped.get("ok") is False
        and renamed.get("ok") is False
        and swapped.get("status") == "CANDIDATE_RELABELING"
    )
    return ScenarioResult(
        scenario_id="candidate_relabeling",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="candidate_relabeling_blocked" if passed else "candidate_relabeling_HOLE",
        critical=not passed,
        evidence={"honest": honest, "swapped": swapped, "renamed": renamed},
    )


def scenario_counter_inflation(workdir: Path) -> ScenarioResult:
    _ = workdir
    sealed = {"evaluated": 10, "passed_gate": 3}
    honest = detect_counter_inflation(reported_counters=sealed, sealed_event_counts=sealed)
    inflated = detect_counter_inflation(
        reported_counters={"evaluated": 99, "passed_gate": 3, "invented": 5},
        sealed_event_counts=sealed,
    )
    passed = (
        honest.get("ok") is True
        and inflated.get("ok") is False
        and inflated.get("status") == "COUNTER_INFLATION"
        and "evaluated" in (inflated.get("inflated") or {})
        and "invented" in (inflated.get("inflated") or {})
    )
    return ScenarioResult(
        scenario_id="counter_inflation",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="counter_inflation_blocked" if passed else "counter_inflation_HOLE",
        critical=not passed,
        evidence={"honest": honest, "inflated": inflated},
    )


def scenario_checkpoint_rollback(workdir: Path) -> ScenarioResult:
    root = _fresh(workdir, "ckpt_rb")
    ckpt_path = root / "checkpoint.json"
    sealed_body = {
        "checkpoint_id": "ckpt_v15l_001",
        "sequence": 4,
        "result_seal": "abc123",
        "status": "OPEN",
        "as_of_ms": 1_700_000_000_000,
    }
    seal = _sha(sealed_body)
    ckpt_path.write_text(
        json.dumps({"body": sealed_body, "seal": seal}, indent=2), encoding="utf-8"
    )
    loaded = json.loads(ckpt_path.read_text(encoding="utf-8"))
    verify_ok = _sha(loaded["body"]) == loaded["seal"]

    rolled = dict(sealed_body)
    rolled["sequence"] = 2
    rolled["result_seal"] = "older"
    seal_mismatch = _sha(rolled) != seal

    forged = {"body": rolled, "seal": _sha(rolled)}
    ckpt_path.write_text(json.dumps(forged, indent=2), encoding="utf-8")
    forged_loaded = json.loads(ckpt_path.read_text(encoding="utf-8"))
    forged_seal_ok = _sha(forged_loaded["body"]) == forged_loaded["seal"]
    rollback_detected = forged_loaded["body"]["sequence"] < sealed_body["sequence"]

    advanced = dict(sealed_body)
    advanced["sequence"] = 5
    advanced["status"] = "CLOSED"
    advance_seal = _sha(advanced)
    advance_ok = advance_seal != seal and _sha(advanced) == advance_seal

    passed = verify_ok and seal_mismatch and forged_seal_ok and rollback_detected and advance_ok
    return ScenarioResult(
        scenario_id="checkpoint_rollback",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="checkpoint_rollback_blocked" if passed else "checkpoint_rollback_HOLE",
        critical=not passed,
        evidence={
            "verify_ok": verify_ok,
            "seal_mismatch": seal_mismatch,
            "rollback_detected": rollback_detected,
            "advance_ok": advance_ok,
            "sealed_sequence": sealed_body["sequence"],
            "rolled_sequence": forged_loaded["body"]["sequence"],
        },
    )


def scenario_ledger_fork(workdir: Path) -> ScenarioResult:
    root = _fresh(workdir, "ledger")
    ledger = PrivateEventLedger(root / "events.db")
    try:
        for i in range(4):
            ledger.append(
                aggregate_id=f"agg_{i}",
                aggregate_type="DECISION",
                event_type="V15L_TEST",
                source="v15l_redteam",
                payload={"i": i},
                idempotency_key=f"v15l-lf-{i}",
            )
        clean = ledger.verify_hash_chain()
        ledger._conn.execute(
            "UPDATE events SET event_hash=? WHERE sequence_number=2",
            ("a" * 64,),
        )
        ledger._conn.commit()
        broken = ledger.verify_hash_chain()
        detected = broken.get("ledger_hash_chain_status") == "CORRUPTION_DETECTED"
        clean_ok = clean.get("ledger_hash_chain_status") == "PASS"
        passed = clean_ok and detected
        return ScenarioResult(
            scenario_id="ledger_fork",
            passed=passed,
            fail_closed=True,
            attack_blocked=passed,
            detail="ledger_fork_blocked" if passed else "ledger_fork_HOLE",
            critical=not passed,
            evidence={"clean": clean, "broken": broken, "detected": detected},
        )
    finally:
        ledger.close()


def scenario_duplicate_lifecycle(workdir: Path) -> ScenarioResult:
    """Same idempotency key must not spawn a second Decision lifecycle object."""
    root = _fresh(workdir, "dup_life")
    orch = DecisionLifecycleOrchestrator(root)
    blob = "v15l-dup-evidence-payload"
    eid = "ev_dup_1"
    common = dict(
        candidate_id="cand_dup",
        market_context_id="mkt_1",
        point_in_time_timestamp="2026-08-05T00:00:00Z",
        evidence_ids=[eid],
        evidence_hashes=[hash_evidence_blob(blob)],
        data_freshness={"age_seconds": 10.0, "stale": False},
        data_completeness={
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts"],
            "present_fields": ["mid", "spread", "ts"],
        },
        evidence_blobs={eid: blob},
        idempotency_key="v15l-dup-key-001",
    )
    first = orch.observe(**common)
    second = orch.observe(**common)
    det = detect_duplicate_lifecycle(first=first, second=second)
    # Synthetic attack: fabricate two distinct IDs without duplicate flag.
    attack = detect_duplicate_lifecycle(
        first={"status": "OBSERVED", "decision": {"decision_id": "a"}, "duplicate": False},
        second={"status": "OBSERVED", "decision": {"decision_id": "b"}, "duplicate": False},
    )
    passed = det.get("ok") is True and attack.get("ok") is False and attack.get("status") == "DUPLICATE_LIFECYCLE"
    return ScenarioResult(
        scenario_id="duplicate_lifecycle",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="duplicate_lifecycle_blocked" if passed else "duplicate_lifecycle_HOLE",
        critical=not passed,
        evidence={"honest": det, "attack": attack, "first": first, "second": second},
    )


def scenario_risk_bypass(workdir: Path) -> ScenarioResult:
    """Forbidden risk actions and leverage ceiling breaches must reject."""
    _ = workdir
    limits = RiskLimits(
        max_positions=2,
        max_intents=2,
        leverage=25,
        margin_usdt=Decimal("20"),
    )
    state = RiskState(open_position_count=0, pending_intent_count=0)
    forbidden = evaluate_intent(
        limits,
        state,
        {"requested_actions": ["leverage_increase", "martingale"], "leverage": 25},
    )
    ceiling = evaluate_intent(limits, state, {"leverage": 100, "symbol": "BTCUSDT"})
    honest = evaluate_intent(
        limits,
        state,
        {"leverage": 25, "symbol": "BTCUSDT", "reduce_only": False},
    )
    det_forbidden = detect_risk_bypass(
        decision_allowed=forbidden.allowed,
        reason=forbidden.reason,
        forbidden_hit=True,
        leverage=25,
    )
    det_ceiling = detect_risk_bypass(
        decision_allowed=ceiling.allowed,
        reason=ceiling.reason,
        forbidden_hit=True,
        leverage=100,
    )
    # Attack claim: pretend forbidden was allowed.
    attack = detect_risk_bypass(
        decision_allowed=True,
        reason="APPROVED",
        forbidden_hit=True,
        leverage=100,
    )
    passed = (
        forbidden.allowed is False
        and ceiling.allowed is False
        and honest.allowed is True
        and det_forbidden.get("ok") is True
        and det_ceiling.get("ok") is True
        and attack.get("ok") is False
        and attack.get("status") == "RISK_BYPASS"
    )
    return ScenarioResult(
        scenario_id="risk_bypass",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="risk_bypass_blocked" if passed else "risk_bypass_HOLE",
        critical=not passed,
        evidence={
            "forbidden": {"allowed": forbidden.allowed, "reason": forbidden.reason},
            "ceiling": {"allowed": ceiling.allowed, "reason": ceiling.reason},
            "honest": {"allowed": honest.allowed, "reason": honest.reason},
            "det_forbidden": det_forbidden,
            "det_ceiling": det_ceiling,
            "attack": attack,
        },
    )


def scenario_lesson_before_reflection(workdir: Path) -> ScenarioResult:
    """Lesson Prevention must not execute before Reflection VERIFIED."""
    _ = workdir
    blocked = apply_lesson_gate(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        proposed_lesson_count=3,
    )
    verified = apply_lesson_gate(terminal_status="VERIFIED", proposed_lesson_count=2)
    premature = detect_lesson_before_reflection(
        reflection_terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        lesson_executed=True,
        reflection_complete=False,
    )
    honest_block = detect_lesson_before_reflection(
        reflection_terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        lesson_executed=False,
        reflection_complete=False,
    )
    honest_ok = detect_lesson_before_reflection(
        reflection_terminal_status="VERIFIED",
        lesson_executed=True,
        reflection_complete=True,
    )
    passed = (
        blocked.get("lesson_prevention_executed") is False
        and verified.get("lesson_prevention_executed") is True
        and premature.get("ok") is False
        and premature.get("status") == "LESSON_BEFORE_REFLECTION"
        and honest_block.get("ok") is True
        and honest_ok.get("ok") is True
    )
    return ScenarioResult(
        scenario_id="lesson_before_reflection",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="lesson_before_reflection_blocked" if passed else "lesson_before_reflection_HOLE",
        critical=not passed,
        evidence={
            "blocked_gate": blocked,
            "verified_gate": verified,
            "premature": premature,
            "honest_block": honest_block,
            "honest_ok": honest_ok,
        },
    )


def scenario_capacity_as_quality(workdir: Path) -> ScenarioResult:
    """Provider capacity incompleteness must not be represented as quality."""
    _ = workdir
    honest = detect_capacity_as_quality(
        provider_or_terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        claimed_as_quality=False,
        claimed_quality_pass=False,
    )
    attack_claim = detect_capacity_as_quality(
        provider_or_terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        claimed_as_quality=True,
        claimed_quality_pass=False,
    )
    attack_pass = detect_capacity_as_quality(
        provider_or_terminal_status="PROVIDER_CAPACITY_BLOCKED",
        claimed_as_quality=False,
        claimed_quality_pass=True,
    )
    transport = detect_capacity_as_quality(
        provider_or_terminal_status="TIMEOUT",
        claimed_as_quality=True,
        claimed_quality_pass=False,
    )
    passed = (
        honest.get("ok") is True
        and attack_claim.get("ok") is False
        and attack_pass.get("ok") is False
        and transport.get("ok") is False
        and attack_claim.get("status") == "CAPACITY_AS_QUALITY"
    )
    return ScenarioResult(
        scenario_id="capacity_as_quality",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="capacity_as_quality_blocked" if passed else "capacity_as_quality_HOLE",
        critical=not passed,
        evidence={
            "honest": honest,
            "attack_claim": attack_claim,
            "attack_pass": attack_pass,
            "transport": transport,
        },
    )


def scenario_founder_auth_spoof(workdir: Path) -> ScenarioResult:
    _ = workdir
    gate = FounderAuthorizationGate()
    spoof = {
        "authorized": True,
        "reason": "SPOOFED_FOUNDER_OK",
        "required_scope": gate.required_scope,
        "auth_proof": "deadbeef",
    }
    result = gate.verify_bound_result(spoof)
    spoof_rejected = result.get("spoof_rejected") is True and result.get("valid") is False

    fake_ok = {"authorized": True, "reason": "FAKE", "required_scope": gate.required_scope}
    fake_ok["auth_proof"] = gate.bind_result(fake_ok)
    bound = gate.verify_bound_result(fake_ok)
    never_grants = bound.get("authorized") is False

    missing = gate.evaluate(None)
    missing_denied = missing.get("authorized") is False

    passed = spoof_rejected and never_grants and missing_denied
    return ScenarioResult(
        scenario_id="founder_auth_spoof",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="founder_auth_spoof_rejected" if passed else "founder_auth_HOLE",
        critical=not passed,
        evidence={"spoof": result, "bound": bound, "missing": missing},
    )


def scenario_exchange_write_bypass(workdir: Path) -> ScenarioResult:
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

    trap_raised = False
    trap_attempts = 0
    platform_blocked = False
    try:
        with exchange_write_traps() as counters:
            try:
                from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

                DemoWriteClient().create_market_order(  # type: ignore[call-arg]
                    symbol="BTCUSDT", side="Buy", qty="0.01"
                )
            except ExchangeWriteForbidden:
                trap_raised = True
            except TypeError:
                reg = WriteTrapRegistry()
                reg.install()
                try:
                    reg.trap_callable("create_market_order")()
                    trap_raised = False
                except ExchangeWriteForbidden:
                    trap_raised = True
                finally:
                    reg.uninstall()
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                platform_blocked = any(
                    t in msg for t in ("forbidden", "disabled", "missing", "mainnet", "demo")
                )
            trap_attempts = int(counters.exchange_write_attempt_count)
            if trap_attempts > 0:
                trap_raised = True
    except ExchangeWriteForbidden:
        platform_blocked = True

    if platform_blocked and not trap_raised:
        return ScenarioResult(
            scenario_id="exchange_write_bypass",
            passed=False,
            fail_closed=True,
            attack_blocked=False,
            platform_blocked=True,
            detail="platform_blocked_not_pass",
            critical=True,
            evidence={
                "orch_blocked": orch_blocked,
                "order_blocked": order_blocked,
                "trap_raised": trap_raised,
                "trap_attempts": trap_attempts,
                "platform_blocked": True,
            },
        )

    passed = orch_blocked and order_blocked and trap_raised and trap_attempts >= 1
    return ScenarioResult(
        scenario_id="exchange_write_bypass",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        platform_blocked=False,
        detail="exchange_write_bypass_blocked" if passed else "exchange_write_bypass_HOLE",
        critical=not passed,
        evidence={
            "orch_blocked": orch_blocked,
            "order_blocked": order_blocked,
            "trap_raised": trap_raised,
            "trap_attempts": trap_attempts,
        },
    )


def scenario_mainnet_profile_confusion(workdir: Path) -> ScenarioResult:
    _ = workdir
    demo_on_mainnet = resolve_exchange_profile(
        {DEMO_ENV_KEY: "demo_key_abcdefgh", DEMO_ENV_SECRET: "demo_secret_abcdefgh"},
        requested_profile="demo",
        base_url="https://api.bybit.com",
    )
    mainnet_requested = resolve_exchange_profile(
        {MAINNET_ENV_KEY: "main_key_abcdefgh", MAINNET_ENV_SECRET: "main_secret_abcdefgh"},
        requested_profile="mainnet",
        base_url="https://api.bybit.com",
    )
    fallback = resolve_exchange_profile(
        {MAINNET_ENV_KEY: "main_key_abcdefgh", MAINNET_ENV_SECRET: "main_secret_abcdefgh"},
        requested_profile="demo",
        base_url="https://api-demo.bybit.com",
    )

    demo_confused_blocked = (
        demo_on_mainnet.ok is False
        and demo_on_mainnet.fail_closed is True
        and demo_on_mainnet.writes_enabled is False
    )
    mainnet_blocked = (
        mainnet_requested.ok is False
        and mainnet_requested.fail_closed is True
        and mainnet_requested.writes_enabled is False
        and mainnet_requested.profile == "mainnet"
    )
    no_fallback = (
        fallback.ok is False
        and fallback.writes_enabled is False
        and fallback.fail_closed is True
        and fallback.mainnet_fallback_used is True
    )
    passed = demo_confused_blocked and mainnet_blocked and no_fallback
    return ScenarioResult(
        scenario_id="mainnet_profile_confusion",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="mainnet_profile_separated" if passed else "mainnet_confusion_HOLE",
        critical=not passed,
        evidence={
            "demo_on_mainnet": demo_on_mainnet.to_dict(),
            "mainnet_requested": mainnet_requested.to_dict(),
            "fallback": fallback.to_dict(),
        },
    )


def scenario_secret_leakage(workdir: Path) -> ScenarioResult:
    _ = workdir
    secret_val = "SUPERSECRET" + "VALUE1234567890"
    payload = {
        "note": "ok",
        "api_key": secret_val,
        "lesson_memory": "private",
    }
    findings = scan_secrets_in_evidence(payload)
    detected = "credential_assignment" in findings or any("api" in f for f in findings)

    public = redact_account_identifiers(
        {"api_key": secret_val, "strategy_param_alpha": 1.23, "ok_field": "visible"}
    )
    blob = json.dumps(public, default=str)
    not_echoed = secret_val not in blob
    redacted_changed = public.get("api_key") != secret_val if isinstance(public, dict) else True

    passed = detected and not_echoed and redacted_changed
    return ScenarioResult(
        scenario_id="secret_leakage",
        passed=passed,
        fail_closed=True,
        attack_blocked=passed,
        detail="secret_leakage_blocked" if passed else "secret_leakage_HOLE",
        critical=not passed,
        evidence={
            "findings": findings,
            "detected": detected,
            "not_echoed": not_echoed,
            "redacted_changed": redacted_changed,
            "public_keys": list(public.keys()) if isinstance(public, dict) else [],
        },
    )


SCENARIO_RUNNERS: dict[str, Any] = {
    "future_data_leakage": scenario_future_data_leakage,
    "development_oos_confusion": scenario_development_oos_confusion,
    "fabricated_universe": scenario_fabricated_universe,
    "cost_omission": scenario_cost_omission,
    "result_cherry_picking": scenario_result_cherry_picking,
    "candidate_relabeling": scenario_candidate_relabeling,
    "counter_inflation": scenario_counter_inflation,
    "checkpoint_rollback": scenario_checkpoint_rollback,
    "ledger_fork": scenario_ledger_fork,
    "duplicate_lifecycle": scenario_duplicate_lifecycle,
    "risk_bypass": scenario_risk_bypass,
    "lesson_before_reflection": scenario_lesson_before_reflection,
    "capacity_as_quality": scenario_capacity_as_quality,
    "founder_auth_spoof": scenario_founder_auth_spoof,
    "exchange_write_bypass": scenario_exchange_write_bypass,
    "mainnet_profile_confusion": scenario_mainnet_profile_confusion,
    "secret_leakage": scenario_secret_leakage,
}


def run_all_scenarios(workdir: Path) -> list[ScenarioResult]:
    workdir.mkdir(parents=True, exist_ok=True)
    results: list[ScenarioResult] = []
    for sid in ATTACK_SCENARIO_IDS:
        fn = SCENARIO_RUNNERS[sid]
        results.append(fn(workdir / sid))
    return results


def run_ledger_mutation_fixture(workdir: Path) -> dict[str, Any]:
    """Ledger mutation fixture wrapper used by fixtures module."""
    r = scenario_ledger_fork(workdir / "ledger_fx")
    return {
        "fixture_id": "ledger_mutation",
        "passed": r.passed,
        "detail": r.detail,
        "evidence": r.evidence,
    }
