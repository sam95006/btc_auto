"""V11.1 C4 — Canonical checkpoint envelope authority tests (two-pass)."""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"

import pytest

from backend.nexus_checkpoint.adapters import (
    wrap_control_plane_payload,
    wrap_decision_payload,
    wrap_microstructure_payload,
    wrap_qualification_payload,
    wrap_reflection_payload,
    wrap_session_payload,
)
from backend.nexus_checkpoint.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CANONICAL_CHECKPOINT_ENVELOPE_COUNT,
    CHECKPOINT_OK,
    CORRUPTION_DETECTED,
    ENVELOPE_SCHEMA,
    LIVE_V23_CHECKPOINT_NAME,
    MIGRATION_DRY_RUN,
    RECOVERED_EXACT,
)
from backend.nexus_checkpoint.envelope import (
    build_envelope,
    compute_payload_checksum,
    detect_corruption,
    validate_envelope,
)
from backend.nexus_checkpoint.migrate import dry_run_migrate_live_v23, migrate_legacy_to_envelope
from backend.nexus_checkpoint.store import CanonicalCheckpointStore, atomic_write_json
from backend.nexus_contracts.authority_registry import get_authority
from tools.architecture.check_contract_drift import check_checkpoint_drift, run_drift_checks


ROOT = Path(__file__).resolve().parents[1]
LIVE_V23 = Path(r"D:\NEXUS\btc_bot\.nexus_runtime") / LIVE_V23_CHECKPOINT_NAME


def test_canonical_envelope_count_is_one():
    assert CANONICAL_CHECKPOINT_ENVELOPE_COUNT == 1
    auth = get_authority("checkpoint")
    assert auth.canonical_module == "backend.nexus_checkpoint.store"
    assert auth.canonical_symbol == "CanonicalCheckpointStore"
    assert auth.status == "active_compat_present"
    assert auth.authority_id == "private_core.checkpoint.envelope_v1"


def test_build_and_validate_envelope_roundtrip():
    env = build_envelope(
        payload={"session_id": "s1", "state": "RUNNING"},
        payload_type="session",
        idempotency_key="k1",
        source_runtime="test",
        ledger_sequence=7,
        manifest_checksum="m1",
    )
    assert env["schema"] == ENVELOPE_SCHEMA
    assert env["payload_checksum"] == compute_payload_checksum(env["payload"])
    assert validate_envelope(env)["ok"] is True


def test_all_payload_type_adapters():
    payloads = {
        "session": wrap_session_payload({"x": 1}, idempotency_key="s"),
        "reflection": wrap_reflection_payload(
            {"schema": "blind_reflection_v23_checkpoint_v4", "schema_version": 4},
            idempotency_key="r",
        ),
        "microstructure": wrap_microstructure_payload({"run_id": "m"}, idempotency_key="m"),
        "qualification": wrap_qualification_payload({"stage": "BLOCKED_READY"}, idempotency_key="q"),
        "decision": wrap_decision_payload({"decision_id": "d1"}, idempotency_key="d"),
        "control_plane": wrap_control_plane_payload({"run_id": "c"}, idempotency_key="c"),
    }
    for ptype, env in payloads.items():
        assert env["payload_type"] == ptype
        assert validate_envelope(env)["ok"] is True
        assert env["migration_history"]


def test_atomic_write_fsync_rename_and_verify(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    result = store.save(
        payload={"n": 1},
        payload_type="session",
        idempotency_key="atomic-1",
        ledger_sequence=1,
        manifest_checksum="man",
    )
    assert result["status"] == CHECKPOINT_OK
    assert result["duplicate"] is False
    assert result["write"]["fsync"] is True
    assert result["write"]["rename"] is True
    path = Path(result["path"])
    assert path.is_file()
    assert not path.with_name(path.name + ".tmp").exists()
    loaded = store.load(result["checkpoint_id"])
    assert loaded["status"] == CHECKPOINT_OK


def test_idempotent_save(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    a = store.save(payload={"n": 1}, payload_type="decision", idempotency_key="same")
    b = store.save(payload={"n": 2}, payload_type="decision", idempotency_key="same")
    assert a["checkpoint_id"] == b["checkpoint_id"]
    assert b["duplicate"] is True
    assert b["envelope"]["payload"]["n"] == 1


def test_corruption_detection_payload_tamper(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    saved = store.save(payload={"ok": True}, payload_type="session", idempotency_key="tamper")
    path = Path(saved["path"])
    env = json.loads(path.read_text(encoding="utf-8"))
    env["payload"]["ok"] = False  # tamper without updating checksums
    path.write_text(json.dumps(env), encoding="utf-8")
    loaded = store.load(saved["checkpoint_id"])
    assert loaded["status"] == CORRUPTION_DETECTED
    assert loaded["reason"] == "payload_checksum_mismatch"


def test_corruption_detection_envelope_checksum(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    saved = store.save(payload={"ok": True}, payload_type="session", idempotency_key="env-tamper")
    path = Path(saved["path"])
    env = json.loads(path.read_text(encoding="utf-8"))
    env["source_runtime"] = "mutated"
    path.write_text(json.dumps(env), encoding="utf-8")
    probe = detect_corruption(path.read_text(encoding="utf-8"))
    assert probe["ok"] is False
    assert probe["reason"] == "envelope_checksum_mismatch"


def test_lkg_restore_exact(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    saved = store.save(
        payload={"phase": 1},
        payload_type="session",
        idempotency_key="lkg1",
        ledger_sequence=10,
    )
    restored = store.restore_last_known_good()
    assert restored["status"] == RECOVERED_EXACT
    assert restored["envelope"]["checkpoint_id"] == saved["checkpoint_id"]
    assert restored["silent_recovery_guess"] is False


def test_ambiguous_restore_when_newer_ahead_of_lkg(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    first = store.save(
        payload={"phase": 1},
        payload_type="session",
        idempotency_key="amb-1",
        ledger_sequence=1,
    )
    # Write a newer checkpoint without updating LKG.
    store.save(
        payload={"phase": 2},
        payload_type="session",
        idempotency_key="amb-2",
        ledger_sequence=2,
        update_lkg=False,
        previous_checkpoint_id=first["checkpoint_id"],
    )
    blocked = store.restore_last_known_good()
    assert blocked["status"] == BLOCKED_AMBIGUOUS_STATE
    assert blocked["reason"] == "newer_checkpoint_ahead_of_lkg"


def test_ambiguous_lkg_target_missing(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    saved = store.save(payload={"x": 1}, payload_type="session", idempotency_key="miss")
    Path(saved["path"]).unlink()
    blocked = store.restore_last_known_good()
    assert blocked["status"] == BLOCKED_AMBIGUOUS_STATE
    assert blocked["reason"] == "lkg_target_missing"


def test_refuse_write_to_live_v23_name(tmp_path: Path):
    banned = tmp_path / LIVE_V23_CHECKPOINT_NAME
    with pytest.raises(PermissionError):
        atomic_write_json(banned, {"schema": "nope"})


def test_schema_migration_in_memory():
    legacy = {
        "schema": "blind_reflection_v23_checkpoint_v4",
        "schema_version": 4,
        "calibration_manifest_checksum": "abc",
        "case_ids": ["c1"],
    }
    result = migrate_legacy_to_envelope(
        legacy,
        payload_type="reflection",
        idempotency_key="mig-1",
        dry_run=True,
    )
    assert result["status"] == MIGRATION_DRY_RUN
    assert result["destructive_write"] is False
    assert result["validation"]["ok"] is True
    assert result["envelope"]["payload"]["case_ids"] == ["c1"]


@pytest.mark.skipif(not LIVE_V23.is_file(), reason="live V2.3 checkpoint not present")
def test_dry_run_live_v23_untouched(tmp_path: Path):
    before = LIVE_V23.read_bytes()
    before_mtime = LIVE_V23.stat().st_mtime_ns
    out = tmp_path / "dry_run_envelope.json"
    result = dry_run_migrate_live_v23(LIVE_V23, artifact_out=out)
    assert result["status"] == MIGRATION_DRY_RUN
    assert result["live_untouched"] is True
    assert result["destructive_write"] is False
    assert LIVE_V23.read_bytes() == before
    assert LIVE_V23.stat().st_mtime_ns == before_mtime
    assert out.is_file()
    artifact = json.loads(out.read_text(encoding="utf-8"))
    assert validate_envelope(artifact["envelope"])["ok"] is True
    assert artifact["live_untouched"] is True
    assert artifact["destructive_write"] is False


def test_checkpoint_drift_no_multi_scope_blocker():
    findings = check_checkpoint_drift(ROOT)
    codes = {f["code"] for f in findings}
    assert "MULTI_SCOPE_AUTHORITY_CHECKPOINT" not in codes
    assert "CANONICAL_ENVELOPE_SYMBOL_MISSING" not in codes
    assert "ENVELOPE_COUNT_NOT_ONE" not in codes
    # Adapter-aware informational finding is acceptable.
    assert "MULTI_PAYLOAD_SCHEMAS_ADAPTED" in codes or not any(
        f.get("severity") == "critical" for f in findings
    )


def test_drift_report_checkpoint_not_critical_blocker():
    report = run_drift_checks(ROOT)
    ckpt_blockers = [
        b for b in report["blockers"] if b.get("domain") == "checkpoint"
    ]
    assert ckpt_blockers == []


# --- Pass 2 negative / adversarial ---


def test_pass2_invalid_payload_type_rejected():
    with pytest.raises(ValueError):
        build_envelope(
            payload={},
            payload_type="not_a_real_type",
            idempotency_key="x",
            source_runtime="t",
        )


def test_pass2_missing_idempotency_rejected():
    with pytest.raises(ValueError):
        build_envelope(
            payload={},
            payload_type="session",
            idempotency_key="",
            source_runtime="t",
        )


def test_pass2_lkg_file_checksum_mismatch(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    saved = store.save(payload={"z": 1}, payload_type="session", idempotency_key="cksum")
    path = Path(saved["path"])
    # Rewrite file with valid envelope but different bytes than LKG recorded.
    env = json.loads(path.read_text(encoding="utf-8"))
    env["payload"]["z"] = 2
    from backend.nexus_checkpoint.envelope import compute_envelope_checksum, compute_payload_checksum

    env["payload_checksum"] = compute_payload_checksum(env["payload"])
    env["envelope_checksum"] = compute_envelope_checksum(env)
    # Write without going through store so LKG file_sha256 stays stale.
    path.write_text(json.dumps(env, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = store.restore_last_known_good()
    assert result["status"] == CORRUPTION_DETECTED
    assert result["reason"] == "lkg_file_checksum_mismatch"


def test_pass2_no_silent_guess_flag_on_ambiguous(tmp_path: Path):
    store = CanonicalCheckpointStore(tmp_path / "ckpt")
    amb = store.fail_closed_ambiguous(reason="forced")
    assert amb["status"] == BLOCKED_AMBIGUOUS_STATE
    assert amb["silent_recovery_guess"] is False
    assert amb["exchange_write_attempt_count"] == 0
    assert amb["demo_order_count"] == 0
