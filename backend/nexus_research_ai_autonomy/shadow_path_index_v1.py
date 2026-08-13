"""Compact streaming index over path_records.jsonl — no full OHLC materialization.

Historical JSONL remains immutable evidence. Hot cycles use this index for counts/keys.
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from backend.nexus_research_ai_autonomy.shadow_signal_v1 import (
    HORIZON_LABELS,
    REQUIRED_HORIZONS_SEC,
    shadow_dir,
)

INDEX_SCHEMA = "v30_shadow_path_index_v1"
HORIZON_SECS = REQUIRED_HORIZONS_SEC


def path_index_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "shadow_path_index.json"


def path_records_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "path_records.jsonl"


def outcomes_path(campaign_root: Path) -> Path:
    return shadow_dir(campaign_root) / "shadow_outcomes.jsonl"


def iter_jsonl_dicts(path: Path) -> Iterator[dict[str, Any]]:
    """Stream JSONL line-by-line without Path.read_text() of the whole file."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _path_status(rec: dict[str, Any]) -> str:
    unavail = (
        rec.get("unavailable_reason") == "HISTORICAL_PATH_UNAVAILABLE"
        or rec.get("measurement_quality") == "HISTORICAL_PATH_UNAVAILABLE"
        or (
            not rec.get("bars")
            and rec.get("post_cost_hypothetical") is None
            and rec.get("MFE") is None
        )
    )
    return "UNAVAILABLE" if unavail else "VALID"


def empty_index() -> dict[str, Any]:
    return {
        "schema": INDEX_SCHEMA,
        "updated_at_ms": 0,
        "path_file_bytes": 0,
        "path_file_lines_scanned": 0,
        "path_record_rows": 0,
        "unique_path_keys": 0,
        "duplicate_path_record_rows": 0,
        "outcome_rows": 0,
        "unique_outcome_keys": 0,
        "duplicate_outcome_rows": 0,
        # key "signal_id|horizon_sec" -> VALID|UNAVAILABLE
        "keys": {},
        "valid_by_horizon": {HORIZON_LABELS[h]: 0 for h in HORIZON_SECS},
        "unavailable_by_horizon": {HORIZON_LABELS[h]: 0 for h in HORIZON_SECS},
        "signals_with_valid_horizon": {},  # sid -> list of horizon labels with VALID
        "fully_valid_signal_ids": [],
        "byte_offset": 0,  # for incremental append scan of path_records.jsonl
        "outcome_byte_offset": 0,
    }


def load_path_index(campaign_root: Path) -> dict[str, Any]:
    path = path_index_path(campaign_root)
    if not path.exists():
        return empty_index()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return empty_index()
        base = empty_index()
        base.update(raw)
        base["keys"] = dict(raw.get("keys") or {})
        base["signals_with_valid_horizon"] = dict(raw.get("signals_with_valid_horizon") or {})
        return base
    except Exception:  # noqa: BLE001
        return empty_index()


def save_path_index(campaign_root: Path, index: dict[str, Any]) -> None:
    d = shadow_dir(campaign_root)
    d.mkdir(parents=True, exist_ok=True)
    path = path_index_path(campaign_root)
    index = dict(index)
    index["schema"] = INDEX_SCHEMA
    index["updated_at_ms"] = int(time.time() * 1000)
    # Keep fully_valid list compact
    fully = [
        sid
        for sid, labels in (index.get("signals_with_valid_horizon") or {}).items()
        if set(labels) >= {HORIZON_LABELS[h] for h in HORIZON_SECS}
    ]
    index["fully_valid_signal_ids"] = fully
    index["signals_fully_matured_valid_all_horizons"] = len(fully)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, separators=(",", ":"), default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def _key(sid: str, h: int) -> str:
    return f"{sid}|{h}"


def _ingest_path_row(index: dict[str, Any], rec: dict[str, Any]) -> None:
    sid = str(rec.get("signal_id") or "")
    try:
        h = int(rec.get("horizon_sec") or 0)
    except (TypeError, ValueError):
        return
    if not sid or h <= 0:
        return
    index["path_record_rows"] = int(index.get("path_record_rows") or 0) + 1
    k = _key(sid, h)
    keys = index.setdefault("keys", {})
    if k in keys:
        index["duplicate_path_record_rows"] = int(index.get("duplicate_path_record_rows") or 0) + 1
        return
    st = _path_status(rec)
    keys[k] = st
    index["unique_path_keys"] = int(index.get("unique_path_keys") or 0) + 1
    label = HORIZON_LABELS.get(h, str(h))
    if st == "VALID":
        vb = index.setdefault("valid_by_horizon", {})
        vb[label] = int(vb.get(label) or 0) + 1
        sv = index.setdefault("signals_with_valid_horizon", {})
        labs = list(sv.get(sid) or [])
        if label not in labs:
            labs.append(label)
        sv[sid] = labs
    else:
        ub = index.setdefault("unavailable_by_horizon", {})
        ub[label] = int(ub.get(label) or 0) + 1


def _ingest_outcome_row(index: dict[str, Any], rec: dict[str, Any]) -> None:
    sid = str(rec.get("signal_id") or "")
    try:
        h = int(rec.get("horizon_sec") or 0)
    except (TypeError, ValueError):
        return
    if not sid or h <= 0:
        return
    index["outcome_rows"] = int(index.get("outcome_rows") or 0) + 1
    # Track uniqueness via path keys namespace prefixed
    ok = f"o:{sid}|{h}"
    seen = index.setdefault("_outcome_seen", {})
    if ok in seen:
        index["duplicate_outcome_rows"] = int(index.get("duplicate_outcome_rows") or 0) + 1
        return
    seen[ok] = 1
    index["unique_outcome_keys"] = int(index.get("unique_outcome_keys") or 0) + 1


def rebuild_path_index_streaming(campaign_root: Path, *, max_sec: float | None = None) -> dict[str, Any]:
    """Full streaming rebuild (no bars retained). May be deferred if over budget."""
    t0 = time.time()
    max_sec = float(max_sec if max_sec is not None else os.environ.get("NEXUS_SHADOW_INDEX_REBUILD_MAX_SEC") or 15)
    index = empty_index()
    path = path_records_path(campaign_root)
    scanned = 0
    if path.exists():
        index["path_file_bytes"] = path.stat().st_size
        with path.open("r", encoding="utf-8") as fh:
            while True:
                if (time.time() - t0) >= max_sec:
                    index["rebuild_status"] = "PARTIAL"
                    break
                line = fh.readline()
                if not line:
                    index["byte_offset"] = fh.tell()
                    index["rebuild_status"] = "COMPLETE"
                    break
                scanned += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    # Drop bars before ingest to limit transient memory
                    row.pop("bars", None)
                    _ingest_path_row(index, row)
            else:
                index["byte_offset"] = fh.tell()
                index["rebuild_status"] = "COMPLETE"
    else:
        index["rebuild_status"] = "COMPLETE"
    index["path_file_lines_scanned"] = scanned

    outp = outcomes_path(campaign_root)
    if outp.exists() and index.get("rebuild_status") == "COMPLETE":
        with outp.open("r", encoding="utf-8") as fh:
            while True:
                if (time.time() - t0) >= max_sec:
                    index["rebuild_status"] = "PARTIAL"
                    break
                line = fh.readline()
                if not line:
                    index["outcome_byte_offset"] = fh.tell()
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    _ingest_outcome_row(index, row)
    # Drop transient outcome seen set before persist (recomputable)
    index.pop("_outcome_seen", None)
    save_path_index(campaign_root, index)
    return index


def ensure_path_index(campaign_root: Path, *, force_rebuild: bool = False) -> dict[str, Any]:
    """Load index; rebuild if missing/stale vs file size, using streaming."""
    path = path_records_path(campaign_root)
    index = load_path_index(campaign_root)
    size = path.stat().st_size if path.exists() else 0
    if force_rebuild or (size > 0 and not index.get("keys") and int(index.get("byte_offset") or 0) == 0):
        return rebuild_path_index_streaming(campaign_root)
    # Incremental append scan when file grew
    if size > int(index.get("path_file_bytes") or 0) or size > int(index.get("byte_offset") or 0):
        return append_scan_path_index(campaign_root, index)
    index["path_file_bytes"] = size
    return index


def append_scan_path_index(campaign_root: Path, index: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ingest only newly appended path_records bytes."""
    index = dict(index or load_path_index(campaign_root))
    path = path_records_path(campaign_root)
    if not path.exists():
        save_path_index(campaign_root, index)
        return index
    offset = int(index.get("byte_offset") or 0)
    size = path.stat().st_size
    if offset > size:
        # file truncated/replaced — full rebuild
        return rebuild_path_index_streaming(campaign_root)
    with path.open("r", encoding="utf-8") as fh:
        fh.seek(offset)
        while True:
            line = fh.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                row.pop("bars", None)
                _ingest_path_row(index, row)
        index["byte_offset"] = fh.tell()
    index["path_file_bytes"] = size
    index["rebuild_status"] = "COMPLETE"
    # outcomes append
    outp = outcomes_path(campaign_root)
    if outp.exists():
        ooff = int(index.get("outcome_byte_offset") or 0)
        osize = outp.stat().st_size
        if ooff > osize:
            ooff = 0
            index["outcome_rows"] = 0
            index["unique_outcome_keys"] = 0
            index["duplicate_outcome_rows"] = 0
        seen = {}
        # rebuild seen from keys count approximation — track via unique_outcome_keys only on append
        with outp.open("r", encoding="utf-8") as fh:
            fh.seek(ooff)
            while True:
                line = fh.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    _ingest_outcome_row(index, row)
            index["outcome_byte_offset"] = fh.tell()
        index.pop("_outcome_seen", None)
    save_path_index(campaign_root, index)
    return index


def index_key_status(index: dict[str, Any]) -> dict[tuple[str, int], str]:
    out: dict[tuple[str, int], str] = {}
    for k, st in (index.get("keys") or {}).items():
        try:
            sid, hs = str(k).split("|", 1)
            out[(sid, int(hs))] = str(st)
        except ValueError:
            continue
    return out


def compact_observation_counters(campaign_root: Path, *, ledger_stats: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Cheap counters for hot observation path — no OHLC load."""
    index = ensure_path_index(campaign_root)
    state_signals = dict(state.get("signals") or {})
    fully_valid_state = sum(1 for e in state_signals.values() if e.get("fully_matured_valid_all_horizons"))
    fully_resolved = sum(1 for e in state_signals.values() if e.get("fully_resolved_all_horizons"))
    with_unavail = sum(1 for e in state_signals.values() if e.get("has_unavailable_horizon"))
    fully_valid_index = int(index.get("signals_fully_matured_valid_all_horizons") or len(index.get("fully_valid_signal_ids") or []))
    fully_valid = max(fully_valid_state, fully_valid_index)
    unique_created = int(ledger_stats.get("unique_signal_ids") or 0)
    return {
        "signal_ledger_rows": ledger_stats.get("ledger_rows"),
        "unique_signals_created_total": unique_created,
        "duplicate_signal_rows": ledger_stats.get("duplicate_signal_rows"),
        "path_record_rows": index.get("path_record_rows"),
        "unique_path_keys": index.get("unique_path_keys"),
        "duplicate_path_record_rows": index.get("duplicate_path_record_rows"),
        "outcome_rows": index.get("outcome_rows"),
        "unique_outcome_keys": index.get("unique_outcome_keys"),
        "duplicate_outcome_rows": index.get("duplicate_outcome_rows"),
        "signals_matured_valid_1m": (index.get("valid_by_horizon") or {}).get("1m", 0),
        "signals_matured_valid_3m": (index.get("valid_by_horizon") or {}).get("3m", 0),
        "signals_matured_valid_5m": (index.get("valid_by_horizon") or {}).get("5m", 0),
        "signals_matured_valid_15m": (index.get("valid_by_horizon") or {}).get("15m", 0),
        "signals_matured_valid_30m": (index.get("valid_by_horizon") or {}).get("30m", 0),
        "signals_fully_resolved_all_horizons": fully_resolved,
        "signals_fully_matured_valid_all_horizons": fully_valid,
        "signals_with_any_unavailable_horizon": with_unavail,
        "pending_signal_count": max(0, unique_created - fully_resolved),
        "historical_path_unavailable_count": sum(int(v or 0) for v in (index.get("unavailable_by_horizon") or {}).values()),
        "canonical_promotion_maturity_metric": "signals_fully_matured_valid_all_horizons",
        "index_rebuild_status": index.get("rebuild_status"),
    }


def rss_mb() -> float | None:
    """Best-effort Linux RSS without requiring psutil."""
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    # kB
                    parts = line.split()
                    return round(float(parts[1]) / 1024.0, 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        import resource

        # ru_maxrss is KB on Linux, bytes on macOS — treat as KB if large
        val = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if val > 10_000_000:  # likely bytes
            return round(val / (1024.0 * 1024.0), 2)
        return round(val / 1024.0, 2)
    except Exception:  # noqa: BLE001
        return None


def dataset_file_sizes(campaign_root: Path) -> dict[str, Any]:
    """Best-effort sizes for memory/disk telemetry (no file contents)."""
    out: dict[str, Any] = {}
    for label, p in (
        ("path_records_bytes", path_records_path(campaign_root)),
        ("outcomes_bytes", outcomes_path(campaign_root)),
        ("ledger_bytes", shadow_dir(campaign_root) / "active_shadow_signals.jsonl"),
        ("path_index_bytes", path_index_path(campaign_root)),
    ):
        try:
            out[label] = p.stat().st_size if p.exists() else 0
        except OSError:
            out[label] = None
    return out


def write_runtime_stage(
    campaign_root: Path,
    *,
    stage: str,
    status: str,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    d = campaign_root / "autonomy"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "shadow_runtime_stage.json"
    prev = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}
    now = int(time.time() * 1000)
    payload = {
        "schema": "v30_shadow_runtime_stage_v1",
        "stage": stage,
        "status": status,
        "started_at_ms": prev.get("started_at_ms") if status == "RUNNING" and prev.get("stage") == stage else now,
        "completed_at_ms": now if status in {"DONE", "ERROR", "DEFERRED"} else None,
        "last_error": error,
        "pid": os.getpid(),
        "rss_mb": rss_mb(),
        **(extra or {}),
    }
    if status == "RUNNING":
        payload["started_at_ms"] = now
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)
