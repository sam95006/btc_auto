"""V12-A closed-loop campaign: DecisionLifecycle + DecisionExecutionBridge proof.

Uses existing V11.1 Decision↔Execution bridge, risk gates, and lifecycle ontology:
MONITORING → EXITED → UNDER_REVIEW → CALIBRATED → CLOSED.

Intent/Position IDs come only from the canonical execution adapter (no decorative mint).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

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

SCHEMA = "v12_founder_private_closed_loop"
PASS_STATUS = "NEXUS_V12_CLOSED_LOOP_PASS"
INVALID_PREFIX = "NEXUS_V12_CLOSED_LOOP_INVALID"
PACKAGE = "NEXUS_V12_FOUNDER_PRIVATE_CLOSED_LOOP"
FROZEN_SEED = 12_001
TARGET_CANDIDATES = 1000
TARGET_COMPLETED_LIFECYCLES = 500

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

HARD_BANS: tuple[str, ...] = (
    "no_exchange_write",
    "no_demo_shadow_mainnet_real_money",
    "no_formal_walkforward_oos",
    "no_profitability_claims",
    "no_decorative_intent_position_ids",
    "no_auto_integrate_pr27",
    "no_g_deletion",
)

# Ontology stages that must appear on every completed lifecycle.
REQUIRED_ONTOLOGY: tuple[str, ...] = (
    "MONITORING",
    "EXITED",
    "UNDER_REVIEW",
    "CALIBRATED",
    "CLOSED",
)

HISTORICAL_START = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _utc() -> str:
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
        "exchange_write_attempt_count": payload.get("exchange_write_attempt_count"),
        "canonical_path": payload.get("canonical_path"),
        "ontology": payload.get("ontology"),
        "bridge_schema": payload.get("bridge_schema"),
        "invariants": payload.get("invariants"),
        "lesson_gate_summary": payload.get("lesson_gate_summary"),
    }
    raw = json.dumps(material, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_historical_candidates(
    *,
    count: int = TARGET_CANDIDATES,
    seed: int = FROZEN_SEED,
) -> list[dict[str, Any]]:
    """Deterministic historical-replay candidate stream (synthetic PIT bars)."""
    out: list[dict[str, Any]] = []
    # Reserve ~65% for full closed-loop completion, rest for reject/block coverage.
    complete_quota = max(TARGET_COMPLETED_LIFECYCLES, int(count * 0.65))
    for i in range(count):
        pit = HISTORICAL_START + timedelta(hours=i)
        mode = "COMPLETE"
        if i >= complete_quota:
            # Alternate reject vs advisory-block among residual candidates.
            mode = "REJECT" if (i + seed) % 2 == 0 else "ADVISORY_REJECT"
        out.append(
            {
                "candidate_id": f"hist_cand_{seed}_{i:04d}",
                "market_context_id": f"hist_mctx_{seed}",
                "point_in_time_timestamp": pit.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "symbol": "BTCUSDT",
                "side": "BUY" if i % 2 == 0 else "SELL",
                "mark_price": Decimal("100") + Decimal(i % 17),
                "mode": mode,
                "replay_index": i,
                "historical": True,
                "seed": seed,
            }
        )
    return out


def _evidence_for(candidate: dict[str, Any]) -> dict[str, Any]:
    i = int(candidate["replay_index"])
    blobs = {
        f"ev_{i}_mid": f"mid|{candidate['candidate_id']}|{candidate['mark_price']}",
        f"ev_{i}_spread": f"spread|{candidate['candidate_id']}|1.0",
        f"ev_{i}_ts": f"ts|{candidate['point_in_time_timestamp']}",
    }
    ids = list(blobs.keys())
    return {
        "evidence_ids": ids,
        "evidence_hashes": [hash_evidence_blob(blobs[eid]) for eid in ids],
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": 12.0, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts"],
            "present_fields": ["mid", "spread", "ts"],
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
) -> dict[str, Any]:
    """Drive one candidate through the canonical closed-loop path (or reject/close)."""
    stages: list[str] = ["Candidate"]
    ev = _evidence_for(candidate)
    prefix = f"v12-{candidate['replay_index']:04d}"
    mode = str(candidate["mode"])

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
    did = observed["decision"]["decision_id"]
    stages.append("Decision")

    orch.understand(
        did,
        AI_reasoner_outputs=[
            {
                "provider": "historical_replay_sim",
                "view": "neutral",
                "candidate_id": candidate["candidate_id"],
                "pit": candidate["point_in_time_timestamp"],
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
            "idempotency_key": f"v12intent:{candidate['candidate_id']}",
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
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
        }

    stages.append("SimulatedIntent")
    binding_pre = orch.bridge.binding_for(did)
    if binding_pre is None or not binding_pre.order_id:
        raise DecisionLifecycleError("missing_simulated_order_after_approve")
    stages.append("SimulatedOrder")

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
        }
    stages.extend(["Fill", "Position"])
    _assert_no_decorative_ids(recorded["decision"])

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
        }
    stages.append("Exit")

    reviewed = orch.review(
        did,
        reflection_id=f"refl_hist_{candidate['replay_index']:04d}",
        idempotency_key=f"{prefix}-rev",
    )
    stages.append("Reflection")

    # Lesson gate: simulated/control fixture — policy-effect lessons blocked.
    lesson_gate = apply_lesson_gate_v11(
        terminal_status="INCOMPLETE_PROVIDER_CAPACITY",
        quality_gates_passed=False,
        proposed_policy_effect_lesson_count=1,
        fixture_label=CONTROL_FIXTURE_LABEL,
    )
    stages.append("LessonGate")
    lesson_ids: list[str] = []
    if lesson_gate["policy_effect_lesson_allowed"]:
        lesson_ids.append(f"policy_lesson_{candidate['replay_index']:04d}")
    else:
        # Process-only reflection tag (not a policy-effect lesson).
        lesson_ids.append(f"process_note_{candidate['replay_index']:04d}")

    calibrated = orch.calibrate(
        did,
        lesson_ids=lesson_ids,
        idempotency_key=f"{prefix}-cal",
    )
    closed = orch.improve(did, idempotency_key=f"{prefix}-imp")
    stages.append("Closure")
    _assert_no_decorative_ids(closed["decision"])

    ontology = [
        "MONITORING",
        "EXITED",
        "UNDER_REVIEW",
        "CALIBRATED",
        "CLOSED",
    ]
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
    }


def run_v12_closed_loop_campaign(
    *,
    root: Path | str | None = None,
    candidate_count: int = TARGET_CANDIDATES,
    seed: int = FROZEN_SEED,
    keep_root: bool = False,
) -> dict[str, Any]:
    """Execute the V12-A closed-loop proof campaign."""
    _harden_env()
    owns_root = root is None and not keep_root
    work = Path(root) if root is not None else Path(tempfile.mkdtemp(prefix="v12_closed_loop_"))
    work.mkdir(parents=True, exist_ok=True)

    adapter = build_session_execution_adapter(
        max_positions=2,
        max_intents=4,
        leverage=25,
        margin_usdt=20.0,
    )
    bridge = DecisionExecutionBridge(work / "execution_bridge", adapter=adapter)
    orch = DecisionLifecycleOrchestrator(work / "decisions", bridge=bridge)

    candidates = build_historical_candidates(count=candidate_count, seed=seed)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for cand in candidates:
        try:
            results.append(_run_one(orch, cand))
        except Exception as exc:  # noqa: BLE001 — campaign must count fail-closed errors
            errors.append(
                {
                    "candidate_id": cand["candidate_id"],
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
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

    completed = [r for r in results if r.get("completed_lifecycle")]
    rejected = [r for r in results if r.get("outcome") == "REJECTED_CLOSED"]
    blocked = [
        r
        for r in results
        if r.get("outcome") in {"BLOCKED_AFTER_RECORD", "BLOCKED_ON_EXIT"}
    ]

    # Spot-check ontology completeness on completed set.
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

    exchange_writes = int(orch.exchange_write_attempt_count)
    # Adapter may also track attempts.
    exchange_writes += int(getattr(adapter, "exchange_write_attempt_count", 0) or 0)

    invariants = {
        "exchange_write_attempt_count": exchange_writes,
        "order_attempt_count_via_decision": int(orch.order_attempt_count),
        "strategy_mutation_attempt_count": int(orch.strategy_mutation_attempt_count),
        "decorative_id_violations": decorative_violations,
        "ontology_complete_on_completed": ontology_ok,
        "canonical_path_complete_on_completed": path_ok,
        "bridge_schema": BRIDGE_SCHEMA,
        "bridge_module": BRIDGE_MODULE,
        "adapter_id": ADAPTER_ID,
        "canonical_engine": CANONICAL_EXECUTION_ENGINE,
        "cost_model_version": COST_MODEL_VERSION,
        "linkage_authority_bridge": all(
            r.get("linkage_authority") == BRIDGE_MODULE for r in completed
        ),
        "lesson_gate_blocks_policy_effect": lesson_gate_summary["policy_effect_allowed_count"]
        == 0,
        "false_learning_claim_count": lesson_gate_summary["false_learning_claim_count"],
    }

    blockers: list[str] = []
    if len(candidates) < TARGET_CANDIDATES and candidate_count >= TARGET_CANDIDATES:
        blockers.append("candidate_count_below_target")
    if len(completed) < TARGET_COMPLETED_LIFECYCLES:
        blockers.append(
            f"completed_lifecycles_below_target:{len(completed)}<{TARGET_COMPLETED_LIFECYCLES}"
        )
    if exchange_writes != 0:
        blockers.append(f"exchange_write_attempt_count_nonzero:{exchange_writes}")
    if decorative_violations:
        blockers.append(f"decorative_id_violations:{decorative_violations}")
    if not ontology_ok:
        blockers.append("ontology_incomplete")
    if not path_ok:
        blockers.append("canonical_path_incomplete")
    if errors:
        blockers.append(f"candidate_errors:{len(errors)}")
    if lesson_gate_summary["policy_effect_allowed_count"] != 0:
        blockers.append("lesson_gate_allowed_policy_effect_under_fixture")
    if lesson_gate_summary["false_learning_claim_count"] != 0:
        blockers.append("false_learning_claim")

    status = PASS_STATUS if not blockers else f"{INVALID_PREFIX}:{','.join(blockers[:3])}"

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "status": status,
        "pass": status == PASS_STATUS,
        "created_at": _utc(),
        "seed": seed,
        "candidate_count": len(candidates),
        "completed_lifecycle_count": len(completed),
        "rejected_count": len(rejected),
        "blocked_count": len(blocked),
        "error_count": len(errors),
        "targets": {
            "candidates": TARGET_CANDIDATES,
            "completed_lifecycles": TARGET_COMPLETED_LIFECYCLES,
        },
        "canonical_path": list(CANONICAL_PATH),
        "ontology": list(REQUIRED_ONTOLOGY),
        "bridge_schema": BRIDGE_SCHEMA,
        "bridge_module": BRIDGE_MODULE,
        "adapter_id": ADAPTER_ID,
        "canonical_engine": CANONICAL_EXECUTION_ENGINE,
        "cost_model_version": COST_MODEL_VERSION,
        "exchange_write_attempt_count": exchange_writes,
        "hard_bans": list(HARD_BANS),
        "invariants": invariants,
        "lesson_gate_summary": lesson_gate_summary,
        "blockers": blockers,
        "work_root": str(work),
        "sample_completed": completed[:3],
        "sample_rejected": rejected[:3],
        "errors": errors[:20],
        "profitability_claimed": False,
        "formal_walkforward_oos": False,
        "demo_shadow_mainnet": False,
        "auto_integrate_pr27": False,
    }
    report["digest"] = campaign_digest(report)

    if owns_root and not keep_root:
        # Leave work root for evidence when keep_root; otherwise caller owns cleanup.
        report["work_root_ephemeral"] = True

    return report
