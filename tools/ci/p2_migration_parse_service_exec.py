#!/usr/bin/env python3
"""Parse atomic P2 migration service-exec output from a file path (never stdin-as-source)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.ci.p2_migration_atomic import sanitize_prebootstrap_failure


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="path to zeabur service exec stdout capture")
    args = parser.parse_args(argv)
    raw = Path(args.path).read_text(encoding="utf-8", errors="replace")
    diag = sanitize_prebootstrap_failure(raw)
    print(json.dumps(diag, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
