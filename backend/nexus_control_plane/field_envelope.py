"""Typed field envelope — never fake 0/[] as successful reads."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.nexus_control_plane import (
    ALLOWED_DATA_STATUSES,
    DATA_STATUS_MISSING,
    DATA_STATUS_UNKNOWN,
    SCHEMA_VERSION,
)


@dataclass
class FieldEnvelope:
    value: Any
    source_service: str
    source_role: str
    source_timestamp: float | None
    received_at: float
    freshness_seconds: float | None
    data_status: str
    evidence_ref: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        status = self.data_status if self.data_status in ALLOWED_DATA_STATUSES else DATA_STATUS_UNKNOWN
        return {
            "value": self.value,
            "source_service": self.source_service,
            "source_role": self.source_role,
            "source_timestamp": self.source_timestamp,
            "received_at": self.received_at,
            "freshness_seconds": self.freshness_seconds,
            # backward-compatible alias
            "freshness_sec": self.freshness_seconds,
            "data_status": status,
            "evidence_ref": self.evidence_ref,
            "schema_version": self.schema_version,
        }


def envelope(
    value: Any,
    *,
    source_service: str,
    source_role: str | None = None,
    source_timestamp: float | None = None,
    data_status: str,
    evidence_ref: str = "",
    now: float | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, Any]:
    received = now or time.time()
    ts = source_timestamp
    freshness = None
    if ts is not None:
        freshness = max(0.0, received - float(ts))
    return FieldEnvelope(
        value=value,
        source_service=source_service,
        source_role=source_role or source_service,
        source_timestamp=ts,
        received_at=received,
        freshness_seconds=freshness,
        data_status=data_status,
        evidence_ref=evidence_ref,
        schema_version=schema_version,
    ).to_dict()


def missing(
    source_service: str,
    *,
    source_role: str | None = None,
    evidence_ref: str = "",
) -> dict[str, Any]:
    return envelope(
        None,
        source_service=source_service,
        source_role=source_role,
        source_timestamp=None,
        data_status=DATA_STATUS_MISSING,
        evidence_ref=evidence_ref,
    )
