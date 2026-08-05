"""Input parsing for V16-G — fail-closed on provider / JSON faults."""
from __future__ import annotations

import json
from typing import Any

from backend.nexus_uncertainty_abstention.constants import (
    AGREEMENT_CHANNELS,
    PROVIDER_FAILED,
    PROVIDER_INVALID_JSON,
    PROVIDER_OK,
    PROVIDER_STATUSES,
    PROVIDER_TIMEOUT,
    QUALITY_CHANNELS,
    REQUIRED_INPUT_KEYS,
)


class ParseFailure(Exception):
    """Structured parse failure — always maps to BLOCK."""

    def __init__(self, reason: str, *, detail: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or reason


def _as_unit_float(value: Any, *, field: str) -> float:
    if value is None:
        raise ParseFailure("MISSING_FIELD", detail=field)
    if isinstance(value, bool):
        raise ParseFailure("INVALID_TYPE", detail=field)
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ParseFailure("INVALID_NUMBER", detail=field) from exc
    if num != num:  # NaN
        raise ParseFailure("NAN_VALUE", detail=field)
    if num < 0.0 or num > 1.0:
        raise ParseFailure("OUT_OF_RANGE", detail=field)
    return num


def _as_nonneg_float(value: Any, *, field: str) -> float:
    if value is None:
        raise ParseFailure("MISSING_FIELD", detail=field)
    if isinstance(value, bool):
        raise ParseFailure("INVALID_TYPE", detail=field)
    try:
        num = float(value)
    except (TypeError, ValueError) as exc:
        raise ParseFailure("INVALID_NUMBER", detail=field) from exc
    if num != num or num < 0.0:
        raise ParseFailure("INVALID_NUMBER", detail=field)
    return num


def parse_provider_payload(raw: Any) -> dict[str, Any]:
    """Parse provider payload. Invalid JSON / failures never fail open."""
    if raw is None:
        raise ParseFailure("PROVIDER_EMPTY", detail="null payload")

    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseFailure("PROVIDER_INVALID_JSON", detail="undecodable bytes") from exc

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ParseFailure("PROVIDER_EMPTY", detail="empty string")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseFailure("PROVIDER_INVALID_JSON", detail=str(exc)) from exc
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise ParseFailure("PROVIDER_INVALID_TYPE", detail=type(raw).__name__)

    if not isinstance(payload, dict):
        raise ParseFailure("PROVIDER_INVALID_JSON", detail="root must be object")

    status = str(payload.get("provider_status") or PROVIDER_OK).upper()
    if status not in PROVIDER_STATUSES:
        raise ParseFailure("PROVIDER_STATUS_UNKNOWN", detail=status)
    if status in {PROVIDER_FAILED, PROVIDER_TIMEOUT, PROVIDER_INVALID_JSON}:
        raise ParseFailure(f"PROVIDER_{status}", detail=status)

    return normalize_inputs(payload)


def normalize_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate required inputs. Missing fields never default to ALLOW."""
    missing = [k for k in REQUIRED_INPUT_KEYS if k not in payload]
    if missing:
        raise ParseFailure("MISSING_INPUTS", detail=",".join(missing))

    out: dict[str, Any] = {
        "provider_status": str(payload["provider_status"]).upper(),
    }
    if out["provider_status"] not in PROVIDER_STATUSES:
        raise ParseFailure("PROVIDER_STATUS_UNKNOWN", detail=out["provider_status"])
    if out["provider_status"] != PROVIDER_OK:
        raise ParseFailure(f"PROVIDER_{out['provider_status']}", detail=out["provider_status"])

    for key in AGREEMENT_CHANNELS:
        out[key] = _as_unit_float(payload[key], field=key)

    out["calibration_reliability"] = _as_unit_float(
        payload["calibration_reliability"], field="calibration_reliability"
    )
    out["similarity_coverage"] = _as_unit_float(
        payload["similarity_coverage"], field="similarity_coverage"
    )
    out["prediction_interval_width"] = _as_unit_float(
        payload["prediction_interval_width"], field="prediction_interval_width"
    )
    out["data_freshness_sec"] = _as_nonneg_float(
        payload["data_freshness_sec"], field="data_freshness_sec"
    )
    out["stated_confidence"] = _as_unit_float(
        payload["stated_confidence"], field="stated_confidence"
    )

    # Optional metadata — never used to upgrade severity downward.
    out["symbol"] = str(payload.get("symbol") or "UNKNOWN")
    out["case_id"] = str(payload.get("case_id") or "")
    out["notes"] = str(payload.get("notes") or "")
    return out
