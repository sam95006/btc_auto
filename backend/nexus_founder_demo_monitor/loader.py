"""Load founder demo-monitor feed from Agent B campaign / evidence coordinator."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_founder_demo_monitor.constants import (
    CORE_FEED_READY_NAMES,
    DEFAULT_LIVE_FEED_CANDIDATES,
    ENV_EVIDENCE_ROOT,
    ENV_FEED_ONLY,
    ENV_FEED_PATH,
    STALE_CORE_NAMES,
)
from backend.nexus_founder_demo_monitor.core_feed import build_monitor_from_core_evidence


def _is_fixture_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return "fixtures" in parts


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
    schema = str(doc.get("schema", "") or "")
    if schema.startswith("v18_2_2") and doc.get("REAL_DEMO_ACCOUNT"):
        built = build_monitor_from_core_evidence(doc)
        if built:
            return built

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

    real_demo = doc.get("REAL_DEMO_ACCOUNT")
    if isinstance(real_demo, dict) and real_demo:
        built = build_monitor_from_core_evidence(doc)
        if built:
            return built
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
                root_path / "v18_2_28_core.json",
                root_path / "v18_2_27_core.json",
                root_path / "v18_2_26_core.json",
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


def _classify_feed(path: Path, blob: dict[str, Any]) -> str:
    name = path.name.lower()
    if _is_fixture_path(path):
        return "FEED_FIXTURE_FALLBACK"
    if name in CORE_FEED_READY_NAMES or name.startswith("founder_demo_monitor"):
        return "FEED_READY"
    env_feed_raw = str(os.environ.get(ENV_FEED_PATH, "") or "").strip()
    if env_feed_raw and _paths_equal(path, Path(env_feed_raw)):
        return "FEED_READY"
    if name in STALE_CORE_NAMES:
        return "FEED_STALE_CORE"
    if blob.get("schema") or blob.get("_source_kind") in ("REAL_DEMO_ACCOUNT", "CORE_EVIDENCE"):
        return "FEED_READY"
    return "FEED_UNPARSEABLE"


def load_raw_monitor_feed() -> tuple[dict[str, Any] | None, str | None, str, bool]:
    """
    Returns (raw_blob, source_path, status, fixture_used).
    status: FEED_READY | FEED_UNAVAILABLE | FEED_UNPARSEABLE | FEED_STALE_CORE | FEED_FIXTURE_FALLBACK
    """
    env_feed_raw = str(os.environ.get(ENV_FEED_PATH, "") or "").strip()
    env_feed_path = Path(env_feed_raw) if env_feed_raw else None

    tried: list[str] = []
    fixture_candidate: tuple[dict[str, Any], str] | None = None

    for path in candidate_feed_paths():
        tried.append(str(path))
        doc = _safe_read_json(path)
        if doc is None:
            continue
        blob = _extract_monitor_blob(doc)
        if blob is None:
            continue

        status = _classify_feed(path, blob)
        if status == "FEED_FIXTURE_FALLBACK":
            fixture_candidate = (blob, str(path))
            continue
        if status == "FEED_STALE_CORE":
            continue
        if status == "FEED_READY":
            return blob, str(path), status, False

    if fixture_candidate is not None:
        blob, source = fixture_candidate
        return blob, source, "FEED_FIXTURE_FALLBACK", True

    if any(Path(p).is_file() for p in tried):
        return None, None, "FEED_UNPARSEABLE", False
    return None, None, "FEED_UNAVAILABLE", False
