"""Stage 4 Stage-3 context summaries for LLM prompts (no secrets)."""
from __future__ import annotations

import json
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

STAGE3_JSONL_FILES = (
    "trade_results.jsonl",
    "reflection_records.jsonl",
    "applied_learning_patches.jsonl",
)

PATCH_BLOCK_ACTIONS = frozenset({"block_reentry", "manual_review_required"})


def resolve_stage3_data_dir() -> Path:
    """Resolve Stage 3 learning dir (cloud /data or local fallback)."""
    custom = os.environ.get("STAGE3_OUTPUT_DIR", "").strip()
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True)
        return p
    nexus = os.environ.get("NEXUS_DATA_DIR", "").strip()
    if nexus:
        candidate = Path(nexus) / "stage3_demo_learning"
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return candidate
        except OSError:
            pass
    out = ROOT / "data" / "external_alpha" / "stage3_demo_learning"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def summarize_trade_result(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "close_pnl": row.get("close_pnl"),
        "failure_reason": str(row.get("exit_reason") or row.get("failure_reason") or "")[:120],
        "setup_key": str(row.get("setup_key") or "")[:120],
        "created_at_utc": str(row.get("created_at_utc") or row.get("closed_at_utc") or "")[:32],
    }


def summarize_reflection(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "failure_reason": str(row.get("failure_reason") or row.get("root_cause") or "")[:120],
        "patch_action": str(row.get("recommended_action") or row.get("patch_action") or "")[:64],
        "setup_key": str(row.get("setup_key") or "")[:120],
        "created_at_utc": str(row.get("created_at_utc") or "")[:32],
    }


def summarize_patch(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or "").upper(),
        "patch_action": str(row.get("action") or "")[:64],
        "setup_key": str(row.get("setup_key") or "")[:120],
        "failure_reason": str(row.get("failure_reason") or row.get("reason") or "")[:120],
        "created_at_utc": str(row.get("created_at_utc") or row.get("applied_at_utc") or "")[:32],
    }


def summarize_trades(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [summarize_trade_result(r) for r in rows[:limit]]


def summarize_reflections(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [summarize_reflection(r) for r in rows[:limit]]


def summarize_patches(rows: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    return [summarize_patch(r) for r in rows[:limit]]


def blocking_patches(patches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in patches if str(p.get("action") or "") in PATCH_BLOCK_ACTIONS]


def load_stage3_context(
    stage3_dir: Optional[Path] = None,
    *,
    symbol: str = "",
    trade_limit: int = 5,
    reflection_limit: int = 5,
    patch_limit: int = 5,
) -> Dict[str, Any]:
    """Load Stage 3 summaries with availability flags; never raises."""
    data_dir = stage3_dir or resolve_stage3_data_dir()
    sym = symbol.upper()

    missing_files = [name for name in STAGE3_JSONL_FILES if not (data_dir / name).is_file()]
    trades_all = _read_jsonl(data_dir / "trade_results.jsonl")
    reflections_all = _read_jsonl(data_dir / "reflection_records.jsonl")
    patches_all = _read_jsonl(data_dir / "applied_learning_patches.jsonl")

    if sym:
        trades_filtered = [t for t in reversed(trades_all) if str(t.get("symbol", "")).upper() == sym]
    else:
        trades_filtered = list(reversed(trades_all))

    recent_trades = trades_filtered[:trade_limit]
    recent_reflections = list(reversed(reflections_all))[:reflection_limit]
    active_patches = list(reversed(patches_all))[:patch_limit]

    has_data = bool(recent_trades or recent_reflections or active_patches)
    if has_data:
        reason = "ok"
    elif missing_files == list(STAGE3_JSONL_FILES):
        reason = "files_missing"
    elif missing_files:
        reason = "partial_files_missing"
    else:
        reason = "files_empty"

    return {
        "stage3_context_available": has_data,
        "stage3_context_reason": reason,
        "stage3_data_dir": str(data_dir),
        "stage3_missing_files": missing_files,
        "recent_trade_results_count": len(recent_trades),
        "recent_reflections_count": len(recent_reflections),
        "active_patches_count": len(active_patches),
        "recent_trade_results": summarize_trades(recent_trades, limit=trade_limit),
        "recent_reflections": summarize_reflections(recent_reflections, limit=reflection_limit),
        "active_patches": summarize_patches(active_patches, limit=patch_limit),
    }


def import_stage3_context_seed(
    source: Path,
    *,
    target_dir: Optional[Path] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Import Stage3 JSONL files or bundle tar.gz into stage3 data dir (no secrets)."""
    target = target_dir or resolve_stage3_data_dir()
    target.mkdir(parents=True, exist_ok=True)
    imported: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    def _copy_jsonl(src: Path, name: str) -> None:
        dst = target / name
        if dst.is_file() and not overwrite:
            skipped.append(name)
            return
        shutil.copy2(src, dst)
        imported.append(name)

    if source.is_file() and source.suffixes[-2:] == [".tar", ".gz"] or str(source).endswith(".tar.gz"):
        try:
            with tarfile.open(source, "r:gz") as tar:
                for member in tar.getmembers():
                    base = Path(member.name).name
                    if base in STAGE3_JSONL_FILES and member.isfile():
                        tar.extract(member, path=target / "_import_tmp")
                        tmp = target / "_import_tmp" / member.name
                        _copy_jsonl(tmp, base)
                        tmp.unlink(missing_ok=True)
            shutil.rmtree(target / "_import_tmp", ignore_errors=True)
        except Exception as exc:
            errors.append(f"tar_import_error:{str(exc)[:80]}")
    elif source.is_dir():
        for name in STAGE3_JSONL_FILES:
            src = source / name
            if src.is_file():
                _copy_jsonl(src, name)
    elif source.is_file() and source.name in STAGE3_JSONL_FILES:
        _copy_jsonl(source, source.name)
    else:
        errors.append(f"unsupported_source:{source}")

    return {
        "record_type": "stage3_context_import",
        "target_dir": str(target),
        "source": str(source),
        "imported_files": imported,
        "skipped_files": skipped,
        "errors": errors,
        "success": not errors and bool(imported),
    }
