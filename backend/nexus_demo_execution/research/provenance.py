"""Market-data provenance helpers (manifest-oriented; no fake zeros)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "artifacts" / "readiness" / "MARKET_DATASET_MANIFEST.json"


def load_market_manifest() -> dict[str, Any]:
    if not MANIFEST.is_file():
        raise FileNotFoundError(MANIFEST)
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
