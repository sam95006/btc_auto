"""NEXUS Phase 6 Gate B — Storage Discovery.

Checks only the *presence* of environment variable names (never their values
or database URLs/passwords).  Returns a recommended storage mode without
exposing any credentials.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_POSTGRES = "postgres"
MODE_SQLITE_PERSISTENT = "sqlite_persistent"
MODE_SQLITE_EPHEMERAL = "sqlite_ephemeral"
MODE_MEMORY = "memory"

_CHECKED_ENV_NAMES = (
    "NEXUS_RESEARCH_DATABASE_URL",
    "DATABASE_URL",
    "NEXUS_DATA_DIR",
    "PGHOST",
    "POSTGRES_URL",
    "MYSQL_URL",
)


def discover_storage() -> dict[str, Any]:
    """Return a storage discovery report.

    Inspects only whether env variable names are set (True/False).
    The actual value of every env var is discarded immediately after
    the boolean check — it is never stored, logged, or returned.
    """
    ts = int(time.time() * 1000)

    # ── env-name presence checks (values intentionally discarded) ────────────
    def _has(name: str) -> bool:
        return bool(os.getenv(name, "").strip())

    has_research_db_url = _has("NEXUS_RESEARCH_DATABASE_URL")
    has_database_url    = _has("DATABASE_URL")
    has_data_dir        = _has("NEXUS_DATA_DIR")
    has_pghost          = _has("PGHOST")
    has_postgres_url    = _has("POSTGRES_URL")
    has_mysql_url       = _has("MYSQL_URL")
    has_storage_mode    = _has("NEXUS_RESEARCH_STORAGE_MODE")

    postgres_env_present = (
        has_research_db_url or has_database_url or has_pghost or has_postgres_url
    )

    # ── trading.db isolation check ────────────────────────────────────────────
    trading_db_exists  = False
    trading_db_path: str | None = None
    try:
        from backend.core.data_paths import resolve_runtime_db_path  # type: ignore
        tdb_raw = resolve_runtime_db_path()
        if tdb_raw:
            tdb = Path(str(tdb_raw))
            if tdb.exists():
                trading_db_exists = True
                trading_db_path = str(tdb)
    except Exception:  # noqa: BLE001
        pass

    # ── NEXUS_DATA_DIR writability ────────────────────────────────────────────
    data_dir_writable  = False
    data_dir_path: str | None = None
    volume_confirmed   = False

    if has_data_dir:
        raw_dir = os.getenv("NEXUS_DATA_DIR", "").strip()
        if raw_dir:
            data_dir_path = raw_dir
            try:
                p = Path(raw_dir)
                p.mkdir(parents=True, exist_ok=True)
                probe = p / ".nexus_write_probe"
                probe.write_text("probe", encoding="utf-8")
                probe.unlink()
                data_dir_writable = True
                # Volume is confirmed only when a sentinel file is present.
                # The sentinel must be placed by the operator/deployment provisioner
                # to attest that the directory is backed by a durable volume.
                sentinel = p / ".nexus_volume_confirmed"
                volume_confirmed = sentinel.exists()
            except Exception:  # noqa: BLE001
                data_dir_writable = False

    # ── Recommended mode ──────────────────────────────────────────────────────
    storage_mode_override = os.getenv("NEXUS_RESEARCH_STORAGE_MODE", "").strip().lower()

    if storage_mode_override == "postgres":
        recommended_mode = MODE_POSTGRES if postgres_env_present else MODE_MEMORY
    elif storage_mode_override == "sqlite":
        if data_dir_writable and volume_confirmed:
            recommended_mode = MODE_SQLITE_PERSISTENT
        elif data_dir_writable:
            # Writable dir but volume persistence not confirmed → NOT durable
            recommended_mode = MODE_SQLITE_EPHEMERAL
        else:
            recommended_mode = MODE_MEMORY
    elif storage_mode_override == "memory":
        recommended_mode = MODE_MEMORY
    else:
        # auto — pick best available
        if postgres_env_present:
            recommended_mode = MODE_POSTGRES
        elif data_dir_writable and volume_confirmed:
            recommended_mode = MODE_SQLITE_PERSISTENT
        elif data_dir_writable:
            recommended_mode = MODE_SQLITE_EPHEMERAL
        else:
            recommended_mode = MODE_MEMORY

    durable_claim = recommended_mode in (MODE_POSTGRES, MODE_SQLITE_PERSISTENT)
    production_persistence_available = durable_claim

    return {
        "discoveredAt": ts,
        "envPresence": {
            "NEXUS_RESEARCH_DATABASE_URL": has_research_db_url,
            "DATABASE_URL": has_database_url,
            "NEXUS_DATA_DIR": has_data_dir,
            "PGHOST": has_pghost,
            "POSTGRES_URL": has_postgres_url,
            "MYSQL_URL": has_mysql_url,
            "NEXUS_RESEARCH_STORAGE_MODE": has_storage_mode,
        },
        "postgresEnvPresent": postgres_env_present,
        "dataDirWritable": data_dir_writable,
        "dataDirPath": data_dir_path,
        "volumeConfirmed": volume_confirmed,
        "tradingDbExists": trading_db_exists,
        "tradingDbPath": trading_db_path,
        "researchIsolationRequired": True,
        "recommendedMode": recommended_mode,
        "durableClaim": durable_claim,
        "productionPersistenceAvailable": production_persistence_available,
        "postgresDriverPending": True,
    }
