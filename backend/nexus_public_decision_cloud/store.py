"""Local/staging fixture store for Public Decision Cloud (read-only)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "staging_catalog.json"
_CACHE: dict[str, Any] | None = None


def fixture_path() -> Path:
    return _FIXTURE_PATH


def load_catalog(*, reload: bool = False) -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None and not reload:
        return deepcopy(_CACHE)
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("staging catalog must be an object")
    _CACHE = data
    return deepcopy(data)


def list_decisions() -> list[dict[str, Any]]:
    catalog = load_catalog()
    rows = catalog.get("decisions") or []
    return [deepcopy(r) for r in rows if isinstance(r, dict)]


def get_decision(decision_id: str) -> dict[str, Any] | None:
    for row in list_decisions():
        if str(row.get("decision_id")) == decision_id:
            return row
    return None
