"""Compute PUB2-B required counters over live UI bindings."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_public_v2_live_binding.binder import bind_all_components
from backend.nexus_public_v2_live_binding.constants import (
    BINDING_REQUIRED_KEYS,
    FAIL_RECOMMENDATION,
    HARD_BANS,
    LANE,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    REQUIRED_COUNTERS,
)
from backend.nexus_public_v2_live_binding.display_rules import is_unavailable_shown_as_zero
from backend.nexus_public_v2_live_binding.inventory import COMPONENT_LIVE_SPECS
from backend.nexus_public_v2_live_binding.source_scan import scan_hardcoded_live_in_frontend
from pathlib import Path


@dataclass(frozen=True)
class LiveBindingCounters:
    hardcoded_live_value_count: int
    fabricated_live_value_count: int
    stale_without_indicator_count: int
    unavailable_shown_as_zero_count: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    @property
    def all_zero(self) -> bool:
        return all(v == 0 for v in self.as_dict().values())


def compute_counters(
    payload: dict[str, Any] | None = None,
    *,
    root: Path | None = None,
) -> LiveBindingCounters:
    data = payload if payload is not None else bind_all_components()
    components = data.get("components") or {}

    hardcoded = 0
    fabricated = 0
    stale_no_ind = 0
    unavail_zero = 0

    for spec in COMPONENT_LIVE_SPECS:
        comp = components.get(spec.component_id)
        if not comp or not comp.get("slots"):
            # Unmapped → treat as fabricated risk (must be bound)
            fabricated += 1
            continue
        for slot in comp["slots"]:
            for key in BINDING_REQUIRED_KEYS:
                if key not in slot or (slot[key] is None and key not in {"as_of", "unit"}):
                    if key == "as_of" and slot.get("freshness") in {"UNAVAILABLE", "BLOCKED"}:
                        continue
                    if key == "unit" and slot.get("unit") is None:
                        # unit may be null for status fields — ok
                        continue
                    if key not in slot:
                        fabricated += 1

            if slot.get("hardcoded") or slot.get("value_source") not in {"LIVE"}:
                hardcoded += 1
            if slot.get("fabricated") or slot.get("demo_data"):
                fabricated += 1
            freshness = str(slot.get("freshness") or "")
            if freshness.upper() in {"STALE", "DEGRADED"} and not slot.get("stale_indicator_present"):
                stale_no_ind += 1
            if is_unavailable_shown_as_zero(
                value=slot.get("raw_value"),
                freshness=freshness,
                completeness=str(slot.get("completeness") or ""),
                display_text=str(slot.get("display_value") or ""),
            ):
                unavail_zero += 1
            # Also catch display_value literally "0" under UNAVAILABLE
            if freshness.upper() in {"UNAVAILABLE", "BLOCKED"} and str(slot.get("display_value")) in {
                "0",
                "0.0",
            }:
                unavail_zero += 1

    if root is not None:
        scan = scan_hardcoded_live_in_frontend(root)
        hardcoded += int(scan.get("count") or 0)

    return LiveBindingCounters(
        hardcoded_live_value_count=hardcoded,
        fabricated_live_value_count=fabricated,
        stale_without_indicator_count=stale_no_ind,
        unavailable_shown_as_zero_count=unavail_zero,
    )


def verify_live_e2e_binding(
    *,
    root: Path | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = payload if payload is not None else bind_all_components()
    counters = compute_counters(data, root=root)
    passed = counters.all_zero
    return {
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "status": "PASS" if passed else "FAIL",
        "recommendation": PASS_RECOMMENDATION if passed else FAIL_RECOMMENDATION,
        "counters": counters.as_dict(),
        "required_counters": list(REQUIRED_COUNTERS),
        "component_count": data.get("component_count"),
        "hard_bans": list(HARD_BANS),
        "mode": data.get("mode"),
        "binding_required_keys": list(BINDING_REQUIRED_KEYS),
    }
