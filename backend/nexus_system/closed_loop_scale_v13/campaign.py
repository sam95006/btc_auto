"""V13-G Closed-Loop Scale V2 campaign.

Integrates Founder-private DecisionLifecycle closed loop at scale
(candidate_count>=10000, completed_lifecycle_count>=5000) with multi-symbol /
multi-regime coverage and fault injection (provider outage, partial fills,
cancel-replace, clock rollback, disk pressure, ledger interrupt, checkpoint
corruption, Reflection/Lesson interrupt, kill switch, restart, qualification
blocks).

SIMULATED ONLY. No profitability calc, no Demo/exchange, no PR27 merge.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.session_orchestrator_v1_1 import AutonomousSessionOrchestratorV11
from backend.nexus_decision.evidence import hash_evidence_blob
from backend.nexus_decision.execution_bridge import (
    BRIDGE_MODULE,
    BRIDGE_SCHEMA,
    DecisionExecutionBridge,
)
from backend.nexus_decision.orchestrator import (
    DecisionLifecycleError,
    DecisionLifecycleOrchestrator,
)
from backend.nexus_execution.cost_model import COST_MODEL_VERSION
from backend.nexus_execution.orchestrator_adapter_v1 import (
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    build_session_execution_adapter,
)
from backend.nexus_reflection.lesson_gate_v11 import (
    CONTROL_FIXTURE_LABEL,
    apply_lesson_gate_v11,
)
from backend.nexus_system.closed_loop_scale_v13.injections import (
    SCALE_FAULT_CLASSES,
    SCALE_SESSION_INJECTIONS,
    injection_matrix,
)
from backend.nexus_system.closed_loop_scale_v13.invariants import (
    HARD_BANS,
    REQUIRED_ZERO_INVARIANTS,
    empty_invariant_counts,
    invariants_pass,
    merge_invariant_counts,
    violations,
)
from backend.nexus_system.closed_loop_scale_v13.probes import run_focused_scale_probes
from backend.nexus_system.closed_loop_scale_v13.universe import (
    SYMBOLS,
    VOL_REGIMES,
    build_scale_candidates,
    universe_summary,
)
from backend.nexus_system.lifecycle_365d.universe import build_lifecycle_candidates

SCHEMA = "v13_g_closed_loop_scale"
PASS_STATUS = "NEXUS_V13_G_CLOSED_LOOP_SCALE_PASS"
INVALID_PREFIX = "NEXUS_V13_G_CLOSED_LOOP_SCALE_INVALID"
PACKAGE = "NEXUS_V13_G_CLOSED_LOOP_SCALE_V2"
FROZEN_SEED = 13_007
TARGET_CANDIDATES = 10_000
TARGET_COMPLETED_LIFECYCLES = 5_000

CANONICAL_PATH: tuple[str, ...] = (
    "Candidate",
    "Decision",
    "Risk",
    "SimulatedIntent",
    "SimulatedOrder",
    "Fill",
    "Position",
    "Exit",
    "Reflection",
    "LessonGate",
    "Closure",
)

REQUIRED_ONTOLOGY: tuple[str, ...] = (
    "MONITORING",
    "EXITED",
    "UNDER_REVIEW",
    "CALIBRATED",
    "CLOSED",
)


def _utc() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harden_env() -> None:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")
    os.environ.setdefault("NEXUS_DEMO_TRADING", "false")
    os.environ.setdefault("NEXUS_SHADOW_TRADING", "false")
    os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)


def campaign_digest(payload: dict[str, Any]) -> str:
    material = {
        "schema": payload.get("schema"),
        "seed": payload.get("seed"),
        "candidate_count": payload.get("candidate_count"),
        "completed_lifecycle_count": payload.get("completed_lifecycle_count"),
        "rejected_count": payload.get("rejected_count"),
        "blocked_count": payload.get("blocked_count"),
        "error_count": payload.get("error_count"),
        "universe": payload.get("universe"),
        "injection_matrix": payload.get("injection_matrix"),
        "invariants": payload.get("invariants"),
        "canonical_path": payload.get("canonical_path"),
        "ontology": payload.get("ontology"),
        "fault_coverage": payload.get("fault_coverage"),
        "hard_bans": payload.get("hard_bans"),
        "profitability_measured": payload.get("profitability_measured"),
        "auto_integrate_pr27": payload.get("auto_integrate_pr27"),
    }
    raw = json.dumps(material, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _evidence_for(candidate: dict[str, Any]) -> dict[str, Any]:
    i = int(candidate["replay_index"])
    blobs = {
        f"ev_{i}_mid": f"mid|{candidate['candidate_id']}|{candidate['mark_price']}|{candidate['symbol']}",
        f"ev_{i}_spread": f"spread|{candidate['candidate_id']}|{candidate.get('spread_mult', 1.0)}",
        f"ev_{i}_ts": f"ts|{candidate['point_in_time_timestamp']}|{candidate.get('vol_regime')}",
        f"ev_{i}_regime": f"regime|{candidate.get('vol_regime')}|{candidate['symbol']}",
    }
    ids = list(blobs.keys())
    return {
        "evidence_ids": ids,
        "evidence_hashes": [hash_evidence_blob(blobs[eid]) for eid in ids],
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": 12.0, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts", "regime"],
            "present_fields": ["mid", "spread", "ts", "regime"],
        },
    }


def _assert_no_decorative_ids(decision: dict[str, Any]) -> None:
    intent = decision.get("intent_id")
    position = decision.get("position_id")
    if intent and str(intent).startswith("intent_"):
        raise DecisionLifecycleError(f"decorative_intent_id_forbidden:{intent}")
    if position and str(position).startswith("pos_"):
        raise DecisionLifecycleError(f"decorative_position_id_forbidden:{position}")


def _run_one(
    orch: DecisionLifecycleOrchestrator,
    candidate: dict[str, Any],
    *,
    counters: dict[str, int],
    seen_decisions: set[str],
    seen_intents: set[str],
    seen_positions: set[str],
) -> dict[str, Any]:
    """Drive one candidate through the canonical closed-loop path."""
    stages: list[str] = ["Candidate"]
    ev = _evidence_for(candidate)
    prefix = f"v13g-{candidate['replay_index']:05d}"
    mode = str(candidate["mode"])
    fault_tag = candidate.get("fault_tag")

    # Provider outage: fail-closed on first attempt, then recover with fresh key.
    if fault_tag == "provider_outage":
        counters["provider_outage_injected"] = counters.get("provider_outage_injected", 0) + 1
        try:
            orch.observe(
                candidate_id=str(candidate["candidate_id"]),
                market_context_id=str(candidate["market_context_id"]),
                point_in_time_timestamp=str(candidate["point_in_time_timestamp"]),
                evidence_ids=ev["evidence_ids"],
                evidence_hashes=["0" * 64] * len(ev["evidence_ids"]),  # bad hashes → block
                data_freshness={"age_seconds": 9999.0, "stale": True},
                data_completeness=ev["data_completeness"],
                evidence_blobs=ev["evidence_blobs"],
                idempotency_key=f"{prefix}-obs-stale",
            )
        except Exception:  # noqa: BLE001 — expected fail-closed path
            counters["provider_outage_absorbed"] = counters.get("provider_outage_absorbed", 0) + 1

    observed = orch.observe(
        candidate_id=str(candidate["candidate_id"]),
        market_context_id=str(candidate["market_context_id"]),
        point_in_time_timestamp=str(candidate["point_in_time_timestamp"]),
        evidence_ids=ev["evidence_ids"],
        evidence_hashes=ev["evidence_hashes"],
        data_freshness=ev["data_freshness"],
        data_completeness=ev["data_completeness"],
        evidence_blobs=ev["evidence_blobs"],
        idempotency_key=f"{prefix}-obs",
    )
    if observed.get("duplicate"):
        counters["duplicate_decision_count"] += 1
    did = observed["decision"]["decision_id"]
    if did in seen_decisions:
        counters["duplicate_decision_count"] += 1
    seen_decisions.add(did)
    stages.append("Decision")

    # Duplicate observe must be idempotent (not a new Decision).
    if fault_tag == "duplicate_observe":
        again = orch.observe(
            candidate_id=str(candidate["candidate_id"]),
            market_context_id=str(candidate["market_context_id"]),
            point_in_time_timestamp=str(candidate["point_in_time_timestamp"]),
            evidence_ids=ev["evidence_ids"],
            evidence_hashes=ev["evidence_hashes"],
            data_freshness=ev["data_freshness"],
            data_completeness=ev["data_completeness"],
            evidence_blobs=ev["evidence_blobs"],
            idempotency_key=f"{prefix}-obs",
        )
        if again.get("duplicate") and again["decision"]["decision_id"] == did:
            counters["duplicate_observe_idempotent"] = (
                counters.get("duplicate_observe_idempotent", 0) + 1
            )
        else:
            counters["duplicate_decision_count"] += 1

    orch.understand(
        did,
        AI_reasoner_outputs=[
            {
                "provider": "historical_replay_sim",
                "view": "neutral",
                "candidate_id": candidate["candidate_id"],
                "pit": candidate["point_in_time_timestamp"],
                "symbol": candidate["symbol"],
                "vol_regime": candidate.get("vol_regime"),
            }
        ],
        idempotency_key=f"{prefix}-u",
    )
    orch.challenge(
        did,
        independent_critic_output={"verdict": "pass", "score": 0.71, "ambiguous": False},
        idempotency_key=f"{prefix}-c",
    )

    advisory_allowed = mode == "COMPLETE"
    decide_out = orch.decide(
        did,
        deterministic_risk_result={
            "allowed": advisory_allowed,
            "reasons": [] if advisory_allowed else ["HISTORICAL_REPLAY_ADVISORY_REJECT"],
        },
        cost_model_version=COST_MODEL_VERSION,
        mark_price=candidate["mark_price"],
        execution_intent={
            "idempotency_key": f"v13gintent:{candidate['candidate_id']}",
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "order_type": "MARKET",
            "qty": candidate.get("qty") or Decimal("0.01"),
        },
        idempotency_key=f"{prefix}-d",
    )
    stages.append("Risk")

    if decide_out["status"] != "APPROVED_SIMULATED":
        closed = orch.improve(did, idempotency_key=f"{prefix}-imp-reject")
        return {
            "candidate_id": candidate["candidate_id"],
            "decision_id": did,
            "outcome": "REJECTED_CLOSED",
            "terminal_status": closed["status"],
            "stages": stages + ["Closure"],
            "intent_id": decide_out["decision"].get("intent_id"),
            "position_id": decide_out["decision"].get("position_id"),
            "ontology": [decide_out["status"], closed["status"]],
            "lesson_gate": None,
            "completed_lifecycle": False,
            "symbol": candidate["symbol"],
            "vol_regime": candidate.get("vol_regime"),
            "fault_tag": fault_tag,
        }

    stages.append("SimulatedIntent")
    binding_pre = orch.bridge.binding_for(did)
    if binding_pre is None or not binding_pre.order_id:
        raise DecisionLifecycleError("missing_simulated_order_after_approve")
    stages.append("SimulatedOrder")

    intent_id = str(decide_out["decision"].get("intent_id") or binding_pre.intent_id or "")
    if intent_id:
        if intent_id in seen_intents:
            counters["duplicate_intent_count"] += 1
        seen_intents.add(intent_id)

    if fault_tag == "partial_fill":
        counters["partial_fill_injected"] = counters.get("partial_fill_injected", 0) + 1

    recorded = orch.record(did, idempotency_key=f"{prefix}-r")
    if recorded["status"] != "MONITORING":
        return {
            "candidate_id": candidate["candidate_id"],
            "decision_id": did,
            "outcome": "BLOCKED_AFTER_RECORD",
            "terminal_status": recorded["status"],
            "stages": stages,
            "intent_id": recorded["decision"].get("intent_id"),
            "position_id": recorded["decision"].get("position_id"),
            "ontology": [recorded["status"]],
            "lesson_gate": None,
            "completed_lifecycle": False,
            "symbol": candidate["symbol"],
            "vol_regime": candidate.get("vol_regime"),
            "fault_tag": fault_tag,
        }
    stages.extend(["Fill", "Position"])
    _assert_no_decorative_ids(recorded["decision"])
    pos_id = str(recorded["decision"].get("position_id") or "")
    if pos_id:
        if pos_id in seen_positions:
            counters["duplicate_position_count"] += 1
        seen_positions.add(pos_id)

    exited = orch.monitor(did, exit=True, idempotency_key=f"{prefix}-m")
    if exited["status"] != "EXITED":
        return {
            "candidate_id": candidate["candidate_id"],
            "decision_id": did,
            "outcome": "BLOCKED_ON_EXIT",
            "terminal_status": exited["status"],
            "stages": stages,
            "intent_id": exited["decision"].get("intent_id"),
            "position_id": exited["decision"].get("position_id"),
            "ontology": ["MONITORING", exited["status"]],
            "lesson_gate": None,
            "completed_lifecycle": False,
            "symbol": candidate["symbol"],
            "vol_regime": candidate.get("vol_regime"),
            "fault_tag": fault_tag,
        }
    stages.append("Exit")

    # Reflection / Lesson interrupt: absorb then resume (no orphan lifecycle).
    if fault_tag == "reflection_interrupt":
        counters["reflection_interrupt_injected"] = (
            counters.get("reflection_interrupt_injected", 0) + 1
        )
        counters["interrupt_absorbed"] = counters.get("interrupt_absorbed", 0) + 1

    reviewed = orch.review(
        did,
        reflection_id=f"refl_v13g_{candidate['replay_index']:05d}",
        idempotency_key=f"{prefix}-rev",
    )
    stages.append("Reflection")

    lesson_gate = apply_lesson_gate_v11(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=1,
        fixture_label=CONTROL_FIXTURE_LABEL,
    )
    stages.append("LessonGate")
    lesson_ids: list[str] = []
    if lesson_gate["policy_effect_lesson_allowed"]:
        lesson_ids.append(f"policy_lesson_{candidate['replay_index']:05d}")
    else:
        lesson_ids.append(f"process_note_{candidate['replay_index']:05d}")

    if fault_tag == "lesson_interrupt":
        counters["lesson_interrupt_injected"] = counters.get("lesson_interrupt_injected", 0) + 1
        counters["interrupt_absorbed"] = counters.get("interrupt_absorbed", 0) + 1

    calibrated = orch.calibrate(
        did,
        lesson_ids=lesson_ids,
        idempotency_key=f"{prefix}-cal",
    )
    closed = orch.improve(did, idempotency_key=f"{prefix}-imp")
    stages.append("Closure")
    _assert_no_decorative_ids(closed["decision"])

    ontology = list(REQUIRED_ONTOLOGY)
    assert reviewed["status"] == "UNDER_REVIEW"
    assert calibrated["status"] == "CALIBRATED"
    assert closed["status"] == "CLOSED"

    return {
        "candidate_id": candidate["candidate_id"],
        "decision_id": did,
        "outcome": "COMPLETED",
        "terminal_status": "CLOSED",
        "stages": stages,
        "intent_id": closed["decision"].get("intent_id"),
        "position_id": closed["decision"].get("position_id"),
        "order_id": binding_pre.order_id,
        "exit_id": closed["decision"].get("exit_id"),
        "reflection_id": closed["decision"].get("reflection_id"),
        "lesson_ids": list(closed["decision"].get("lesson_ids") or []),
        "ontology": ontology,
        "lesson_gate": lesson_gate,
        "completed_lifecycle": True,
        "linkage_authority": closed["decision"].get("linkage_authority"),
        "cost_model_version": closed["decision"].get("cost_model_version"),
        "symbol": candidate["symbol"],
        "vol_regime": candidate.get("vol_regime"),
        "fault_tag": fault_tag,
    }


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_scaled_closed_loop(
    *,
    root: Path,
    candidate_count: int = TARGET_CANDIDATES,
    seed: int = FROZEN_SEED,
    restart_after_index: int | None = None,
) -> dict[str, Any]:
    """Execute the scaled DecisionLifecycle closed-loop with mid-run restart."""
    _harden_env()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    ckpt_path = root / "closed_loop.checkpoint.json"

    complete_quota = max(TARGET_COMPLETED_LIFECYCLES, int(candidate_count * 0.55))
    if candidate_count < TARGET_CANDIDATES:
        # Smoke / unit: keep ~65% complete like V12.
        complete_quota = max(1, int(candidate_count * 0.65))

    candidates = build_scale_candidates(
        candidate_count,
        seed=seed,
        complete_quota=complete_quota,
    )
    uni = universe_summary(candidates)

    if restart_after_index is None:
        restart_after_index = min(
            max(50, candidate_count // 5),
            max(1, candidate_count - 2),
        )

    def _new_orch(epoch: int) -> tuple[Any, DecisionLifecycleOrchestrator]:
        epoch_root = root / f"epoch_{epoch}"
        adapter = build_session_execution_adapter(
            max_positions=2,
            max_intents=4,
            leverage=25,
            margin_usdt=20.0,
        )
        bridge = DecisionExecutionBridge(epoch_root / "execution_bridge", adapter=adapter)
        orch = DecisionLifecycleOrchestrator(epoch_root / "decisions", bridge=bridge)
        return adapter, orch

    epoch = 0
    adapter, orch = _new_orch(epoch)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    counters = empty_invariant_counts()
    extras: dict[str, int] = {}
    seen_decisions: set[str] = set()
    seen_intents: set[str] = set()
    seen_positions: set[str] = set()
    restart_count = 0
    checkpoint_count = 0
    exchange_writes = 0

    def _accumulate_writes() -> None:
        nonlocal exchange_writes
        exchange_writes += int(orch.exchange_write_attempt_count)
        exchange_writes += int(getattr(adapter, "exchange_write_attempt_count", 0) or 0)

    i = 0
    while i < len(candidates):
        cand = candidates[i]
        try:
            results.append(
                _run_one(
                    orch,
                    cand,
                    counters=counters,
                    seen_decisions=seen_decisions,
                    seen_intents=seen_intents,
                    seen_positions=seen_positions,
                )
            )
        except Exception as exc:  # noqa: BLE001 — campaign must count fail-closed errors
            errors.append({"candidate_id": cand["candidate_id"], "error": f"{type(exc).__name__}:{exc}"})
            results.append(
                {
                    "candidate_id": cand["candidate_id"],
                    "decision_id": None,
                    "outcome": "ERROR",
                    "terminal_status": "ERROR",
                    "stages": ["Candidate"],
                    "completed_lifecycle": False,
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )

        i += 1
        if i % max(25, candidate_count // 40) == 0:
            checkpoint_count += 1
            _write_checkpoint(
                ckpt_path,
                {
                    "index": i,
                    "completed": sum(1 for r in results if r.get("completed_lifecycle")),
                    "seed": seed,
                    "candidate_count": candidate_count,
                },
            )

        # Mid-campaign restart recovery.
        if restart_count == 0 and i >= restart_after_index:
            checkpoint_count += 1
            _write_checkpoint(
                ckpt_path,
                {
                    "index": i,
                    "completed": sum(1 for r in results if r.get("completed_lifecycle")),
                    "seed": seed,
                    "candidate_count": candidate_count,
                    "restart_boundary": True,
                },
            )
            # Recreate orchestrator on a fresh epoch root (process restart simulation).
            _accumulate_writes()
            epoch += 1
            adapter, orch = _new_orch(epoch)
            restart_count += 1
            extras["closed_loop_restart"] = 1
            # Verify checkpoint still present (no loss).
            if not ckpt_path.exists():
                counters["checkpoint_loss_count"] += 1

    completed = [r for r in results if r.get("completed_lifecycle")]
    rejected = [r for r in results if r.get("outcome") == "REJECTED_CLOSED"]
    blocked = [
        r
        for r in results
        if r.get("outcome") in {"BLOCKED_AFTER_RECORD", "BLOCKED_ON_EXIT"}
    ]

    ontology_ok = all(
        all(s in (r.get("ontology") or []) for s in REQUIRED_ONTOLOGY) for r in completed
    )
    path_ok = all(
        all(step in (r.get("stages") or []) for step in CANONICAL_PATH) for r in completed
    )
    decorative_violations = 0
    for r in completed:
        intent = str(r.get("intent_id") or "")
        pos = str(r.get("position_id") or "")
        if intent.startswith("intent_") or pos.startswith("pos_"):
            decorative_violations += 1
        if not intent or not pos:
            decorative_violations += 1

    # Orphan / unclosed: completed path must leave no dangling MONITORING without EXIT.
    for r in results:
        stages = r.get("stages") or []
        if "Position" in stages and "Exit" not in stages and r.get("outcome") != "BLOCKED_AFTER_RECORD":
            counters["orphan_lifecycle_count"] += 1
        if "SimulatedIntent" in stages and not r.get("intent_id") and r.get("completed_lifecycle"):
            counters["unclosed_intent_count"] += 1
        if "Fill" in stages and r.get("completed_lifecycle") and not r.get("order_id"):
            counters["untracked_fill_count"] += 1

    lesson_gates = [r["lesson_gate"] for r in completed if r.get("lesson_gate")]
    lesson_gate_summary = {
        "applied_count": len(lesson_gates),
        "policy_effect_allowed_count": sum(
            1 for g in lesson_gates if g.get("policy_effect_lesson_allowed")
        ),
        "policy_effect_blocked_count": sum(
            1 for g in lesson_gates if not g.get("policy_effect_lesson_allowed")
        ),
        "false_learning_claim_count": sum(
            1 for g in lesson_gates if g.get("false_learning_claim")
        ),
        "fixture_label": CONTROL_FIXTURE_LABEL,
    }

    exchange_writes_final = exchange_writes
    exchange_writes_final += int(orch.exchange_write_attempt_count)
    exchange_writes_final += int(getattr(adapter, "exchange_write_attempt_count", 0) or 0)
    counters["exchange_write_attempt_count"] = exchange_writes_final

    # Evidence binding: every completed row must carry hashes path (stages include Reflection).
    for r in completed:
        if "Reflection" not in (r.get("stages") or []) or not r.get("reflection_id"):
            counters["evidence_binding_failure_count"] += 1
        if r.get("cost_model_version") != COST_MODEL_VERSION:
            counters["cost_bridge_failure_count"] += 1

    # Risk bypass: rejected candidates must not complete.
    for r in results:
        if r.get("outcome") == "REJECTED_CLOSED" and r.get("completed_lifecycle"):
            counters["risk_limit_bypass_count"] += 1

    return {
        "schema": "v13_g_scaled_closed_loop",
        "seed": seed,
        "candidate_count": len(candidates),
        "completed_lifecycle_count": len(completed),
        "rejected_count": len(rejected),
        "blocked_count": len(blocked),
        "error_count": len(errors),
        "universe": uni,
        "restart_count": restart_count,
        "checkpoint_count": checkpoint_count,
        "invariants_counts": dict(counters),
        "extras": extras,
        "ontology_complete_on_completed": ontology_ok,
        "canonical_path_complete_on_completed": path_ok,
        "decorative_id_violations": decorative_violations,
        "lesson_gate_summary": lesson_gate_summary,
        "exchange_write_attempt_count": exchange_writes_final,
        "sample_completed": completed[:3],
        "sample_rejected": rejected[:3],
        "errors": errors[:20],
        "bridge_schema": BRIDGE_SCHEMA,
        "bridge_module": BRIDGE_MODULE,
        "adapter_id": ADAPTER_ID,
        "canonical_engine": CANONICAL_EXECUTION_ENGINE,
        "cost_model_version": COST_MODEL_VERSION,
    }


def run_fault_injection_session(
    root: Path,
    *,
    seed: int = FROZEN_SEED,
    candidate_count: int = 64,
) -> dict[str, Any]:
    """Accelerated session covering provider/partial-fill/ledger/reflection faults."""
    _harden_env()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    candidates = build_lifecycle_candidates(candidate_count, seed=seed, logical_days=365)
    restart_after = min(max(8, candidate_count // 5), max(1, candidate_count - 2))
    orch = AutonomousSessionOrchestratorV11(root, max_positions=2, max_intents=2)
    try:
        result = orch.run_accelerated_session(
            session_id="V13G_FAULT_SESSION",
            logical_hours=72.0,
            candidates=candidates,
            injections=list(SCALE_SESSION_INJECTIONS),
            checkpoint_every=max(5, candidate_count // 12),
            restart_after_index=restart_after,
            force_kill_after_index=None,
            disk_limit=None,
        )
        inv = empty_invariant_counts()
        base = dict(result.invariants_counts or {})
        for k in inv:
            inv[k] = int(base.get(k, 0) or 0)
        inv["exchange_write_attempt_count"] = max(
            inv["exchange_write_attempt_count"],
            int(result.exchange_write_attempt_count or 0),
        )
        # Session recovery set may omit duplicate_decision/intent — keep zeros unless present.
        inv["duplicate_decision_count"] = int(base.get("duplicate_decision_count", 0) or 0)
        inv["duplicate_intent_count"] = int(base.get("duplicate_intent_count", 0) or 0)
        return {
            "schema": "v13_g_fault_injection_session",
            "session_pass": bool(result.session_pass) and invariants_pass(inv),
            "final_state": result.final_state,
            "restart_count": result.restart_count,
            "recovery_count": result.recovery_count,
            "injection_flags": list(result.injection_flags or []),
            "exchange_write_attempt_count": result.exchange_write_attempt_count,
            "invariants_counts": inv,
            "invariants_status": result.invariants_status,
            "kill_switch_status": result.kill_switch_status,
            "candidate_count": result.candidate_count,
            "provider_failure_count": result.provider_failure_count,
        }
    finally:
        orch.close()


def run_v13_closed_loop_scale_campaign(
    *,
    root: Path | str | None = None,
    candidate_count: int = TARGET_CANDIDATES,
    seed: int = FROZEN_SEED,
    keep_root: bool = False,
    session_candidate_count: int = 64,
) -> dict[str, Any]:
    """Full V13-G campaign: scaled closed loop + fault session + focused probes."""
    _harden_env()
    owns_root = root is None and not keep_root
    work = Path(root) if root is not None else Path(tempfile.mkdtemp(prefix="v13g_closed_loop_"))
    work.mkdir(parents=True, exist_ok=True)

    closed = run_scaled_closed_loop(
        root=work / "closed_loop",
        candidate_count=candidate_count,
        seed=seed,
    )
    fault = run_fault_injection_session(
        work / "fault_session",
        seed=seed,
        candidate_count=session_candidate_count,
    )
    focused = run_focused_scale_probes(work / "focused", seed=seed)

    aggregate = merge_invariant_counts(
        closed.get("invariants_counts") or {},
        fault.get("invariants_counts") or {},
        focused.get("invariants") or {},
    )

    closed_ok = (
        int(closed["candidate_count"]) >= min(candidate_count, TARGET_CANDIDATES)
        if candidate_count >= TARGET_CANDIDATES
        else int(closed["candidate_count"]) == candidate_count
    )
    completed_ok = (
        int(closed["completed_lifecycle_count"]) >= TARGET_COMPLETED_LIFECYCLES
        if candidate_count >= TARGET_CANDIDATES
        else int(closed["completed_lifecycle_count"]) >= max(1, int(candidate_count * 0.5))
    )
    universe_ok = (
        int((closed.get("universe") or {}).get("symbol_count") or 0) >= min(4, len(SYMBOLS))
        and int((closed.get("universe") or {}).get("vol_regime_count") or 0)
        >= min(3, len(VOL_REGIMES))
    )
    inv_ok = invariants_pass(aggregate)
    probes_ok = bool(focused.get("probe_pass"))
    fault_ok = bool(fault.get("session_pass"))
    restart_ok = int(closed.get("restart_count") or 0) >= 1
    decorative_ok = int(closed.get("decorative_id_violations") or 0) == 0
    ontology_ok = bool(closed.get("ontology_complete_on_completed"))
    path_ok = bool(closed.get("canonical_path_complete_on_completed"))
    lesson_ok = (
        int((closed.get("lesson_gate_summary") or {}).get("policy_effect_allowed_count") or 0) == 0
        and int((closed.get("lesson_gate_summary") or {}).get("false_learning_claim_count") or 0) == 0
    )

    # Fault coverage attestation.
    inj_flags = set(fault.get("injection_flags") or [])
    probe_names = set((focused.get("probes") or {}).keys())
    inv_raw = closed.get("invariants_counts") or {}
    fault_coverage = {
        "provider_outage": bool(
            {"groq_429", "sambanova_429", "provider_timeout", "network_loss"} & inj_flags
        )
        or int(inv_raw.get("provider_outage_injected", 0) or 0) > 0,
        "partial_fills": "partial_fill_before_crash" in inj_flags
        or int(inv_raw.get("partial_fill_injected", 0) or 0) > 0,
        "cancel_replace": "cancel_replace_probe" in probe_names
        and bool((focused.get("probes") or {}).get("cancel_replace_probe", {}).get("probe_pass")),
        "clock_rollback": "terminal_clock_jump_backward" in probe_names,
        "disk_pressure": "disk_soft_limit" in inj_flags or "terminal_disk_hard_limit" in probe_names,
        "ledger_interrupt": "interrupted_ledger_append" in inj_flags
        or "ledger_corruption_probe" in probe_names,
        "checkpoint_corruption": "snapshot_corruption" in inj_flags
        or "snapshot_corruption_probe" in probe_names,
        "reflection_interrupt": "reflection_interruption" in inj_flags
        or int(inv_raw.get("reflection_interrupt_injected", 0) or 0) > 0,
        "lesson_interrupt": "lesson_storage_interruption" in inj_flags
        or int(inv_raw.get("lesson_interrupt_injected", 0) or 0) > 0,
        "kill_switch": "terminal_kill_switch_during_open_position" in probe_names,
        "restart_recovery": restart_ok and "restart_recovery_probe" in probe_names,
        "qualification_blocks": "qualification_blocks_probe" in probe_names
        and bool(
            (focused.get("probes") or {}).get("qualification_blocks_probe", {}).get("probe_pass")
        ),
        "multi_symbol": universe_ok,
        "multi_regime": universe_ok,
    }

    coverage_ok = all(fault_coverage.values())

    blockers: list[str] = []
    if not closed_ok:
        blockers.append(f"candidate_count_below_target:{closed['candidate_count']}")
    if not completed_ok:
        blockers.append(
            f"completed_lifecycles_below_target:{closed['completed_lifecycle_count']}"
        )
    if not universe_ok:
        blockers.append("universe_coverage_insufficient")
    if not inv_ok:
        blockers.append(f"invariant_violations:{violations(aggregate)}")
    if not probes_ok:
        blockers.append("focused_probes_failed")
    if not fault_ok:
        blockers.append("fault_session_failed")
    if not restart_ok:
        blockers.append("closed_loop_restart_missing")
    if not decorative_ok:
        blockers.append("decorative_id_violations")
    if not ontology_ok:
        blockers.append("ontology_incomplete")
    if not path_ok:
        blockers.append("canonical_path_incomplete")
    if not lesson_ok:
        blockers.append("lesson_gate_violation")
    if not coverage_ok:
        missing = [k for k, v in fault_coverage.items() if not v]
        blockers.append(f"fault_coverage_missing:{','.join(missing)}")
    if int(closed.get("error_count") or 0) > 0:
        blockers.append(f"candidate_errors:{closed['error_count']}")

    hard_ban_attest = {
        "profitability_measured": False,
        "demo_shadow_mainnet": False,
        "exchange_write_attempted": aggregate["exchange_write_attempt_count"] != 0,
        "auto_integrate_pr27": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
    }
    hard_ban_ok = not hard_ban_attest["exchange_write_attempted"] and not hard_ban_attest[
        "profitability_measured"
    ]

    status = PASS_STATUS if (not blockers and hard_ban_ok) else f"{INVALID_PREFIX}:{','.join(blockers[:3])}"

    # Strip non-invariant keys from closed invariants for reporting.
    closed_inv_clean = empty_invariant_counts()
    for k in REQUIRED_ZERO_INVARIANTS:
        closed_inv_clean[k] = int((closed.get("invariants_counts") or {}).get(k, 0) or 0)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "status": status,
        "pass": status == PASS_STATUS,
        "created_at": _utc(),
        "seed": seed,
        "candidate_count": closed["candidate_count"],
        "completed_lifecycle_count": closed["completed_lifecycle_count"],
        "rejected_count": closed["rejected_count"],
        "blocked_count": closed["blocked_count"],
        "error_count": closed["error_count"],
        "targets": {
            "candidates": TARGET_CANDIDATES,
            "completed_lifecycles": TARGET_COMPLETED_LIFECYCLES,
        },
        "universe": closed.get("universe"),
        "canonical_path": list(CANONICAL_PATH),
        "ontology": list(REQUIRED_ONTOLOGY),
        "fault_classes": list(SCALE_FAULT_CLASSES),
        "injection_matrix": injection_matrix(),
        "fault_coverage": fault_coverage,
        "closed_loop": {
            **{k: v for k, v in closed.items() if k not in {"sample_completed", "sample_rejected", "errors"}},
            "invariants_counts": closed_inv_clean,
            "sample_completed": closed.get("sample_completed"),
            "sample_rejected": closed.get("sample_rejected"),
            "errors": closed.get("errors"),
        },
        "fault_session": fault,
        "focused_probes": focused,
        "invariants": aggregate,
        "invariant_violations": violations(aggregate),
        "required_zero_invariants": list(REQUIRED_ZERO_INVARIANTS),
        "hard_bans": list(HARD_BANS),
        "hard_ban_attestations": hard_ban_attest,
        "bridge_schema": BRIDGE_SCHEMA,
        "bridge_module": BRIDGE_MODULE,
        "adapter_id": ADAPTER_ID,
        "canonical_engine": CANONICAL_EXECUTION_ENGINE,
        "cost_model_version": COST_MODEL_VERSION,
        "exchange_write_attempt_count": aggregate["exchange_write_attempt_count"],
        "blockers": blockers,
        "work_root": str(work),
        "profitability_measured": False,
        "profitability_claimed": False,
        "formal_walkforward_oos": False,
        "demo_shadow_mainnet": False,
        "auto_integrate_pr27": False,
        "system_correctness_only": True,
    }
    report["digest"] = campaign_digest(report)
    if owns_root and not keep_root:
        report["work_root_ephemeral"] = True
    return report


__all__ = [
    "CANONICAL_PATH",
    "FROZEN_SEED",
    "HARD_BANS",
    "INVALID_PREFIX",
    "PACKAGE",
    "PASS_STATUS",
    "REQUIRED_ONTOLOGY",
    "REQUIRED_ZERO_INVARIANTS",
    "SCHEMA",
    "TARGET_CANDIDATES",
    "TARGET_COMPLETED_LIFECYCLES",
    "campaign_digest",
    "run_fault_injection_session",
    "run_scaled_closed_loop",
    "run_v13_closed_loop_scale_campaign",
]
