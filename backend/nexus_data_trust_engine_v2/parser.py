"""Input parsing for V17-F Data Trust Engine V2 (fail-closed)."""
from __future__ import annotations

from typing import Any

from backend.nexus_data_trust_engine_v2.constants import (
    INVERSE_SCORE_CHANNELS,
    LICENSE_STATUSES,
    QUALITY_SCORE_CHANNELS,
    REQUIRED_INPUT_KEYS,
)


class ParseFailure(Exception):
    """Raised when provider payload cannot be safely evaluated."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail or reason


def _clamp01(value: Any, field: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ParseFailure("INVALID_SCORE", f"{field}={value!r}") from exc
    if x != x:  # NaN
        raise ParseFailure("INVALID_SCORE", f"{field}=nan")
    if x < 0.0 or x > 1.0:
        raise ParseFailure("SCORE_OUT_OF_RANGE", f"{field}={x}")
    return x


def parse_trust_inputs(raw: Any) -> dict[str, Any]:
    """Normalize raw inputs. Missing/invalid → ParseFailure (caller maps to UNAVAILABLE)."""
    if raw is None:
        raise ParseFailure("NULL_PAYLOAD", "payload is None")
    if isinstance(raw, (bytes, bytearray)):
        raise ParseFailure("INVALID_JSON", "bytes payload unsupported")
    if isinstance(raw, str):
        raise ParseFailure("INVALID_JSON", "string payload must be pre-parsed object")
    if not isinstance(raw, dict):
        raise ParseFailure("INVALID_PAYLOAD_TYPE", f"type={type(raw).__name__}")

    missing = [k for k in REQUIRED_INPUT_KEYS if k not in raw]
    if missing:
        raise ParseFailure("MISSING_INPUTS", ",".join(missing))

    out: dict[str, Any] = {}
    for key in QUALITY_SCORE_CHANNELS:
        out[key] = _clamp01(raw[key], key)
    for key in INVERSE_SCORE_CHANNELS:
        out[key] = _clamp01(raw[key], key)

    license_status = str(raw["license_status"]).strip().upper()
    if license_status not in LICENSE_STATUSES:
        raise ParseFailure("INVALID_LICENSE_STATUS", license_status)
    out["license_status"] = license_status

    if "ai_confidence" in raw and raw["ai_confidence"] is not None:
        out["ai_confidence"] = _clamp01(raw["ai_confidence"], "ai_confidence")
    else:
        out["ai_confidence"] = None

    if "availability" in raw and raw["availability"] is not None:
        if not isinstance(raw["availability"], bool):
            raise ParseFailure("INVALID_AVAILABILITY", repr(raw["availability"]))
        out["availability"] = raw["availability"]
    else:
        out["availability"] = True

    for opt in ("case_id", "symbol", "source_id"):
        if opt in raw and raw[opt] is not None:
            out[opt] = str(raw[opt])
        else:
            out[opt] = None

    return out
