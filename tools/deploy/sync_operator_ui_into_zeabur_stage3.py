#!/usr/bin/env python3
"""Sync frontend/dist into Zeabur Stage3 deploy package static/operator_ui.

Usage (from repo root):
  cd frontend && npm run build
  python tools/deploy/sync_operator_ui_into_zeabur_stage3.py

Does not touch trading logic. READ ONLY UI assets only.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "dist"
DESTS = (
    ROOT / "deploy" / "zeabur_stage3_demo_learning" / "static" / "operator_ui",
    ROOT / "static" / "operator_ui",  # repo-root Flask ROOT when tools/research is used locally
)
MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"


def _sync_one(dest: Path) -> dict:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest)
    blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in dest.rglob("*") if p.is_file())
    found = MARKER in blob
    meta = {
        "source": "frontend/dist",
        "dest": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "marker": MARKER,
        "marker_found": found,
        "file_count": sum(1 for p in dest.rglob("*") if p.is_file()),
    }
    (dest / "operator_ui_build.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    if not SRC.is_dir():
        print(f"FAIL: missing {SRC} — run: cd frontend && npm run build")
        return 1
    metas = [_sync_one(d) for d in DESTS]
    print(json.dumps(metas, indent=2))
    if not all(m["marker_found"] for m in metas):
        print("WARN: build marker not found in synced dist text")
        return 2
    print("PASS: operator UI synced into Zeabur Stage3 package + repo static/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
