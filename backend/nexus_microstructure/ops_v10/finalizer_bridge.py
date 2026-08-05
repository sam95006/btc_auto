"""Finalizer integration — read existing finalize artifacts; never start Event Study."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.ops_v10.constants import (
    DEFAULT_PREVIOUS_CAMPAIGN_ID,
    DEFAULT_REAL_FINALIZER_ARTIFACT_DIR,
    SCHEMA,
)
from backend.nexus_microstructure.ops_v10.integrity_scoring import score_campaign_integrity


class FinalizerIntegrationV10:
    """Bridge to Campaign Finalizer V1 immutable packages (read-only integration)."""

    def __init__(
        self,
        repo_root: Path,
        *,
        artifact_dir: Path | None = None,
        campaign_id: str = DEFAULT_PREVIOUS_CAMPAIGN_ID,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.campaign_id = campaign_id
        self.artifact_dir = Path(artifact_dir) if artifact_dir else (
            self.repo_root / DEFAULT_REAL_FINALIZER_ARTIFACT_DIR
        )

    def _load(self, name: str) -> dict[str, Any] | None:
        path = self.artifact_dir / name
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def load_package(self) -> dict[str, Any]:
        status = self._load("finalizer_status.json") or {}
        readiness = self._load("event_study_readiness.json") or {
            "event_study_readiness_status": "NOT_READY",
            "event_study_real_execution": False,
        }
        report = self._load("campaign_finalize_report.json")
        # Hard invariant: ops lane must never elevate readiness.
        readiness_status = readiness.get("event_study_readiness_status") or "NOT_READY"
        if readiness_status != "NOT_READY":
            readiness = {
                **readiness,
                "event_study_readiness_status": "NOT_READY",
                "ops_v10_forced_not_ready": True,
                "prior_status": readiness_status,
            }
        integrity = score_campaign_integrity(finalizer_status=status)
        finalized = bool(status) and status.get("campaign_id") == self.campaign_id
        # A finalize package existing counts as finalized for gate purposes even if FAIL.
        package_present = (self.artifact_dir / "finalizer_status.json").is_file()
        return {
            "schema": f"{SCHEMA}_finalizer_integration",
            "campaign_id": self.campaign_id,
            "artifact_dir": str(self.artifact_dir),
            "package_present": package_present,
            "previous_campaign_finalized": package_present and finalized,
            "finalizer_status": status,
            "event_study_readiness": readiness,
            "event_study_readiness_status": "NOT_READY",
            "event_study_real_execution": False,
            "integrity_score": integrity,
            "campaign_finalize_report_present": report is not None,
            "Microstructure_Finalizer_status": status.get("Microstructure_Finalizer_status"),
            "clean_campaign_finalization": status.get("clean_campaign_finalization"),
            "live_campaign_interfered": False,
            "new_strategy_generated_count": 0,
        }

    def import_into_registry(self, registry: Any) -> dict[str, Any]:
        package = self.load_package()
        if not package["package_present"]:
            return package
        if registry.get(self.campaign_id) is None:
            registry.register_campaign(self.campaign_id)
        status = package.get("finalizer_status") or {}
        registry.mark_finalized(
            self.campaign_id,
            finalizer_status=str(status.get("Microstructure_Finalizer_status") or "UNKNOWN"),
            integrity_status=str(status.get("integrity_status") or "UNKNOWN"),
            artifact_dir=str(self.artifact_dir),
        )
        resume_meta = (status.get("campaign_resume_metadata") or {})
        if resume_meta:
            registry.set_resume_checkpoint(self.campaign_id, resume_meta)
        return package
