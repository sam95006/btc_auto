"""Two-pass adversarial probes for V15-F Formal Walk-Forward Plan Compiler."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_formal_wf_plan.compiler import FormalWalkForwardPlanCompiler
from backend.nexus_formal_wf_plan.constants import (
    PLAN_DIMENSIONS,
    PLAN_STATUS_READY_EXECUTION_BLOCKED,
    SCHEMA_ID,
)
from backend.nexus_formal_wf_plan.hard_bans import HardBanViolation


def _tamper_plan_execute_flag(plan: dict[str, Any]) -> dict[str, Any]:
    tainted = deepcopy(plan)
    tainted["formal_walk_forward_executed"] = True
    tainted["executed"] = True
    tainted["status"] = "EXECUTED"
    return tainted


def run_pass1(compiler: FormalWalkForwardPlanCompiler | None = None) -> dict[str, Any]:
    comp = compiler or FormalWalkForwardPlanCompiler()
    return comp.compile_bundle()


def run_pass2_adversarial(
    pass1: dict[str, Any],
    *,
    compiler: FormalWalkForwardPlanCompiler | None = None,
) -> dict[str, Any]:
    """PASS 2: force-execute, flag tamper, OOS interval, dimension completeness."""
    comp = compiler or FormalWalkForwardPlanCompiler()
    plans = pass1.get("plans") or []
    first = plans[0] if plans else {}

    force_execute = comp.attempt_execute(first) if first else {
        "allowed": False,
        "executed": False,
        "reason": "NO_PLAN",
    }

    fold_attempts = []
    if first:
        for fold in (first.get("folds") or [])[:3]:
            fold_attempts.append(comp.gate.attempt_execute_fold(first, fold["fold_id"]))

    force_raise_blocked = False
    force_raise_error: str | None = None
    try:
        comp.gate.force_execute_or_raise(first)
    except HardBanViolation as exc:
        force_raise_blocked = True
        force_raise_error = str(exc)

    tamper = _tamper_plan_execute_flag(first) if first else {}
    tamper_detected = False
    tamper_error: str | None = None
    if tamper:
        try:
            comp.gate.assert_never_executed(tamper)
        except HardBanViolation as exc:
            tamper_detected = True
            tamper_error = str(exc)

    # Adversarial: OOS_RESERVED category must be refused by the compiler.
    as_of = int(pass1.get("as_of_ms") or 1_700_000_000_000)
    from backend.nexus_formal_wf_plan.compiler import compile_formal_wf_plan
    from backend.nexus_formal_wf_plan.fixtures import synthetic_candidate

    oos_injection_blocked = False
    cand_oos = synthetic_candidate(as_of_ms=as_of)
    cand_oos["development_interval"] = {
        "start_ms": as_of - 90 * 86_400_000,
        "end_ms": as_of - 30 * 86_400_000,
        "category": "OOS_RESERVED",
    }
    try:
        compile_formal_wf_plan(
            cand_oos, code_version=pass1.get("code_version"), as_of_ms=as_of
        )
    except ValueError as exc:
        if "forbidden_interval_category" in str(exc):
            oos_injection_blocked = True

    # OOS_UNTOUCHED category likewise blocked.
    cand_untouched = synthetic_candidate(as_of_ms=as_of)
    cand_untouched["development_interval"] = {
        "start_ms": as_of - 90 * 86_400_000,
        "end_ms": as_of - 30 * 86_400_000,
        "category": "OOS_UNTOUCHED",
    }
    try:
        compile_formal_wf_plan(
            cand_untouched, code_version=pass1.get("code_version"), as_of_ms=as_of
        )
        oos_injection_blocked = False
    except ValueError as exc:
        if "forbidden_interval_category" not in str(exc):
            oos_injection_blocked = False

    # Selected/promoted candidate refusal.
    select_blocked = False
    cand_sel = synthetic_candidate(as_of_ms=as_of)
    cand_sel["selected"] = True
    try:
        compile_formal_wf_plan(
            cand_sel, code_version=pass1.get("code_version"), as_of_ms=as_of
        )
    except ValueError as exc:
        if "selected_or_promoted" in str(exc):
            select_blocked = True
    # Stable recompile.
    pass2_rerun = comp.compile_bundle(as_of_ms=pass1.get("as_of_ms"))
    stability = {
        "status_stable": pass1["status"]
        == pass2_rerun["status"]
        == PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "executed_flag_stable_false": pass1["formal_walk_forward_executed"] is False
        and pass2_rerun["formal_walk_forward_executed"] is False,
        "plan_count_stable": pass1["plan_count"] == pass2_rerun["plan_count"],
        "dimensions_stable": pass1["dimensions_covered"] == pass2_rerun["dimensions_covered"],
        "all_plans_blocked_stable": pass1["all_plans_blocked"]
        and pass2_rerun["all_plans_blocked"],
    }

    dimensions_ok = all(
        all(dim in p for dim in PLAN_DIMENSIONS) for p in (pass1.get("plans") or [])
    )

    adversarial_ok = (
        force_execute.get("allowed") is False
        and force_execute.get("executed") is False
        and force_execute.get("formal_walk_forward_executed") is False
        and all((not a.get("allowed")) and (not a.get("executed")) for a in fold_attempts)
        and force_raise_blocked
        and tamper_detected
        and oos_injection_blocked
        and select_blocked
        and dimensions_ok
        and all(stability.values())
        and pass2_rerun["formal_walk_forward_executed"] is False
        and pass2_rerun["status"] == PLAN_STATUS_READY_EXECUTION_BLOCKED
    )

    return {
        "schema": SCHEMA_ID,
        "pass": 2,
        "force_execute": force_execute,
        "fold_attempts": fold_attempts,
        "force_raise_blocked": force_raise_blocked,
        "force_raise_error": force_raise_error,
        "tamper_detected": tamper_detected,
        "tamper_error": tamper_error,
        "oos_injection_blocked": oos_injection_blocked,
        "select_blocked": select_blocked,
        "dimensions_ok": dimensions_ok,
        "stability": stability,
        "stable_rerun": {
            "status": pass2_rerun["status"],
            "plan_count": pass2_rerun["plan_count"],
            "formal_walk_forward_executed": pass2_rerun["formal_walk_forward_executed"],
            "all_plans_blocked": pass2_rerun["all_plans_blocked"],
        },
        "adversarial_ok": adversarial_ok,
        "formal_walk_forward_executed": False,
    }


def run_two_pass_campaign(
    *,
    compiler: FormalWalkForwardPlanCompiler | None = None,
) -> dict[str, Any]:
    comp = compiler or FormalWalkForwardPlanCompiler()
    pass1 = run_pass1(comp)
    pass2 = run_pass2_adversarial(pass1, compiler=comp)
    both_ok = bool(
        pass1.get("status") == PLAN_STATUS_READY_EXECUTION_BLOCKED
        and pass1.get("formal_walk_forward_executed") is False
        and pass1.get("all_plans_blocked")
        and pass1.get("all_dimensions_present")
        and pass1.get("execution_gate", {}).get("all_attempts_refused")
        and pass2.get("adversarial_ok")
    )
    return {
        "schema": SCHEMA_ID,
        "lane": "V15-F",
        "pass1": pass1,
        "pass2": pass2,
        "status": PLAN_STATUS_READY_EXECUTION_BLOCKED,
        "formal_walk_forward_executed": False,
        "both_passes_ok": both_ok,
        "plan_count": pass1.get("plan_count", 0),
    }
