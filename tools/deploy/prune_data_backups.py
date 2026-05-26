#!/usr/bin/env python3
"""
Prune legacy trading.db backup files under NEXUS_DATA_DIR (or ./data).

Keeps the active trading.db, WAL/SHM sidecars, and layout_overrides.json untouched.
Removes trading_backup_*.db and trading_shield_backup.db beyond --keep N newest backups.

Usage:
  python tools/deploy/prune_data_backups.py --dry-run
  python tools/deploy/prune_data_backups.py --keep 2
  python tools/deploy/prune_data_backups.py --shield --logs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.data_paths import resolve_data_dir, resolve_runtime_db_path


def _resolve_data_root() -> Path:
    data_dir = resolve_data_dir()
    if data_dir is not None:
        return Path(data_dir)
    return ROOT / "data"


def _backup_files(data_root: Path) -> list[Path]:
    patterns = ("trading_backup_*.db", "trading_backup_*.db-*")
    found: list[Path] = []
    if not data_root.is_dir():
        return found
    for pattern in patterns:
        found.extend(data_root.glob(pattern))
    return sorted({path.resolve() for path in found if path.is_file()}, key=lambda p: p.stat().st_mtime, reverse=True)


def _shield_backups(data_root: Path) -> list[Path]:
    if not data_root.is_dir():
        return []
    return sorted(
        [path.resolve() for path in data_root.glob("trading_shield_backup*.db") if path.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _log_files(data_root: Path) -> list[Path]:
    logs_dir = data_root / "logs"
    if not logs_dir.is_dir():
        logs_dir = ROOT / "logs"
    if not logs_dir.is_dir():
        return []
    return sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)


def _unlink(path: Path, dry_run: bool) -> bool:
    if not path.exists():
        return False
    if dry_run:
        print(f"would remove: {path}")
        return True
    try:
        path.unlink()
        print(f"removed: {path}")
        return True
    except PermissionError:
        print(f"skip (in use): {path}")
        return False


def prune_backups(data_root: Path, keep: int, include_shield: bool, include_logs: bool, dry_run: bool) -> tuple[int, int]:
    removed = 0
    skipped = 0

    backups = _backup_files(data_root)
    for path in backups[keep:]:
        if _unlink(path, dry_run):
            removed += 1
        else:
            skipped += 1

    if include_shield:
        for path in _shield_backups(data_root):
            if _unlink(path, dry_run):
                removed += 1
            else:
                skipped += 1

    if include_logs:
        for path in _log_files(data_root)[5:]:
            if _unlink(path, dry_run):
                removed += 1
            else:
                skipped += 1

    active = Path(resolve_runtime_db_path())
    print(f"data root: {data_root}")
    print(f"active db: {active} (kept)")
    print(f"backups found: {len(backups)} | keep: {keep} | prune candidates: {max(0, len(backups) - keep)}")
    return removed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune legacy trading.db backups under data/")
    parser.add_argument("--keep", type=int, default=2, help="Number of newest trading_backup_* files to retain")
    parser.add_argument("--shield", action="store_true", help="Also remove trading_shield_backup*.db")
    parser.add_argument("--logs", action="store_true", help="Also remove old *.log beyond the 5 newest")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without deleting")
    args = parser.parse_args()

    if args.keep < 0:
        print("--keep must be >= 0")
        return 2

    data_root = _resolve_data_root()
    removed, skipped = prune_backups(
        data_root,
        keep=max(0, int(args.keep)),
        include_shield=bool(args.shield),
        include_logs=bool(args.logs),
        dry_run=bool(args.dry_run),
    )
    if args.dry_run:
        print("dry-run complete (no files deleted)")
    else:
        print(f"done: removed={removed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
