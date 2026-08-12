"""Shared helpers for V14-A capture supervisor (no silent fallbacks)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_hour_key(dt: datetime | None = None) -> str:
    d = dt or utc_now()
    return d.strftime("%Y%m%d_%H")


def parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_json(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"status": "MISSING", "path": str(path), "silent_fallback": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "UNREADABLE",
            "path": str(path),
            "reason": f"{type(exc).__name__}:{exc}",
            "silent_fallback": False,
        }
    if not isinstance(data, dict):
        return {
            "status": "INVALID_TYPE",
            "path": str(path),
            "reason": f"expected_object_got_{type(data).__name__}",
            "silent_fallback": False,
        }
    out = dict(data)
    out["status"] = "OK"
    out["_path"] = str(path)
    return out


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def severity_rank(level: str) -> int:
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    return order.get(str(level).upper(), 99)


def finding(
    *,
    code: str,
    severity: str,
    summary: str,
    evidence: dict[str, Any] | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity.upper(),
        "summary": summary,
        "evidence": evidence or {},
        "recommendation": recommendation,
        "observed_at": utc_stamp(),
    }
