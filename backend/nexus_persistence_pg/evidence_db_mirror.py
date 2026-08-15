"""Best-effort inline evidence mirror — JSONL remains authoritative."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.nexus_persistence_pg.runtime import EvidenceDbWriter


class CampaignEnsurer(Protocol):
    def ensure_campaign(self, campaign_id: str, *, status: str = "mirror") -> None: ...


def canonical_content_sha256(record: dict[str, Any]) -> str:
    """Stable digest from persisted record payload (mirror boundary)."""
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class EvidenceDbMirror:
    """Optional mirror invoked after successful JSONL append; never blocks evidence."""

    campaign_id: str
    writer: EvidenceDbWriter
    campaign_ensurer: CampaignEnsurer | None = None
    mirror_errors_stream: bool = False
    mirrored_count: int = field(default=0, init=False)
    skipped_count: int = field(default=0, init=False)
    failure_count: int = field(default=0, init=False)
    last_error: str | None = field(default=None, init=False)
    _campaign_ready: bool = field(default=False, init=False)

    def mirror_record(self, stream_name: str, record: dict[str, Any]) -> None:
        if not self.mirror_errors_stream and stream_name == "errors.jsonl":
            self.skipped_count += 1
            return
        try:
            if not self._campaign_ready and self.campaign_ensurer is not None:
                self.campaign_ensurer.ensure_campaign(self.campaign_id)
                self._campaign_ready = True
            digest = canonical_content_sha256(record)
            self.writer.append_event(
                {
                    "campaign_id": self.campaign_id,
                    "stream_name": stream_name,
                    "event_time_ms": record.get("event_time_ms"),
                    "symbol": record.get("symbol"),
                    "decision_id": record.get("decision_id"),
                    "candidate_id": record.get("candidate_id"),
                    "position_id": record.get("position_id"),
                    "lifecycle_id": record.get("lifecycle_id"),
                    "cycle_index": record.get("cycle_index"),
                    "payload_json": record,
                    "content_sha256": digest,
                }
            )
            self.mirrored_count += 1
        except Exception as exc:  # noqa: BLE001 — mirror must never break JSONL path
            self.failure_count += 1
            self.last_error = str(exc)

    def status(self) -> dict[str, Any]:
        return {
            "mirrored_count": self.mirrored_count,
            "skipped_count": self.skipped_count,
            "failure_count": self.failure_count,
            "last_error": self.last_error,
            "campaign_ready": self._campaign_ready,
        }
