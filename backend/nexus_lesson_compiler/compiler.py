"""Fail-closed compile of Reflection → typed LessonRule (CANDIDATE only)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_lesson_compiler.constants import (
    ALLOWED_ACTION_KINDS,
    ALLOWED_CONDITION_OPS,
    ALLOWED_REGIMES,
    ALLOWED_SCOPES,
    ANTI_PATTERN_ACTION_KINDS,
    BANNED_ACTION_TARGETS,
    CATALOG_VERSION,
    EXPECTED_FIXTURE_COUNT,
    FORBIDDEN_LESSON_STATUSES,
    LESSON_STATUS_CANDIDATE,
    MIN_LESSON_COUNT,
    NON_LEARNING_PROCESS_CLASSES,
    REQUIRED_LESSON_FIELDS,
)
from backend.nexus_lesson_compiler.contracts import (
    Condition,
    ExpirySpec,
    LessonRule,
    ReflectionFixture,
    ThenAction,
)
from backend.nexus_lesson_compiler.fixtures import REFLECTION_FIXTURES


class LessonCompileError(Exception):
    """Fail-closed compile rejection — never emit a partial/ACTIVE rule."""


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_conditions(raw: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> tuple[Condition, ...]:
    if not raw:
        raise LessonCompileError("conditions_empty")
    out: list[Condition] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise LessonCompileError(f"condition_not_object:{i}")
        field = str(item.get("field") or "").strip()
        op = str(item.get("op") or "").strip().upper()
        if not field:
            raise LessonCompileError(f"condition_field_missing:{i}")
        if op not in ALLOWED_CONDITION_OPS:
            raise LessonCompileError(f"condition_op_illegal:{op}")
        if "value" not in item:
            raise LessonCompileError(f"condition_value_missing:{i}")
        out.append(Condition(field=field, op=op, value=item["value"]))
    return tuple(out)


def _validate_then_action(raw: dict[str, Any]) -> ThenAction:
    if not isinstance(raw, dict):
        raise LessonCompileError("then_action_not_object")
    expert = str(raw.get("expert") or "").strip()
    kind = str(raw.get("action_kind") or "").strip().upper()
    target = str(raw.get("target") or "").strip().lower()
    detail = str(raw.get("detail") or "").strip()
    if not expert:
        raise LessonCompileError("then_action_expert_missing")
    if kind not in ALLOWED_ACTION_KINDS:
        raise LessonCompileError(f"then_action_kind_illegal:{kind}")
    if not target:
        raise LessonCompileError("then_action_target_missing")
    if target in BANNED_ACTION_TARGETS or any(b in target for b in BANNED_ACTION_TARGETS):
        raise LessonCompileError(f"then_action_mutates_production_risk_or_leverage:{target}")
    if not detail:
        raise LessonCompileError("then_action_detail_missing")
    return ThenAction(expert=expert, action_kind=kind, target=target, detail=detail)


def _validate_expiry(raw: dict[str, Any]) -> ExpirySpec:
    if not isinstance(raw, dict):
        raise LessonCompileError("expiry_not_object")
    expires_at_ms = raw.get("expires_at_ms")
    max_age_bars = raw.get("max_age_bars")
    revalidation = raw.get("revalidation_required")
    if expires_at_ms is not None and not isinstance(expires_at_ms, int):
        raise LessonCompileError("expiry_expires_at_ms_type")
    if max_age_bars is not None and (not isinstance(max_age_bars, int) or max_age_bars <= 0):
        raise LessonCompileError("expiry_max_age_bars_invalid")
    if expires_at_ms is None and max_age_bars is None:
        raise LessonCompileError("expiry_missing_both_bounds")
    if revalidation is not True:
        raise LessonCompileError("expiry_revalidation_required_must_be_true")
    return ExpirySpec(
        expires_at_ms=expires_at_ms,
        max_age_bars=max_age_bars,
        revalidation_required=True,
    )


def compile_reflection(
    fixture: ReflectionFixture,
    *,
    forced_status: str | None = None,
) -> LessonRule:
    """Compile one Reflection into a typed LessonRule. Fail-closed on any error.

    forced_status is accepted only for negative tests; non-CANDIDATE is rejected.
    """
    status = (forced_status or LESSON_STATUS_CANDIDATE).strip().upper()
    if status != LESSON_STATUS_CANDIDATE:
        raise LessonCompileError(f"lesson_status_must_be_candidate:{status}")
    if status in FORBIDDEN_LESSON_STATUSES:
        raise LessonCompileError(f"forbidden_lesson_status:{status}")

    conditions = _validate_conditions(fixture.conditions)
    then_action = _validate_then_action(fixture.then_action)

    # V16-A lineage gate: BAD_PROCESS_WIN / INSUFFICIENT_EVIDENCE cannot mint ALLOW lessons.
    process_class = str(fixture.source_process_class or "").strip().upper() or None
    if process_class in NON_LEARNING_PROCESS_CLASSES:
        if then_action.action_kind not in ANTI_PATTERN_ACTION_KINDS:
            raise LessonCompileError(
                f"process_class_lineage_forbids_action:{process_class}:{then_action.action_kind}"
            )

    scope = str(fixture.scope or "").strip().upper()
    if scope not in ALLOWED_SCOPES:
        raise LessonCompileError(f"scope_illegal:{scope}")

    affected = str(fixture.affected_expert or "").strip()
    if not affected:
        raise LessonCompileError("affected_expert_missing")
    if affected != then_action.expert:
        raise LessonCompileError("affected_expert_mismatch_then_action")

    regimes_raw = tuple(str(r).strip().upper() for r in fixture.regimes)
    if not regimes_raw:
        raise LessonCompileError("regimes_empty")
    for r in regimes_raw:
        if r not in ALLOWED_REGIMES:
            raise LessonCompileError(f"regime_illegal:{r}")

    expiry = _validate_expiry(fixture.expiry)

    evidence_count = int(fixture.evidence_count)
    if evidence_count < 1:
        raise LessonCompileError("evidence_count_below_one")

    confidence = float(fixture.confidence)
    if not (0.0 <= confidence <= 1.0):
        raise LessonCompileError("confidence_out_of_range")

    author_model = str(fixture.author_model or "").strip()
    author_version = str(fixture.author_version or "").strip()
    if not author_model or not author_version:
        raise LessonCompileError("author_model_or_version_missing")

    contradictory = tuple(str(x) for x in fixture.contradictory_evidence)
    # Contradictory evidence must be acknowledged (may be empty only if evidence_count==0 — already banned).
    # For positive evidence we still require the field to exist (tuple ok empty for rare cases,
    # but fixtures always include at least one note). Allow empty only when confidence < 0.5.
    if not contradictory and confidence >= 0.5:
        raise LessonCompileError("contradictory_evidence_required_when_confidence_ge_0_5")

    lesson_id = f"LESSON_{fixture.reflection_id}"
    public_core = {
        "lesson_id": lesson_id,
        "status": LESSON_STATUS_CANDIDATE,
        "conditions": [c.to_public_dict() for c in conditions],
        "then_action": then_action.to_public_dict(),
        "scope": scope,
        "affected_expert": affected,
        "regimes": list(regimes_raw),
        "expiry": expiry.to_public_dict(),
        "evidence_count": evidence_count,
        "confidence": confidence,
        "contradictory_evidence": list(contradictory),
        "author_model": author_model,
        "author_version": author_version,
        "mutates_production_risk": False,
        "mutates_production_leverage": False,
        "reflection_id": fixture.reflection_id,
        "catalog_version": CATALOG_VERSION,
    }
    digest = _digest(public_core)
    rule = LessonRule(
        lesson_id=lesson_id,
        status=LESSON_STATUS_CANDIDATE,
        conditions=conditions,
        then_action=then_action,
        scope=scope,
        affected_expert=affected,
        regimes=regimes_raw,
        expiry=expiry,
        evidence_count=evidence_count,
        confidence=confidence,
        contradictory_evidence=contradictory,
        author_model=author_model,
        author_version=author_version,
        mutates_production_risk=False,
        mutates_production_leverage=False,
        reflection_id=fixture.reflection_id,
        catalog_version=CATALOG_VERSION,
        compile_digest=digest,
    )
    public = rule.to_public_dict()
    for field in REQUIRED_LESSON_FIELDS:
        if field not in public or public[field] in (None, "", [], {}):
            # contradictory_evidence may be empty list only when confidence < 0.5
            if field == "contradictory_evidence" and public[field] == [] and confidence < 0.5:
                continue
            raise LessonCompileError(f"missing_required_field:{field}")
    if public["status"] != LESSON_STATUS_CANDIDATE:
        raise LessonCompileError("emitted_non_candidate_status")
    if public["mutates_production_risk"] or public["mutates_production_leverage"]:
        raise LessonCompileError("emitted_production_mutation_flags")
    return rule


def compile_raw_dict(payload: dict[str, Any]) -> LessonRule:
    """Compile an arbitrary dict Reflection. Fail-closed."""
    if not isinstance(payload, dict):
        raise LessonCompileError("payload_not_object")
    try:
        fixture = ReflectionFixture(
            reflection_id=str(payload.get("reflection_id") or ""),
            conditions=tuple(payload.get("conditions") or ()),
            then_action=dict(payload.get("then_action") or {}),
            scope=str(payload.get("scope") or ""),
            affected_expert=str(payload.get("affected_expert") or ""),
            regimes=tuple(payload.get("regimes") or ()),
            expiry=dict(payload.get("expiry") or {}),
            evidence_count=int(payload.get("evidence_count") or 0),
            confidence=float(payload.get("confidence") if payload.get("confidence") is not None else -1),
            contradictory_evidence=tuple(payload.get("contradictory_evidence") or ()),
            author_model=str(payload.get("author_model") or ""),
            author_version=str(payload.get("author_version") or ""),
            narrative=str(payload.get("narrative") or ""),
            source_process_class=(
                str(payload.get("source_process_class")).strip().upper()
                if payload.get("source_process_class")
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        raise LessonCompileError(f"payload_coerce_failed:{exc}") from exc
    if not fixture.reflection_id:
        raise LessonCompileError("reflection_id_missing")
    return compile_reflection(fixture, forced_status=payload.get("status"))


def assert_lessons_safe(rules: list[LessonRule]) -> None:
    if len(rules) < MIN_LESSON_COUNT:
        raise AssertionError(f"lesson_count_below_min:{len(rules)}<{MIN_LESSON_COUNT}")
    ids = [r.lesson_id for r in rules]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate_lesson_id")
    for r in rules:
        if r.status != LESSON_STATUS_CANDIDATE:
            raise AssertionError(f"non_candidate_lesson:{r.lesson_id}:{r.status}")
        if r.mutates_production_risk or r.mutates_production_leverage:
            raise AssertionError(f"production_mutation:{r.lesson_id}")
        if r.status in FORBIDDEN_LESSON_STATUSES:
            raise AssertionError(f"forbidden_status:{r.lesson_id}")


def compile_all_lessons() -> list[LessonRule]:
    if len(REFLECTION_FIXTURES) != EXPECTED_FIXTURE_COUNT:
        raise AssertionError(
            f"unexpected_fixture_count:{len(REFLECTION_FIXTURES)}!={EXPECTED_FIXTURE_COUNT}"
        )
    rules = [compile_reflection(f) for f in REFLECTION_FIXTURES]
    assert_lessons_safe(rules)
    return rules


def lesson_catalog() -> list[dict[str, Any]]:
    return [r.to_public_dict() for r in compile_all_lessons()]
