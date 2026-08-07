#!/usr/bin/env python3
"""Sync frontend/dist into Zeabur Stage3 deploy package static/operator_ui.

Usage (from repo root):
  cd frontend && npm run build
  python tools/deploy/sync_operator_ui_into_zeabur_stage3.py

Does not touch trading logic. READ ONLY UI assets only.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "dist"
DESTS = (
    ROOT / "deploy" / "zeabur_stage3_demo_learning" / "static" / "operator_ui",
    ROOT / "static" / "operator_ui",  # repo-root Flask ROOT when tools/research is used locally
)
MARKER = "PUBLIC_V18_2_7_MEMBER_PRODUCT_RESET_HEAD"
PHASE4_LEGACY_MARKER = "NEXUS_UI_PRODUCT_AND_INTELLIGENCE_PHASE4"
PHASE3_MARKER = "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE3_SECTOR_CHART_EQUITIES"
PHASE2_MARKER = "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE2_DECISION_EXPERIENCE"
PHASE1_MARKER = "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE1_MARKET_SCANNER"
MVP22D_MARKER = "NEXUS_UI_MVP22D_ANOMALY_OUTCOME_RESEARCH"
MVP22C_MARKER = "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR"
MVP22B_MARKER = "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT"
MVP22A_MARKER = "NEXUS_UI_MVP22A_LIVE_MARKET_DATA"
LEGACY_MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"
ASSET_REF_RE = re.compile(r"/assets/(index-[^\"']+\.(?:js|css))", re.I)
MAX_RETAINED_GENERATIONS = 3


def _extract_asset_refs(html: str) -> set[str]:
    return set(ASSET_REF_RE.findall(html))


def _collect_hashed_assets(assets_dir: Path) -> dict[str, bytes]:
    if not assets_dir.is_dir():
        return {}
    retained: dict[str, bytes] = {}
    for path in assets_dir.iterdir():
        if path.is_file() and path.name.startswith("index-") and path.suffix in {".js", ".css"}:
            retained[path.name] = path.read_bytes()
    return retained


def _sync_one(dest: Path) -> dict:
    index_path = dest / "index.html"
    assets_dir = dest / "assets"
    previous_refs: set[str] = set()
    previous_assets: dict[str, bytes] = {}
    if index_path.is_file():
        previous_refs = _extract_asset_refs(index_path.read_text(encoding="utf-8", errors="ignore"))
    previous_assets = _collect_hashed_assets(assets_dir)

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest)

    new_index = (dest / "index.html").read_text(encoding="utf-8", errors="ignore")
    new_refs = _extract_asset_refs(new_index)
    keep_refs = set(new_refs)
    keep_refs.update(previous_refs)

    out_assets = dest / "assets"
    for name, data in previous_assets.items():
        if name in keep_refs and not (out_assets / name).exists():
            (out_assets / name).write_bytes(data)

    allowed = set(new_refs)
    allowed.update(previous_refs)
    for path in out_assets.iterdir():
        if path.is_file() and path.name.startswith("index-") and path.name not in allowed:
            path.unlink()

    retained_assets = sorted(
        p.name for p in out_assets.iterdir() if p.is_file() and p.name.startswith("index-")
    )
    blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in dest.rglob("*") if p.is_file())
    found = (
        MARKER in blob
        or PHASE3_MARKER in blob
        or PHASE2_MARKER in blob
        or PHASE1_MARKER in blob
        or MVP22D_MARKER in blob
        or MVP22C_MARKER in blob
        or MVP22B_MARKER in blob
        or MVP22A_MARKER in blob
        or LEGACY_MARKER in blob
    )
    meta = {
        "source": "frontend/dist",
        "dest": str(dest.relative_to(ROOT)).replace("\\", "/"),
        "marker": MARKER,
        "phase3_marker": PHASE3_MARKER,
        "phase2_marker": PHASE2_MARKER,
        "mvp22d_marker": MVP22D_MARKER,
        "mvp22c_marker": MVP22C_MARKER,
        "mvp22b_marker": MVP22B_MARKER,
        "mvp22a_marker": MVP22A_MARKER,
        "legacy_marker": LEGACY_MARKER,
        "marker_found": found,
        "file_count": sum(1 for p in dest.rglob("*") if p.is_file()),
        "current_assets": sorted(new_refs),
        "retained_assets": retained_assets,
        "retained_generations": MAX_RETAINED_GENERATIONS,
        "previous_assets": sorted(previous_refs),
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
