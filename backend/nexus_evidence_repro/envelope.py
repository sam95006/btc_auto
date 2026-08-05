"""Build and verify V12 reproducibility envelopes for completed Decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_decision.evidence import evidence_binding_hash, hash_evidence_blob
from backend.nexus_evidence_repro.constants import (
    HARD_BAN_FLAGS,
    PROOF_DIMENSIONS,
    REPRO_SCHEMA,
    REPRO_SCHEMA_VERSION,
    REQUIRED_ENVELOPE_KEYS,
)
from backend.nexus_evidence_repro.provenance import (
    build_classification_provenance,
    extract_ai_provider_model_identifiers,
    transition_paths,
)
from backend.nexus_evidence_repro.versions import resolve_version_pins


class ReproEnvelopeError(ValueError):
    """Reproducibility envelope incomplete or mismatched — fail closed."""


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_replay_fingerprint(
    *,
    decision: dict[str, Any],
    versions: dict[str, Any],
    ai_ids: list[dict[str, str]],
    classification: dict[str, Any],
) -> str:
    """Fingerprint excluding wall-clock volatility for deterministic replay compare."""
    risk = decision.get("deterministic_risk_result") or {}
    state_path, stage_path = transition_paths(decision)

    body = {
        "decision_id": decision.get("decision_id"),
        "candidate_id": decision.get("candidate_id"),
        "market_context_id": decision.get("market_context_id"),
        "point_in_time_timestamp": decision.get("point_in_time_timestamp"),
        "evidence_ids": list(decision.get("evidence_ids") or []),
        "evidence_hashes": list(decision.get("evidence_hashes") or []),
        "evidence_binding_hash": decision.get("evidence_binding_hash"),
        "decision_status": decision.get("decision_status"),
        "cost_model_version": decision.get("cost_model_version") or versions.get("cost_version"),
        "cost_version": versions.get("cost_version"),
        "risk_version": versions.get("risk_version"),
        "risk_gates_fingerprint": versions.get("risk_gates_fingerprint"),
        "risk_allowed": risk.get("allowed"),
        "risk_authority": risk.get("authority"),
        "checkpoint_version_id": versions.get("checkpoint_version_id"),
        "code_version": versions.get("code_version"),
        "decision_schema_version": versions.get("decision_schema_version"),
        "ai_provider_model_identifiers": ai_ids,
        "classification_label": classification.get("classification_label"),
        "state_path": state_path,
        "stage_path": stage_path,
        "intent_id": decision.get("intent_id"),
        # Presence only — simulator may mint non-deterministic position/exit UUIDs.
        "position_id_present": bool(decision.get("position_id")),
        "exit_id_present": bool(decision.get("exit_id")),
        "lesson_ids": list(decision.get("lesson_ids") or []),
        "rejection_reasons": list(decision.get("rejection_reasons") or []),
    }
    return _sha(body)


def build_repro_envelope(
    decision: dict[str, Any],
    *,
    root: Any = None,
    evidence_blobs: dict[str, str | bytes] | None = None,
    versions: dict[str, Any] | None = None,
    replay_match: bool | None = None,
    replay_peer_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Construct a fail-closed reproducibility envelope for one Decision."""
    if not isinstance(decision, dict):
        raise ReproEnvelopeError("decision_not_dict")
    did = decision.get("decision_id")
    if not did:
        raise ReproEnvelopeError("decision_id_missing")
    terminal = str(decision.get("decision_status") or "")
    # Completed simulated lifecycle = CLOSED. REJECTED / BLOCKED_AMBIGUOUS are
    # fail-closed terminals eligible for envelope capture but not "completed".
    if terminal not in {"CLOSED", "REJECTED", "BLOCKED_AMBIGUOUS"}:
        raise ReproEnvelopeError(f"decision_not_terminal:{terminal}")

    pins = versions or resolve_version_pins(root)
    evidence_ids = list(decision.get("evidence_ids") or [])
    evidence_hashes = list(decision.get("evidence_hashes") or [])
    if not evidence_ids or not evidence_hashes:
        raise ReproEnvelopeError("input_evidence_hashes_missing")
    if len(evidence_ids) != len(evidence_hashes):
        raise ReproEnvelopeError("evidence_ids_hashes_length_mismatch")

    if evidence_blobs is not None:
        for eid, expected in zip(evidence_ids, evidence_hashes):
            if eid not in evidence_blobs:
                raise ReproEnvelopeError(f"evidence_blob_missing:{eid}")
            actual = hash_evidence_blob(evidence_blobs[eid])
            if actual != expected:
                raise ReproEnvelopeError(f"evidence_hash_mismatch:{eid}")

    binding = decision.get("evidence_binding_hash") or evidence_binding_hash(
        evidence_ids, evidence_hashes
    )
    ai_ids = extract_ai_provider_model_identifiers(decision)
    if not ai_ids:
        raise ReproEnvelopeError("ai_provider_model_identifiers_missing")
    for entry in ai_ids:
        if not entry.get("provider"):
            raise ReproEnvelopeError("ai_provider_empty")
        if not entry.get("model"):
            raise ReproEnvelopeError("ai_model_empty")

    classification = build_classification_provenance(decision)
    fingerprint = build_replay_fingerprint(
        decision=decision,
        versions=pins,
        ai_ids=ai_ids,
        classification=classification,
    )

    cost_bound = decision.get("cost_model_version") or pins["cost_version"]
    if cost_bound != pins["cost_version"]:
        raise ReproEnvelopeError(
            f"cost_version_mismatch:decision={cost_bound}:pin={pins['cost_version']}"
        )

    risk = decision.get("deterministic_risk_result") or {}
    risk_authority = risk.get("authority")
    if risk_authority and risk_authority != pins["risk_authority"]:
        raise ReproEnvelopeError(
            f"risk_authority_mismatch:got={risk_authority}:pin={pins['risk_authority']}"
        )

    envelope: dict[str, Any] = {
        "schema": REPRO_SCHEMA,
        "schema_version": REPRO_SCHEMA_VERSION,
        "decision_id": did,
        "candidate_id": decision.get("candidate_id"),
        "terminal_status": terminal,
        "input_evidence_hashes": {
            "evidence_ids": evidence_ids,
            "evidence_hashes": evidence_hashes,
            "pairs": [
                {"evidence_id": i, "sha256": h} for i, h in zip(evidence_ids, evidence_hashes)
            ],
        },
        "evidence_binding_hash": binding,
        "code_version": pins["code_version"],
        "cost_version": pins["cost_version"],
        "risk_version": pins["risk_version"],
        "risk_authority": pins["risk_authority"],
        "risk_gates_fingerprint": pins["risk_gates_fingerprint"],
        "checkpoint_version": pins["checkpoint_version"],
        "checkpoint_version_id": pins["checkpoint_version_id"],
        "decision_schema_version": pins["decision_schema_version"],
        "ai_provider_model_identifiers": ai_ids,
        "classification_provenance": classification,
        "replay_fingerprint": fingerprint,
        "proof_dimensions": list(PROOF_DIMENSIONS),
        **HARD_BAN_FLAGS,
    }
    if replay_match is not None:
        envelope["deterministic_replay_result"] = {
            "match": bool(replay_match),
            "fingerprint": fingerprint,
            "peer_fingerprint": replay_peer_fingerprint,
        }
    return envelope


def verify_repro_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed verification that all proof dimensions are present and coherent."""
    if not isinstance(envelope, dict):
        raise ReproEnvelopeError("envelope_not_dict")
    missing = [k for k in REQUIRED_ENVELOPE_KEYS if k not in envelope]
    # deterministic_replay_result may be attached after replay; allow pre-replay verify
    # only when explicitly checking completeness post-campaign.
    soft = {"deterministic_replay_result"}
    hard_missing = [k for k in missing if k not in soft]
    if hard_missing:
        raise ReproEnvelopeError(f"envelope_missing_keys:{hard_missing}")

    if envelope.get("schema") != REPRO_SCHEMA:
        raise ReproEnvelopeError(f"schema_mismatch:{envelope.get('schema')}")
    if envelope.get("simulated_only") is not True:
        raise ReproEnvelopeError("simulated_only_required")
    if envelope.get("exchange_write") is not False:
        raise ReproEnvelopeError("exchange_write_forbidden")
    if envelope.get("demo_order") is not False:
        raise ReproEnvelopeError("demo_order_forbidden")
    if envelope.get("learning_claim") is not False:
        raise ReproEnvelopeError("learning_claim_forbidden")
    if envelope.get("profitability_claim") is not False:
        raise ReproEnvelopeError("profitability_claim_forbidden")

    ieh = envelope.get("input_evidence_hashes") or {}
    hashes = ieh.get("evidence_hashes") or []
    if not hashes or any(not h or len(str(h)) != 64 for h in hashes):
        raise ReproEnvelopeError("invalid_input_evidence_hashes")
    if not envelope.get("code_version"):
        raise ReproEnvelopeError("code_version_missing")
    if not envelope.get("cost_version"):
        raise ReproEnvelopeError("cost_version_missing")
    if not envelope.get("risk_version"):
        raise ReproEnvelopeError("risk_version_missing")
    if not envelope.get("checkpoint_version"):
        raise ReproEnvelopeError("checkpoint_version_missing")
    ai_ids = envelope.get("ai_provider_model_identifiers") or []
    if not ai_ids:
        raise ReproEnvelopeError("ai_provider_model_identifiers_missing")
    prov = envelope.get("classification_provenance") or {}
    if not prov.get("classification_label"):
        raise ReproEnvelopeError("classification_provenance_incomplete")

    dimensions_ok = {
        "input_evidence_hashes": True,
        "code_version": True,
        "cost_version": True,
        "risk_version": True,
        "checkpoint_version": True,
        "ai_provider_model_identifiers": True,
        "classification_provenance": True,
        "deterministic_replay_result": "deterministic_replay_result" in envelope
        and bool((envelope.get("deterministic_replay_result") or {}).get("match")),
    }
    return {
        "ok": all(
            dimensions_ok[d] for d in PROOF_DIMENSIONS if d != "deterministic_replay_result"
        )
        and (
            dimensions_ok["deterministic_replay_result"]
            if "deterministic_replay_result" in envelope
            else True
        ),
        "dimensions": dimensions_ok,
        "decision_id": envelope.get("decision_id"),
        "terminal_status": envelope.get("terminal_status"),
    }
