"""Phase 6.1 — process boot identity (no secrets).

Boot ID is generated once per process and persisted under the research data dir
so restart proofs can compare createdBootId vs currentBootId.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_BOOT: dict[str, Any] | None = None


def _research_root() -> Path | None:
    raw = (os.getenv("NEXUS_DATA_DIR") or "").strip()
    if not raw:
        return None
    return Path(raw) / "nexus-research"


def get_boot_identity() -> dict[str, Any]:
    """Return stable boot identity for this process."""
    global _BOOT
    with _LOCK:
        if _BOOT is not None:
            return dict(_BOOT)

        boot_id = str(uuid.uuid4())
        started_at = int(time.time() * 1000)
        deployment_id = (os.getenv("ZEABUR_DEPLOYMENT_ID") or os.getenv("ZEABUR_SERVICE_ID") or "").strip() or None
        identity = {
            "bootId": boot_id,
            "startedAt": started_at,
            "deploymentIdPresent": bool(deployment_id),
            # Never expose raw deployment IDs in public responses — only presence.
            "researchOnly": True,
        }

        root = _research_root()
        if root is not None:
            try:
                root.mkdir(parents=True, exist_ok=True)
                (root / "volume_probe").mkdir(parents=True, exist_ok=True)
                (root / "backups").mkdir(parents=True, exist_ok=True)
                (root / "exports").mkdir(parents=True, exist_ok=True)
                path = root / "current_boot.json"
                path.write_text(json.dumps(identity, ensure_ascii=False), encoding="utf-8")
                identity["bootRecordPathRedacted"] = str(path).replace(str(root.parent), "/data")
            except Exception:  # noqa: BLE001
                identity["bootRecordPathRedacted"] = None

        _BOOT = identity
        return dict(identity)


def research_data_dir() -> Path | None:
    """Return dedicated research directory under NEXUS_DATA_DIR, if configured."""
    root = _research_root()
    if root is None:
        return None
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / "volume_probe").mkdir(parents=True, exist_ok=True)
        (root / "backups").mkdir(parents=True, exist_ok=True)
        (root / "exports").mkdir(parents=True, exist_ok=True)
        return root
    except Exception:  # noqa: BLE001
        return None
