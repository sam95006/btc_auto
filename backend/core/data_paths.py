import os
from pathlib import Path


def _probe_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def resolve_data_dir():
    """Resolve NEXUS_DATA_DIR without crashing the web process.

    If the configured directory is missing/unwritable (common when Zeabur
    volume is not mounted), fall back to writable ephemeral paths so
    /health can still return 200.
    """
    raw = str(os.getenv("NEXUS_DATA_DIR", "") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    candidates.extend(
        [
            Path("/tmp/nexus_demo_validation"),
            Path("/tmp/nexus_data"),
            Path("data"),
        ]
    )
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if _probe_writable(path):
            # Keep process env consistent with the actual writable root.
            if raw and str(path) != raw:
                os.environ["NEXUS_DATA_DIR"] = str(path)
                os.environ["NEXUS_DATA_DIR_FALLBACK"] = "true"
            return path
    return None


def resolve_runtime_db_path(explicit=None):
    if explicit:
        return str(explicit)
    db_ref = str(os.getenv("NEXUS_RUNTIME_DB", "trading.db") or "trading.db").strip()
    db_path = Path(db_ref)
    if db_path.is_absolute():
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return str(db_path)
        except Exception:
            fallback = Path("/tmp") / db_path.name
            return str(fallback)
    data_dir = resolve_data_dir()
    if data_dir is not None:
        target = data_dir / db_path.name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            return str(target)
        except Exception:
            return str(Path("/tmp") / db_path.name)
    return str(db_path)


def resolve_layout_path():
    data_dir = resolve_data_dir()
    if data_dir is not None:
        return data_dir / "layout_overrides.json"
    return Path(__file__).resolve().parents[2] / "static" / "nexus" / "layout_overrides.json"
