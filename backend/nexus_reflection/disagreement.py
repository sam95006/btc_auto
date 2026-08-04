"""Disagreement adjudication taxonomy — no automatic preference for det or Groq."""
from __future__ import annotations

from typing import Any

from backend.nexus_edge_discovery.blind_reflection_v23 import migrate_process_classification
from backend.nexus_edge_discovery.quota_aware_v23 import classify_disagreement as _base_classify

ALLOWED_CONFLICT_TYPES = (
    "AI_MISCLASSIFICATION",
    "DETERMINISTIC_BASELINE_TOO_COARSE",
    "EVIDENCE_PACKET_AMBIGUOUS",
    "TAXONOMY_AMBIGUOUS",
    "OUTCOME_PROCESS_MAPPING_ERROR",
    "BOTH_SUPPORTED",
    "BOTH_UNSUPPORTED",
    "CRITIC_UNRESOLVED",
    "PROVIDER_BLOCKED",
)


def classify_conflict(
    row: dict[str, Any],
    *,
    critic_verdict: str | None = None,
    provider_blocked: bool = False,
) -> str:
    if provider_blocked or row.get("transport_status") == "RATE_LIMITED":
        # 429 / capacity is PROVIDER_BLOCKED, never AI quality failure
        if str(row.get("transport_status") or "").upper() in {
            "RATE_LIMITED",
            "CIRCUIT_OPEN",
            "TIMEOUT",
            "BUCKET_THROTTLED",
        } or provider_blocked:
            if row.get("evidence_sufficiency") is None and row.get("process_classification") is None:
                return "PROVIDER_BLOCKED"
    verdict = critic_verdict if critic_verdict is not None else row.get("critic_verdict")
    v = str(verdict or "").strip().upper()
    if v in {"BOTH_SUPPORTED", "BOTH_UNSUPPORTED"}:
        return v
    if v == "INDEPENDENT_DISAGREEMENT":
        return "TAXONOMY_AMBIGUOUS"
    if "MAPPING" in v or v == "OUTCOME_PROCESS_MAPPING_ERROR":
        return "OUTCOME_PROCESS_MAPPING_ERROR"
    base = _base_classify(row, verdict)
    if base not in ALLOWED_CONFLICT_TYPES:
        return "TAXONOMY_AMBIGUOUS"
    return base


def build_disagreement_record(
    *,
    trade_id: str,
    groq_classification: str | None,
    groq_evidence_ids: list[str] | None,
    deterministic_classification: str | None,
    deterministic_rule_ids: list[str] | None,
    sambanova_result: str | None,
    evidence_sufficiency: str | None,
    conflict_type: str,
    legacy_process_raw: str | None = None,
) -> dict[str, Any]:
    groq_cls = migrate_process_classification(groq_classification)
    det_cls = migrate_process_classification(deterministic_classification)
    ct = conflict_type if conflict_type in ALLOWED_CONFLICT_TYPES else "TAXONOMY_AMBIGUOUS"
    rec = {
        "trade_id": trade_id,
        "groq_classification": groq_cls,
        "groq_evidence_ids": list(groq_evidence_ids or [])[:16],
        "deterministic_classification": det_cls,
        "deterministic_rule_ids": list(deterministic_rule_ids or [])[:16],
        "sambanova_result": sambanova_result,
        "evidence_sufficiency": evidence_sufficiency,
        "conflict_type": ct,
        # Explicit: no automatic preference
        "preferred_side": "NONE",
        "auto_prefer_deterministic": False,
        "auto_prefer_groq": False,
    }
    if legacy_process_raw and str(legacy_process_raw).upper() in {
        "UNDETERMINED_PROCESS",
        "PROCESS_UNDETERMINED",
        "INCONCLUSIVE",
    }:
        rec["legacy_process_classification"] = str(legacy_process_raw).upper()
        rec["migrated_to"] = "UNDETERMINED"
    return rec
