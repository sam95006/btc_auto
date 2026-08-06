"""Listing/Delisting Events and Contract Spec Timeline builders."""
from __future__ import annotations

from typing import Any

from backend.nexus_historical_universe.fixtures import fixture_instruments
from backend.nexus_historical_universe.hashutil import sha_obj


def build_listing_delisting_events(
    instruments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Emit chronological listing/delisting event log from instrument lifecycles."""
    rows = instruments if instruments is not None else fixture_instruments()
    events: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row["symbol"])
        events.append(
            {
                "event_type": "LISTING",
                "symbol": symbol,
                "canonical_instrument_id": row.get("canonical_instrument_id"),
                "event_ms": int(row["listing_ms"]),
                "status_after": "Trading",
            }
        )
        if row.get("delisting_ms") is not None:
            events.append(
                {
                    "event_type": "DELISTING",
                    "symbol": symbol,
                    "canonical_instrument_id": row.get("canonical_instrument_id"),
                    "event_ms": int(row["delisting_ms"]),
                    "status_after": "Delisted",
                }
            )
    events.sort(key=lambda e: (int(e["event_ms"]), e["event_type"], e["symbol"]))
    return {
        "schema": "v17_e_listing_delisting_events_v1",
        "event_count": len(events),
        "events": events,
        "events_checksum": sha_obj(events),
    }


def build_contract_spec_timeline(
    instruments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Flatten per-instrument contract specification timelines."""
    rows = instruments if instruments is not None else fixture_instruments()
    timeline: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row["symbol"])
        prev: dict[str, Any] | None = None
        for spec in row.get("spec_timeline") or []:
            entry = {
                "symbol": symbol,
                "canonical_instrument_id": row.get("canonical_instrument_id"),
                "effective_ms": int(spec["effective_ms"]),
                "contract_rule_version": spec.get("contract_rule_version"),
                "tick_size": spec.get("tick_size"),
                "qty_step": spec.get("qty_step"),
                "minimum_notional": spec.get("minimum_notional"),
                "minimum_order_qty": spec.get("minimum_order_qty"),
                "contract_type": spec.get("contract_type"),
                "quote_coin": spec.get("quote_coin"),
                "settle_coin": spec.get("settle_coin"),
                "changed_fields": [],
            }
            if prev is not None:
                changed = []
                for k in (
                    "tick_size",
                    "qty_step",
                    "minimum_notional",
                    "minimum_order_qty",
                    "contract_rule_version",
                ):
                    if prev.get(k) != entry.get(k):
                        changed.append(k)
                entry["changed_fields"] = changed
            timeline.append(entry)
            prev = entry
    timeline.sort(key=lambda e: (int(e["effective_ms"]), e["symbol"]))
    return {
        "schema": "v17_e_contract_spec_timeline_v1",
        "entry_count": len(timeline),
        "timeline": timeline,
        "timeline_checksum": sha_obj(timeline),
    }


def events_as_of(as_of_ms: int, instruments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Events known at as_of (event_ms <= as_of)."""
    catalog = build_listing_delisting_events(instruments)
    return [e for e in catalog["events"] if int(e["event_ms"]) <= int(as_of_ms)]


def specs_as_of(as_of_ms: int, instruments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Spec timeline entries effective at or before as_of."""
    catalog = build_contract_spec_timeline(instruments)
    return [e for e in catalog["timeline"] if int(e["effective_ms"]) <= int(as_of_ms)]
