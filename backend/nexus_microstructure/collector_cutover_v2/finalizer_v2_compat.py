"""Finalizer V2 compatibility bridge — read-only; never starts Event Study."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import (
    EVENT_STUDY_STATUS,
    REFERENCE_CAMPAIGN_ID,
    RETAINED_CLASSIFICATION_COUNTS,
    RETAINED_PRIMARY_CLASSIFICATION_COUNTS,
    SCHEMA,
)
from backend.nexus_microstructure.collector_cutover_v2.open_tail_seal import open_tail_seal_policy
from backend.nexus_microstructure.ops_v10.finalizer_bridge import FinalizerIntegrationV10


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FinalizerV2Compat:
    """Produce a Finalizer V2-compatible envelope from V1 artifacts + cutover policy.

    Does not mutate prior campaign bytes. Forces event_study=NOT_READY.
    """

    SCHEMA_V2 = "microstructure_campaign_finalizer_v2_compat"

    def __init__(self, repo_root: Path, *, campaign_id: str = REFERENCE_CAMPAIGN_ID) -> None:
        self.repo_root = Path(repo_root)
        self.campaign_id = campaign_id
        self.v1 = FinalizerIntegrationV10(repo_root, campaign_id=campaign_id)

    def build_envelope(
        self,
        *,
        cutover_writer_report: dict[str, Any] | None = None,
        linkage_audit: dict[str, Any] | None = None,
        storage_controller: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        v1_pkg = self.v1.load_package()
        seal = open_tail_seal_policy(
            prior_open_tail_count=RETAINED_CLASSIFICATION_COUNTS["EXPECTED_OPEN_TAIL"]
        )
        return {
            "schema": self.SCHEMA_V2,
            "compatible_with": ["microstructure_campaign_finalizer_v1", SCHEMA],
            "created_at": _utc(),
            "campaign_id": self.campaign_id,
            "v1_finalizer_integration": {
                "package_present": v1_pkg.get("package_present"),
                "previous_campaign_finalized": v1_pkg.get("previous_campaign_finalized"),
                "Microstructure_Finalizer_status": v1_pkg.get("Microstructure_Finalizer_status"),
                "artifact_dir": v1_pkg.get("artifact_dir"),
            },
            "retained_classifications": {
                "raw_modified": False,
                "classification_counts": dict(RETAINED_CLASSIFICATION_COUNTS),
                "primary_classification_counts": dict(RETAINED_PRIMARY_CLASSIFICATION_COUNTS),
            },
            "open_tail_seal_policy": seal,
            "cutover_writer": cutover_writer_report,
            "linkage_audit": linkage_audit,
            "storage_controller": storage_controller,
            "event_study_readiness_status": EVENT_STUDY_STATUS,
            "event_study_real_execution": False,
            "collector_cutover_required_features": {
                "exclusive_partition_ids": True,
                "atomic_manifest_seal": True,
                "open_tail_seal_policy": True,
                "persistent_clock_guard": True,
                "resume_safe_linkage": True,
                "automatic_safe_stop": True,
                "storage_controller": True,
            },
            "integrity_status": "NOT_PASS_PRIOR_OPEN_TAILS_RETAINED",
            "silent_repair_executed": False,
            "new_strategy_generated_count": 0,
        }

    def write_envelope(self, out_dir: Path, envelope: dict[str, Any]) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "finalizer_v2_compat_envelope.json"
        path.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        readiness = {
            "schema": "event_study_readiness_v1",
            "event_study_readiness_status": EVENT_STUDY_STATUS,
            "event_study_real_execution": False,
            "note": "Collector Cutover V2 must not start Event Study.",
            "created_at": _utc(),
        }
        (out_dir / "event_study_readiness.json").write_text(
            json.dumps(readiness, indent=2) + "\n", encoding="utf-8"
        )
        return path
