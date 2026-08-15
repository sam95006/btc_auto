"""Public-safe V1 product event bridge over the shared realtime transport."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.nexus_event_contract import EVENT_TYPES, event_envelope
from backend.nexus_public_realtime_transport.stream_hub import PublicStreamHub

_PUBLIC_KIND_BY_EVENT_TYPE = {
    "runtime.health": "freshness_change",
    "market.observation": "availability",
    "opportunity.candidate": "decision_update",
    "decision.ai": "decision_update",
    "decision.risk": "decision_update",
    "shadow.position.open": "outcome_review",
    "shadow.position.close": "outcome_review",
    "alert.runtime": "thesis_alert",
}


class ProductEventRuntime:
    """Emits only read-model events and deduplicates source event IDs."""

    def __init__(self, hub: PublicStreamHub) -> None:
        self.hub = hub
        self._sequence = 0
        self._seen_event_ids: set[str] = set()

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported_product_event_type:{event_type}")
        if event_type not in _PUBLIC_KIND_BY_EVENT_TYPE:
            raise ValueError(f"event_type_not_public_read_model:{event_type}")
        stable_id = event_id or str(uuid.uuid4())
        if stable_id in self._seen_event_ids:
            return {"duplicate": True, "event_id": stable_id}

        self._sequence += 1
        occurred_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        envelope = event_envelope(
            event_id=stable_id,
            event_type=event_type,
            occurred_at=occurred_at,
            sequence=self._sequence,
            payload=payload,
        )
        self._seen_event_ids.add(stable_id)
        self.hub.publish(
            kind=_PUBLIC_KIND_BY_EVENT_TYPE[event_type],
            topic=f"public.product.{event_type.replace('.', '_')}",
            payload={
                "api_version": "v1",
                "event_contract": envelope,
                "event_hash": hashlib.sha256(
                    json.dumps(envelope, sort_keys=True).encode("utf-8")
                ).hexdigest(),
            },
        )
        return {"duplicate": False, "event": envelope}
