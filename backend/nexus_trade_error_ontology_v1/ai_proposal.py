"""AI proposal path — proposes only; cannot override deterministic classification."""
from __future__ import annotations

from typing import Any

from backend.nexus_trade_error_ontology_v1.classifier import (
    classify_trade_error,
    migrate_classification,
)
from backend.nexus_trade_error_ontology_v1.constants import (
    ERROR_DIMENSIONS,
    PROCESS_CLASSES,
    SCHEMA_AI_PROPOSAL,
)
from backend.nexus_trade_error_ontology_v1.hard_bans import HardBanViolation, refuse_ai_override
from backend.nexus_trade_error_ontology_v1.schema import validate_classification_record


def normalize_ai_proposal(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize an AI-proposed classification payload (advisory only)."""
    raw = raw or {}
    proposed = migrate_classification(raw.get("process_classification") or raw.get("proposed_class"))
    dims_raw = raw.get("dimensions") or raw.get("proposed_dimensions") or []
    dims: list[str] = []
    for d in dims_raw:
        ds = str(d).strip().upper()
        if ds in ERROR_DIMENSIONS and ds not in dims:
            dims.append(ds)
    severity = str(raw.get("severity") or "").upper() or None
    avoidability = str(raw.get("avoidability") or "").upper() or None
    narrative = str(raw.get("narrative") or raw.get("rationale") or "")[:500]
    return {
        "schema": SCHEMA_AI_PROPOSAL,
        "proposed_class": proposed if proposed in PROCESS_CLASSES else "INSUFFICIENT_EVIDENCE",
        "proposed_dimensions": dims,
        "proposed_severity": severity,
        "proposed_avoidability": avoidability,
        "narrative": narrative,
        "authority": "advisory_only",
        "can_override_deterministic": False,
    }


def apply_ai_proposal(
    packet: dict[str, Any],
    ai_raw: dict[str, Any] | None,
    *,
    allow_override: bool = False,
) -> dict[str, Any]:
    """Merge AI proposal into deterministic classification.

    Final process_classification ALWAYS equals deterministic_class.
    If allow_override is requested, raise HardBanViolation.
    """
    if allow_override:
        refuse_ai_override()

    det = classify_trade_error(packet)
    proposal = normalize_ai_proposal(ai_raw)
    disagree = proposal["proposed_class"] != det["deterministic_class"]

    # AI may annotate dimensions/narrative only; never rewrite final class.
    annotated_dims = list(det["dimensions"])
    for d in proposal["proposed_dimensions"]:
        if d not in annotated_dims:
            # Proposed dims recorded separately; do not mutate deterministic dims.
            pass

    record = dict(det)
    record["ai_proposed_class"] = proposal["proposed_class"]
    record["ai_proposal"] = proposal
    record["ai_proposed_dimensions"] = proposal["proposed_dimensions"]
    record["classifier_authority"] = {
        "deterministic_is_final": True,
        "ai_can_override": False,
        "fallback": "deterministic_classifier",
        "ai_disagreement": disagree,
    }
    # Explicit: final class locked to deterministic.
    record["process_classification"] = det["deterministic_class"]

    errors = validate_classification_record(record)
    if errors:
        raise HardBanViolation(f"classification_record_invalid:{','.join(errors[:5])}")
    return record


def attempt_ai_override(
    packet: dict[str, Any],
    ai_raw: dict[str, Any],
) -> dict[str, Any]:
    """Adversarial helper: any attempt to force AI class into final must fail closed."""
    det = classify_trade_error(packet)
    forced = migrate_classification(ai_raw.get("process_classification"))
    if forced != det["deterministic_class"]:
        # Simulate attacker writing AI class into final field — refuse.
        raise HardBanViolation(
            f"no_ai_override_of_deterministic_class:ai={forced}:det={det['deterministic_class']}"
        )
    return apply_ai_proposal(packet, ai_raw)
