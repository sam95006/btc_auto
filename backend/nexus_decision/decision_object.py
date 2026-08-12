"""Canonical Decision Object contract for Founder-private Decision Lifecycle V11."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "nexus_decision_object_v11"

DECISION_OBJECT_REQUIRED_FIELDS: tuple[str, ...] = (
    "decision_id",
    "candidate_id",
    "market_context_id",
    "point_in_time_timestamp",
    "evidence_ids",
    "evidence_hashes",
    "data_freshness",
    "data_completeness",
    "AI_reasoner_outputs",
    "independent_critic_output",
    "deterministic_risk_result",
    "decision_status",
    "rejection_reasons",
    "intent_id",
    "position_id",
    "exit_id",
    "reflection_id",
    "lesson_ids",
    "created_at",
    "updated_at",
    "schema_version",
    "idempotency_key",
)


class DecisionObjectError(ValueError):
    """Decision Object contract violation — fail closed."""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass
class DecisionObject:
    """Immutable-field-aware canonical Decision Object.

    Linkage fields (intent_id, position_id, …) may be None until later stages.
    Evidence lists and hashes must stay length-aligned.
    """

    decision_id: str
    candidate_id: str
    market_context_id: str
    point_in_time_timestamp: str
    evidence_ids: list[str]
    evidence_hashes: list[str]
    data_freshness: dict[str, Any]
    data_completeness: dict[str, Any]
    AI_reasoner_outputs: list[dict[str, Any]]
    independent_critic_output: dict[str, Any] | None
    deterministic_risk_result: dict[str, Any] | None
    decision_status: str
    rejection_reasons: list[str]
    intent_id: str | None
    position_id: str | None
    exit_id: str | None
    reflection_id: str | None
    lesson_ids: list[str]
    created_at: str
    updated_at: str
    schema_version: str
    idempotency_key: str
    ledger_event_ids: list[str] = field(default_factory=list)
    transition_history: list[dict[str, Any]] = field(default_factory=list)
    checkpoint_seq: int = 0
    blocked_reason: str | None = None
    evidence_binding_hash: str | None = None
    # Bound to backend.nexus_execution.cost_model.COST_MODEL_VERSION on approve.
    cost_model_version: str | None = None
    # Provenance: intent/position IDs must come from the DecisionExecutionBridge.
    linkage_authority: str | None = None

    def validate(self) -> None:
        payload = self.to_dict()
        missing = [f for f in DECISION_OBJECT_REQUIRED_FIELDS if f not in payload]
        if missing:
            raise DecisionObjectError(f"missing_required_fields:{missing}")
        if self.schema_version != SCHEMA_VERSION:
            raise DecisionObjectError(f"schema_version_mismatch:{self.schema_version}")
        if not self.decision_id or not self.idempotency_key:
            raise DecisionObjectError("decision_id_or_idempotency_key_empty")
        if len(self.evidence_ids) != len(self.evidence_hashes):
            raise DecisionObjectError(
                f"evidence_ids_hashes_length_mismatch:{len(self.evidence_ids)}!={len(self.evidence_hashes)}"
            )
        if not isinstance(self.evidence_ids, list) or not isinstance(self.evidence_hashes, list):
            raise DecisionObjectError("evidence_must_be_lists")
        if not isinstance(self.rejection_reasons, list) or not isinstance(self.lesson_ids, list):
            raise DecisionObjectError("rejection_reasons_and_lesson_ids_must_be_lists")
        if not isinstance(self.AI_reasoner_outputs, list):
            raise DecisionObjectError("AI_reasoner_outputs_must_be_list")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def content_hash(self) -> str:
        body = self.to_dict()
        # Exclude volatile bookkeeping for content identity.
        body.pop("updated_at", None)
        body.pop("checkpoint_seq", None)
        body.pop("transition_history", None)
        body.pop("ledger_event_ids", None)
        return _sha(body)

    def touch(self) -> None:
        self.updated_at = _utc()

    @classmethod
    def create(
        cls,
        *,
        decision_id: str,
        candidate_id: str,
        market_context_id: str,
        point_in_time_timestamp: str,
        evidence_ids: list[str],
        evidence_hashes: list[str],
        data_freshness: dict[str, Any],
        data_completeness: dict[str, Any],
        idempotency_key: str,
        decision_status: str = "OBSERVED",
        AI_reasoner_outputs: list[dict[str, Any]] | None = None,
        independent_critic_output: dict[str, Any] | None = None,
        deterministic_risk_result: dict[str, Any] | None = None,
        rejection_reasons: list[str] | None = None,
        intent_id: str | None = None,
        position_id: str | None = None,
        exit_id: str | None = None,
        reflection_id: str | None = None,
        lesson_ids: list[str] | None = None,
    ) -> DecisionObject:
        now = _utc()
        obj = cls(
            decision_id=decision_id,
            candidate_id=candidate_id,
            market_context_id=market_context_id,
            point_in_time_timestamp=point_in_time_timestamp,
            evidence_ids=list(evidence_ids),
            evidence_hashes=list(evidence_hashes),
            data_freshness=dict(data_freshness),
            data_completeness=dict(data_completeness),
            AI_reasoner_outputs=list(AI_reasoner_outputs or []),
            independent_critic_output=independent_critic_output,
            deterministic_risk_result=deterministic_risk_result,
            decision_status=decision_status,
            rejection_reasons=list(rejection_reasons or []),
            intent_id=intent_id,
            position_id=position_id,
            exit_id=exit_id,
            reflection_id=reflection_id,
            lesson_ids=list(lesson_ids or []),
            created_at=now,
            updated_at=now,
            schema_version=SCHEMA_VERSION,
            idempotency_key=idempotency_key,
        )
        obj.validate()
        return obj

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionObject:
        required = {f: data.get(f) for f in DECISION_OBJECT_REQUIRED_FIELDS}
        missing = [k for k, v in required.items() if v is None and k not in {
            "independent_critic_output",
            "deterministic_risk_result",
            "intent_id",
            "position_id",
            "exit_id",
            "reflection_id",
        }]
        # None is allowed for optional linkage / outputs; lists must exist.
        for list_field in (
            "evidence_ids",
            "evidence_hashes",
            "AI_reasoner_outputs",
            "rejection_reasons",
            "lesson_ids",
        ):
            if data.get(list_field) is None:
                missing.append(list_field)
        for scalar in (
            "decision_id",
            "candidate_id",
            "market_context_id",
            "point_in_time_timestamp",
            "data_freshness",
            "data_completeness",
            "decision_status",
            "created_at",
            "updated_at",
            "schema_version",
            "idempotency_key",
        ):
            if data.get(scalar) is None:
                if scalar not in missing:
                    missing.append(scalar)
        if missing:
            raise DecisionObjectError(f"from_dict_missing:{missing}")
        obj = cls(
            decision_id=str(data["decision_id"]),
            candidate_id=str(data["candidate_id"]),
            market_context_id=str(data["market_context_id"]),
            point_in_time_timestamp=str(data["point_in_time_timestamp"]),
            evidence_ids=list(data["evidence_ids"]),
            evidence_hashes=list(data["evidence_hashes"]),
            data_freshness=dict(data["data_freshness"]),
            data_completeness=dict(data["data_completeness"]),
            AI_reasoner_outputs=list(data["AI_reasoner_outputs"]),
            independent_critic_output=data.get("independent_critic_output"),
            deterministic_risk_result=data.get("deterministic_risk_result"),
            decision_status=str(data["decision_status"]),
            rejection_reasons=list(data["rejection_reasons"]),
            intent_id=data.get("intent_id"),
            position_id=data.get("position_id"),
            exit_id=data.get("exit_id"),
            reflection_id=data.get("reflection_id"),
            lesson_ids=list(data["lesson_ids"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            schema_version=str(data["schema_version"]),
            idempotency_key=str(data["idempotency_key"]),
            ledger_event_ids=list(data.get("ledger_event_ids") or []),
            transition_history=list(data.get("transition_history") or []),
            checkpoint_seq=int(data.get("checkpoint_seq") or 0),
            blocked_reason=data.get("blocked_reason"),
            evidence_binding_hash=data.get("evidence_binding_hash"),
            cost_model_version=data.get("cost_model_version"),
            linkage_authority=data.get("linkage_authority"),
        )
        obj.validate()
        return obj
