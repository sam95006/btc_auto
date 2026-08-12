"""Manifest seal for V17-B Bronze lake."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_bronze_immutable_raw_lake.constants import (
    ARTIFACT_REL,
    BRONZE_REQUIRED_FIELDS,
    HARD_BAN_FLAGS,
    HARD_BANS,
    SCHEMA_MANIFEST,
    SCHEMA_VERSION,
)
from backend.nexus_bronze_immutable_raw_lake.hashing import sha_obj, utc_now_iso
from backend.nexus_bronze_immutable_raw_lake.lake import BronzeLake


def build_manifest_document(lake: BronzeLake, *, inventory: dict[str, Any]) -> dict[str, Any]:
    rows = lake.list_manifest()
    ingested = [r for r in rows if r.get("status") != "QUARANTINED"]
    quarantined = [r for r in rows if r.get("status") == "QUARANTINED"]
    doc = {
        "schema": SCHEMA_MANIFEST,
        "schema_version": SCHEMA_VERSION,
        "built_at": utc_now_iso(),
        "lake_root": str(lake.root).replace("\\", "/"),
        "disk_usage_bytes": lake.disk_usage_bytes(),
        "max_disk_bytes": lake.max_disk_bytes,
        "bounded_disk": True,
        "append_only": True,
        "utc_only": True,
        "required_fields": list(BRONZE_REQUIRED_FIELDS),
        "entry_count": len(ingested),
        "quarantine_count": len(quarantined),
        "entries": rows,
        "resume_checkpoint": lake.read_checkpoint(),
        "inventory": inventory,
        "hard_bans": list(HARD_BANS),
        "hard_ban_flags": dict(HARD_BAN_FLAGS),
        "claims_15y_history_downloaded": False,
        "data_classification": "FIXTURE_AND_BOUNDED_OFFICIAL_SAMPLE_ONLY",
    }
    doc["manifest_digest"] = sha_obj({k: v for k, v in doc.items() if k != "manifest_digest"})
    return doc


def write_manifest_artifact(root: Path, lake: BronzeLake, *, inventory: dict[str, Any]) -> Path:
    art = root / ARTIFACT_REL
    art.mkdir(parents=True, exist_ok=True)
    doc = build_manifest_document(lake, inventory=inventory)
    path = art / "bronze_manifest.json"
    payload = json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path
