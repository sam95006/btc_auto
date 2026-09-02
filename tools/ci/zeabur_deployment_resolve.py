#!/usr/bin/env python3
"""Resolve the exact NEW Zeabur deployment id created by a deploy, by set-diffing
the 24-hex Mongo-style object-id tokens found in the `zeabur deployment list`
output BEFORE vs AFTER the deploy.

This is robust to the precise `--json` field names (and even to the CLI wrapping
JSON in log lines) because it works on the raw text. Stable ids (service /
environment / project) appear in both snapshots and cancel out in the diff, so
the only token left is the newly-created deployment. 40-char SHAs and redacted
40+ char secrets never match the strict 24-hex boundary.

Commands:
  ids <file>                     -> print every 24-hex id (one per line, sorted)
  new <before_file> <after_file> -> print the single NEW id, or:
                                       NONE            (not appeared yet)
                                       AMBIGUOUS:<csv> (cannot uniquely identify)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Exactly 24 hex chars, not part of a longer hex run (excludes 40-hex SHAs and
# redacted 40+ char secrets).
ID_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{24}(?![0-9a-f])", re.IGNORECASE)


def _ids(path: str) -> set[str]:
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set()
    return {m.lower() for m in ID_RE.findall(raw)}


def main() -> int:
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "ids":
        for i in sorted(_ids(args[1])):
            print(i)
        return 0
    if len(args) == 3 and args[0] == "new":
        new = sorted(_ids(args[2]) - _ids(args[1]))
        if len(new) == 1:
            print(new[0])
        elif not new:
            print("NONE")
        else:
            print("AMBIGUOUS:" + ",".join(new))
        return 0
    print("NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
