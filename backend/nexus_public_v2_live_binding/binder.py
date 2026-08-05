"""End-to-end binder: UI component → live field → lineage-complete binding."""
from __future__ import annotations

from typing import Any

from backend.nexus_public_live_data import adapter as live_adapter
from backend.nexus_public_live_data.constants import LINEAGE_REQUIRED_KEYS, MODE_LIVE
from backend.nexus_public_live_data.lineage import utc_iso
from backend.nexus_public_v2_live_binding.constants import (
    BASE_COMMIT,
    BINDING_REQUIRED_KEYS,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    MODE_LIVE as V2_MODE_LIVE,
    PACKAGE,
    PROGRAM_ID,
    SCHEMA_VERSION,
)
from backend.nexus_public_v2_live_binding.display_rules import (
    format_display_value,
    requires_stale_indicator,
)
from backend.nexus_public_v2_live_binding.inventory import COMPONENT_LIVE_SPECS, LiveFieldSlot


def _ui_binding_from_live_row(
    *,
    component_id: str,
    slot: LiveFieldSlot,
    live_row: dict[str, Any],
) -> dict[str, Any]:
    freshness = str(live_row.get("freshness") or "UNAVAILABLE")
    completeness = str(live_row.get("completeness") or "MISSING")
    raw_value = live_row.get("value")
    display_text, shown_as_zero = format_display_value(
        raw_value,
        freshness=freshness,
        completeness=completeness,
        allow_zero_when_available=slot.allow_zero_when_available,
    )
    stale_needed = requires_stale_indicator(freshness)
    unavailable = freshness.upper() in {"UNAVAILABLE", "BLOCKED"} or raw_value is None

    binding = {
        "component_id": component_id,
        "slot_id": slot.slot_id,
        "mode": V2_MODE_LIVE,
        "value_source": "LIVE",
        "hardcoded": False,
        "fabricated": False,
        # Required honesty keys (directive)
        "source": live_row.get("source_system") or live_row.get("source") or "UNKNOWN",
        "field": live_row.get("source_field") or slot.live_field_id,
        "unit": live_row.get("unit") if live_row.get("unit") is not None else slot.unit_hint,
        "as_of": live_row.get("as_of"),
        "retrieved_at": live_row.get("retrieved_at"),
        "freshness": freshness,
        "completeness": completeness,
        "quality": live_row.get("quality") or "unknown",
        "lineage": live_row.get("lineage_id") or live_row.get("lineage"),
        "fallback": live_row.get("fallback") or "display_UNAVAILABLE",
        # Extra operational fields
        "live_field_id": slot.live_field_id,
        "raw_value": raw_value,
        "display_value": display_text,
        "display_state": live_row.get("display_state") or freshness,
        "stale_indicator_present": stale_needed,
        "unavailable_indicator_present": unavailable,
        "shown_as_zero": shown_as_zero,
        "demo_data": bool(live_row.get("demo_data")),
        "source_endpoint": live_row.get("source_endpoint"),
        "allow_zero_when_available": slot.allow_zero_when_available,
    }
    for key in BINDING_REQUIRED_KEYS:
        if key not in binding:
            raise ValueError(f"binding missing required key: {key}")
    return binding


def bind_component(component_id: str, *, live_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bind one catalog component to live lineage rows."""
    specs = {s.component_id: s for s in COMPONENT_LIVE_SPECS}
    spec = specs.get(component_id)
    if spec is None:
        raise KeyError(f"unknown_component:{component_id}")

    if live_fields is None:
        envelope = live_adapter.bind_all(mode=MODE_LIVE)
        live_fields = envelope.get("fields") or {}

    slots_out: list[dict[str, Any]] = []
    for slot in spec.slots:
        row = live_fields.get(slot.live_field_id)
        if not isinstance(row, dict):
            # Honest unavailable shell — never fabricate.
            retrieved = utc_iso()
            row = {
                "value": None,
                "unit": slot.unit_hint,
                "source_system": "LIVE_ADAPTER",
                "source_endpoint": f"live://{slot.live_field_id}",
                "source_field": slot.live_field_id,
                "as_of": None,
                "retrieved_at": retrieved,
                "freshness": "UNAVAILABLE",
                "completeness": "MISSING",
                "quality": "field_missing_from_adapter",
                "lineage_id": f"missing_{slot.live_field_id}",
                "fallback": "display_UNAVAILABLE",
                "demo_data": False,
                "display_state": "UNAVAILABLE",
            }
        else:
            for key in LINEAGE_REQUIRED_KEYS:
                if key == "as_of":
                    continue
                if key not in row:
                    raise ValueError(f"live field {slot.live_field_id} missing lineage key {key}")
            if row.get("demo_data") or row.get("mode") == "FIXTURE":
                raise RuntimeError(
                    f"DEMO/FIXTURE leak into LIVE binding for {component_id}/{slot.slot_id}"
                )
        slots_out.append(_ui_binding_from_live_row(component_id=component_id, slot=slot, live_row=row))

    return {
        "component_id": component_id,
        "page": spec.page,
        "kind": spec.kind,
        "label": spec.label,
        "mode": V2_MODE_LIVE,
        "slots": slots_out,
        "slot_count": len(slots_out),
    }


def bind_all_components(*, mode: str | None = None) -> dict[str, Any]:
    """Bind every visible UI component. LIVE only — fixture merge banned."""
    resolved = (mode or V2_MODE_LIVE).strip().upper()
    if resolved != V2_MODE_LIVE:
        raise ValueError("PUB2-B e2e binder is LIVE-only; DEMO/FIXTURE merge refused")

    envelope = live_adapter.bind_all(mode=MODE_LIVE)
    live_fields = envelope.get("fields") or {}
    components: dict[str, Any] = {}
    for spec in COMPONENT_LIVE_SPECS:
        components[spec.component_id] = bind_component(spec.component_id, live_fields=live_fields)

    return {
        "ok": True,
        "schema": SCHEMA_VERSION,
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "package": PACKAGE,
        "base_commit": BASE_COMMIT,
        "mode": V2_MODE_LIVE,
        "read_only": True,
        "customer_trading": False,
        "exchange_write": False,
        "hard_bans": list(HARD_BANS),
        "component_count": len(components),
        "binding_required_keys": list(BINDING_REQUIRED_KEYS),
        "live_field_count": len(live_fields),
        "components": components,
        "as_of": envelope.get("as_of"),
    }
