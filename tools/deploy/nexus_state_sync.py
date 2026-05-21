#!/usr/bin/env python3
"""
Pack / restore NEXUS local runtime state for Zeabur (or any cloud host).

Usage:
  python tools/deploy/nexus_state_sync.py export
  python tools/deploy/nexus_state_sync.py import path/to/nexus_state_bundle.zip

Exports trading.db (+ WAL sidecars) and layout_overrides.json without secrets.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.data_paths import resolve_layout_path, resolve_runtime_db_path

BUNDLE_VERSION = 1


def _snapshot_db_file(db_path: Path, dest_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)
    except Exception:
        source = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        dest = sqlite3.connect(str(dest_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return True


def export_bundle(output_dir: Path | None = None) -> Path:
    db_path = Path(resolve_runtime_db_path())
    layout_path = Path(resolve_layout_path())
    out_dir = output_dir or (ROOT / "data" / "state_bundles")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_path = out_dir / f"nexus_state_{stamp}.zip"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_db = Path(tmp_dir) / "trading.db"
        has_db = _snapshot_db_file(db_path, tmp_db)

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "manifest.json",
                (
                    '{"bundle_version":%d,"exported_at":"%s","db":"trading.db","layout":"layout_overrides.json"}'
                    % (BUNDLE_VERSION, stamp)
                ),
            )
            if has_db:
                zf.write(tmp_db, arcname="data/trading.db")
            if layout_path.exists():
                zf.write(layout_path, arcname="data/layout_overrides.json")

    print(f"[export] bundle written: {bundle_path}")
    if not db_path.exists():
        print("[export] warning: trading.db not found; bundle may be empty")
    return bundle_path


def import_bundle(bundle_path: Path, target_data_dir: Path | None = None) -> None:
    bundle_path = bundle_path.resolve()
    if not bundle_path.exists():
        raise FileNotFoundError(bundle_path)

    data_dir = target_data_dir or Path(
        str(__import__("os").getenv("NEXUS_DATA_DIR", "") or "").strip() or ROOT
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(bundle_path, "r") as zf:
        members = [name for name in zf.namelist() if name.startswith("data/") and not name.endswith("/")]
        for member in members:
            filename = Path(member).name
            dest = data_dir / filename
            if dest.exists():
                backup = dest.with_suffix(dest.suffix + ".bak")
                shutil.copy2(dest, backup)
                print(f"[import] backed up {dest.name} -> {backup.name}")
            with zf.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            print(f"[import] restored {dest}")

    print(f"[import] state restored under: {data_dir}")
    print("[import] set Zeabur env: NEXUS_DATA_DIR=/data  NEXUS_RUNTIME_DB=trading.db")


def main():
    parser = argparse.ArgumentParser(description="NEXUS state bundle export/import")
    sub = parser.add_subparsers(dest="command", required=True)

    export_cmd = sub.add_parser("export", help="Create a state bundle zip from local files")
    export_cmd.add_argument("--output-dir", type=Path, default=None)

    import_cmd = sub.add_parser("import", help="Restore a state bundle zip")
    import_cmd.add_argument("bundle", type=Path)
    import_cmd.add_argument("--data-dir", type=Path, default=None)

    args = parser.parse_args()
    if args.command == "export":
        export_bundle(args.output_dir)
        return
    import_bundle(args.bundle, args.data_dir)


if __name__ == "__main__":
    main()
