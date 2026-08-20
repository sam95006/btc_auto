"""P2 migration rollout readiness: positive proof only; NOT_RUNNING is wait."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_rollout_readiness import (
    CURRENT_IMAGE_PROBE_PASS_MARKER,
    INLINE_CURRENT_IMAGE_PROBE_SH,
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
        f"{CURRENT_IMAGE_PROBE_PASS_MARKER}\n"
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
    assert classified["pass_marker_present"] is False
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

    # Single valid hit after NOT_RUNNING must not converge yet (streak reset).
    result = wait_for_current_image_streak(
        probe=probe,
        max_attempts=3,
        consecutive_needed=3,
        sleep=lambda _s: None,
    )
    assert result["converged"] is False
    assert result["history"][0]["ready"] is False
    assert result["history"][0]["not_running_yet"] is True
    assert result["history"][2]["ready"] is True


def test_exit_zero_missing_baked_source_is_not_ready():
    raw = (
        f"expected_sha={CURRENT}\n"
        "baked_sha=\n"
        "source_sha=\n"
        f"expected_sha_prefix={CURRENT[:12]}\n"
        "baked_sha_prefix=\n"
        "source_sha_prefix=\n"
        "helper_present=true\n"
        "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=false\n"
    )
    classified = classify_readiness_probe_output(raw, expected_sha=CURRENT, transport_exit_code=0)
    assert classified["ready"] is False
    assert classified["sha_ok"] is False
    assert classified["baked_sha_prefix"] == ""
    assert classified["source_sha_prefix"] == ""


def test_valid_sha_helper_proof_is_ready():
    classified = classify_readiness_probe_output(
        _valid_probe_stdout(),
        expected_sha=CURRENT,
        transport_exit_code=1,  # exit code ignored when positive proof present
    )
    assert classified["ready"] is True
    assert classified["pass_marker_present"] is True
    assert classified["helper_present"] is True
    assert classified["not_running_yet"] is False


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
    assert result["attempts"] == 3
    assert all(row["ready"] for row in result["history"])


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
    assert [row["ready"] for row in result["history"]] == [False, False, True, True, True]
    assert result["history"][0]["not_running_yet"] is True
    assert result["create_order_calls"] == 0
    assert result["exchange_write_call_count"] == 0


def test_workflow_requires_positive_proof_marker_not_exit_code():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true" in source
    assert "P2_MIGRATION_SERVICE_NOT_RUNNING_YET=true" in source
    assert "NOT_RUNNING_SERVICE" in source
    assert "execute command failed" in source
    assert CURRENT_IMAGE_PROBE_PASS_MARKER.split("=")[0] in INLINE_CURRENT_IMAGE_PROBE_SH
    assert "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true" in INLINE_CURRENT_IMAGE_PROBE_SH
    # Must not treat transport exit alone as success.
    readiness = source[
        source.index("Wait for fresh migration service baked SHA readiness") : source.index(
            "Require final disarmed runtime with ledger DSN"
        )
    ]
    assert 'if [ "$CODE" = 0 ]; then' not in readiness
    assert "P2_MIGRATION_CURRENT_IMAGE_PROBE_PASS=true" in readiness
