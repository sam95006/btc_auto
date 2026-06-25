#!/usr/bin/env python3
"""Export Stage 3 demo learning artifacts bundle from /data output dir."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage3_learning_loop import OUTPUT_FILES, resolve_output_dir  # noqa: E402

BUNDLE_FILES = (
    *OUTPUT_FILES,
    "background_session_status.json",
    "background_session_report.json",
    "background_session.log",
    "background_session.pid",
)

LOCAL_REPORT = ROOT / "data/external_alpha/reports/stage3_demo_learning_bundle_export.json"


def export_bundle(output_dir: Path | None = None) -> Dict[str, Any]:
    out = output_dir or resolve_output_dir()
    bundle_dir = out / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    archive = bundle_dir / "stage3_demo_learning_bundle.tar.gz"

    included: List[str] = []
    missing: List[str] = []
    for name in BUNDLE_FILES:
        src = out / name
        if src.is_file():
            included.append(name)
        else:
            missing.append(name)

    with tarfile.open(archive, "w:gz") as tar:
        for name in included:
            tar.add(out / name, arcname=name)

    manifest = {
        "record_type": "stage3_demo_learning_bundle_export",
        "phase": "C+3",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "bundle_path": str(archive),
        "bundle_dir": str(bundle_dir),
        "included_files": included,
        "missing_files": missing,
        "file_count": len(included),
    }
    write_json(bundle_dir / "bundle_manifest.json", manifest)
    write_json(LOCAL_REPORT, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Stage 3 demo learning bundle")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    result = export_bundle(out)
    print(json.dumps(result, indent=2))
    return 0 if result["file_count"] >= len(OUTPUT_FILES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
