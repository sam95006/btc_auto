#!/usr/bin/env python3
"""CLI: list V17-A data sources filtered by status.

Examples:
  python tools/data_source_registry/list_sources.py
  python tools/data_source_registry/list_sources.py --status LICENSE_REVIEW_REQUIRED
  python tools/data_source_registry/list_sources.py --status APPROVED_PUBLIC --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)


def main() -> int:
    from backend.nexus_data_source_registry import (
        SOURCE_STATUSES,
        DataSourceRegistry,
        write_fixture_artifact,
        write_schema_artifact,
    )

    parser = argparse.ArgumentParser(
        description="List V17-A Data Source Registry entries by status"
    )
    parser.add_argument(
        "--status",
        choices=list(SOURCE_STATUSES),
        default=None,
        help="Filter by registry status (default: list all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a table",
    )
    parser.add_argument(
        "--counts",
        action="store_true",
        help="Print status counts only",
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write schema + fixture JSON under artifacts/",
    )
    args = parser.parse_args()

    if args.write_artifacts:
        schema_path = write_schema_artifact(ROOT)
        fixture_path = write_fixture_artifact(ROOT)
        print(f"schema={schema_path}")
        print(f"fixtures={fixture_path}")

    reg = DataSourceRegistry.from_fixtures()

    if args.counts:
        counts = reg.statuses_present()
        if args.json:
            print(json.dumps(counts, indent=2, ensure_ascii=False))
        else:
            for st in SOURCE_STATUSES:
                print(f"{st}\t{counts[st]}")
        return 0

    rows = reg.list_by_status(args.status) if args.status else reg.list_all()
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    print(f"status_filter={args.status or 'ALL'} count={len(rows)}")
    for src in rows:
        print(
            f"{src['status']}\t{src['source_id']}\t{src['provider']}\t"
            f"{src['dataset']}\ttraining={src['training_allowed']}\t"
            f"redistrib={src['redistribution_allowed']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
