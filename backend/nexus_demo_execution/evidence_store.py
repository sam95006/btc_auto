"""Evidence manifest helpers (canonical evidence index).

Readiness/audit only — does not alter trading or Cost Gate logic.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "artifacts" / "readiness" / "NEXUS_EVIDENCE_MANIFEST.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest() -> dict[str, Any]:
    if not MANIFEST.is_file():
        return {"schema_version": "nexus_evidence_manifest_v1", "entries": []}
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def save_manifest(data: dict[str, Any]) -> None:
    data = dict(data)
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def upsert_entry(entry: dict[str, Any]) -> dict[str, Any]:
    man = load_manifest()
    entries = list(man.get("entries") or [])
    eid = entry.get("evidence_id")
    replaced = False
    for i, e in enumerate(entries):
        if e.get("evidence_id") == eid:
            entries[i] = entry
            replaced = True
            break
    if not replaced:
        entries.append(entry)
    man["entries"] = entries
    save_manifest(man)
    return man


def orphan_count() -> int:
    man = load_manifest()
    n = 0
    for e in man.get("entries") or []:
        if e.get("status") == "SOURCE_MISSING":
            continue
        path = e.get("path")
        if path and not (ROOT / path).is_file():
            n += 1
    return n
