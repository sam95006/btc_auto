"""Typed contracts for V16-E Lesson Compiler (WHEN → THEN Expert action)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Condition:
    """Single typed WHEN predicate."""

    field: str
    op: str
    value: Any

    def to_public_dict(self) -> dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}


@dataclass(frozen=True, slots=True)
class ThenAction:
    """THEN Expert action — never mutates production risk/leverage."""

    expert: str
    action_kind: str
    target: str
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuthorMeta:
    model: str
    version: str

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ExpirySpec:
    expires_at_ms: int | None
    max_age_bars: int | None
    revalidation_required: bool

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LessonRule:
    """Compiled verifiable lesson rule. status is always CANDIDATE at emit."""

    lesson_id: str
    status: str
    conditions: tuple[Condition, ...]
    then_action: ThenAction
    scope: str
    affected_expert: str
    regimes: tuple[str, ...]
    expiry: ExpirySpec
    evidence_count: int
    confidence: float
    contradictory_evidence: tuple[str, ...]
    author_model: str
    author_version: str
    mutates_production_risk: bool
    mutates_production_leverage: bool
    reflection_id: str
    catalog_version: str
    compile_digest: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "status": self.status,
            "conditions": [c.to_public_dict() for c in self.conditions],
            "then_action": self.then_action.to_public_dict(),
            "scope": self.scope,
            "affected_expert": self.affected_expert,
            "regimes": list(self.regimes),
            "expiry": self.expiry.to_public_dict(),
            "evidence_count": self.evidence_count,
            "confidence": self.confidence,
            "contradictory_evidence": list(self.contradictory_evidence),
            "author_model": self.author_model,
            "author_version": self.author_version,
            "mutates_production_risk": self.mutates_production_risk,
            "mutates_production_leverage": self.mutates_production_leverage,
            "reflection_id": self.reflection_id,
            "catalog_version": self.catalog_version,
            "compile_digest": self.compile_digest,
        }


@dataclass(frozen=True, slots=True)
class ReflectionFixture:
    """Synthetic / development Reflection payload ready for compilation."""

    reflection_id: str
    conditions: tuple[dict[str, Any], ...]
    then_action: dict[str, Any]
    scope: str
    affected_expert: str
    regimes: tuple[str, ...]
    expiry: dict[str, Any]
    evidence_count: int
    confidence: float
    contradictory_evidence: tuple[str, ...]
    author_model: str
    author_version: str
    narrative: str
    # V16-A lineage: process class that produced this reflection (optional → fail-closed when set).
    source_process_class: str | None = None
