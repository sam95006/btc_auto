#!/usr/bin/env python3
"""Export Stage 4 AI decision dry-run outputs to tar.gz (no secrets)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_ai_decision_agent import resolve_stage4_output_dir  # noqa: E402

BUNDLE_FILES = (
    "ai_decisions.jsonl",
    "risk_supervisor_decisions.jsonl",
    "llm_client_debug.jsonl",
    "stage4_ai_decision_summary.json",
    "stage4_30m_dry_run.log",
    "stage4_short_run.log",
    "stage4_cloud_dry_run.log",
)

SECRET_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.I),
)


def _scan_secrets(text: str) -> List[str]:
    hits: List[str] = []
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            hits.append(pat.pattern[:40])
    return hits


def export_bundle(output_dir: Path | None = None, *, bundle_name: str = "stage4_44_decision_bundle.tar.gz") -> Dict[str, Any]:
    out = output_dir or resolve_stage4_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    archive = out / bundle_name

    included: List[str] = []
    missing: List[str] = []
    secret_hits: List[str] = []

    for name in BUNDLE_FILES:
        src = out / name
        if src.is_file():
            text = src.read_text(encoding="utf-8", errors="replace")
            hits = _scan_secrets(text)
            if hits:
                secret_hits.extend([f"{name}:{h}" for h in hits])
            included.append(name)
        else:
            missing.append(name)

    with tarfile.open(archive, "w:gz") as tar:
        for name in included:
            tar.add(out / name, arcname=name)

    manifest = {
        "record_type": "stage4_ai_decision_bundle_export",
        "phase": "4.4",
        "generated_at_utc": utc_now_iso(),
        "output_dir": str(out),
        "bundle_path": str(archive),
        "included_files": included,
        "missing_files": missing,
        "file_count": len(included),
        "secret_scan_hits": secret_hits,
        "bundle_safe": not secret_hits,
    }
    write_json(out / "stage4_bundle_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Stage 4 decision dry-run bundle")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--bundle-name", default="stage4_44_decision_bundle.tar.gz")
    args = parser.parse_args()
    out = Path(args.output_dir) if args.output_dir else None
    result = export_bundle(out, bundle_name=args.bundle_name)
    print(json.dumps(result, indent=2))
    return 0 if result.get("bundle_safe") and result.get("file_count", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
