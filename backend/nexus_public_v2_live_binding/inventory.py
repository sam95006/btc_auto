"""Visible UI component inventory for PUB2-B live end-to-end binding.

Each component declares the live field slot(s) it must bind, and whether
numeric zero is a legitimate policy value (rare — e.g. qualification_ready_count).
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.nexus_public_ui_trace.component_catalog import UI_COMPONENT_CATALOG


@dataclass(frozen=True)
class LiveFieldSlot:
    """One visible value on a component, mapped to a public-safe live field."""

    slot_id: str
    live_field_id: str
    unit_hint: str | None = None
    allow_zero_when_available: bool = False


@dataclass(frozen=True)
class ComponentLiveSpec:
    component_id: str
    page: str
    kind: str
    label: str
    slots: tuple[LiveFieldSlot, ...]


def _slot(slot_id: str, field: str, unit: str | None = None, *, allow_zero: bool = False) -> LiveFieldSlot:
    return LiveFieldSlot(
        slot_id=slot_id,
        live_field_id=field,
        unit_hint=unit,
        allow_zero_when_available=allow_zero,
    )


# Map every catalog component to at least one public-safe live field.
# Decision/evidence surfaces bind decision.cloud.* or system.* honesty fields
# when no dedicated live series exists yet — never demoCatalog numbers as LIVE.
_SLOT_MAP: dict[str, tuple[LiveFieldSlot, ...]] = {
    # Home
    "home.hero_decision_summary": (
        _slot("posture", "decision.cloud.availability", "status"),
        _slot("freshness", "decision.cloud.freshness", "band"),
    ),
    "home.market_context_card": (
        _slot("btc", "market.last_price.BTCUSDT", "USD"),
        _slot("health", "system.runtime_health", "status"),
    ),
    "home.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "home.confidence_gauge": (_slot("availability", "decision.cloud.availability", "status"),),
    "home.risk_open_chip": (_slot("qual", "system.qualification_state", "status"),),
    "home.alert_notification": (_slot("capture", "system.capture_campaign_health", "status"),),
    "home.regime_chart": (_slot("btc", "market.last_price.BTCUSDT", "USD"),),
    # Market
    "market.overview_btc_card": (_slot("price", "market.last_price.BTCUSDT", "USD"),),
    "market.overview_eth_card": (_slot("price", "market.last_price.ETHUSDT", "USD"),),
    "market.freshness_card": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "market.availability_card": (_slot("availability", "decision.cloud.availability", "status"),),
    "market.symbols_table": (
        _slot("btc", "market.last_price.BTCUSDT", "USD"),
        _slot("eth", "market.last_price.ETHUSDT", "USD"),
        _slot("sol", "market.last_price.SOLUSDT", "USD"),
    ),
    "market.regime_chip": (_slot("mark", "market.mark_price.BTCUSDT", "USD"),),
    "market.freshness_gauge": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "market.completeness_chart": (_slot("funding", "market.funding_rate.BTCUSDT", "rate"),),
    # Decision Feed
    "decisions.feed_table": (
        _slot("availability", "decision.cloud.availability", "status"),
        _slot("freshness", "decision.cloud.freshness", "band"),
    ),
    "decisions.summary_card": (_slot("availability", "decision.cloud.availability", "status"),),
    "decisions.posture_chip": (_slot("availability", "decision.cloud.availability", "status"),),
    "decisions.confidence_gauge": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "decisions.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "decisions.posture_chart": (_slot("btc", "market.last_price.BTCUSDT", "USD"),),
    # Decision Detail
    "detail.decision_summary": (_slot("availability", "decision.cloud.availability", "status"),),
    "detail.thesis_card": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "detail.context_card": (_slot("btc", "market.last_price.BTCUSDT", "USD"),),
    "detail.evidence_table": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "detail.counter_evidence_table": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "detail.risk_table": (_slot("qual", "system.qualification_state", "status"),),
    "detail.confidence_gauge": (_slot("availability", "decision.cloud.availability", "status"),),
    "detail.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "detail.outcome_card": (_slot("qual", "system.qualification_state", "status"),),
    "detail.calibration_chart": (_slot("funding", "market.funding_rate.BTCUSDT", "rate"),),
    # Evidence
    "evidence.list_table": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "evidence.summary_card": (_slot("availability", "decision.cloud.availability", "status"),),
    "evidence.polarity_chip": (_slot("availability", "decision.cloud.availability", "status"),),
    "evidence.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "evidence.polarity_chart": (_slot("btc", "market.last_price.BTCUSDT", "USD"),),
    # Counter
    "counter.list_table": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "counter.summary_card": (_slot("availability", "decision.cloud.availability", "status"),),
    "counter.polarity_chip": (_slot("availability", "decision.cloud.availability", "status"),),
    "counter.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    # Risk
    "risk.conditions_table": (_slot("qual", "system.qualification_state", "status"),),
    "risk.open_gauge": (
        _slot("ready_count", "system.qualification_ready_count", "count", allow_zero=True),
    ),
    "risk.severity_chip": (_slot("qual", "system.qualification_state", "status"),),
    "risk.alert_notification": (_slot("capture", "system.capture_campaign_health", "status"),),
    "risk.severity_chart": (_slot("event", "system.event_study_readiness", "status"),),
    # Thesis
    "thesis.monitor_table": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "thesis.status_chip": (_slot("availability", "decision.cloud.availability", "status"),),
    "thesis.drift_card": (_slot("reflection", "system.reflection_v23_progress", "status"),),
    "thesis.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "thesis.status_chart": (_slot("btc", "market.last_price.BTCUSDT", "USD"),),
    # Alerts
    "alerts.notification_list": (_slot("capture", "system.capture_campaign_health", "status"),),
    "alerts.severity_chip": (_slot("qual", "system.qualification_state", "status"),),
    "alerts.kind_table": (_slot("runtime", "system.runtime_health", "status"),),
    "alerts.count_gauge": (
        _slot("ready_count", "system.qualification_ready_count", "count", allow_zero=True),
    ),
    # Memory
    "memory.decision_table": (_slot("availability", "decision.cloud.availability", "status"),),
    "memory.summary_card": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "memory.freshness_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "memory.timeline_chart": (_slot("btc", "market.last_price.BTCUSDT", "USD"),),
    # Outcome
    "outcome.review_table": (_slot("qual", "system.qualification_state", "status"),),
    "outcome.class_chip": (_slot("event", "system.event_study_readiness", "status"),),
    "outcome.review_card": (_slot("reflection", "system.reflection_v23_progress", "status"),),
    "outcome.class_chart": (
        _slot("ready_count", "system.qualification_ready_count", "count", allow_zero=True),
    ),
    # NEX AI
    "nexai.availability_card": (_slot("availability", "decision.cloud.availability", "status"),),
    "nexai.disclaimer_chip": (_slot("qual", "system.qualification_state", "status"),),
    "nexai.status_gauge": (_slot("runtime", "system.runtime_health", "status"),),
    # Membership / Account / Privacy / Deletion / Notify
    # These are entitlement/settings surfaces — bind honesty system fields, never fabricated tiers.
    "membership.tier_card": (_slot("availability", "decision.cloud.availability", "status"),),
    "membership.entitlement_chip": (_slot("qual", "system.qualification_state", "status"),),
    "membership.billing_note_card": (_slot("event", "system.event_study_readiness", "status"),),
    "account.profile_card": (_slot("runtime", "system.runtime_health", "status"),),
    "account.locale_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "privacy.consent_table": (_slot("availability", "decision.cloud.availability", "status"),),
    "privacy.consent_chip": (_slot("qual", "system.qualification_state", "status"),),
    "deletion.request_card": (_slot("runtime", "system.runtime_health", "status"),),
    "deletion.export_chip": (_slot("availability", "decision.cloud.availability", "status"),),
    "notify.settings_table": (_slot("freshness", "decision.cloud.freshness", "band"),),
    "notify.decision_chip": (_slot("availability", "decision.cloud.availability", "status"),),
    "notify.risk_chip": (_slot("qual", "system.qualification_state", "status"),),
    "notify.stale_chip": (_slot("freshness", "decision.cloud.freshness", "band"),),
}


def build_component_live_specs() -> tuple[ComponentLiveSpec, ...]:
    specs: list[ComponentLiveSpec] = []
    for comp in UI_COMPONENT_CATALOG:
        slots = _SLOT_MAP.get(comp.component_id)
        if not slots:
            raise AssertionError(f"PUB2-B missing live slot map for {comp.component_id}")
        specs.append(
            ComponentLiveSpec(
                component_id=comp.component_id,
                page=comp.page,
                kind=comp.kind,
                label=comp.label,
                slots=slots,
            )
        )
    return tuple(specs)


COMPONENT_LIVE_SPECS: tuple[ComponentLiveSpec, ...] = build_component_live_specs()


def specs_by_id() -> dict[str, ComponentLiveSpec]:
    return {s.component_id: s for s in COMPONENT_LIVE_SPECS}
