"""Composed PostgreSQL health/readiness helpers."""
from __future__ import annotations

from typing import Any

from backend.nexus_persistence_pg.migrate import MigrationRunner
from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig


def postgres_health(config: PostgresRuntimeConfig | None = None) -> dict[str, Any]:
    cfg = config or PostgresRuntimeConfig.from_env()
    # Do not call cfg.health() here: enabled configs delegate back to this
    # function. Construct the non-sensitive health envelope directly.
    base: dict[str, Any] = {
        "status": "CONNECTING",
        "configured": cfg.database_url is not None,
        "runtime_enabled": cfg.enabled,
        "evidence_mirror_enabled": cfg.evidence_mirror_enabled,
        "connected": False,
        "live_shadow_writer_enabled": False,
    }
    if not cfg.enabled or not cfg.database_url:
        base["db_ready"] = False
        return base
    pool = PostgresPool(cfg.database_url)
    try:
        pool.open()
        ready = pool.readiness()
        base.update(
            {
                "status": "READY" if ready.get("ready", False) else "UNAVAILABLE",
                "connected": ready.get("ready", False),
                "db_ready": ready.get("ready", False),
                "readiness_reason": ready.get("reason"),
            }
        )
        if ready.get("ready"):
            runner = MigrationRunner()
            base["migration_catalog_valid"] = runner.validate()["ok"]
    except Exception as exc:  # noqa: BLE001
        base["status"] = "UNAVAILABLE"
        base["connected"] = False
        base["db_ready"] = False
        base["readiness_reason"] = f"{type(exc).__name__}"
    finally:
        pool.close()
    return base
