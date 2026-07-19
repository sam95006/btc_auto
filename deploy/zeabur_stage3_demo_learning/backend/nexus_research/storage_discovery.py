"""NEXUS Phase 6 / 6.1 — Storage Discovery.

Checks only the *presence* of environment variable names (never their values
or database URLs/passwords).  Returns a recommended storage mode without
exposing any credentials.

Durable claim / production_persistence_available require restart proof —
writable /data or operator PV attestation alone is NOT sufficient.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# ── Mode constants ────────────────────────────────────────────────────────────
MODE_POSTGRES = "postgres"
MODE_SQLITE_PERSISTENT = "sqlite_persistent"
MODE_SQLITE_VOLUME_PENDING_RESTART = "sqlite_volume_pending_restart_proof"
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


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def discover_storage() -> dict[str, Any]:
    """Return a storage discovery report (no secrets / no DSN values)."""
    ts = int(time.time() * 1000)

    def _has(name: str) -> bool:
        return bool(os.getenv(name, "").strip())

    has_research_db_url = _has("NEXUS_RESEARCH_DATABASE_URL")
    has_database_url = _has("DATABASE_URL")
    has_data_dir = _has("NEXUS_DATA_DIR")
    has_pghost = _has("PGHOST")
    has_postgres_url = _has("POSTGRES_URL")
    has_mysql_url = _has("MYSQL_URL")
    has_storage_mode = _has("NEXUS_RESEARCH_STORAGE_MODE")

    postgres_env_present = (
        has_research_db_url or has_database_url or has_pghost or has_postgres_url
    )

    trading_db_exists = False
    trading_db_path_redacted: str | None = None
    try:
        from backend.core.data_paths import resolve_runtime_db_path  # type: ignore

        tdb_raw = resolve_runtime_db_path()
        if tdb_raw:
            tdb = Path(str(tdb_raw))
            if tdb.exists():
                trading_db_exists = True
                p = str(tdb).replace("\\", "/")
                idx = p.find("/data/")
                trading_db_path_redacted = p[idx:] if idx >= 0 else "trading.db"
    except Exception:  # noqa: BLE001
        pass

    data_dir_writable = False
    data_dir_path_redacted: str | None = None
    volume_sentinel_present = False
    research_dir_writable = False
    research_db_path_redacted: str | None = None
    research_isolated = True

    if has_data_dir:
        raw_dir = os.getenv("NEXUS_DATA_DIR", "").strip()
        if raw_dir:
            normalized = raw_dir.replace("\\", "/").rstrip("/")
            is_data_mount = normalized == "/data" or normalized.endswith("/data")
            # Never return arbitrary host paths — only /data shape or opaque marker.
            data_dir_path_redacted = "/data" if is_data_mount else "<configured_data_dir>"
            try:
                p = Path(raw_dir)
                p.mkdir(parents=True, exist_ok=True)
                probe = p / ".nexus_write_probe"
                probe.write_text("probe", encoding="utf-8")
                probe.unlink()
                data_dir_writable = True
                # Sentinel is *additional* evidence only — not durable claim.
                volume_sentinel_present = (p / ".nexus_volume_confirmed").exists()

                research_root = p / "nexus-research"
                research_root.mkdir(parents=True, exist_ok=True)
                (research_root / "volume_probe").mkdir(parents=True, exist_ok=True)
                (research_root / "backups").mkdir(parents=True, exist_ok=True)
                (research_root / "exports").mkdir(parents=True, exist_ok=True)
                rprobe = research_root / ".nexus_write_probe"
                rprobe.write_text("probe", encoding="utf-8")
                rprobe.unlink()
                research_dir_writable = True
                research_db_path_redacted = (
                    "/data/nexus-research/nexus_research.db"
                    if is_data_mount
                    else "<configured_data_dir>/nexus-research/nexus_research.db"
                )

                # Isolation: research DB must not be trading.db
                if trading_db_path_redacted and "trading.db" in trading_db_path_redacted:
                    research_isolated = research_db_path_redacted != trading_db_path_redacted
            except Exception:  # noqa: BLE001
                data_dir_writable = False

    # Operator-attested Zeabur Persistent Volume (volume name `data` → /data).
    # Confirmed outside the app; does NOT equal restart durability proof.
    env_resource = _truthy("NEXUS_PERSISTENT_VOLUME_RESOURCE_CONFIRMED")
    mount_is_data = bool(
        data_dir_writable and data_dir_path_redacted == "/data"
    )
    persistent_volume_resource_confirmed = bool(env_resource or mount_is_data)
    persistent_volume_mount_confirmed = bool(mount_is_data)
    persistent_volume_path = "/data" if persistent_volume_mount_confirmed else None

    restart_proof_verified = False
    try:
        raw_dir = os.getenv("NEXUS_DATA_DIR", "").strip()
        if raw_dir:
            proof = Path(raw_dir) / "nexus-research" / "volume_probe" / ".restart_proof_verified"
            restart_proof_verified = proof.exists()
    except Exception:  # noqa: BLE001
        restart_proof_verified = False

    storage_mode_override = os.getenv("NEXUS_RESEARCH_STORAGE_MODE", "").strip().lower()

    if storage_mode_override == "postgres":
        recommended_mode = MODE_POSTGRES if postgres_env_present else MODE_MEMORY
    elif storage_mode_override == "sqlite":
        if data_dir_writable and restart_proof_verified:
            recommended_mode = MODE_SQLITE_PERSISTENT
        elif data_dir_writable and persistent_volume_resource_confirmed:
            recommended_mode = MODE_SQLITE_VOLUME_PENDING_RESTART
        elif data_dir_writable:
            recommended_mode = MODE_SQLITE_EPHEMERAL
        else:
            recommended_mode = MODE_MEMORY
    elif storage_mode_override == "memory":
        recommended_mode = MODE_MEMORY
    else:
        if postgres_env_present:
            recommended_mode = MODE_POSTGRES
        elif data_dir_writable and restart_proof_verified:
            recommended_mode = MODE_SQLITE_PERSISTENT
        elif data_dir_writable and persistent_volume_resource_confirmed:
            recommended_mode = MODE_SQLITE_VOLUME_PENDING_RESTART
        elif data_dir_writable:
            recommended_mode = MODE_SQLITE_EPHEMERAL
        else:
            recommended_mode = MODE_MEMORY

    # Durable claim ONLY after restart proof (or managed postgres when driver ready).
    durable_claim = recommended_mode == MODE_SQLITE_PERSISTENT or (
        recommended_mode == MODE_POSTGRES and False  # driver pending
    )
    production_persistence_available = bool(durable_claim and restart_proof_verified)

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
            "NEXUS_PERSISTENT_VOLUME_RESOURCE_CONFIRMED": _has(
                "NEXUS_PERSISTENT_VOLUME_RESOURCE_CONFIRMED"
            ),
        },
        "postgresEnvPresent": postgres_env_present,
        "managedPostgresAvailable": False,
        "researchDatabaseUrlPresent": has_research_db_url,
        "dataDirWritable": data_dir_writable,
        "dataDirPath": data_dir_path_redacted,
        "nexusDataDirPresent": has_data_dir,
        "nexusDataDirPathRedacted": data_dir_path_redacted,
        "researchDirWritable": research_dir_writable,
        "researchDatabasePath": research_db_path_redacted,
        "researchDatabasePathRedacted": research_db_path_redacted,
        "researchDatabaseIsolatedFromTradingDatabase": research_isolated,
        "volumeConfirmed": volume_sentinel_present,
        "volumeSentinelPresent": volume_sentinel_present,
        "persistentVolumeResourceConfirmed": persistent_volume_resource_confirmed,
        "persistentVolumeMountConfirmed": persistent_volume_mount_confirmed,
        "persistentVolumePath": persistent_volume_path,
        "restartProofVerified": restart_proof_verified,
        "tradingDbExists": trading_db_exists,
        "tradingDbPath": trading_db_path_redacted,
        "researchIsolationRequired": True,
        "recommendedMode": recommended_mode,
        "currentStorageClaim": recommended_mode,
        "durableClaim": durable_claim,
        "productionPersistenceAvailable": production_persistence_available,
        "manualZeaburActionRequired": not persistent_volume_resource_confirmed,
        "postgresDriverPending": True,
        "note": (
            "Sentinel / writable /data / operator PV attestation are not restart proof. "
            "productionPersistenceAvailable stays false until controlled restart recovery PASS."
        ),
    }
