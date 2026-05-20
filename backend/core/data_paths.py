import os
from pathlib import Path


def resolve_data_dir():
    raw = str(os.getenv("NEXUS_DATA_DIR", "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_runtime_db_path(explicit=None):
    if explicit:
        return str(explicit)
    db_ref = str(os.getenv("NEXUS_RUNTIME_DB", "trading.db") or "trading.db").strip()
    db_path = Path(db_ref)
    if db_path.is_absolute():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path)
    data_dir = resolve_data_dir()
    if data_dir is not None:
        target = data_dir / db_path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)
    return str(db_path)


def resolve_layout_path():
    data_dir = resolve_data_dir()
    if data_dir is not None:
        return data_dir / "layout_overrides.json"
    return Path(__file__).resolve().parents[2] / "static" / "nexus" / "layout_overrides.json"
