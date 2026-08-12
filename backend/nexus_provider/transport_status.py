"""Transport status taxonomy — never conflate with AI quality / evidence."""
from __future__ import annotations

from typing import Any

PROVIDER_TRANSPORT_STATUSES = frozenset(
    {
        "SUCCESS",
        "RATE_LIMITED",  # HTTP 429
        "TIMEOUT",
        "INVALID_JSON",
        "INVALID_SCHEMA",
        "CIRCUIT_OPEN",
        "BUCKET_THROTTLED",
        "OTHER_FAILURE",
        "DEDUP_SKIPPED",
        "IDEMPOTENT_REPLAY",
    }
)

# These must NEVER map into UNDETERMINED / evidence insufficient / AI disagreement.
QUALITY_NEUTRAL_TRANSPORT = frozenset(
    {
        "RATE_LIMITED",
        "TIMEOUT",
        "CIRCUIT_OPEN",
        "BUCKET_THROTTLED",
        "DEDUP_SKIPPED",
        "IDEMPOTENT_REPLAY",
    }
)


def classify_transport_status(
    *,
    http_status: int | None = None,
    result_status: str | None = None,
    invalid_json: bool = False,
    invalid_schema: bool = False,
    timeout: bool = False,
    circuit_open: bool = False,
    bucket_throttled: bool = False,
    dedup_skipped: bool = False,
) -> str:
    if dedup_skipped:
        return "DEDUP_SKIPPED"
    if circuit_open:
        return "CIRCUIT_OPEN"
    if bucket_throttled:
        return "BUCKET_THROTTLED"
    if timeout or str(result_status or "").upper() == "TIMEOUT":
        return "TIMEOUT"
    if invalid_json:
        return "INVALID_JSON"
    if invalid_schema or str(result_status or "").upper() in {"INVALID_SCHEMA", "SCHEMA_INVALID"}:
        return "INVALID_SCHEMA"
    if http_status == 429 or str(result_status or "").upper() in {"RATE_LIMITED", "HTTP_429"}:
        return "RATE_LIMITED"
    if str(result_status or "").upper() in {"OK", "SUCCESS"} and http_status in {None, 200}:
        return "SUCCESS"
    if http_status == 200 and not invalid_json and not invalid_schema:
        return "SUCCESS"
    return "OTHER_FAILURE"


def is_quality_neutral_transport(status: str) -> bool:
    return str(status or "").upper() in QUALITY_NEUTRAL_TRANSPORT


def assert_429_not_quality_failure(status: str, quality_fields: dict[str, Any] | None = None) -> None:
    """Invariant: a 429 must not pollute AI quality fields."""
    if classify_transport_status(result_status=status) != "RATE_LIMITED":
        return
    qf = quality_fields or {}
    banned_values = {
        "UNDETERMINED",
        "EVIDENCE_INSUFFICIENT",
        "SCHEMA_INVALID",
        "AI_DISAGREEMENT",
        "AI_QUALITY_FAILURE",
    }
    for k, v in qf.items():
        if str(v).upper() in banned_values:
            raise AssertionError(f"429 must not set quality field {k}={v}")
