"""Sync frontend/dist -> static/operator_ui (+ stage3 copy) for Zeabur preview serve."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "frontend" / "dist"
TARGETS = [
    ROOT / "static" / "operator_ui",
    ROOT / "deploy" / "zeabur_stage3_demo_learning" / "static" / "operator_ui",
]


def main() -> None:
    if not (DIST / "index.html").exists():
        raise SystemExit(f"missing build: {DIST}")
    html = (DIST / "index.html").read_text(encoding="utf-8")
    assets = re.findall(r"/assets/index-[^\"]+", html)
    print("dist assets", assets)
    marker_js = None
    for p in (DIST / "assets").glob("index-*.js"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if "PUBLIC_V18_2_21_PAID_BETA_IDENTITY_HEAD" in text:
            marker_js = p.name
            break
    print("marker_js", marker_js)
    if not marker_js:
        raise SystemExit("built JS missing V18.2.21 marker")

    for target in TARGETS:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(DIST, target)
        print("synced", target)


if __name__ == "__main__":
    main()
