"""Local analytics event store — not a production customer database."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AnalyticsEvent:
    event_name: str
    subject_hash: str
    props: dict[str, Any]
    recorded_at: str


@dataclass
class LocalAnalyticsStore:
    """In-memory / optional file-backed local store. Never a production DB."""

    production_customer_database: bool = False
    events: list[AnalyticsEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.production_customer_database:
            from backend.nexus_public_product_analytics.hard_bans import (
                refuse_production_customer_db,
            )

            refuse_production_customer_db()

    def append(
        self,
        *,
        event_name: str,
        subject_hash: str,
        props: dict[str, Any] | None = None,
    ) -> AnalyticsEvent:
        ev = AnalyticsEvent(
            event_name=event_name,
            subject_hash=subject_hash,
            props=dict(props or {}),
            recorded_at=_utcnow(),
        )
        self.events.append(ev)
        return ev

    def clear(self) -> None:
        self.events.clear()

    def as_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "event_name": e.event_name,
                "subject_hash": e.subject_hash,
                "props": dict(e.props),
                "recorded_at": e.recorded_at,
            }
            for e in self.events
        ]
