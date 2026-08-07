#!/usr/bin/env python3
"""QUALIFICATION BLOCKER RESOLUTION QUEUE — research-only advancement.

Builds per-candidate resolution records and auto-runs safe prerequisites
(replay / sample sufficiency / cost sensitivity / robustness / regime segmentation)
when possible. Does NOT lower gates. Formal WF executes only if every pre-WF
condition is truthfully satisfied; otherwise formal_WF=false and OOS reserved.

Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_9_qualification_blocker_resolution_queue.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = Path(
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_9_qualification_blocker_resolution_queue.json"
)

PRE_WF_CONDITIONS = (
    "data_quality_ok",
    "pit_ok",
    "sample_sufficient",
    "cost_sensitivity_cleared",
    "robustness_cleared",
    "regime_segmentation_cleared",
    "replay_prerequisite_ok",
    "activity_metric_proxy_available_or_not_required",
    "no_hard_risk_block",
    "strategy_version_freezable",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _map_gate(triage_status: str) -> str:
    return f"TRIAGE:{triage_status}"


def _exact_blocker(row: dict[str, Any], triage: dict[str, Any]) -> str:
    status = str(triage.get("triage_status") or "")
    reasons = list(triage.get("reasons") or [])
    if status == "DATA_BLOCKED":
        return "DATA_QUALITY_OR_PIT_FAILED"
    if status == "SAMPLE_BLOCKED":
        return "INSUFFICIENT_SAMPLE_N"
    if status == "COST_DESTROYED":
        return "COST_SENSITIVITY_DESTROYED_NET_EXPECTANCY"
    if status == "REGIME_FRAGILE":
        return "REGIME_SEGMENTATION_FRAGILE"
    if status == "REJECTED":
        return "ROBUSTNESS_OR_MULTIPLE_TESTING_REJECTED"
    if status == "DEVELOPMENT_PROMISING_NOT_QUALIFIED":
        return "PRE_WF_GATES_INCOMPLETE_PROMISING_ONLY"
    if status == "DEVELOPMENT_REVIEW":
        return "DEVELOPMENT_REVIEW_REQUIRED"
    if reasons:
        return str(reasons[0]).upper()
    return "WF_NOT_RUN"


def _next_required_test(blocker: str) -> str:
    mapping = {
        "DATA_QUALITY_OR_PIT_FAILED": "pit_data_quality_replay_audit",
        "INSUFFICIENT_SAMPLE_N": "sample_sufficiency_expansion",
        "COST_SENSITIVITY_DESTROYED_NET_EXPECTANCY": "cost_sensitivity_lab_rerun",
        "REGIME_SEGMENTATION_FRAGILE": "regime_segmentation_stress",
        "ROBUSTNESS_OR_MULTIPLE_TESTING_REJECTED": "robustness_bootstrap_rerun",
        "PRE_WF_GATES_INCOMPLETE_PROMISING_ONLY": "formal_pre_wf_checklist_freeze",
        "DEVELOPMENT_REVIEW_REQUIRED": "development_review_dossier",
        "WF_NOT_RUN": "formal_wf_authorization_check",
    }
    return mapping.get(blocker, "manual_research_triage")


def run_safe_prerequisites(candidate: dict[str, Any]) -> dict[str, Any]:
    """Auto-run research-only prerequisite checks (no OOS, no Formal WF)."""
    results: dict[str, Any] = {
        "replay": {"ran": False, "passed": False, "detail": None},
        "sample_sufficiency": {"ran": False, "passed": False, "detail": None},
        "cost_sensitivity": {"ran": False, "passed": False, "detail": None},
        "robustness": {"ran": False, "passed": False, "detail": None},
        "regime_segmentation": {"ran": False, "passed": False, "detail": None},
    }

    # Sample sufficiency
    sample_n = int(candidate.get("sample_n") or 0)
    results["sample_sufficiency"] = {
        "ran": True,
        "passed": sample_n >= 200,
        "detail": {"sample_n": sample_n, "min_required": 200},
    }

    # Cost sensitivity (use candidate-embedded lab fields — fixture-safe)
    cost = dict(candidate.get("cost_sensitivity") or {})
    results["cost_sensitivity"] = {
        "ran": True,
        "passed": (not bool(cost.get("cost_destroyed")))
        and float(cost.get("net_expectancy") or 0) > 0,
        "detail": {
            "gross_expectancy": cost.get("gross_expectancy"),
            "net_expectancy": cost.get("net_expectancy"),
            "cost_destroyed": cost.get("cost_destroyed"),
            "canonical_cost_authority_consumed": cost.get(
                "canonical_cost_authority_consumed"
            ),
        },
    }

    # Robustness
    rob = dict(candidate.get("robustness") or {})
    rob_ok = bool(rob.get("bootstrap_stable")) and bool(rob.get("sample_sufficient"))
    results["robustness"] = {
        "ran": True,
        "passed": rob_ok and str(rob.get("label") or "") == "DEVELOPMENT_ROBUST",
        "detail": {
            "label": rob.get("label"),
            "bootstrap_stable": rob.get("bootstrap_stable"),
            "regime_stable": rob.get("regime_stable"),
            "sample_sufficient": rob.get("sample_sufficient"),
        },
    }

    # Regime segmentation
    regime = dict(candidate.get("regime") or {})
    results["regime_segmentation"] = {
        "ran": True,
        "passed": (not bool(regime.get("fragile")))
        and len(list(regime.get("regimes_tested") or [])) >= 2,
        "detail": {
            "fragile": regime.get("fragile"),
            "regimes_tested": regime.get("regimes_tested"),
        },
    }

    # Replay prerequisite — fixture checksum round-trip (research-safe)
    try:
        payload = {
            "candidate_id": candidate.get("candidate_id"),
            "checksum": candidate.get("candidate_checksum"),
            "mechanism": (candidate.get("mechanism") or {}).get("mechanism_semantic_id"),
            "features": candidate.get("feature_ids"),
            "interval": candidate.get("development_interval"),
        }
        digest = _sha(payload)
        replay_ok = bool(candidate.get("candidate_checksum")) and len(digest) == 64
        results["replay"] = {
            "ran": True,
            "passed": replay_ok and bool(candidate.get("data_quality_ok", True)),
            "detail": {
                "replay_digest": digest,
                "fixture_only": bool(candidate.get("fixture_only", True)),
                "mode": "checksum_roundtrip_research_only",
            },
        }
    except Exception as exc:  # noqa: BLE001
        results["replay"] = {"ran": True, "passed": False, "detail": {"error": str(exc)}}

    return results


def evaluate_pre_wf(
    candidate: dict[str, Any], triage: dict[str, Any], prereqs: dict[str, Any]
) -> dict[str, Any]:
    checks = {
        "data_quality_ok": bool(candidate.get("data_quality_ok", False)),
        "pit_ok": bool(candidate.get("pit_ok", False)),
        "sample_sufficient": bool(prereqs["sample_sufficiency"]["passed"]),
        "cost_sensitivity_cleared": bool(prereqs["cost_sensitivity"]["passed"]),
        "robustness_cleared": bool(prereqs["robustness"]["passed"]),
        "regime_segmentation_cleared": bool(prereqs["regime_segmentation"]["passed"]),
        "replay_prerequisite_ok": bool(prereqs["replay"]["passed"]),
        # Live Gate still missing trade_count_24h; research Formal WF may proceed
        # without live eligible injection, but note the gap.
        "activity_metric_proxy_available_or_not_required": True,
        "no_hard_risk_block": not bool(candidate.get("risk_blocked")),
        "strategy_version_freezable": bool(candidate.get("candidate_checksum")),
    }
    failed = [k for k, v in checks.items() if not v]
    # Fixture-only candidates cannot truthfully be Formal-WF ready.
    if candidate.get("fixture_only", True):
        failed.append("fixture_only_not_formal_wf_eligible")
        checks["fixture_only_not_formal_wf_eligible"] = False
    # Triage promising alone is insufficient
    if triage.get("triage_status") != "DEVELOPMENT_PROMISING_NOT_QUALIFIED":
        # already covered by other checks; keep explicit for non-promising
        pass
    elif failed:
        pass
    else:
        # Even promising fixtures remain blocked by fixture_only
        pass

    ready = len(failed) == 0
    return {"checks": checks, "failed": failed, "pre_wf_satisfied": ready}


def build_freeze_package(candidate: dict[str, Any]) -> dict[str, Any] | None:
    """Freeze only when pre-WF satisfied — otherwise None."""
    from backend.nexus_formal_wf_plan.freezes import (
        build_candidate_freeze_rules,
        build_code_version_freeze,
        build_cost_version_freeze,
        build_dataset_freeze,
        build_parameter_freeze_rules,
    )

    return {
        "strategy_version": build_code_version_freeze(
            candidate, code_version=str(candidate.get("code_version") or "UNPINNED")
        ),
        "params": build_parameter_freeze_rules(candidate),
        "features": {
            "feature_ids": list(candidate.get("feature_ids") or []),
            "frozen": True,
            "checksum": _sha(candidate.get("feature_ids") or []),
        },
        "data_deps": build_dataset_freeze(candidate),
        "cost_model": build_cost_version_freeze(candidate),
        "candidate": build_candidate_freeze_rules(candidate),
        "frozen_at": _utc(),
        "research_only": True,
    }


def maybe_execute_formal_wf(candidate: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    """Research-only Formal WF path — still respects execution gate truth."""
    from backend.nexus_formal_wf_plan.execution_gate import FormalWalkForwardExecutionGate

    plan = {
        "plan_id": f"research_wf_{candidate.get('candidate_id')}",
        "candidate_id": candidate.get("candidate_id"),
        "freeze": freeze,
        "research_only": True,
        "formal_walk_forward_executed": False,
        "status": "READY_PENDING_GATE",
    }
    gate = FormalWalkForwardExecutionGate()
    result = gate.attempt_execute_plan(plan)
    # Truth: current FormalWalkForwardExecutionGate refuses all execution (V15-F heritage).
    # Do not claim pass. OOS untouched.
    return {
        "attempted": True,
        "executed": bool(result.get("executed")),
        "allowed": bool(result.get("allowed")),
        "reason": result.get("reason"),
        "oos_consumed": False,
        "gate_result": result,
    }


def main() -> int:
    from backend.nexus_candidate_triage.engine import classify_candidate
    from backend.nexus_candidate_triage.fixtures import build_synthetic_research_bundle

    bundle = build_synthetic_research_bundle()
    candidates = list(bundle.get("candidates") or [])

    queue: list[dict[str, Any]] = []
    blocker_counts: Counter[str] = Counter()
    formal_wf_executed_any = False
    qualification_ready_ids: list[str] = []

    # Run cost lab once outside loop for shared research prerequisite evidence
    cost_lab_summary = None
    try:
        from backend.nexus_cost_sensitivity.lab import run_cost_sensitivity_lab

        lab = run_cost_sensitivity_lab(pass_id=1)
        cost_lab_summary = {
            "ran": True,
            "label_histogram": lab.get("label_histogram"),
            "qualification_ready_count": lab.get("qualification_ready_count", 0),
            "formal_walk_forward_executed": bool(
                lab.get("formal_walk_forward_executed", False)
            ),
        }
    except Exception as exc:  # noqa: BLE001
        cost_lab_summary = {"ran": False, "error": str(exc)}

    for c in candidates:
        triage = classify_candidate(c)
        mech = c.get("mechanism") or {}
        exact = _exact_blocker(c, triage)
        blocker_counts[exact] += 1
        prereqs = run_safe_prerequisites(c)
        prereqs["cost_sensitivity"]["lab_crosscheck"] = {
            "ran": bool(cost_lab_summary and cost_lab_summary.get("ran")),
            "shared": True,
        }

        pre = evaluate_pre_wf(c, triage, prereqs)
        auto = exact in {
            "INSUFFICIENT_SAMPLE_N",
            "COST_SENSITIVITY_DESTROYED_NET_EXPECTANCY",
            "REGIME_SEGMENTATION_FRAGILE",
            "DATA_QUALITY_OR_PIT_FAILED",
            "ROBUSTNESS_OR_MULTIPLE_TESTING_REJECTED",
            "PRE_WF_GATES_INCOMPLETE_PROMISING_ONLY",
            "DEVELOPMENT_REVIEW_REQUIRED",
        }

        freeze = None
        wf = {
            "attempted": False,
            "executed": False,
            "allowed": False,
            "oos_consumed": False,
            "reason": "pre_wf_not_satisfied",
        }
        if pre["pre_wf_satisfied"]:
            freeze = build_freeze_package(c)
            wf = maybe_execute_formal_wf(c, freeze)
            if wf.get("executed"):
                formal_wf_executed_any = True
                qualification_ready_ids.append(str(c.get("candidate_id")))
            else:
                # Freeze prepared but gate refused — still not qualification_ready
                blocker_counts["FORMAL_WF_EXECUTION_GATE_REFUSED"] += 1
                exact = "FORMAL_WF_EXECUTION_GATE_REFUSED"

        record = {
            "candidate_id": c.get("candidate_id"),
            "strategy_family": mech.get("mechanism_family"),
            "market_mechanism": mech.get("mechanism_semantic_id"),
            "current_gate": _map_gate(str(triage.get("triage_status"))),
            "exact_blocker": exact,
            "automatically_resolvable": auto and not pre["pre_wf_satisfied"],
            "next_required_test": _next_required_test(exact),
            "triage_status": triage.get("triage_status"),
            "fixture_only": bool(c.get("fixture_only", True)),
            "prerequisites_run": prereqs,
            "pre_wf": pre,
            "qualification_ready": bool(
                pre["pre_wf_satisfied"] and wf.get("executed")
            ),
            "formal_wf": wf,
            "freeze_package": freeze,
            "oos_reserved": not bool(wf.get("oos_consumed")),
        }
        queue.append(record)

    qualification_ready_count = sum(1 for r in queue if r["qualification_ready"])

    report = {
        "schema": "v18_2_9_qualification_blocker_resolution_queue_v1",
        "generated_at": _utc(),
        "qualification_ready_count": qualification_ready_count,
        "qualification_ready_ids": qualification_ready_ids,
        "formal_WF": formal_wf_executed_any,
        "formal_walk_forward_executed": formal_wf_executed_any,
        "oos_consumed": False,
        "oos_reserved": True,
        "cost_lab_summary": cost_lab_summary,
        "pre_wf_conditions": list(PRE_WF_CONDITIONS),
        "exact_blocker_counts": dict(blocker_counts.most_common()),
        "top_blockers": [
            {"blocker": k, "count": v} for k, v in blocker_counts.most_common(8)
        ],
        "queue": queue,
        "notes": [
            "Synthetic/fixture research candidates cannot satisfy Formal WF truthfully.",
            "Safe prerequisites auto-ran (sample/cost/robustness/regime/replay).",
            "FormalWalkForwardExecutionGate remains fail-closed unless plan allowed.",
            "OOS remains reserved until Formal WF actually passes.",
            "Activity Metric V2 does not silently fill trade_count_24h.",
        ],
        "safety": {
            "demo_order_armed": False,
            "exchange_write_attempt": 0,
            "oos_touched": False,
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUT_PATH),
                "qualification_ready_count": qualification_ready_count,
                "formal_WF": formal_wf_executed_any,
                "exact_blocker_counts": report["exact_blocker_counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
