"""P2 migration rollout readiness: operational service-exec is authoritative."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_rollout_readiness import (
    ACTIVATION_READINESS_PASS_MARKER,
    BOOTSTRAP_READINESS_PASS_MARKER,
    CURRENT_IMAGE_PROBE_PASS_MARKER,
    INLINE_CURRENT_IMAGE_PROBE_SH,
    OPERATIONAL_READINESS_PASS_MARKER,
    classify_readiness_probe_output,
    wait_for_current_image_streak,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")
CURRENT = "3cd53ad694060e38fc1b9f129ff0082c0c349320"


def _valid_probe_stdout(*, sha: str = CURRENT) -> str:
    return (
        f"expected_sha={sha}\n"
        f"baked_sha={sha}\n"
        f"source_sha={sha}\n"
        f"expected_sha_prefix={sha[:12]}\n"
        f"baked_sha_prefix={sha[:12]}\n"
        f"source_sha_prefix={sha[:12]}\n"
        "helper_present=true\n"
        "safety_flags_ok=true\n"
        f"{CURRENT_IMAGE_PROBE_PASS_MARKER}\n"
        f"{OPERATIONAL_READINESS_PASS_MARKER}\n"
    )


def test_exit_zero_not_running_service_is_not_ready_and_resets_streak():
    raw = (
        "ERROR execute command failed\n"
        "code=NOT_RUNNING_SERVICE\n"
        "This service is not in the running state\n"
    )
    classified = classify_readiness_probe_output(raw, expected_sha=CURRENT, transport_exit_code=0)
    assert classified["ready"] is False
    assert classified["not_running_yet"] is True
    assert classified["hard_fail"] is False
    assert classified["exchange_write_call_count"] == 0

    sequence = [
        {"stdout": raw, "exit_code": 0, "expected_sha": CURRENT},
        {"stdout": raw, "exit_code": 0, "expected_sha": CURRENT},
        {"stdout": _valid_probe_stdout(), "exit_code": 0, "expected_sha": CURRENT},
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        idx = min(calls["n"], len(sequence) - 1)
        calls["n"] += 1
        return sequence[idx]

    result = wait_for_current_image_streak(
        probe=probe,
        max_attempts=3,
        consecutive_needed=3,
        sleep=lambda _s: None,
    )
    assert result["converged"] is False
    assert result["history"][0]["not_running_yet"] is True


def test_exit_zero_missing_baked_source_is_hard_fail():
    raw = (
        f"expected_sha={CURRENT}\n"
        "baked_sha=\n"
        "source_sha=\n"
        f"expected_sha_prefix={CURRENT[:12]}\n"
        "baked_sha_prefix=\n"
        "source_sha_prefix=\n"
        "helper_present=true\n"
        "safety_flags_ok=true\n"
        "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false\n"
        "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false\n"
    )
    classified = classify_readiness_probe_output(raw, expected_sha=CURRENT, transport_exit_code=0)
    assert classified["ready"] is False
    assert classified["hard_fail"] is True
    assert classified["sha_ok"] is False


def test_valid_sha_helper_safety_proof_is_ready():
    classified = classify_readiness_probe_output(
        _valid_probe_stdout(),
        expected_sha=CURRENT,
        transport_exit_code=1,
    )
    assert classified["ready"] is True
    assert classified["safety_flags_ok"] is True
    assert classified["pass_marker_present"] is True


def test_safety_flag_true_is_hard_fail():
    raw = (
        f"expected_sha={CURRENT}\n"
        f"baked_sha={CURRENT}\n"
        f"source_sha={CURRENT}\n"
        f"expected_sha_prefix={CURRENT[:12]}\n"
        f"baked_sha_prefix={CURRENT[:12]}\n"
        f"source_sha_prefix={CURRENT[:12]}\n"
        "helper_present=true\n"
        "safety_flags_ok=false\n"
        "safety_flag_bad=EXCHANGE_WRITE\n"
        "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false\n"
    )
    classified = classify_readiness_probe_output(raw, expected_sha=CURRENT)
    assert classified["ready"] is False
    assert classified["hard_fail"] is True


def test_three_valid_consecutive_proofs_converge():
    def probe(_attempt: int) -> dict:
        return {"stdout": _valid_probe_stdout(), "exit_code": 0, "expected_sha": CURRENT}

    result = wait_for_current_image_streak(
        probe=probe,
        max_attempts=12,
        consecutive_needed=3,
        sleep=lambda _s: None,
    )
    assert result["converged"] is True
    assert result["streak"] == 3
    assert result["P2_MIGRATION_OPERATIONAL_READINESS_PASS"] is True
    assert result["P2_MIGRATION_DEPLOYMENT_CONVERGED"] is True


def test_not_running_then_valid_probes_only_valid_count_toward_streak():
    outs = [
        "ERROR execute command failed\ncode=NOT_RUNNING_SERVICE\nInactive service\n",
        "ERROR execute command failed\ncode=NOT_RUNNING_SERVICE\nThis service is not in the running state\n",
        _valid_probe_stdout(),
        _valid_probe_stdout(),
        _valid_probe_stdout(),
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        idx = min(calls["n"], len(outs) - 1)
        calls["n"] += 1
        return {"stdout": outs[idx], "exit_code": 0, "expected_sha": CURRENT}

    result = wait_for_current_image_streak(
        probe=probe,
        max_attempts=12,
        consecutive_needed=3,
        sleep=lambda _s: None,
    )
    assert result["converged"] is True
    assert result["attempts"] == 5


def test_hard_fail_stops_streak_immediately():
    outs = [
        _valid_probe_stdout(),
        (
            f"expected_sha={CURRENT}\n"
            f"baked_sha=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
            f"source_sha=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n"
            f"expected_sha_prefix={CURRENT[:12]}\n"
            "baked_sha_prefix=deadbeefdead\n"
            "source_sha_prefix=deadbeefdead\n"
            "helper_present=true\n"
            "safety_flags_ok=true\n"
            "P2_MIGRATION_OPERATIONAL_READINESS_PASS=false\n"
        ),
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> dict:
        idx = min(calls["n"], len(outs) - 1)
        calls["n"] += 1
        return {"stdout": outs[idx], "exit_code": 0, "expected_sha": CURRENT}

    result = wait_for_current_image_streak(
        probe=probe,
        max_attempts=12,
        consecutive_needed=3,
        sleep=lambda _s: None,
    )
    assert result["converged"] is False
    assert result["hard_fail"] is True
    assert result["attempts"] == 2


def test_workflow_requires_positive_proof_marker_not_exit_code():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "P2_MIGRATION_OPERATIONAL_READINESS_PASS=true" in source
    assert "P2_MIGRATION_SERVICE_NOT_RUNNING_YET=true" in source
    assert ACTIVATION_READINESS_PASS_MARKER in source
    assert "safety_flags_ok=" in INLINE_CURRENT_IMAGE_PROBE_SH
    readiness = source[
        source.index("Operational runtime readiness before migration") : source.index(
            "Metadata diagnostic audit-only"
        )
    ]
    assert 'if [ "$CODE" = 0 ]; then' not in readiness
    assert "runtime_readiness_streak=" in readiness
    assert "MAX_ATTEMPTS=24" in readiness
