"""Load founder demo-monitor feed from Agent B campaign / evidence coordinator."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_founder_demo_monitor.constants import (
    DEFAULT_LIVE_FEED_CANDIDATES,
    ENV_EVIDENCE_ROOT,
    ENV_FEED_ONLY,
    ENV_FEED_PATH,
)


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _extract_monitor_blob(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Accept dedicated feed or core evidence envelopes with founder_monitor."""
    if doc.get("schema", "").startswith("v18_2_") and "founder_monitor" not in doc:
        # Full core evidence — dig for monitor blocks.
        pass
    # Dedicated live feed shaped as the monitor contract itself.
    if doc.get("demo_uid") or doc.get("account_uid") or doc.get("active_position") is not None:
        if doc.get("founder_monitor") and isinstance(doc["founder_monitor"], dict):
            return dict(doc["founder_monitor"])
        return dict(doc)

    for key in ("founder_monitor", "FOUNDER_MONITOR", "demo_monitor"):
        blob = doc.get(key)
        if isinstance(blob, dict) and blob:
            return dict(blob)

    autonomy = doc.get("AUTONOMY")
    if isinstance(autonomy, dict):
        fm = autonomy.get("founder_monitor")
        if isinstance(fm, dict) and fm:
            return dict(fm)

    real_auto = doc.get("REAL_AUTONOMY")
    if isinstance(real_auto, dict):
        fm = real_auto.get("founder_monitor")
        if isinstance(fm, dict) and fm:
            return dict(fm)

    # Compact REAL_DEMO_ACCOUNT + WALLET pair from core evidence (Agent B).
    real_demo = doc.get("REAL_DEMO_ACCOUNT")
    if isinstance(real_demo, dict) and real_demo:
        out = dict(real_demo)
        wallet = doc.get("WALLET")
        if isinstance(wallet, dict):
            out["_wallet_block"] = wallet
        pnl = doc.get("PNL_PROVENANCE")
        if isinstance(pnl, dict):
            out["_pnl_provenance"] = pnl
        out["_source_kind"] = "REAL_DEMO_ACCOUNT"
        return out

    return None


def candidate_feed_paths() -> list[Path]:
    paths: list[Path] = []
    env_feed = str(os.environ.get(ENV_FEED_PATH, "") or "").strip()
    if env_feed:
        paths.append(Path(env_feed))

    root = str(os.environ.get(ENV_EVIDENCE_ROOT, "") or "").strip()
    if root:
        root_path = Path(root)
        paths.extend(
            [
                root_path / "founder_demo_monitor_live.json",
                root_path / "v18_2_25_core.json",
                root_path / "v18_2_24_core.json",
                root_path / "v18_2_23_core.json",
            ]
        )

    feed_only = str(os.environ.get(ENV_FEED_ONLY, "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not (feed_only or env_feed):
        for p in DEFAULT_LIVE_FEED_CANDIDATES:
            paths.append(Path(p))

    # De-dupe while preserving order.
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _paths_equal(a: Path, b: Path) -> bool:
    try:
        return a.resolve().as_posix().lower() == b.resolve().as_posix().lower()
    except OSError:
        return str(a).lower() == str(b).lower()


def load_raw_monitor_feed() -> tuple[dict[str, Any] | None, str | None, str]:
    """
    Returns (raw_blob, source_path, status).
    status: FEED_READY | FEED_UNAVAILABLE | FEED_UNPARSEABLE | FEED_STALE_CORE
    """
    env_feed_raw = str(os.environ.get(ENV_FEED_PATH, "") or "").strip()
    env_feed_path = Path(env_feed_raw) if env_feed_raw else None

    tried: list[str] = []
    for path in candidate_feed_paths():
        tried.append(str(path))
        doc = _safe_read_json(path)
        if doc is None:
            continue
        blob = _extract_monitor_blob(doc)
        if blob is None:
            # File exists but no monitor contract — keep looking.
            continue
        name = path.name.lower()
        if name == "v18_2_25_core.json" or name.startswith("founder_demo_monitor"):
            return blob, str(path), "FEED_READY"
        if env_feed_path is not None and _paths_equal(path, env_feed_path):
            return blob, str(path), "FEED_READY"
        # Older core evidence exists but Agent B v25 campaign feed is not ready.
        if blob.get("schema") or blob.get("_source_kind") == "REAL_DEMO_ACCOUNT":
            return blob, str(path), "FEED_STALE_CORE"

    if any(Path(p).is_file() for p in tried):
        return None, None, "FEED_UNPARSEABLE"
    return None, None, "FEED_UNAVAILABLE"
