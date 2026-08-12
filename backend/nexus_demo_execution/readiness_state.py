"""Shared readiness state helpers (canonical SOT updates).

Not part of frozen H3 trading semantics — readiness/reporting only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOT_JSON = ROOT / "artifacts" / "readiness" / "NEXUS_READINESS_SOT.json"
SOT_MD = ROOT / "docs" / "04_readiness" / "NEXUS_READINESS_SOT.md"


def load_sot() -> dict[str, Any]:
    if not SOT_JSON.is_file():
        raise FileNotFoundError(SOT_JSON)
    return json.loads(SOT_JSON.read_text(encoding="utf-8"))


def save_sot(data: dict[str, Any]) -> None:
    data = dict(data)
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    SOT_JSON.parent.mkdir(parents=True, exist_ok=True)
    SOT_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def patch_sot(**fields: Any) -> dict[str, Any]:
    data = load_sot()
    data.update(fields)
    save_sot(data)
    return data
