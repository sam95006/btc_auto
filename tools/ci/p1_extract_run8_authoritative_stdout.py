#!/usr/bin/env python3
"""Extract authoritative Run #8 JSON from atomic service-exec stdout."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from p1_run8_atomic_recovery import extract_authoritative_run8_stdout, write_authoritative_artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", dest="input")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    raw = Path(args.input).read_text(encoding="utf-8", errors="replace") if args.input else sys.stdin.read()
    result = extract_authoritative_run8_stdout(raw)
    write_authoritative_artifact(result, Path(args.out))
    print(f"authoritative_stdout={str(result['authoritative']).lower()}")
    print(f"authoritative_kind={result['kind']}")
    print(f"control_decision={result['decision']}")
    print("file_channel_authoritative=false")
    if result["decision"] == "PASS" and result["authoritative"]:
        return 0
    return 1 if result["authoritative"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
