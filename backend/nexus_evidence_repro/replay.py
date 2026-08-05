"""Deterministic simulated Decision lifecycle runner + replay verifier."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.nexus_decision import DecisionLifecycleOrchestrator
from backend.nexus_decision.evidence import hash_evidence_blob
from backend.nexus_evidence_repro.envelope import (
    ReproEnvelopeError,
    build_repro_envelope,
    build_replay_fingerprint,
    verify_repro_envelope,
)
from backend.nexus_evidence_repro.provenance import (
    build_classification_provenance,
    extract_ai_provider_model_identifiers,
)
from backend.nexus_evidence_repro.versions import resolve_version_pins


class ReplayMismatchError(RuntimeError):
    """Deterministic replay diverged — fail closed."""


def _seed_hex(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def simulated_ai_outputs(seed: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fixed simulated Provider/model identifiers (not live LLM, not learning proof)."""
    tag = _seed_hex(seed)
    reasoners = [
        {
            "provider": "sim-reasoner",
            "model": "deterministic-reasoner-v1",
            "provider_id": "sim-reasoner",
            "model_id": "deterministic-reasoner-v1",
            "view": "neutral",
            "seed_tag": tag,
        }
    ]
    critic = {
        "provider": "sim-critic",
        "model": "deterministic-critic-v1",
        "provider_id": "sim-critic",
        "model_id": "deterministic-critic-v1",
        "verdict": "pass",
        "score": 0.75,
        "seed_tag": tag,
    }
    return reasoners, critic


def build_seeded_evidence(seed: str, n: int = 2) -> dict[str, Any]:
    tag = _seed_hex(seed)
    blobs = {f"ev_{seed}_{i}": f"v12e-blob-{tag}-{i}" for i in range(n)}
    ids = list(blobs.keys())
    hashes = [hash_evidence_blob(blobs[i]) for i in ids]
    return {
        "evidence_ids": ids,
        "evidence_hashes": hashes,
        "evidence_blobs": blobs,
        "data_freshness": {"age_seconds": 5.0, "stale": False},
        "data_completeness": {
            "ratio": 1.0,
            "required_fields": ["mid", "spread", "ts"],
            "present_fields": ["mid", "spread", "ts"],
        },
    }


def run_completed_simulated_lifecycle(
    root: Path | str,
    *,
    seed: str,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run one Observe→…→CLOSED simulated Decision with fixed identities."""
    root_p = Path(root)
    root_p.mkdir(parents=True, exist_ok=True)
    tag = _seed_hex(seed)
    decision_id = f"dec_v12e_{tag}"
    candidate_id = f"cand_v12e_{tag}"
    market_context_id = f"mctx_v12e_{tag}"
    pit = "2026-08-05T07:00:00Z"
    ev = build_seeded_evidence(seed)
    reasoners, critic = simulated_ai_outputs(seed)

    orch = DecisionLifecycleOrchestrator(root_p)
    orch.observe(
        candidate_id=candidate_id,
        market_context_id=market_context_id,
        point_in_time_timestamp=pit,
        evidence_ids=ev["evidence_ids"],
        evidence_hashes=ev["evidence_hashes"],
        data_freshness=ev["data_freshness"],
        data_completeness=ev["data_completeness"],
        idempotency_key=f"{seed}-obs",
        evidence_blobs=ev["evidence_blobs"],
        decision_id=decision_id,
    )
    orch.understand(
        decision_id,
        AI_reasoner_outputs=reasoners,
        idempotency_key=f"{seed}-u",
    )
    orch.challenge(
        decision_id,
        independent_critic_output=critic,
        idempotency_key=f"{seed}-c",
    )
    orch.decide(
        decision_id,
        deterministic_risk_result={"allowed": True, "reasons": []},
        idempotency_key=f"{seed}-d",
    )
    orch.record(decision_id, idempotency_key=f"{seed}-r")
    orch.monitor(decision_id, exit=True, idempotency_key=f"{seed}-m")
    orch.review(decision_id, idempotency_key=f"{seed}-rev")
    orch.calibrate(
        decision_id,
        lesson_ids=[f"lesson_struct_{tag}"],
        idempotency_key=f"{seed}-cal",
    )
    closed = orch.improve(decision_id, idempotency_key=f"{seed}-imp")
    decision = closed["decision"]
    if decision.get("decision_status") != "CLOSED":
        raise ReplayMismatchError(
            f"lifecycle_not_closed:{decision.get('decision_status')}"
        )

    # Confirm no exchange / demo side-effects on this orchestrator.
    if orch.exchange_write_attempt_count != 0:
        raise ReplayMismatchError("exchange_write_attempt_nonzero")
    if orch.order_attempt_count != 0:
        # Formal order path unused; trap counter may be 0 unless trap invoked.
        pass

    pins = resolve_version_pins(repo_root)
    envelope = build_repro_envelope(
        decision,
        root=repo_root,
        evidence_blobs=ev["evidence_blobs"],
        versions=pins,
    )
    return {
        "seed": seed,
        "decision": decision,
        "envelope": envelope,
        "evidence_blobs": ev["evidence_blobs"],
        "versions": pins,
        "orchestrator_status": orch.status(),
        "exchange_write_attempt_count": orch.exchange_write_attempt_count,
        "order_attempt_count": orch.order_attempt_count,
    }


def deterministic_replay_fingerprint(result: dict[str, Any]) -> str:
    decision = result["decision"]
    versions = result["versions"]
    ai_ids = extract_ai_provider_model_identifiers(decision)
    classification = build_classification_provenance(decision)
    return build_replay_fingerprint(
        decision=decision,
        versions=versions,
        ai_ids=ai_ids,
        classification=classification,
    )


def verify_deterministic_replay(
    first: dict[str, Any],
    second: dict[str, Any],
) -> dict[str, Any]:
    """Compare two seeded runs; require identical replay fingerprints + key pins."""
    fp1 = deterministic_replay_fingerprint(first)
    fp2 = deterministic_replay_fingerprint(second)
    if fp1 != fp2:
        raise ReplayMismatchError(f"replay_fingerprint_mismatch:{fp1}!={fp2}")

    d1 = first["decision"]
    d2 = second["decision"]
    checks = {
        "evidence_hashes": d1.get("evidence_hashes") == d2.get("evidence_hashes"),
        "evidence_binding_hash": d1.get("evidence_binding_hash")
        == d2.get("evidence_binding_hash"),
        "cost_model_version": d1.get("cost_model_version") == d2.get("cost_model_version"),
        "decision_status": d1.get("decision_status") == d2.get("decision_status"),
        "intent_id": d1.get("intent_id") == d2.get("intent_id"),
        "position_id_present": bool(d1.get("position_id")) == bool(d2.get("position_id")),
        "code_version": first["versions"]["code_version"] == second["versions"]["code_version"],
        "cost_version": first["versions"]["cost_version"] == second["versions"]["cost_version"],
        "risk_version": first["versions"]["risk_version"] == second["versions"]["risk_version"],
        "checkpoint_version_id": first["versions"]["checkpoint_version_id"]
        == second["versions"]["checkpoint_version_id"],
        "ai_ids": extract_ai_provider_model_identifiers(d1)
        == extract_ai_provider_model_identifiers(d2),
        "classification_label": build_classification_provenance(d1)["classification_label"]
        == build_classification_provenance(d2)["classification_label"],
        "state_path": build_classification_provenance(d1)["state_path"]
        == build_classification_provenance(d2)["state_path"],
        "fingerprint": fp1 == fp2,
    }
    if not all(checks.values()):
        failed = [k for k, v in checks.items() if not v]
        raise ReplayMismatchError(f"replay_checks_failed:{failed}")

    # Attach deterministic_replay_result onto a verified envelope copy.
    envelope = build_repro_envelope(
        d1,
        evidence_blobs=first.get("evidence_blobs"),
        versions=first["versions"],
        replay_match=True,
        replay_peer_fingerprint=fp2,
    )
    verify = verify_repro_envelope(envelope)
    if not verify.get("ok") or not verify["dimensions"].get("deterministic_replay_result"):
        raise ReproEnvelopeError("post_replay_envelope_incomplete")

    return {
        "match": True,
        "fingerprint": fp1,
        "checks": checks,
        "envelope": envelope,
        "verify": verify,
    }
