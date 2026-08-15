"""Factory helpers for optional evidence mirror wiring."""
from __future__ import annotations

import os
from typing import Any

from backend.nexus_persistence_pg.evidence_db_mirror import EvidenceDbMirror
from backend.nexus_persistence_pg.evidence_mirror import EvidenceMirrorService
from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.runtime import EvidenceDbWriter, PostgresRuntimeConfig


def evidence_mirror_enabled() -> bool:
    return (os.getenv("NEXUS_PG_EVIDENCE_MIRROR_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def build_evidence_mirror_from_env(
    campaign_id: str,
    *,
    config: PostgresRuntimeConfig | None = None,
) -> EvidenceDbMirror | None:
    """Return mirror only when runtime + mirror flags and URL are all explicitly set."""
    cfg = config or PostgresRuntimeConfig.from_env()
    if not cfg.enabled or not cfg.database_url or not evidence_mirror_enabled():
        return None
    pool = PostgresPool(cfg.database_url)
    pool.open()
    service = EvidenceMirrorService(pool)
    writer = EvidenceDbWriter(pool)
    return EvidenceDbMirror(
        campaign_id=campaign_id,
        writer=writer,
        campaign_ensurer=service,
    )


def mirror_config_health() -> dict[str, Any]:
    cfg = PostgresRuntimeConfig.from_env()
    return {
        "runtime_enabled": cfg.enabled,
        "evidence_mirror_enabled": evidence_mirror_enabled(),
        "configured": cfg.database_url is not None,
        "live_shadow_writer_enabled": cfg.enabled and evidence_mirror_enabled(),
    }
