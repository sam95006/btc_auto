#!/usr/bin/env python3
"""Import Stage 3 learning JSONL or bundle into stage3 data dir for Stage 4 context."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_context_summary import import_stage3_context_seed, resolve_stage3_data_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Stage3 context seed for Stage 4 prompts")
    parser.add_argument("source", help="JSONL file, directory, or .tar.gz bundle")
    parser.add_argument("--target-dir", default="", help="Default: STAGE3_OUTPUT_DIR or /data/stage3_demo_learning")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    target = Path(args.target_dir) if args.target_dir else None
    result = import_stage3_context_seed(Path(args.source), target_dir=target, overwrite=args.overwrite)
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
