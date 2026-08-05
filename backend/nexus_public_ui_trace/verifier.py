"""Verify LIVE UI bindings against public DTO contract counters."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_public_ui_trace.bindings import (
    LIVE_COMPONENT_BINDINGS,
    ComponentBinding,
    assert_bindings_complete,
    binding_rows,
)
from backend.nexus_public_ui_trace.component_catalog import (
    UI_COMPONENT_CATALOG,
    catalog_by_id,
    required_kinds_present,
)
from backend.nexus_public_ui_trace.constants import (
    DENIED_PRIVATE_FIELDS,
    FAIL_RECOMMENDATION,
    HARD_BANS,
    LANE,
    PASS_RECOMMENDATION,
    PROGRAM_ID,
    REQUIRED_COUNTERS,
)
from backend.nexus_public_ui_trace.public_dto_registry import (
    assert_registry_allowlisted,
    schema_version,
)


@dataclass(frozen=True)
class TraceabilityCounters:
    visible_mock_value_count: int
    unmapped_live_component_count: int
    private_field_binding_count: int
    stale_without_indicator: int
    unavailable_fabrication: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)

    @property
    def all_zero(self) -> bool:
        return all(v == 0 for v in self.as_dict().values())


def _leaf(dto_path: str) -> str:
    return dto_path.rsplit(".", 1)[-1]


def compute_counters(
    bindings: dict[str, ComponentBinding] | None = None,
    *,
    mode: str = "LIVE",
) -> TraceabilityCounters:
    """Compute required counters for a binding map under the given UI mode."""
    bindings = bindings if bindings is not None else LIVE_COMPONENT_BINDINGS
    catalog = catalog_by_id()

    visible_mock = 0
    unmapped = 0
    private_bind = 0
    stale_no_ind = 0
    unavail_fab = 0

    for cid, comp in catalog.items():
        if not comp.required_in_live:
            continue
        binding = bindings.get(cid)
        if binding is None or not binding.fields:
            if mode == "LIVE":
                unmapped += 1
            continue

        for f in binding.fields:
            leaf = _leaf(f.dto_path)
            path_parts = set(f.dto_path.split("."))
            if leaf in DENIED_PRIVATE_FIELDS or (path_parts & DENIED_PRIVATE_FIELDS):
                private_bind += 1

            if mode == "LIVE":
                if f.value_source in {"MOCK", "DEMO"} or f.visible_value_kind == "mock":
                    visible_mock += 1
                if f.freshness_state == "STALE" and not f.stale_indicator_present:
                    stale_no_ind += 1
                if f.freshness_state == "UNAVAILABLE" and (
                    f.fabricated_when_unavailable or f.visible_value_kind == "fabricated"
                ):
                    unavail_fab += 1

    return TraceabilityCounters(
        visible_mock_value_count=visible_mock,
        unmapped_live_component_count=unmapped,
        private_field_binding_count=private_bind,
        stale_without_indicator=stale_no_ind,
        unavailable_fabrication=unavail_fab,
    )


def verify_ui_data_traceability(
    bindings: dict[str, ComponentBinding] | None = None,
    *,
    mode: str = "LIVE",
) -> dict[str, Any]:
    assert_registry_allowlisted()
    assert_bindings_complete()
    if not required_kinds_present():
        raise AssertionError("catalog missing required component kinds")

    counters = compute_counters(bindings, mode=mode)
    rows = binding_rows()
    kind_counts = {k: 0 for k in ("card", "table", "chart", "gauge", "chip", "notification", "decision_summary")}
    for c in UI_COMPONENT_CATALOG:
        kind_counts[c.kind] = kind_counts.get(c.kind, 0) + 1

    passed = counters.all_zero and mode == "LIVE"
    return {
        "program_id": PROGRAM_ID,
        "lane": LANE,
        "schema_version": schema_version(),
        "mode": mode,
        "status": "PASS" if passed else "FAIL",
        "recommendation": PASS_RECOMMENDATION if passed else FAIL_RECOMMENDATION,
        "counters": counters.as_dict(),
        "required_counters": list(REQUIRED_COUNTERS),
        "component_count": len(UI_COMPONENT_CATALOG),
        "binding_row_count": len(rows),
        "kind_counts": kind_counts,
        "pages": sorted({c.page for c in UI_COMPONENT_CATALOG}),
        "hard_bans": list(HARD_BANS),
        "mapping_sample": rows[:5],
    }
