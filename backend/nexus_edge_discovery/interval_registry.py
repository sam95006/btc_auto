"""Development interval registry — exploration vs confirmation; excludes reserved OOS."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import (
    RESEARCH_V2_V3_END_MS,
    SEPTEMBER_OOS_END_MS,
    SEPTEMBER_OOS_START_MS,
)
from backend.nexus_edge_discovery import INTERVAL_REGISTRY
from backend.nexus_strategy_engine.broad_acquisition import DEV_END_MS, DEV_START_MS


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _ms_label(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_development_interval_registry(root) -> dict[str, Any]:
    try:
        from backend.nexus_demo_execution.closed_historical_registry import build_used_interval_registry

        used_intervals = [asdict_safe(u) for u in build_used_interval_registry(root)]
    except Exception:
        used_intervals = [
            {
                "label": "SEPTEMBER_H3_RESERVED_OOS",
                "start_ms": SEPTEMBER_OOS_START_MS,
                "end_ms": SEPTEMBER_OOS_END_MS,
                "category": "RESERVED_OOS",
            }
        ]

    # Current V1.2 window
    v12_start = DEV_START_MS
    v12_end = DEV_END_MS
    span = v12_end - v12_start
    # First 60% exploration, last 40% confirmation — sealed before mechanism proposals
    split = v12_start + int(span * 0.60)
    exploration = [{"start_ms": v12_start, "end_ms": split - 1, "label": "EVENT_EXPLORATION_PRIMARY"}]
    confirmation = [{"start_ms": split, "end_ms": v12_end, "label": "DEVELOPMENT_CONFIRMATION_PRIMARY"}]
    excluded = [
        {
            "label": "SEPTEMBER_H3_RESERVED_OOS",
            "start_ms": SEPTEMBER_OOS_START_MS,
            "end_ms": SEPTEMBER_OOS_END_MS,
            "reason": "RESERVED_UNTOUCHED",
        },
        {
            "label": "ALL_FUTURE_UNTOUCHED_RESERVATIONS",
            "start_ms": SEPTEMBER_OOS_END_MS + 1,
            "end_ms": SEPTEMBER_OOS_END_MS + 365 * 86_400_000,
            "reason": "FUTURE_RESERVATION_EXCLUDED",
        },
    ]
    for u in used_intervals:
        excluded.append({**u, "reason": "CONSUMED_OR_RESERVED"})

    payload = {
        "schema": INTERVAL_REGISTRY,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "v1_2_development_window": {
            "start_ms": v12_start,
            "end_ms": v12_end,
            "start_utc": _ms_label(v12_start),
            "end_utc": _ms_label(v12_end),
            "approx_local_note": "2026-04-04 17:30 +08 through 2026-08-02 17:30 +08",
        },
        "EVENT_EXPLORATION_INTERVALS": exploration,
        "DEVELOPMENT_CONFIRMATION_INTERVALS": confirmation,
        "excluded_intervals": excluded,
        "confirmation_sealed_before_mechanism_proposals": True,
        "is_formal_walk_forward": False,
        "is_oos": False,
        "research_v2_v3_end_ms": RESEARCH_V2_V3_END_MS,
    }
    payload["registry_checksum"] = _sha(
        {
            "exploration": exploration,
            "confirmation": confirmation,
            "excluded_labels": [e.get("label") for e in excluded],
        }
    )
    return payload


def asdict_safe(u: Any) -> dict[str, Any]:
    return {
        "source": getattr(u, "source", None),
        "label": getattr(u, "label", None),
        "start_ms": getattr(u, "start_ms", None),
        "end_ms": getattr(u, "end_ms", None),
        "category": getattr(u, "category", None),
    }


def interval_contains(ts_ms: int, intervals: list[dict[str, Any]]) -> bool:
    for iv in intervals:
        if int(iv["start_ms"]) <= ts_ms <= int(iv["end_ms"]):
            return True
    return False
