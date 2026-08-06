"""In-memory Data Source Registry with status filtering."""
from __future__ import annotations

from typing import Any, Iterable

from backend.nexus_data_source_registry.constants import (
    LANE,
    SCHEMA,
    SCHEMA_VERSION,
    SOURCE_STATUSES,
)
from backend.nexus_data_source_registry.fixtures import fixture_sources
from backend.nexus_data_source_registry.schema import (
    validate_registry_document,
    validate_source_record,
)


class DataSourceRegistryError(ValueError):
    """Fail-closed registry mutation / load error."""


class DataSourceRegistry:
    """Machine-readable registry of data sources + license posture."""

    def __init__(self, sources: Iterable[dict[str, Any]] | None = None) -> None:
        self._by_id: dict[str, dict[str, Any]] = {}
        if sources is not None:
            for src in sources:
                self.register(src)

    @classmethod
    def from_fixtures(cls) -> "DataSourceRegistry":
        return cls(fixture_sources())

    def register(self, source: dict[str, Any]) -> dict[str, Any]:
        errors = validate_source_record(source)
        if errors:
            raise DataSourceRegistryError(";".join(errors))
        sid = str(source["source_id"])
        if sid in self._by_id:
            raise DataSourceRegistryError(f"duplicate_source_id:{sid}")
        stored = dict(source)
        self._by_id[sid] = stored
        return stored

    def get(self, source_id: str) -> dict[str, Any] | None:
        src = self._by_id.get(source_id)
        return dict(src) if src else None

    def list_all(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self._by_id.values()]

    def list_by_status(self, status: str) -> list[dict[str, Any]]:
        if status not in SOURCE_STATUSES:
            raise DataSourceRegistryError(f"bad_status:{status}")
        return [dict(s) for s in self._by_id.values() if s.get("status") == status]

    def statuses_present(self) -> dict[str, int]:
        counts = {s: 0 for s in SOURCE_STATUSES}
        for src in self._by_id.values():
            st = src.get("status")
            if st in counts:
                counts[st] += 1
        return counts

    def to_document(self) -> dict[str, Any]:
        doc = {
            "schema": SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "lane": LANE,
            "source_count": len(self._by_id),
            "status_counts": self.statuses_present(),
            "sources": self.list_all(),
        }
        errors = validate_registry_document(doc)
        if errors:
            raise DataSourceRegistryError(";".join(errors))
        return doc

    def allows_training(self, source_id: str) -> bool:
        src = self._by_id.get(source_id)
        if not src:
            return False
        if src.get("status") in {
            "LICENSE_REVIEW_REQUIRED",
            "TRAINING_FORBIDDEN",
            "DEPRECATED",
            "UNAVAILABLE",
        }:
            return False
        return bool(src.get("training_allowed") is True)

    def allows_public_display(self, source_id: str) -> bool:
        src = self._by_id.get(source_id)
        if not src:
            return False
        if src.get("status") != "APPROVED_PUBLIC":
            return False
        if src.get("public_display_allowed") is False:
            return False
        return True

    def authorization_claimed(self, source_id: str) -> bool:
        src = self._by_id.get(source_id)
        if not src:
            return False
        if src.get("status") == "LICENSE_REVIEW_REQUIRED":
            return False
        return bool(src.get("authorization_claimed") is True)
