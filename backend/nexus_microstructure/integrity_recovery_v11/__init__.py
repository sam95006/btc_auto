"""V11 Microstructure Integrity Recovery — forensic RCA + durable writer/finalizer fixes.

Hard bans: no raw campaign partition mutation, no Event Study, no silent repair, no strategy gen.
"""
from __future__ import annotations

from backend.nexus_microstructure.integrity_recovery_v11.classify import (
    classify_campaign_partitions,
    discover_partitions_v11,
)
from backend.nexus_microstructure.integrity_recovery_v11.constants import (
    CLASSIFICATIONS,
    REFERENCE_CAMPAIGN_ID,
    SCHEMA,
)
from backend.nexus_microstructure.integrity_recovery_v11.linkage import audit_linkage_v11
from backend.nexus_microstructure.integrity_recovery_v11.orchestrator import (
    run_forensic_rca,
    run_integrity_recovery,
)
from backend.nexus_microstructure.integrity_recovery_v11.writer_v11 import (
    DurablePartitionWriterV11,
    PartitionIdentityConflict,
)

__all__ = [
    "SCHEMA",
    "CLASSIFICATIONS",
    "REFERENCE_CAMPAIGN_ID",
    "DurablePartitionWriterV11",
    "PartitionIdentityConflict",
    "discover_partitions_v11",
    "classify_campaign_partitions",
    "audit_linkage_v11",
    "run_forensic_rca",
    "run_integrity_recovery",
]
