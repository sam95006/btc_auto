"""License binding gate — refuse unlicensed ingest."""
from __future__ import annotations

from typing import Any

from backend.nexus_data_source_registry.registry import DataSourceRegistry
from backend.nexus_incremental_backfill_live_ingest.hard_bans import (
    HardBanViolation,
    refuse_unlicensed_ingest,
)

# Statuses that may bind for ingest this round.
LICENSED_STATUSES: frozenset[str] = frozenset(
    {
        "APPROVED_PUBLIC",
        "APPROVED_INTERNAL_ONLY",
    }
)


class LicenseBindingError(HardBanViolation):
    pass


class LicenseGate:
    """Bind ingest to V17-A data source registry license posture."""

    def __init__(self, registry: DataSourceRegistry | None = None) -> None:
        self.registry = registry or DataSourceRegistry.from_fixtures()

    def assert_licensed(
        self,
        *,
        source_id: str,
        license_reference: str,
    ) -> dict[str, Any]:
        src = self.registry.get(source_id)
        if src is None:
            refuse_unlicensed_ingest()
            raise LicenseBindingError(f"unlicensed_unknown_source:{source_id}")
        status = str(src.get("status") or "")
        if status not in LICENSED_STATUSES:
            refuse_unlicensed_ingest()
            raise LicenseBindingError(f"unlicensed_status:{source_id}:{status}")
        if not license_reference or not str(license_reference).strip():
            refuse_unlicensed_ingest()
            raise LicenseBindingError(f"missing_license_reference:{source_id}")
        # Retention / training flags must be coherent for sample ingest.
        if src.get("retention_allowed") is False and status == "APPROVED_PUBLIC":
            # Still allow ephemeral live-read-only; caller classifies.
            pass
        return {
            "source_id": source_id,
            "status": status,
            "license_type": src.get("license_type"),
            "license_reference": license_reference,
            "redistribution_allowed": bool(src.get("redistribution_allowed")),
            "training_allowed": bool(src.get("training_allowed")),
            "retention_allowed": bool(src.get("retention_allowed")),
            "bound": True,
        }
