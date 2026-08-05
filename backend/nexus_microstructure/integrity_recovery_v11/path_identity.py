"""Path / filename identity inference for partitions missing manifests."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HOUR_RE = re.compile(r"_(\d{8}_\d{2})_(\d+)\.jsonl(?:\.gz)?$")
_SESSION_FAM_RE = re.compile(
    r"^(?P<session>.+)_(?P<family>AGGRESSIVE_TRADE_FLOW|LIQUIDATION_EVENTS)_(?P<symbol>[A-Z0-9]+)_(?P<hour>\d{8}_\d{2})_(?P<seq>\d+)"
)


def partition_id_from_gz(path: Path) -> str:
    """Stable partition_id without trailing .gz; keep .jsonl stem for V1 compatibility."""
    name = path.name
    if name.endswith(".jsonl.gz"):
        return name[: -len(".gz")]
    return path.stem


def infer_identity_from_path(path: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Infer capture_session_id / family / symbol / UTC_hour / seq from path + filename.

    Layout expected: .../{FAMILY}/{SYMBOL}/{session}_{FAMILY}_{SYMBOL}_{YYYYMMDD_HH}_{seq}.jsonl.gz
    """
    manifest = manifest or {}
    path = Path(path)
    name = path.name
    if name.endswith(".jsonl.gz"):
        base = name[: -len(".jsonl.gz")]
    elif name.endswith(".jsonl"):
        base = name[: -len(".jsonl")]
    else:
        base = path.stem

    family = manifest.get("family") or (path.parent.parent.name if path.parent.parent else None)
    symbol = manifest.get("symbol") or path.parent.name
    session = manifest.get("capture_session_id")
    hour = manifest.get("UTC_hour")
    seq: int | None = None

    m = _SESSION_FAM_RE.match(base + ".jsonl") if not base.endswith(".jsonl") else _SESSION_FAM_RE.match(base)
    # Match against base without requiring .jsonl suffix
    m = _SESSION_FAM_RE.match(base)
    if m:
        session = session or m.group("session")
        family = family or m.group("family")
        symbol = symbol or m.group("symbol")
        hour = hour or m.group("hour")
        seq = int(m.group("seq"))
    else:
        hm = _HOUR_RE.search(name)
        if hm:
            hour = hour or hm.group(1)
            seq = int(hm.group(2))
        if family and f"_{family}_" in base:
            session = session or base.split(f"_{family}_")[0]

    return {
        "partition_id": manifest.get("partition_id") or partition_id_from_gz(path),
        "capture_session_id": session,
        "family": family,
        "symbol": symbol,
        "UTC_hour": hour,
        "partition_seq": seq,
        "path": str(path),
    }


def sort_key_for_partition(p: dict[str, Any]) -> tuple:
    """Chronological order within a linkage chain."""
    hour = str(p.get("UTC_hour") or "")
    seq = p.get("partition_seq")
    if seq is None:
        # fall back: trailing _N before .jsonl
        pid = str(p.get("partition_id") or "")
        m = re.search(r"_(\d+)(?:\.jsonl)?$", pid)
        seq = int(m.group(1)) if m else -1
    return (hour, int(seq), str(p.get("partition_id") or ""))
