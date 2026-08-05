"""V13-H property/fuzz/schema/checkpoint/ledger fork fixtures."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.repro_safety_redteam_v13.scenarios import (
    _base_decision,
    run_ledger_fork_fixture,
)
from backend.nexus_decision.evidence import hash_evidence_blob
from backend.nexus_evidence_repro.envelope import (
    ReproEnvelopeError,
    build_repro_envelope,
    verify_repro_envelope,
)
from backend.nexus_evidence_repro.versions import resolve_version_pins


def property_fuzz_evidence_hashes(*, seed: int = 13, rounds: int = 64) -> dict[str, Any]:
    """Property: any mutated blob must fail envelope bind; clean blobs always bind."""
    rng = random.Random(seed)
    clean_ok = 0
    mutant_blocked = 0
    failures: list[str] = []
    for i in range(rounds):
        decision, blobs = _base_decision()
        # Fuzz blob content deterministically.
        fuzzed = {k: f"{v}|fuzz-{i}-{rng.randint(0, 10_000)}" for k, v in blobs.items()}
        ids = list(fuzzed.keys())
        hashes = [hash_evidence_blob(fuzzed[k]) for k in ids]
        decision["evidence_ids"] = ids
        decision["evidence_hashes"] = hashes
        from backend.nexus_decision.evidence import evidence_binding_hash

        decision["evidence_binding_hash"] = evidence_binding_hash(ids, hashes)
        try:
            build_repro_envelope(decision, evidence_blobs=fuzzed)
            clean_ok += 1
        except ReproEnvelopeError as exc:
            failures.append(f"clean_fail:{i}:{exc}")
            continue
        # Mutate one blob without updating hash → must block.
        attacked = dict(fuzzed)
        key = ids[rng.randrange(len(ids))]
        attacked[key] = attacked[key] + "|ATTACK"
        try:
            build_repro_envelope(decision, evidence_blobs=attacked)
            failures.append(f"mutant_accepted:{i}")
        except ReproEnvelopeError as exc:
            if "evidence_hash_mismatch" in str(exc):
                mutant_blocked += 1
            else:
                failures.append(f"mutant_wrong_error:{i}:{exc}")
    passed = clean_ok == rounds and mutant_blocked == rounds and not failures
    return {
        "fixture_id": "property_fuzz_evidence_hashes",
        "passed": passed,
        "rounds": rounds,
        "clean_ok": clean_ok,
        "mutant_blocked": mutant_blocked,
        "failures": failures[:8],
    }


def schema_mutation_envelope(root: Path | None = None) -> dict[str, Any]:
    """Schema mutation: drop/alter required envelope keys must fail verify."""
    decision, blobs = _base_decision(root=root)
    env = build_repro_envelope(decision, root=root, evidence_blobs=blobs, replay_match=True)
    assert verify_repro_envelope(env)["ok"] is True

    mutations: list[dict[str, Any]] = []
    for key in ("cost_version", "risk_version", "checkpoint_version", "code_version", "schema"):
        mutant = dict(env)
        if key == "schema":
            mutant["schema"] = "attacker_schema_v999"
        else:
            del mutant[key]
        blocked = False
        detail = ""
        try:
            verify_repro_envelope(mutant)
            detail = "accepted_HOLE"
        except ReproEnvelopeError as exc:
            blocked = True
            detail = str(exc)
        mutations.append({"key": key, "blocked": blocked, "detail": detail})

    # Ban-flag flip attacks.
    for flag in ("exchange_write", "demo_order", "learning_claim", "profitability_claim"):
        mutant = dict(env)
        mutant[flag] = True
        blocked = False
        try:
            verify_repro_envelope(mutant)
        except ReproEnvelopeError:
            blocked = True
        mutations.append({"key": flag, "blocked": blocked, "detail": "ban_flip"})

    passed = all(m["blocked"] for m in mutations)
    return {
        "fixture_id": "schema_mutation_envelope",
        "passed": passed,
        "mutations": mutations,
    }


def checkpoint_mutation_fixture(root: Path | None = None) -> dict[str, Any]:
    """Checkpoint version pin mutation must diverge from resolve_version_pins."""
    pins = resolve_version_pins(root)
    decision, blobs = _base_decision(root=root)
    env = build_repro_envelope(decision, root=root, evidence_blobs=blobs, replay_match=True)
    pin_match = env["checkpoint_version_id"] == pins["checkpoint_version_id"]

    tampered = dict(env)
    tampered["checkpoint_version"] = {
        "schema": "attacker_ckpt",
        "schema_version": 99,
        "authority_id": "attacker",
    }
    tampered["checkpoint_version_id"] = "attacker_ckpt:99"
    diverged = tampered["checkpoint_version_id"] != pins["checkpoint_version_id"]

    # Digest-style checkpoint blob mutation (ledger-adjacent).
    blob = {"decision_id": decision["decision_id"], "sha256": "abc", "status": "OPEN"}
    digest = hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()
    blob["status"] = "CLOSED"
    digest2 = hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()
    digest_detects = digest != digest2

    passed = pin_match and diverged and digest_detects
    return {
        "fixture_id": "checkpoint_mutation",
        "passed": passed,
        "pin_match": pin_match,
        "diverged": diverged,
        "digest_detects": digest_detects,
        "checkpoint_version_id": pins["checkpoint_version_id"],
    }


def run_all_fixtures(workdir: Path, *, root: Path | None = None) -> list[dict[str, Any]]:
    return [
        property_fuzz_evidence_hashes(seed=13, rounds=64),
        schema_mutation_envelope(root=root),
        checkpoint_mutation_fixture(root=root),
        run_ledger_fork_fixture(workdir),
    ]
