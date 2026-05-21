#!/usr/bin/env python3
"""
Remove stale local runtime data so capital/positions re-sync from Binance testnet only.

Usage:
  python tools/deploy/purge_runtime.py              # DB + WAL only
  python tools/deploy/purge_runtime.py --logs       # also logs/*.log
  python tools/deploy/purge_runtime.py --bundles       # also data/state_bundles/*.zip
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.data_paths import resolve_runtime_db_path


def _unlink(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        path.unlink()
    except PermissionError:
        print(f"skip (in use): {path}")
        return False
    print(f"removed: {path}")
    return True


def purge_runtime_db() -> None:
    db_path = Path(resolve_runtime_db_path())
    for suffix in ("", "-wal", "-shm", ".snapshot.lock", "-journal"):
        _unlink(Path(f"{db_path}{suffix}"))


def purge_logs() -> None:
    logs_dir = ROOT / "logs"
    if not logs_dir.is_dir():
        return
    for item in logs_dir.glob("*.log"):
        _unlink(item)


def purge_state_bundles() -> None:
    bundle_dir = ROOT / "data" / "state_bundles"
    if not bundle_dir.is_dir():
        return
    for item in bundle_dir.glob("*.zip"):
        _unlink(item)


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge stale NEXUS runtime files")
    parser.add_argument("--logs", action="store_true", help="Remove logs/*.log")
    parser.add_argument("--bundles", action="store_true", help="Remove data/state_bundles/*.zip")
    args = parser.parse_args()

    purge_runtime_db()
    if args.logs:
        purge_logs()
    if args.bundles:
        purge_state_bundles()
    print("Done. Restart run.py — capital will reload from Binance testnet on first sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
