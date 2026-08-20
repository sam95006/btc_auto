#!/usr/bin/env python3
"""Extract authoritative P2 migration JSON from atomic service-exec stdout."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.ci.p2_migration_atomic import extract_authoritative_migration_stdout, write_authoritative_artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    raw = Path(args.input).read_text(encoding="utf-8")
    result = extract_authoritative_migration_stdout(raw)
    written = write_authoritative_artifact(result, Path(args.out))
    print(json.dumps({"authoritative": result.get("authoritative"), "kind": result.get("kind"), "written": bool(written)}))
    if result.get("authoritative") and result.get("kind") == "migration":
        payload = result.get("payload") or {}
        if payload.get("P2_MIGRATION_0007_APPLIED_PASS") is True:
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
