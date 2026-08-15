"""CLI for explicit PostgreSQL migration apply (never auto-wired to Shadow)."""
from __future__ import annotations

import argparse
import json
import sys

from backend.nexus_persistence_pg import MigrationRunner, PostgresPool
from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus_persistence_pg.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate")
    migrate_sub = migrate.add_subparsers(dest="migrate_cmd", required=True)
    migrate_sub.add_parser("catalog")
    apply = migrate_sub.add_parser("apply")
    apply.add_argument("--allow-destructive", action="store_true")

    args = parser.parse_args(argv)
    runner = MigrationRunner()

    if args.migrate_cmd == "catalog":
        print(json.dumps(runner.catalog(), indent=2))
        return 0

    cfg = PostgresRuntimeConfig.from_env()
    if not cfg.database_url:
        print(json.dumps({"ok": False, "error": "NEXUS_POSTGRES_URL not configured"}))
        return 2
    pool = PostgresPool(cfg.database_url)
    pool.open()
    try:
        result = runner.apply_pending(pool, allow_destructive=args.allow_destructive)
    finally:
        pool.close()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
