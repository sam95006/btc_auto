"""Checkpoint persistence for Founder-private control plane (local only)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


SECRET_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "password",
        "token",
        "private_key",
        "authorization",
        "bybit_api_key",
        "bybit_api_secret",
    }
)


def sanitize_checkpoint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip secret-like keys recursively. Fail-closed redaction."""

    def _clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if str(k).lower() in SECRET_KEYS or "secret" in str(k).lower() or "api_key" in str(k).lower():
                    out[k] = "[REDACTED]"
                else:
                    out[k] = _clean(v)
            return out
        if isinstance(obj, list):
            return [_clean(x) for x in obj]
        return obj

    return _clean(payload)


class CheckpointStore:
    """Atomic JSON checkpoint writer under a local private root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._seq = 0

    def save(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._seq += 1
        cleaned = sanitize_checkpoint_payload(dict(payload))
        cleaned["checkpoint_seq"] = self._seq
        cleaned["checkpoint_at"] = _utc()
        cleaned["run_id"] = run_id
        text = json.dumps(cleaned, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        digest = _sha(text)
        cleaned["checkpoint_sha256"] = digest
        text = json.dumps(cleaned, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        path = self.root / f"{run_id}.checkpoint.{self._seq:04d}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        latest = self.root / f"{run_id}.checkpoint.latest.json"
        latest.write_text(text, encoding="utf-8")
        return {
            "checkpoint_id": f"{run_id}:{self._seq:04d}",
            "path": str(path),
            "sha256": digest,
            "seq": self._seq,
            "created_at": cleaned["checkpoint_at"],
        }

    def load_latest(self, run_id: str) -> dict[str, Any] | None:
        latest = self.root / f"{run_id}.checkpoint.latest.json"
        if not latest.exists():
            return None
        try:
            return json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
