"""Optional PostgreSQL runtime boundary.

This module intentionally does not import a driver or open a database connection
until an operator provides a PostgreSQL URL and calls an integration adapter.
Shadow JSONL evidence remains the live source of record.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol


class EvidenceExecutor(Protocol):
    """Minimal DB boundary suitable for psycopg/async adapter implementations."""

    def execute(self, statement: str, params: tuple[Any, ...]) -> Any: ...


def _json_payload(value: Any) -> Any:
    """Adapt JSON payloads for psycopg3 while preserving fake-executor tests."""
    try:
        from psycopg.types.json import Json

        return Json(value)
    except ImportError:
        return value


@dataclass(frozen=True)
class PostgresRuntimeConfig:
    database_url: str | None
    enabled: bool
    evidence_mirror_enabled: bool

    @classmethod
    def from_env(cls) -> "PostgresRuntimeConfig":
        # DATABASE_URL is the Zeabur-managed backend secret convention;
        # NEXUS_POSTGRES_URL remains the explicit local/test override.
        url = (
            (os.getenv("NEXUS_POSTGRES_URL") or os.getenv("DATABASE_URL") or "").strip()
            or None
        )
        enabled = (os.getenv("NEXUS_PG_RUNTIME_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        mirror = (os.getenv("NEXUS_PG_EVIDENCE_MIRROR_ENABLED") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if enabled and not url:
            raise ValueError("NEXUS_PG_RUNTIME_ENABLED requires NEXUS_POSTGRES_URL")
        if mirror and not enabled:
            raise ValueError("NEXUS_PG_EVIDENCE_MIRROR_ENABLED requires NEXUS_PG_RUNTIME_ENABLED")
        if mirror and not url:
            raise ValueError("NEXUS_PG_EVIDENCE_MIRROR_ENABLED requires NEXUS_POSTGRES_URL")
        if url and not (url.startswith("postgresql://") or url.startswith("postgres://")):
            raise ValueError("NEXUS_POSTGRES_URL must use a PostgreSQL URL")
        return cls(database_url=url, enabled=enabled, evidence_mirror_enabled=mirror)

    def health(self) -> dict[str, Any]:
        """Configuration health; connectivity requires explicit pool open."""
        from backend.nexus_persistence_pg.health import postgres_health

        if not self.database_url:
            return {
                "status": "NOT_CONFIGURED",
                "configured": False,
                "runtime_enabled": self.enabled,
                "evidence_mirror_enabled": self.evidence_mirror_enabled,
                "connected": False,
                "live_shadow_writer_enabled": False,
            }
        if not self.enabled:
            return {
                "status": "DISABLED",
                "configured": True,
                "runtime_enabled": False,
                "evidence_mirror_enabled": self.evidence_mirror_enabled,
                "connected": False,
                "live_shadow_writer_enabled": False,
            }
        return postgres_health(self)


@dataclass
class EvidenceDbWriter:
    """Explicit opt-in writer for a future DB mirror; never mutates Shadow policy."""

    executor: EvidenceExecutor

    def append_event(self, event: dict[str, Any]) -> None:
        required = ("campaign_id", "stream_name", "content_sha256", "payload_json")
        missing = [key for key in required if event.get(key) is None]
        if missing:
            raise ValueError(f"runtime_evidence_missing:{','.join(missing)}")
        self.executor.execute(
            """
            INSERT INTO nexus.runtime_evidence_events
              (campaign_id, stream_name, event_time_ms, symbol, decision_id,
               candidate_id, position_id, lifecycle_id, cycle_index,
               payload_json, content_sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (campaign_id, stream_name, content_sha256) DO NOTHING
            """,
            (
                event["campaign_id"],
                event["stream_name"],
                event.get("event_time_ms"),
                event.get("symbol"),
                event.get("decision_id"),
                event.get("candidate_id"),
                event.get("position_id"),
                event.get("lifecycle_id"),
                event.get("cycle_index"),
                _json_payload(event["payload_json"]),
                event["content_sha256"],
            ),
        )
