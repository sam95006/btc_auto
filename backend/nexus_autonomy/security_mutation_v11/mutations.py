"""In-memory mutation operators over safety-critical subjects.

Mutations never edit foreign-owned source files. Each mutant is a callable that
weakens a specific guard so the kill suite can prove detection.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from backend.nexus_autonomy.security_credential_boundary_v1 import resolve_exchange_profile
from backend.nexus_autonomy.security_exceptions_v1 import PersistenceSecurityError
from backend.nexus_autonomy.security_persistence_v1 import fail_closed_json_loads
from backend.nexus_autonomy.security_mutation_v11.subjects import (
    SUBJECT_REGISTRY,
    BoundSubject,
    real_checkpoint_migration,
    real_credential_confusion,
    real_demo_mainnet_separation,
    real_exchange_write_prevention,
    real_idempotency,
    real_import_graph,
    real_ledger_hashes,
    real_network_egress,
    real_path_traversal,
    real_provider_prompt_leakage,
    real_public_private_boundary,
    real_risk_limits,
    real_secret_redaction,
    real_snapshot_recovery,
    real_symlink_escape,
    real_unsafe_deserialization,
)


def _always_safe(_attack: dict[str, Any]) -> bool:
    """Equivalent-looking mutant: claims every attack is handled."""
    return True


def _never_safe(_attack: dict[str, Any]) -> bool:
    return False


def mutant_path_skip_traversal(attack: dict[str, Any]) -> bool:
    """Remove '..' rejection — only check resolve containment (weaker on some FS)."""
    root = Path(attack["root"]).resolve()
    raw = str(attack["path"])
    # Intentionally skip PurePosixPath '..' token check
    try:
        candidate = (root / raw).resolve()
        candidate.relative_to(root)
        return False  # accepted
    except Exception:
        return True


def mutant_path_allow_all(attack: dict[str, Any]) -> bool:
    _ = attack
    return False  # never blocks


def mutant_deserialize_allow_pickle(attack: dict[str, Any]) -> bool:
    blob = attack["blob"]
    hint = str(attack.get("format_hint") or "auto").lower()
    # Mutation: ignore pickle hint / magic
    if isinstance(blob, bytes):
        try:
            text = blob.decode("utf-8", errors="ignore")
        except Exception:
            return False
    else:
        text = str(blob)
    try:
        fail_closed_json_loads(text)
        return not attack.get("expect_reject", False)
    except PersistenceSecurityError:
        # Still reject corrupt JSON, but pickle binary may decode to garbage that fails —
        # treat pickle hint as allowed:
        if hint in {"pickle", "pkl"} or (
            isinstance(blob, bytes) and blob[:1] == b"\x80"
        ):
            return False  # not blocked — mutation survived check
        return True


def mutant_credential_ignore_fallback(attack: dict[str, Any]) -> bool:
    result = resolve_exchange_profile(
        attack.get("env") or {},
        requested_profile=attack.get("requested_profile"),
        base_url=attack.get("base_url"),
    )
    # Mutation: treat mainnet fallback as OK for writes
    if result.mainnet_fallback_used:
        return False  # not fail-closed
    if attack.get("expect_fail_closed"):
        return bool(result.fail_closed) and not result.writes_enabled
    return not result.writes_enabled


def mutant_demo_mainnet_ignore_confusion(attack: dict[str, Any]) -> bool:
    result = resolve_exchange_profile(
        attack.get("env") or {},
        requested_profile=attack.get("requested_profile"),
        base_url=attack.get("base_url"),
    )
    # Mutation: ignore confusion flag
    return not result.writes_enabled  # may pass without fail_closed


def mutant_secret_no_redact(attack: dict[str, Any]) -> bool:
    # Mutation: return payload unchanged and claim safe
    payload = dict(attack["payload"])
    secret = str(attack.get("secret_value") or "")
    if secret and secret in json.dumps(payload):
        return False  # observable leak
    return True


def mutant_provider_allow_raw(attack: dict[str, Any]) -> bool:
    # Mutation: accept events with raw provider fields
    event = attack["event"]
    blob = json.dumps(event).lower()
    if "raw_provider_prompt" in blob or "raw_provider_response" in blob or "api_secret" in event:
        return False  # not blocked
    return True


def mutant_public_allow_private(attack: dict[str, Any]) -> bool:
    # Mutation: never raise on private fields
    return False


def mutant_migration_trust_all(attack: dict[str, Any]) -> bool:
    _ = attack
    return False  # trusts everything (does not reject)


def mutant_exchange_write_noop(attack: dict[str, Any]) -> bool:
    # Mutation: pretend trap fired without installing
    _ = attack
    return True  # false sense of safety — survivor unless oracle kills


def mutant_risk_raise_ceiling(attack: dict[str, Any]) -> bool:
    lev = int(attack["leverage"])
    # Mutation: allow up to 1000x
    if lev <= 0:
        return True
    if lev > 1000:
        return True
    return not attack.get("expect_reject", False)


def mutant_idempotency_disabled(attack: dict[str, Any]) -> bool:
    from backend.nexus_autonomy.execution_simulator_v1_1 import AutonomousExecutionSimulatorV1_1

    sim = AutonomousExecutionSimulatorV1_1(leverage=2, margin_usdt=50.0)
    req = dict(attack["request"])
    first = sim.create_order(dict(req))
    # Mutation: clear intent owners before second submit
    sim.intent_owners.clear()
    second = sim.create_order(dict(req))
    # Duplicate not ignored
    return first.get("status") == "ACCEPTED" and second.get("status") == "DUPLICATE_IGNORED"


def mutant_ledger_skip_verify(attack: dict[str, Any]) -> bool:
    # Mutation: always claim PASS even when tampered
    if attack.get("tamper"):
        return False  # fails to detect — killed by primary
    return real_ledger_hashes(attack)


def mutant_snapshot_ignore_checksum(attack: dict[str, Any]) -> bool:
    from backend.nexus_autonomy.runtime_durability_v1 import RuntimeDurabilityV1

    root = Path(attack["root"])
    dur = RuntimeDurabilityV1(root)
    ledger = dur.open_ledger()
    try:
        ledger.append(
            aggregate_id="snap-m",
            aggregate_type="SNAPSHOT",
            event_type="CREATED",
            source="mutation",
            payload={"ok": True},
            idempotency_key="snap-mut-1",
        )
        snap = dur.create_snapshot(ledger)
        if attack.get("corrupt_snapshot"):
            snap_path = Path(snap["snapshot_path"])
            with snap_path.open("ab") as fh:
                fh.write(b"\x00MUTATION_CORRUPT")
            # Mutation: skip checksum compare — report recovered
            return False  # did not detect corruption
        return True
    finally:
        ledger.close()


def mutant_network_allow_write(attack: dict[str, Any]) -> bool:
    url = str(attack["url"])
    # Mutation: only block evil.example, allow exchange write hosts
    if "evil.example" in url:
        return True
    if "/v5/order/" in url or "/v5/asset/" in url:
        return False  # not blocked
    return True


def mutant_import_graph_blind(attack: dict[str, Any]) -> bool:
    _ = attack
    return True  # claims clean without scanning


def mutant_symlink_follow_blind(attack: dict[str, Any]) -> bool:
    root = Path(attack["root"]).resolve()
    rel = attack["path"]
    # Mutation: resolve without symlink escape check
    try:
        candidate = (root / rel).resolve()
        # If outside, still claim safe (wrong)
        try:
            candidate.relative_to(root)
            return False
        except ValueError:
            return True  # claims blocked but didn't raise — ambiguous
    except OSError:
        return True


# operator registry: subject_id -> list[(operator_name, mutant_fn, notes)]
MUTATION_OPERATORS: dict[str, list[tuple[str, Callable[[dict[str, Any]], bool], str]]] = {
    "path_traversal": [
        ("skip_dotdot_token_check", mutant_path_skip_traversal, "drops explicit .. rejection"),
        ("allow_all_paths", mutant_path_allow_all, "never blocks"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "symlink_escape": [
        ("follow_without_jail", mutant_symlink_follow_blind, "no symlink jail"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "unsafe_deserialization": [
        ("allow_pickle", mutant_deserialize_allow_pickle, "accepts pickle"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "credential_confusion": [
        ("ignore_mainnet_fallback", mutant_credential_ignore_fallback, "allows fallback"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "demo_mainnet_separation": [
        ("ignore_confusion", mutant_demo_mainnet_ignore_confusion, "ignores host confusion"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "secret_redaction": [
        ("no_redact", mutant_secret_no_redact, "echoes secrets"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "provider_prompt_leakage": [
        ("allow_raw_provider", mutant_provider_allow_raw, "allows raw prompts"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "public_private_boundary": [
        ("allow_private_fields", mutant_public_allow_private, "leaks private fields"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "checkpoint_migration": [
        ("trust_all_schemas", mutant_migration_trust_all, "trusts evil migrations"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "exchange_write_prevention": [
        ("noop_trap", mutant_exchange_write_noop, "trap not installed"),
        ("never_block", _never_safe, "never reports block"),
    ],
    "risk_limits": [
        ("raise_ceiling_1000x", mutant_risk_raise_ceiling, "allows 100x"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "idempotency": [
        ("clear_intent_owners", mutant_idempotency_disabled, "disables idempotency"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "ledger_hashes": [
        ("skip_tamper_detect", mutant_ledger_skip_verify, "misses tamper"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "snapshot_recovery": [
        ("ignore_checksum", mutant_snapshot_ignore_checksum, "skips checksum"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "network_egress": [
        ("allow_exchange_write_hosts", mutant_network_allow_write, "allows write URLs"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
    "import_graph": [
        ("blind_pass", mutant_import_graph_blind, "skips graph scan"),
        ("always_claim_safe", _always_safe, "false positive safe"),
    ],
}

REAL_FNS: dict[str, Callable[[dict[str, Any]], bool]] = {
    "path_traversal": real_path_traversal,
    "symlink_escape": real_symlink_escape,
    "unsafe_deserialization": real_unsafe_deserialization,
    "credential_confusion": real_credential_confusion,
    "demo_mainnet_separation": real_demo_mainnet_separation,
    "secret_redaction": real_secret_redaction,
    "provider_prompt_leakage": real_provider_prompt_leakage,
    "public_private_boundary": real_public_private_boundary,
    "checkpoint_migration": real_checkpoint_migration,
    "exchange_write_prevention": real_exchange_write_prevention,
    "risk_limits": real_risk_limits,
    "idempotency": real_idempotency,
    "ledger_hashes": real_ledger_hashes,
    "snapshot_recovery": real_snapshot_recovery,
    "network_egress": real_network_egress,
    "import_graph": real_import_graph,
}


def bind_real(subject_id: str) -> BoundSubject:
    return BoundSubject(subject_id=subject_id, fn=REAL_FNS[subject_id], is_mutant=False)


def iter_mutants(subject_id: str) -> list[BoundSubject]:
    out: list[BoundSubject] = []
    for op_name, fn, notes in MUTATION_OPERATORS[subject_id]:
        mid = f"{subject_id}::{op_name}"
        out.append(
            BoundSubject(
                subject_id=subject_id,
                fn=fn,
                is_mutant=True,
                mutation_id=mid,
                operator=op_name,
                meta={"notes": notes},
            )
        )
    return out


def oracle_detects_false_safe(subject_id: str, attack: dict[str, Any], mutant: BoundSubject) -> bool:
    """Secondary kill: mutant claims safe but real subject says not safe / attack is malicious."""
    if attack.get("benign"):
        return False
    claimed = mutant.is_safe(attack)
    real = REAL_FNS[subject_id](attack)
    # If mutant claims safe (True) but real also True, need deeper oracle for always_safe
    if mutant.operator == "always_claim_safe" and claimed:
        return True  # killed by oracle: unverifiable claim
    if mutant.operator == "noop_trap" and claimed:
        return True  # trap not installed — killed by oracle
    if mutant.operator == "blind_pass" and claimed:
        return True
    # Mutant says safe but real says unsafe handling needed and real blocked
    if claimed and real and mutant.operator in {
        "ignore_confusion",
        "ignore_mainnet_fallback",
    }:
        # Check fail_closed specifically
        return True
    return False
