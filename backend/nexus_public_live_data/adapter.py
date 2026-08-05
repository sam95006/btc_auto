"""Public Live Data Adapter (PUB-C) — LIVE vs FIXTURE with mandatory lineage."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from backend.nexus_public_live_data.constants import (
    BASE_COMMIT,
    BRANCH,
    DEMO_DATA_BANNER,
    HARD_BANS,
    LANE,
    LANE_NAME,
    LINEAGE_REQUIRED_KEYS,
    MODE_FIXTURE,
    MODE_LIVE,
    PACKAGE,
    PUBLIC_SAFE_FIELDS,
    SCHEMA_VERSION,
)
from backend.nexus_public_live_data.lineage import LineageBoundValue, demo_bound, utc_iso
from backend.nexus_public_live_data.sanitize import assert_no_forbidden_keys
from backend.nexus_public_live_data import sources

# Re-export mode constants for consumers / routes
__all_modes__ = (MODE_LIVE, MODE_FIXTURE)
_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "demo_catalog.json"
_FIXTURE_CACHE: dict[str, Any] | None = None


class LiveModeFixtureLeakError(RuntimeError):
    """Raised when LIVE mode would silently serve fixture/DEMO_DATA values."""


def resolve_mode(explicit: str | None = None) -> str:
    raw = (explicit or os.environ.get("NEXUS_PUBLIC_LIVE_DATA_MODE") or MODE_LIVE).strip().upper()
    if raw in ("DEMO", "DEMO_DATA", "FIXTURE", "PREVIEW"):
        return MODE_FIXTURE
    return MODE_LIVE


def load_demo_catalog(*, reload: bool = False) -> dict[str, Any]:
    global _FIXTURE_CACHE
    if _FIXTURE_CACHE is not None and not reload:
        return deepcopy(_FIXTURE_CACHE)
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("demo catalog must be an object")
    _FIXTURE_CACHE = data
    return deepcopy(data)


def _envelope(*, mode: str, **payload: Any) -> dict[str, Any]:
    demo = mode == MODE_FIXTURE
    body: dict[str, Any] = {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "mode": mode,
        "read_only": True,
        "customer_trading": False,
        "exchange_write": False,
        "fabricated_live_values": False,
        "hard_bans": list(HARD_BANS),
        "as_of": utc_iso(),
        "demo_data": demo,
        "banner": DEMO_DATA_BANNER if demo else None,
        "banner_prominent": bool(demo),
        "disclaimer": (
            "DEMO_DATA — fixture catalog only. Not live market data."
            if demo
            else "LIVE mode — real sources only; missing data shows UNAVAILABLE/STALE/DEGRADED/BLOCKED."
        ),
        **payload,
    }
    assert_no_forbidden_keys(body)
    return body


def _fixture_bound(field_id: str) -> LineageBoundValue:
    catalog = load_demo_catalog()
    fields = catalog.get("fields") or {}
    row = fields.get(field_id)
    if not isinstance(row, dict):
        # Even in fixture mode, unknown field is still DEMO_DATA unavailable mark
        return demo_bound(
            field_id=field_id,
            value=None,
            unit=None,
            source_field="missing",
            as_of=catalog.get("generated_at") or utc_iso(),
            note="field absent from DEMO_DATA catalog",
        )
    return demo_bound(
        field_id=field_id,
        value=row.get("value"),
        unit=row.get("unit"),
        source_field=str(row.get("source_field") or field_id),
        as_of=str(row.get("as_of") or catalog.get("generated_at") or utc_iso()),
        note="DEMO_DATA catalog",
    )


def _live_binders() -> dict[str, Callable[[], LineageBoundValue]]:
    return {
        "market.last_price.BTCUSDT": lambda: sources.bind_market_field(
            field_id="market.last_price.BTCUSDT",
            symbol="BTCUSDT",
            source_field="result.list[0].lastPrice",
            unit="USD",
            extractor=lambda r: r.get("lastPrice"),
        ),
        "market.last_price.ETHUSDT": lambda: sources.bind_market_field(
            field_id="market.last_price.ETHUSDT",
            symbol="ETHUSDT",
            source_field="result.list[0].lastPrice",
            unit="USD",
            extractor=lambda r: r.get("lastPrice"),
        ),
        "market.last_price.SOLUSDT": lambda: sources.bind_market_field(
            field_id="market.last_price.SOLUSDT",
            symbol="SOLUSDT",
            source_field="result.list[0].lastPrice",
            unit="USD",
            extractor=lambda r: r.get("lastPrice"),
        ),
        "market.mark_price.BTCUSDT": lambda: sources.bind_market_field(
            field_id="market.mark_price.BTCUSDT",
            symbol="BTCUSDT",
            source_field="result.list[0].markPrice",
            unit="USD",
            extractor=lambda r: r.get("markPrice"),
        ),
        "market.funding_rate.BTCUSDT": lambda: sources.bind_market_field(
            field_id="market.funding_rate.BTCUSDT",
            symbol="BTCUSDT",
            source_field="result.list[0].fundingRate",
            unit="rate",
            extractor=lambda r: r.get("fundingRate"),
        ),
        "system.runtime_health": sources.bind_runtime_health,
        "system.capture_campaign_health": sources.bind_capture_campaign_health,
        "system.reflection_v23_progress": sources.bind_reflection_v23_progress,
        "system.qualification_state": sources.bind_qualification_state,
        "system.event_study_readiness": sources.bind_event_study_readiness,
        "system.qualification_ready_count": sources.bind_qualification_ready_count,
        "decision.cloud.freshness": lambda: sources.bind_decision_cloud_freshness(decision_cloud_meta=None),
        "decision.cloud.availability": lambda: sources.bind_decision_cloud_availability(available=None),
    }


def bind_field(field_id: str, *, mode: str | None = None) -> dict[str, Any]:
    resolved = resolve_mode(mode)
    if field_id not in PUBLIC_SAFE_FIELDS:
        raise KeyError(f"unknown_public_safe_field:{field_id}")
    if resolved == MODE_FIXTURE:
        bound = _fixture_bound(field_id)
    else:
        binder = _live_binders()[field_id]
        bound = binder()
        if bound.demo_data or bound.mode == MODE_FIXTURE:
            raise LiveModeFixtureLeakError(
                f"LIVE mode refused fixture/DEMO_DATA for field {field_id}"
            )
    payload = bound.to_dict()
    for key in LINEAGE_REQUIRED_KEYS:
        if key not in payload:
            raise ValueError(f"lineage incomplete for {field_id}: {key}")
    return payload


def bind_all(*, mode: str | None = None) -> dict[str, Any]:
    resolved = resolve_mode(mode)
    fields: dict[str, Any] = {}
    for field_id in PUBLIC_SAFE_FIELDS:
        fields[field_id] = bind_field(field_id, mode=resolved)
    unavailable = sum(
        1
        for row in fields.values()
        if row.get("display_state") in ("UNAVAILABLE", "BLOCKED") or row.get("value") is None and resolved == MODE_LIVE
    )
    stale = sum(1 for row in fields.values() if row.get("freshness") in ("STALE", "DEGRADED"))
    return _envelope(
        mode=resolved,
        field_count=len(fields),
        fields=fields,
        lineage_required=list(LINEAGE_REQUIRED_KEYS),
        summary={
            "unavailable_or_blocked": unavailable,
            "stale_or_degraded": stale,
            "demo_data_banner": DEMO_DATA_BANNER if resolved == MODE_FIXTURE else None,
            "silent_fixture_fallback": False,
        },
    )


def service_meta(*, mode: str | None = None) -> dict[str, Any]:
    resolved = resolve_mode(mode)
    return _envelope(
        mode=resolved,
        public_safe_fields=list(PUBLIC_SAFE_FIELDS),
        lineage_required=list(LINEAGE_REQUIRED_KEYS),
        modes=[MODE_LIVE, MODE_FIXTURE],
        environment="local_staging",
        methods_allowed=["GET", "HEAD", "OPTIONS"],
    )


def field_catalog(*, mode: str | None = None) -> dict[str, Any]:
    resolved = resolve_mode(mode)
    return _envelope(
        mode=resolved,
        fields=[
            {
                "field_id": fid,
                "lineage_required": list(LINEAGE_REQUIRED_KEYS),
            }
            for fid in PUBLIC_SAFE_FIELDS
        ],
    )


def bind_field_response(field_id: str, *, mode: str | None = None) -> dict[str, Any]:
    """Envelope for a single field binding (HTTP-friendly)."""
    resolved = resolve_mode(mode)
    return _envelope(mode=resolved, field=bind_field(field_id, mode=resolved))
