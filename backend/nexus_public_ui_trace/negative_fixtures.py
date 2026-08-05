"""Negative fixtures — prove counters detect contract violations."""
from __future__ import annotations

from backend.nexus_public_ui_trace.bindings import LIVE_COMPONENT_BINDINGS, ComponentBinding, FieldBinding
from backend.nexus_public_ui_trace.public_dto_registry import dto_path


def binding_with_visible_mock() -> dict[str, ComponentBinding]:
    b = dict(LIVE_COMPONENT_BINDINGS)
    cid = "home.freshness_chip"
    b[cid] = ComponentBinding(
        component_id=cid,
        mode="LIVE",
        fields=(
            FieldBinding(
                dto_path=dto_path("MarketOverviewDto", "freshness_state"),
                value_source="MOCK",
                freshness_state="DEMO",
                stale_indicator_present=False,
                unavailable_indicator_present=False,
                visible_value_kind="mock",
            ),
        ),
    )
    return b


def binding_with_unmapped() -> dict[str, ComponentBinding]:
    b = dict(LIVE_COMPONENT_BINDINGS)
    del b["home.regime_chart"]
    return b


def binding_with_private_field() -> dict[str, ComponentBinding]:
    b = dict(LIVE_COMPONENT_BINDINGS)
    cid = "detail.thesis_card"
    b[cid] = ComponentBinding(
        component_id=cid,
        mode="LIVE",
        fields=(
            FieldBinding(
                dto_path="DecisionSummaryDto.strategy_weights",
                value_source="LIVE",
                freshness_state="FRESH",
                stale_indicator_present=False,
                unavailable_indicator_present=False,
            ),
        ),
    )
    return b


def binding_with_stale_without_indicator() -> dict[str, ComponentBinding]:
    b = dict(LIVE_COMPONENT_BINDINGS)
    cid = "market.freshness_card"
    b[cid] = ComponentBinding(
        component_id=cid,
        mode="LIVE",
        fields=(
            FieldBinding(
                dto_path=dto_path("MarketOverviewDto", "data_freshness"),
                value_source="LIVE",
                freshness_state="STALE",
                stale_indicator_present=False,
                unavailable_indicator_present=False,
            ),
        ),
    )
    return b


def binding_with_unavailable_fabrication() -> dict[str, ComponentBinding]:
    b = dict(LIVE_COMPONENT_BINDINGS)
    cid = "market.availability_card"
    b[cid] = ComponentBinding(
        component_id=cid,
        mode="LIVE",
        fields=(
            FieldBinding(
                dto_path=dto_path("MarketOverviewDto", "system_availability"),
                value_source="LIVE",
                freshness_state="UNAVAILABLE",
                stale_indicator_present=False,
                unavailable_indicator_present=False,
                fabricated_when_unavailable=True,
                visible_value_kind="fabricated",
            ),
        ),
    )
    return b
