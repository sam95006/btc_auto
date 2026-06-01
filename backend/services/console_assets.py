"""Console artwork paths — verified at startup and in /health."""

from __future__ import annotations

from pathlib import Path

REQUIRED_CONSOLE_ASSETS = (
    "static/nexus/assets/nexus_overview.png",
    "static/nexus/assets/hq_roundtable.png",
    "static/nexus/assets/btc_bridge.png",
    "static/nexus/assets/eth_bridge.png",
    "static/nexus/assets/sol_bridge.png",
    "static/nexus/assets/pepe_bridge.png",
    "static/nexus/assets/radar_outpost.png",
    "static/nexus/assets/news_nexus.png",
)


def verify_console_assets(root_path: str | Path) -> dict:
    root = Path(root_path)
    missing = []
    present = []
    for rel in REQUIRED_CONSOLE_ASSETS:
        path = root / rel
        if path.is_file() and path.stat().st_size > 0:
            present.append(rel)
        else:
            missing.append(rel)
    return {
        "ok": len(missing) == 0,
        "present_count": len(present),
        "missing": missing,
        "required_count": len(REQUIRED_CONSOLE_ASSETS),
    }
