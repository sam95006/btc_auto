"""Fixtures for V16-F Lesson Validation Firewall (mechanics only)."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_lesson_validation_firewall.constants import (
    EVIDENCE_CLASS_FIXTURE,
    EVIDENCE_CLASS_REAL,
    FIXTURE_LABEL,
    REAL_LABEL,
)


def synthetic_fixture_lesson(
    *,
    lesson_id: str = "FIX_V16F_LESSON_001",
    include_unfavorable: bool = True,
) -> dict[str, Any]:
    """Labeled fixture — never a real promotion authority."""
    evidence = [
        {"evidence_id": "e_pos_1", "polarity": "favorable", "metric": "replay_hit", "value": 0.72},
        {"evidence_id": "e_pos_2", "polarity": "favorable", "metric": "stability", "value": 0.61},
    ]
    if include_unfavorable:
        evidence.append(
            {
                "evidence_id": "e_neg_1",
                "polarity": "unfavorable",
                "metric": "regression_delta",
                "value": -0.08,
            }
        )
        evidence.append(
            {
                "evidence_id": "e_contradict_1",
                "polarity": "contradictory",
                "metric": "regime_mismatch",
                "value": 1,
            }
        )
    return {
        "lesson_id": lesson_id,
        "evidence_class": EVIDENCE_CLASS_FIXTURE,
        "label": FIXTURE_LABEL,
        "state": "CANDIDATE",
        "real_lesson": False,
        "v23_complete": False,
        "formal_wf": False,
        "oos": False,
        "lesson_prevention": "BLOCKED",
        "baseline_metrics": {
            "error_rate": 0.22,
            "repeat_error_rate": 0.18,
            "coverage": 0.40,
        },
        "patched_metrics": {
            "error_rate": 0.19,
            "repeat_error_rate": 0.15,
            "coverage": 0.42,
        },
        "evidence": evidence,
        "prior_lessons": ["FIX_V16F_PRIOR_A", "FIX_V16F_PRIOR_B"],
        "ttl_seconds": 86_400,
        "expires_at_epoch": 1_700_086_400,
        "as_of_epoch": 1_700_000_000,
    }


def synthetic_real_lesson_blocked(
    *,
    lesson_id: str = "REAL_V16F_LESSON_BLOCKED_001",
) -> dict[str, Any]:
    """Real-labeled lesson — ACTIVE permanently blocked in this window."""
    base = synthetic_fixture_lesson(lesson_id=lesson_id, include_unfavorable=True)
    base.update(
        {
            "evidence_class": EVIDENCE_CLASS_REAL,
            "label": REAL_LABEL,
            "real_lesson": True,
            "v23_complete": False,
            "formal_wf": False,
            "oos": False,
            "lesson_prevention": "BLOCKED",
        }
    )
    return base


def cherry_pick_attempt_fixture(lesson_id: str = "FIX_V16F_CHERRY") -> dict[str, Any]:
    """Favorable-only evidence set — must be rejected by cherry-pick gate."""
    lesson = synthetic_fixture_lesson(lesson_id=lesson_id, include_unfavorable=False)
    lesson["evidence"] = [
        e for e in lesson["evidence"] if e.get("polarity") == "favorable"
    ]
    lesson["cherry_pick_attempt"] = True
    return lesson


def forgetting_attack_fixture() -> dict[str, Any]:
    """Attempt to drop prior lessons — catastrophic forgetting guard must refuse."""
    return {
        "action": "DROP_PRIOR_LESSONS",
        "lesson_id": "FIX_V16F_LESSON_001",
        "drop_ids": ["FIX_V16F_PRIOR_A", "FIX_V16F_PRIOR_B"],
        "allowed": False,
    }


def fixture_catalog() -> dict[str, Any]:
    return {
        "fixture_lesson": synthetic_fixture_lesson(),
        "real_lesson_blocked": synthetic_real_lesson_blocked(),
        "cherry_pick_attempt": cherry_pick_attempt_fixture(),
        "forgetting_attack": forgetting_attack_fixture(),
        "labels": {
            "fixture": FIXTURE_LABEL,
            "real": REAL_LABEL,
        },
        "note": "fixtures_are_mechanics_only_never_real_active_authority",
    }


def clone_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(lesson)
