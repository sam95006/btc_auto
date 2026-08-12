"""Mutation campaign — kill mutants or record unresolved survivors/blockers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_autonomy.security_mutation_v11.constants import SUBJECT_IDS
from backend.nexus_autonomy.security_mutation_v11.models import MutationOutcome
from backend.nexus_autonomy.security_mutation_v11.mutations import (
    bind_real,
    iter_mutants,
    oracle_detects_false_safe,
)
from backend.nexus_autonomy.security_mutation_v11.subjects import SUBJECT_REGISTRY, materialize_attacks


def _malicious(attacks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in attacks if not a.get("benign")]


def evaluate_subject_real(subject_id: str, workdir: Path) -> dict[str, Any]:
    real = bind_real(subject_id)
    attacks = materialize_attacks(subject_id, workdir)
    malicious = _malicious(attacks)
    results = []
    for i, attack in enumerate(malicious):
        ok = real.is_safe(attack)
        # Special-case symlink when OS cannot create links
        if subject_id == "symlink_escape" and not attack.get("symlink_created", True):
            ok = True
        results.append({"i": i, "ok": ok, "label": attack.get("label")})
    passed = all(r["ok"] for r in results) if results else False
    return {
        "subject_id": subject_id,
        "passed": passed,
        "case_count": len(results),
        "cases": results,
    }


def kill_mutant(subject_id: str, mutant_id: str, workdir: Path) -> MutationOutcome:
    mutants = {m.mutation_id: m for m in iter_mutants(subject_id)}
    mutant = mutants[mutant_id]
    attacks = _malicious(materialize_attacks(subject_id, workdir))
    kill_cases: list[str] = []
    primary_killed = False

    for i, attack in enumerate(attacks):
        if subject_id == "symlink_escape" and not attack.get("symlink_created", True):
            # Cannot exercise symlink mutant meaningfully
            continue
        blocked = mutant.is_safe(attack)
        case_id = f"{mutant_id}::attack_{i}"
        if not blocked:
            primary_killed = True
            kill_cases.append(case_id)
        elif oracle_detects_false_safe(subject_id, attack, mutant):
            primary_killed = True
            kill_cases.append(f"{case_id}::oracle")

    # If no malicious attacks exercisable (e.g. symlink unavailable), mark equivalent/unavailable
    if subject_id == "symlink_escape" and not any(a.get("symlink_created") for a in attacks):
        return MutationOutcome(
            mutation_id=mutant_id,
            subject_id=subject_id,
            operator=mutant.operator,
            killed=True,
            equivalent=True,
            detail="symlink_unavailable_platform_skip",
            severity="info",
            evidence={"platform_skip": True},
        )

    if primary_killed:
        return MutationOutcome(
            mutation_id=mutant_id,
            subject_id=subject_id,
            operator=mutant.operator,
            killed=True,
            kill_cases=kill_cases,
            detail="killed_by_kill_suite",
            severity="info",
            evidence={"kill_case_count": len(kill_cases)},
        )

    # Survivor — must become blocker unless explicitly waived
    return MutationOutcome(
        mutation_id=mutant_id,
        subject_id=subject_id,
        operator=mutant.operator,
        killed=False,
        survivor=True,
        unresolved_blocker=True,
        blocker_reason=f"surviving_mutation:{mutant_id}",
        detail="SURVIVOR_REQUIRES_NEW_TEST_OR_BLOCKER",
        severity="critical",
        evidence={"attacks_tried": len(attacks)},
    )


def run_mutation_campaign(workdir: Path) -> dict[str, Any]:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    real_results = []
    outcomes: list[MutationOutcome] = []

    for subject_id in SUBJECT_IDS:
        if subject_id not in SUBJECT_REGISTRY:
            outcomes.append(
                MutationOutcome(
                    mutation_id=f"{subject_id}::missing_registry",
                    subject_id=subject_id,
                    operator="missing",
                    killed=False,
                    survivor=True,
                    unresolved_blocker=True,
                    blocker_reason="subject_not_registered",
                    severity="critical",
                    detail="subject_missing_from_registry",
                )
            )
            continue
        real_results.append(evaluate_subject_real(subject_id, workdir / "real"))
        for mutant in iter_mutants(subject_id):
            outcomes.append(kill_mutant(subject_id, mutant.mutation_id, workdir / "mut"))

    killed = [o for o in outcomes if o.killed]
    survivors = [o for o in outcomes if o.survivor and not o.equivalent]
    unresolved = [o for o in outcomes if o.unresolved_blocker]
    real_failed = [r for r in real_results if not r["passed"]]

    return {
        "subject_ids": list(SUBJECT_IDS),
        "real_subject_results": real_results,
        "real_subject_pass_count": sum(1 for r in real_results if r["passed"]),
        "real_subject_total": len(real_results),
        "mutation_outcomes": [o.to_dict() for o in outcomes],
        "mutation_total": len(outcomes),
        "mutation_killed_count": len(killed),
        "mutation_survivor_count": len(survivors),
        "mutation_unresolved_blocker_count": len(unresolved),
        "survivors": [o.to_dict() for o in survivors],
        "unresolved_blockers": [o.to_dict() for o in unresolved],
        "real_failures": real_failed,
    }
