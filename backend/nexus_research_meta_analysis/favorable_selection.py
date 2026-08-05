"""Favorable-run selection detection and failed-sibling retention."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.nexus_research_meta_analysis.constants import PROMISING_LABELS
from backend.nexus_research_meta_analysis.hard_bans import (
    HardBanViolation,
    refuse_promising_without_siblings,
    refuse_silent_favorable_selection,
)


FAILED_ROLES = frozenset({"failed_sibling", "cherry_omitted"})
FAVORABLE_ROLES = frozenset({"promising", "cherry_favorable", "review", "fragile"})


def group_experiments(
    experiments: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in experiments:
        groups.setdefault(str(e["candidacy_group"]), []).append(dict(e))
    return groups


def detect_favorable_run_selection(
    experiments: Sequence[Mapping[str, Any]],
    *,
    attempted_silent_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect silent favorable-run cherry-picking within candidacy groups.

    If ``attempted_silent_selection`` omits failed siblings, the attempt is
    recorded as blocked (and raises when enforced via ``enforce=True`` path).
    """
    groups = group_experiments(experiments)
    findings: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for gid, members in sorted(groups.items()):
        roles = {m["experiment_id"]: m["role"] for m in members}
        failed = [m for m in members if m["role"] in FAILED_ROLES]
        favorable = [m for m in members if m["role"] in FAVORABLE_ROLES]
        findings.append(
            {
                "candidacy_group": gid,
                "member_count": len(members),
                "failed_sibling_count": len(failed),
                "favorable_count": len(favorable),
                "member_ids": sorted(roles),
            }
        )

    silent_blocked = False
    silent_detail: dict[str, Any] | None = None
    if attempted_silent_selection:
        selected = str(attempted_silent_selection.get("selected_experiment_id") or "")
        disclosed = [
            str(x) for x in (attempted_silent_selection.get("disclosed_member_ids") or [])
        ]
        group_id = str(attempted_silent_selection.get("candidacy_group") or "")
        members = groups.get(group_id) or []
        expected = {m["experiment_id"] for m in members}
        provided = set(disclosed)
        omitted = sorted(expected - provided)
        if omitted or selected not in expected:
            silent_blocked = True
            silent_detail = {
                "candidacy_group": group_id,
                "selected_experiment_id": selected,
                "omitted_member_ids": omitted,
                "extra_member_ids": sorted(provided - expected),
                "blocked": True,
                "reason": "silent_favorable_run_selection",
            }
            blocked.append(silent_detail)

    return {
        "axis": "favorable_run_selection_detection",
        "groups": findings,
        "silent_selection_blocked": silent_blocked,
        "blocked_attempts": blocked,
        "silent_detail": silent_detail,
        "development_only": True,
        "not_oos_claim": True,
    }


def enforce_failed_sibling_retention(
    *,
    promising_experiment_id: str,
    candidacy_group: str,
    experiments: Sequence[Mapping[str, Any]],
    retained_sibling_ids: Sequence[str],
) -> dict[str, Any]:
    """Promising results MUST retain all failed sibling experiments."""
    groups = group_experiments(experiments)
    members = groups.get(candidacy_group) or []
    if not members:
        raise HardBanViolation(f"unknown_candidacy_group:{candidacy_group}")

    member_ids = {m["experiment_id"] for m in members}
    if promising_experiment_id not in member_ids:
        raise HardBanViolation(
            f"promising_not_in_group:{promising_experiment_id}:{candidacy_group}"
        )

    required_failed = sorted(
        m["experiment_id"] for m in members if m["role"] in FAILED_ROLES
    )
    retained = set(str(x) for x in retained_sibling_ids)
    missing = sorted(set(required_failed) - retained)
    if missing:
        refuse_promising_without_siblings()

    return {
        "axis": "failed_sibling_retention",
        "promising_experiment_id": promising_experiment_id,
        "candidacy_group": candidacy_group,
        "required_failed_siblings": required_failed,
        "retained_sibling_ids": sorted(retained),
        "retention_ok": True,
        "development_only": True,
        "qualification_claim": False,
    }


def attempt_silent_cherry_pick(
    *,
    favorable_experiment_id: str,
    omitted_experiment_ids: Sequence[str],
) -> None:
    """Adversarial probe — always raises."""
    _ = favorable_experiment_id, omitted_experiment_ids
    refuse_silent_favorable_selection()


def build_promising_packet(
    *,
    promising: Mapping[str, Any],
    experiments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach all failed siblings to a promising result (required)."""
    group = str(promising["candidacy_group"])
    members = group_experiments(experiments).get(group) or []
    failed = [dict(m) for m in members if m["role"] in FAILED_ROLES]
    retention = enforce_failed_sibling_retention(
        promising_experiment_id=str(promising["experiment_id"]),
        candidacy_group=group,
        experiments=experiments,
        retained_sibling_ids=[m["experiment_id"] for m in failed],
    )
    label = "DEVELOPMENT_PROMISING_NOT_QUALIFIED"
    if label not in PROMISING_LABELS:
        raise HardBanViolation("internal_promising_label_misconfigured")
    return {
        "promising_experiment_id": promising["experiment_id"],
        "label": label,
        "qualification_claim": False,
        "failed_sibling_experiments": failed,
        "failed_sibling_ids": [m["experiment_id"] for m in failed],
        "sibling_retention": retention,
        "candidacy_group": group,
        "not_oos_claim": True,
        "formal_walk_forward": False,
    }
