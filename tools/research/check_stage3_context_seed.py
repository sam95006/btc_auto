#!/usr/bin/env python3
"""Read-only Stage 3 context availability check for Stage 4 (no orders)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.stage4_context_summary import (  # noqa: E402
    load_stage3_context,
    resolve_stage3_data_dir,
)

STAGE3_JSONL_FILES = (
    "trade_results.jsonl",
    "reflection_records.jsonl",
    "applied_learning_patches.jsonl",
)


def check_stage3_context(*, target_dir: Path | None = None, symbol: str = "ETHUSDT") -> dict:
    stage3_dir = target_dir or resolve_stage3_data_dir()
    files_present = {name: (stage3_dir / name).is_file() for name in STAGE3_JSONL_FILES}
    line_counts = {}
    for name in STAGE3_JSONL_FILES:
        path = stage3_dir / name
        if path.is_file():
            line_counts[name] = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        else:
            line_counts[name] = 0

    ctx = load_stage3_context(stage3_dir, symbol=symbol)
    available = bool(ctx.get("stage3_context_available"))
    trade_n = int(ctx.get("recent_trade_results_count") or 0)
    refl_n = int(ctx.get("recent_reflections_count") or 0)
    patch_n = int(ctx.get("active_patches_count") or 0)

    passed = available and trade_n > 0 and refl_n > 0 and patch_n > 0
    errors: list[str] = []
    if not available:
        errors.append(str(ctx.get("stage3_context_reason") or "stage3_context_unavailable"))
    if trade_n <= 0:
        errors.append("recent_trade_results_count_zero")
    if refl_n <= 0:
        errors.append("recent_reflections_count_zero")
    if patch_n <= 0:
        errors.append("active_patches_count_zero")

    return {
        "record_type": "stage3_context_seed_check",
        "target_dir": str(stage3_dir),
        "symbol": symbol.upper(),
        "files_present": files_present,
        "line_counts": line_counts,
        "stage3_context_available": available,
        "stage3_context_reason": ctx.get("stage3_context_reason"),
        "recent_trade_results_count": trade_n,
        "recent_reflections_count": refl_n,
        "active_patches_count": patch_n,
        "passed": passed,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Stage3 context seed check")
    parser.add_argument("--target-dir", default="", help="Default: STAGE3_OUTPUT_DIR or /data/stage3_demo_learning")
    parser.add_argument("--symbol", default="ETHUSDT")
    args = parser.parse_args()
    target = Path(args.target_dir) if args.target_dir else None
    result = check_stage3_context(target_dir=target, symbol=args.symbol)
    print(json.dumps(result, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
