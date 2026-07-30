"""Typed field envelope — never fake 0/[] as successful reads."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.nexus_control_plane import ALLOWED_DATA_STATUSES, DATA_STATUS_MISSING, DATA_STATUS_UNKNOWN


@dataclass
class FieldEnvelope:
    value: Any
    source_service: str
    source_timestamp: float | None
    freshness_sec: float | None
    data_status: str
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        status = self.data_status if self.data_status in ALLOWED_DATA_STATUSES else DATA_STATUS_UNKNOWN
        return {
            "value": self.value,
            "source_service": self.source_service,
            "source_timestamp": self.source_timestamp,
            "freshness_sec": self.freshness_sec,
            "data_status": status,
            "evidence_ref": self.evidence_ref,
        }


def envelope(
    value: Any,
    *,
    source_service: str,
    source_timestamp: float | None = None,
    data_status: str,
    evidence_ref: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    ts = source_timestamp
    freshness = None
    if ts is not None:
        freshness = max(0.0, (now or time.time()) - float(ts))
    return FieldEnvelope(
        value=value,
        source_service=source_service,
        source_timestamp=ts,
        freshness_sec=freshness,
        data_status=data_status,
        evidence_ref=evidence_ref,
    ).to_dict()


def missing(source_service: str, *, evidence_ref: str = "") -> dict[str, Any]:
    return envelope(
        None,
        source_service=source_service,
        source_timestamp=None,
        data_status=DATA_STATUS_MISSING,
        evidence_ref=evidence_ref,
    )
