"""Checksum replay with open-tail vs corruption distinction."""
from __future__ import annotations

import gzip
import hashlib
import zlib
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replay_gzip_sha256(path: Path) -> dict[str, Any]:
    """Replay uncompressed content checksum; classify gzip EOF as truncated open tail candidate."""
    path = Path(path)
    if not path.is_file():
        return {
            "path": str(path),
            "replayed_checksum": None,
            "integrity_status": "MISSING",
            "truncated_tail": False,
            "partial_recoverable": False,
            "partial_line_count": 0,
            "error": "file_missing",
        }

    h = hashlib.sha256()
    try:
        with gzip.open(path, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 256)
                if not chunk:
                    break
                h.update(chunk)
        return {
            "path": str(path),
            "replayed_checksum": h.hexdigest(),
            "integrity_status": "OK",
            "truncated_tail": False,
            "partial_recoverable": True,
            "partial_line_count": None,
            "error": None,
        }
    except EOFError as exc:
        partial = _partial_decompress(path)
        return {
            "path": str(path),
            "replayed_checksum": None,
            "integrity_status": "TRUNCATED_OR_INCOMPLETE",
            "truncated_tail": True,
            "partial_recoverable": partial["line_count"] > 0,
            "partial_line_count": partial["line_count"],
            "partial_sha256": partial.get("sha256"),
            "error": f"EOFError:{exc}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "path": str(path),
            "replayed_checksum": None,
            "integrity_status": "READ_FAILED",
            "truncated_tail": False,
            "partial_recoverable": False,
            "partial_line_count": 0,
            "error": f"{type(exc).__name__}:{exc}",
        }


def _partial_decompress(path: Path) -> dict[str, Any]:
    """Best-effort partial gzip decompress for forensics (never writes repaired bytes)."""
    data = path.read_bytes()
    try:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        out = d.decompress(data)
        try:
            out += d.flush()
        except Exception:  # noqa: BLE001
            pass
        return {"line_count": out.count(b"\n"), "sha256": sha256_bytes(out) if out else None}
    except Exception:  # noqa: BLE001
        return {"line_count": 0, "sha256": None}


def compare_checksum(expected: str | None, replayed: str | None) -> dict[str, Any]:
    if not expected:
        return {"checksum_match": None, "integrity_status": None}
    if not replayed:
        return {"checksum_match": False, "integrity_status": "CHECKSUM_UNAVAILABLE"}
    match = expected == replayed
    return {
        "checksum_match": match,
        "integrity_status": "OK" if match else "CHECKSUM_MISMATCH",
    }
