"""Typed contracts for V18-F Shadow Decision Ledger records."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_shadow_decision_ledger.constants import (
    PUBLIC_FIELD_INVARIANTS,
    RECORD_SCHEMA,
    REQUIRED_PERSIST_FIELDS,
    SCHEMA_VERSION,
    SHADOW_DECISION_KINDS,
)


class ShadowDecisionContractError(ValueError):
    """Fail-closed contract violation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _digest(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def enforce_public_invariants(record: dict[str, Any]) -> dict[str, Any]:
    """Always stamp public fields; reject any attempt to set exchange truth."""
    out = dict(record)
    for key, expected in PUBLIC_FIELD_INVARIANTS.items():
        got = out.get(key, "__MISSING__")
        if got not in ("__MISSING__", expected):
            raise ShadowDecisionContractError(
                f"public_invariant_violation:{key}:{got!r}!={expected!r}"
            )
        out[key] = expected
    return out


@dataclass
class ShadowDecisionRecord:
    """Full Shadow Decision ledger row (research-only; never exchange orders)."""

    shadow_decision_id: str
    lifecycle_state: str
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    universe_decision: dict[str, Any] = field(default_factory=dict)
    candidate: dict[str, Any] = field(default_factory=dict)
    ai_suggestion: dict[str, Any] = field(default_factory=dict)
    critic: dict[str, Any] = field(default_factory=dict)
    deterministic_risk: dict[str, Any] = field(default_factory=dict)
    final_shadow_decision: dict[str, Any] = field(default_factory=dict)
    subsequent_outcome: dict[str, Any] | None = None
    costs: dict[str, Any] | None = None
    invalidation: dict[str, Any] | None = None
    process_classification: dict[str, Any] | None = None
    counterfactual_refs: list[str] = field(default_factory=list)
    lesson_candidate_refs: list[str] = field(default_factory=list)
    actual_ordered: bool = False
    actual_filled: bool = False
    exchange_order_id: str | None = None
    sealed: bool = False
    content_hash: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    transition_history: list[dict[str, Any]] = field(default_factory=list)
    data_class: str = "FIXTURE"
    virtual_research_position: bool = False
    schema: str = RECORD_SCHEMA
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return enforce_public_invariants(payload)

    def public_view(self) -> dict[str, Any]:
        """Member/public projection — never exposes order IDs or fill truth."""
        d = self.to_dict()
        return {
            "schema": d["schema"],
            "shadow_decision_id": d["shadow_decision_id"],
            "lifecycle_state": d["lifecycle_state"],
            "final_shadow_decision": d.get("final_shadow_decision") or {},
            "data_class": d.get("data_class"),
            "actual_ordered": False,
            "actual_filled": False,
            "exchange_order_id": None,
            "virtual_research_position": bool(d.get("virtual_research_position")),
            "lesson_candidate_refs": list(d.get("lesson_candidate_refs") or []),
            "counterfactual_refs": list(d.get("counterfactual_refs") or []),
            "process_classification": d.get("process_classification"),
            "sealed": bool(d.get("sealed")),
            "content_hash": d.get("content_hash"),
        }

    def material_for_hash(self) -> dict[str, Any]:
        d = self.to_dict()
        # Hash excludes mutable bookkeeping stamps that change on every write.
        for k in ("updated_at", "content_hash"):
            d.pop(k, None)
        return d

    def compute_hash(self) -> str:
        return _digest(self.material_for_hash())

    def validate_required(self) -> None:
        d = self.to_dict()
        for key in REQUIRED_PERSIST_FIELDS:
            if key not in d:
                raise ShadowDecisionContractError(f"missing_required_field:{key}")
        kind = str((self.final_shadow_decision or {}).get("kind") or "").upper()
        if kind and kind not in SHADOW_DECISION_KINDS:
            raise ShadowDecisionContractError(f"illegal_shadow_decision_kind:{kind}")
        if self.actual_ordered is not False or self.actual_filled is not False:
            raise ShadowDecisionContractError("actual_order_flags_must_be_false")
        if self.exchange_order_id is not None:
            raise ShadowDecisionContractError("exchange_order_id_must_be_null")

    def clone(self) -> "ShadowDecisionRecord":
        return ShadowDecisionRecord(**copy.deepcopy(self.to_dict()))


def build_empty_record(shadow_decision_id: str, *, data_class: str = "FIXTURE") -> ShadowDecisionRecord:
    return ShadowDecisionRecord(
        shadow_decision_id=shadow_decision_id,
        lifecycle_state="OBSERVED",
        data_class=data_class,
    )
