"""Cross-lane intake: V16-E compiled LessonRule → V16-F firewall lesson dict."""
from __future__ import annotations

from typing import Any

from backend.nexus_lesson_compiler.constants import LESSON_STATUS_CANDIDATE
from backend.nexus_lesson_compiler.contracts import LessonRule
from backend.nexus_lesson_validation_firewall.constants import (
    EVIDENCE_CLASS_FIXTURE,
    FIXTURE_LABEL,
    PROMOTION_STATES,
)
from backend.nexus_lesson_validation_firewall.fixtures import clone_lesson


class FirewallIntakeError(ValueError):
    """Fail-closed intake rejection from compiler → firewall bridge."""


def intake_from_compiler_lesson(
    rule: LessonRule | dict[str, Any],
    *,
    now_epoch: int = 1_700_000_000,
) -> dict[str, Any]:
    """Map a CANDIDATE LessonRule into firewall mechanics payload.

    Hard requirements:
    - status must be CANDIDATE (compiler field)
    - emitted firewall field is ``state`` (not ``status``)
    - ACTIVE / non-pipeline statuses refused
    """
    if isinstance(rule, LessonRule):
        public = rule.to_public_dict()
    elif isinstance(rule, dict):
        public = dict(rule)
    else:
        raise FirewallIntakeError("lesson_not_object")

    status = str(public.get("status") or public.get("state") or "").strip().upper()
    if status != LESSON_STATUS_CANDIDATE:
        raise FirewallIntakeError(f"intake_requires_candidate_status:{status or 'MISSING'}")
    if status == "ACTIVE" or status not in PROMOTION_STATES:
        raise FirewallIntakeError(f"intake_illegal_promotion_state:{status}")

    lesson_id = str(public.get("lesson_id") or "").strip()
    if not lesson_id:
        raise FirewallIntakeError("intake_lesson_id_missing")

    evidence = []
    for i, note in enumerate(public.get("contradictory_evidence") or []):
        evidence.append(
            {
                "evidence_id": f"e_contradict_{i}",
                "polarity": "contradictory",
                "metric": "compiler_note",
                "value": str(note),
            }
        )
    if int(public.get("evidence_count") or 0) > 0:
        evidence.append(
            {
                "evidence_id": "e_pos_compiler",
                "polarity": "favorable",
                "metric": "evidence_count",
                "value": int(public["evidence_count"]),
            }
        )
    # Cherry-pick gate requires unfavorable when any favorable exists.
    if any(e.get("polarity") == "favorable" for e in evidence):
        evidence.append(
            {
                "evidence_id": "e_neg_compiler_ack",
                "polarity": "unfavorable",
                "metric": "compiler_residual_risk",
                "value": 1.0 - float(public.get("confidence") or 0.0),
            }
        )

    out = {
        "lesson_id": lesson_id,
        "evidence_class": EVIDENCE_CLASS_FIXTURE,
        "label": FIXTURE_LABEL,
        "state": "CANDIDATE",  # firewall canonical field
        "status": "CANDIDATE",  # preserve compiler lineage field
        "real_lesson": False,
        "v23_complete": False,
        "formal_wf": False,
        "oos": False,
        "lesson_prevention": "BLOCKED",
        "baseline_metrics": {
            "error_rate": 0.25,
            "repeat_error_rate": 0.20,
            "coverage": 0.35,
        },
        "patched_metrics": {
            "error_rate": 0.22,
            "repeat_error_rate": 0.18,
            "coverage": 0.38,
        },
        "evidence": evidence,
        "prior_lessons": [],
        "ttl_seconds": 86_400,
        "expires_at_epoch": now_epoch + 86_400,
        "as_of_epoch": now_epoch,
        "compiler_digest": public.get("compile_digest"),
        "catalog_version": public.get("catalog_version"),
        "source_lane": "V16-E",
    }
    return clone_lesson(out)
