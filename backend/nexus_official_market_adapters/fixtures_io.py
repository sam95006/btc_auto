"""Fixture loading helpers for V18-A adapters."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"


@lru_cache(maxsize=64)
def load_fixture(provider: str, name: str) -> dict[str, Any] | list[Any]:
    path = FIXTURES_ROOT / provider / name
    if not path.is_file():
        raise FileNotFoundError(f"missing fixture: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def fixture_path(provider: str, name: str) -> Path:
    return FIXTURES_ROOT / provider / name


__all__ = ["load_fixture", "fixture_path", "FIXTURES_ROOT"]
