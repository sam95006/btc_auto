"""Machine-verifiable bindings: UI component → public DTO field path(s)."""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.nexus_public_ui_trace.component_catalog import UI_COMPONENT_CATALOG, catalog_by_id
from backend.nexus_public_ui_trace.constants import DENIED_PRIVATE_FIELDS
from backend.nexus_public_ui_trace.public_dto_registry import all_dto_paths, dto_path


@dataclass(frozen=True)
class FieldBinding:
    """One visible value slot bound to a public DTO path."""

    dto_path: str
    value_source: str  # LIVE | DEMO | MOCK
    freshness_state: str  # FRESH | STALE | DEGRADED | UNAVAILABLE | DEMO
    stale_indicator_present: bool
    unavailable_indicator_present: bool
    fabricated_when_unavailable: bool = False
    visible_value_kind: str = "dto"  # dto | mock | fabricated


@dataclass(frozen=True)
class ComponentBinding:
    component_id: str
    mode: str  # LIVE | DEMO | MOCK
    fields: tuple[FieldBinding, ...] = field(default_factory=tuple)

    @property
    def mapped(self) -> bool:
        return len(self.fields) > 0


def _live(
    path: str,
    *,
    freshness: str = "FRESH",
    stale_indicator: bool | None = None,
    unavailable_indicator: bool | None = None,
    fabricated: bool = False,
) -> FieldBinding:
    if freshness == "STALE":
        ind = True if stale_indicator is None else stale_indicator
    else:
        ind = False if stale_indicator is None else stale_indicator
    if freshness == "UNAVAILABLE":
        uind = True if unavailable_indicator is None else unavailable_indicator
        kind = "fabricated" if fabricated else "dto"
    else:
        uind = False if unavailable_indicator is None else unavailable_indicator
        kind = "dto"
    return FieldBinding(
        dto_path=path,
        value_source="LIVE",
        freshness_state=freshness,
        stale_indicator_present=ind,
        unavailable_indicator_present=uind,
        fabricated_when_unavailable=fabricated,
        visible_value_kind=kind,
    )


def _bindings() -> dict[str, ComponentBinding]:
    """Canonical LIVE bindings — every catalog component mapped to public DTOs only."""
    p = dto_path
    b: dict[str, ComponentBinding] = {}

    def put(cid: str, *fields: FieldBinding) -> None:
        b[cid] = ComponentBinding(component_id=cid, mode="LIVE", fields=fields)

    # Home
    put(
        "home.hero_decision_summary",
        _live(p("DecisionSummaryDto", "decision_id")),
        _live(p("DecisionSummaryDto", "decision_title")),
        _live(p("DecisionSummaryDto", "decision_posture")),
        _live(p("DecisionSummaryDto", "symbol")),
        _live(p("DecisionSummaryDto", "freshness_state")),
        _live(p("DecisionSummaryDto", "stale_indicator"), freshness="FRESH"),
    )
    put(
        "home.market_context_card",
        _live(p("MarketOverviewDto", "market_state")),
        _live(p("MarketOverviewDto", "regime_label")),
        _live(p("MarketOverviewDto", "as_of")),
    )
    put("home.freshness_chip", _live(p("MarketOverviewDto", "freshness_state")))
    put("home.confidence_gauge", _live(p("DecisionSummaryDto", "confidence_band")))
    put("home.risk_open_chip", _live(p("RiskAlertDto", "count")))
    put(
        "home.alert_notification",
        _live(p("NotificationDto", "alert_code")),
        _live(p("NotificationDto", "alert_message")),
        _live(p("NotificationDto", "alert_severity")),
    )
    put("home.regime_chart", _live(p("MarketOverviewDto", "regime_label")), _live(p("MarketOverviewDto", "as_of")))

    # Market
    put("market.overview_btc_card", _live(p("MarketOverviewDto", "market_state")), _live(p("MarketOverviewDto", "symbol")))
    put("market.overview_eth_card", _live(p("MarketOverviewDto", "market_state")), _live(p("MarketOverviewDto", "symbols")))
    put("market.freshness_card", _live(p("MarketOverviewDto", "data_freshness")), _live(p("MarketOverviewDto", "freshness_state")))
    put("market.availability_card", _live(p("MarketOverviewDto", "system_availability")))
    put("market.symbols_table", _live(p("MarketOverviewDto", "symbols")), _live(p("MarketOverviewDto", "retrieved_at")))
    put("market.regime_chip", _live(p("MarketOverviewDto", "regime_label")))
    put("market.freshness_gauge", _live(p("MarketOverviewDto", "data_freshness")))
    put("market.completeness_chart", _live(p("MarketOverviewDto", "data_completeness")))

    # Decision Feed
    put(
        "decisions.feed_table",
        _live(p("DecisionSummaryDto", "decision_id")),
        _live(p("DecisionSummaryDto", "decision_title")),
        _live(p("DecisionSummaryDto", "decision_posture")),
        _live(p("DecisionSummaryDto", "symbol")),
        _live(p("DecisionSummaryDto", "as_of")),
    )
    put(
        "decisions.summary_card",
        _live(p("DecisionSummaryDto", "decision_title")),
        _live(p("DecisionSummaryDto", "decision_posture")),
        _live(p("DecisionSummaryDto", "confidence_band")),
    )
    put("decisions.posture_chip", _live(p("DecisionSummaryDto", "decision_posture")))
    put("decisions.confidence_gauge", _live(p("DecisionSummaryDto", "confidence_calibration")))
    put("decisions.freshness_chip", _live(p("DecisionSummaryDto", "freshness_state")))
    put("decisions.posture_chart", _live(p("DecisionSummaryDto", "decision_posture")), _live(p("DecisionSummaryDto", "count")))

    # Decision Detail
    put(
        "detail.decision_summary",
        _live(p("DecisionSummaryDto", "decision_id")),
        _live(p("DecisionSummaryDto", "decision_title")),
        _live(p("DecisionSummaryDto", "decision_posture")),
        _live(p("DecisionSummaryDto", "decision_state")),
    )
    put("detail.thesis_card", _live(p("DecisionSummaryDto", "thesis_status")), _live(p("DecisionSummaryDto", "thesis_horizon")))
    put("detail.context_card", _live(p("MarketOverviewDto", "market_state")), _live(p("MarketOverviewDto", "as_of")))
    put("detail.evidence_table", _live(p("DecisionDetailDto", "evidence_summaries")))
    put("detail.counter_evidence_table", _live(p("DecisionDetailDto", "contradicting_evidence")))
    put("detail.risk_table", _live(p("DecisionDetailDto", "risk_alerts")))
    put("detail.confidence_gauge", _live(p("DecisionSummaryDto", "confidence_band")))
    put("detail.freshness_chip", _live(p("DecisionSummaryDto", "freshness_state")))
    put(
        "detail.outcome_card",
        _live(p("DecisionDetailDto", "outcome_status")),
        _live(p("DecisionDetailDto", "outcome_review_classification")),
    )
    put("detail.calibration_chart", _live(p("DecisionSummaryDto", "confidence_calibration")))

    # Evidence
    put(
        "evidence.list_table",
        _live(p("EvidenceDto", "evidence_summary")),
        _live(p("EvidenceDto", "source_label")),
        _live(p("EvidenceDto", "as_of")),
    )
    put("evidence.summary_card", _live(p("EvidenceDto", "evidence_summary")))
    put("evidence.polarity_chip", _live(p("EvidenceDto", "evidence_polarity")))
    put("evidence.freshness_chip", _live(p("EvidenceDto", "evidence_freshness")))
    put("evidence.polarity_chart", _live(p("EvidenceDto", "evidence_polarity")), _live(p("DecisionSummaryDto", "citation_count")))

    # Counter Evidence
    put(
        "counter.list_table",
        _live(p("DecisionDetailDto", "contradicting_evidence")),
        _live(p("EvidenceDto", "evidence_polarity")),
    )
    put("counter.summary_card", _live(p("EvidenceDto", "evidence_summary")))
    put("counter.polarity_chip", _live(p("EvidenceDto", "evidence_polarity")))
    put("counter.freshness_chip", _live(p("EvidenceDto", "freshness_state")))

    # Risk
    put(
        "risk.conditions_table",
        _live(p("RiskAlertDto", "risk_alert")),
        _live(p("RiskAlertDto", "alert_severity")),
        _live(p("RiskAlertDto", "alert_message")),
        _live(p("RiskAlertDto", "status")),
    )
    put("risk.open_gauge", _live(p("RiskAlertDto", "count")))
    put("risk.severity_chip", _live(p("RiskAlertDto", "alert_severity")))
    put(
        "risk.alert_notification",
        _live(p("RiskAlertDto", "alert_code")),
        _live(p("RiskAlertDto", "alert_message")),
    )
    put("risk.severity_chart", _live(p("RiskAlertDto", "alert_severity")), _live(p("RiskAlertDto", "count")))

    # Thesis
    put(
        "thesis.monitor_table",
        _live(p("ThesisMonitorDto", "decision_id")),
        _live(p("ThesisMonitorDto", "thesis_status")),
        _live(p("ThesisMonitorDto", "thesis_horizon")),
        _live(p("ThesisMonitorDto", "as_of")),
    )
    put("thesis.status_chip", _live(p("ThesisMonitorDto", "thesis_status")))
    put("thesis.drift_card", _live(p("ThesisMonitorDto", "message")), _live(p("ThesisMonitorDto", "freshness_state")))
    put("thesis.freshness_chip", _live(p("ThesisMonitorDto", "freshness_state")))
    put("thesis.status_chart", _live(p("ThesisMonitorDto", "thesis_status")))

    # Alerts
    put(
        "alerts.notification_list",
        _live(p("NotificationDto", "alert_code")),
        _live(p("NotificationDto", "alert_message")),
        _live(p("NotificationDto", "alert_severity")),
        _live(p("NotificationDto", "as_of")),
    )
    put("alerts.severity_chip", _live(p("NotificationDto", "alert_severity")))
    put("alerts.kind_table", _live(p("NotificationDto", "alert_code")), _live(p("NotificationDto", "decision_id")))
    put("alerts.count_gauge", _live(p("RiskAlertDto", "count")))

    # Memory
    put(
        "memory.decision_table",
        _live(p("DecisionSummaryDto", "decision_id")),
        _live(p("DecisionSummaryDto", "symbol")),
        _live(p("DecisionSummaryDto", "decision_posture")),
        _live(p("DecisionSummaryDto", "as_of")),
    )
    put(
        "memory.summary_card",
        _live(p("DecisionSummaryDto", "decision_title")),
        _live(p("DecisionSummaryDto", "decision_state")),
    )
    put("memory.freshness_chip", _live(p("DecisionSummaryDto", "freshness_state")))
    put("memory.timeline_chart", _live(p("DecisionSummaryDto", "as_of")), _live(p("DecisionSummaryDto", "count")))

    # Outcome
    put(
        "outcome.review_table",
        _live(p("OutcomeReviewDto", "decision_id")),
        _live(p("OutcomeReviewDto", "symbol")),
        _live(p("OutcomeReviewDto", "outcome_status")),
        _live(p("OutcomeReviewDto", "outcome_review_classification")),
    )
    put("outcome.class_chip", _live(p("OutcomeReviewDto", "outcome_review_classification")))
    put("outcome.review_card", _live(p("OutcomeReviewDto", "review_note")), _live(p("OutcomeReviewDto", "outcome_status")))
    put("outcome.class_chart", _live(p("OutcomeReviewDto", "outcome_review_classification")))

    # NEX AI
    put("nexai.availability_card", _live(p("NexAiDto", "nex_ai_availability")), _live(p("NexAiDto", "system_availability")))
    put("nexai.disclaimer_chip", _live(p("NexAiDto", "nex_ai_disclaimer")))
    put("nexai.status_gauge", _live(p("NexAiDto", "nex_ai_availability")))

    # Membership
    put("membership.tier_card", _live(p("MembershipDto", "tier_name")), _live(p("MembershipDto", "tier_blurb")))
    put("membership.entitlement_chip", _live(p("MembershipDto", "entitlement_labels")))
    put("membership.billing_note_card", _live(p("MembershipDto", "billing_note")))

    # Account / Privacy / Deletion / Notify
    put("account.profile_card", _live(p("AccountDto", "display_name")), _live(p("AccountDto", "email_masked")))
    put("account.locale_chip", _live(p("AccountDto", "locale")), _live(p("AccountDto", "timezone")))
    put(
        "privacy.consent_table",
        _live(p("PrivacyDto", "consent_marketing")),
        _live(p("PrivacyDto", "consent_analytics")),
        _live(p("PrivacyDto", "consent_crash")),
    )
    put("privacy.consent_chip", _live(p("PrivacyDto", "consent_analytics")))
    put("deletion.request_card", _live(p("AccountDeletionDto", "deletion_requested")))
    put("deletion.export_chip", _live(p("AccountDeletionDto", "export_requested")))
    put(
        "notify.settings_table",
        _live(p("NotificationSettingsDto", "notify_decision")),
        _live(p("NotificationSettingsDto", "notify_risk")),
        _live(p("NotificationSettingsDto", "notify_stale")),
        _live(p("NotificationSettingsDto", "notify_thesis")),
        _live(p("NotificationSettingsDto", "notify_anomaly")),
    )
    put("notify.decision_chip", _live(p("NotificationSettingsDto", "notify_decision")))
    put("notify.risk_chip", _live(p("NotificationSettingsDto", "notify_risk")))
    put("notify.stale_chip", _live(p("NotificationSettingsDto", "notify_stale")))

    return b


LIVE_COMPONENT_BINDINGS: dict[str, ComponentBinding] = _bindings()


def assert_bindings_complete() -> None:
    catalog = catalog_by_id()
    missing = sorted(set(catalog) - set(LIVE_COMPONENT_BINDINGS))
    extra = sorted(set(LIVE_COMPONENT_BINDINGS) - set(catalog))
    if missing or extra:
        raise AssertionError(f"binding/catalog mismatch missing={missing} extra={extra}")
    known = all_dto_paths()
    for cid, binding in LIVE_COMPONENT_BINDINGS.items():
        if not binding.fields:
            raise AssertionError(f"unmapped binding: {cid}")
        for f in binding.fields:
            if f.dto_path not in known:
                raise AssertionError(f"{cid} unknown dto_path={f.dto_path}")
            leaf = f.dto_path.rsplit(".", 1)[-1]
            if leaf in DENIED_PRIVATE_FIELDS:
                raise AssertionError(f"{cid} private leaf={leaf}")


def binding_rows() -> list[dict[str, str]]:
    """Flat machine-readable mapping rows."""
    rows: list[dict[str, str]] = []
    by_id = catalog_by_id()
    for cid, binding in sorted(LIVE_COMPONENT_BINDINGS.items()):
        comp = by_id[cid]
        for f in binding.fields:
            rows.append(
                {
                    "component_id": cid,
                    "page": comp.page,
                    "kind": comp.kind,
                    "label": comp.label,
                    "mode": binding.mode,
                    "dto_path": f.dto_path,
                    "value_source": f.value_source,
                    "freshness_state": f.freshness_state,
                    "stale_indicator_present": str(f.stale_indicator_present).lower(),
                    "unavailable_indicator_present": str(f.unavailable_indicator_present).lower(),
                }
            )
    return rows


def catalog_component_count() -> int:
    return len(UI_COMPONENT_CATALOG)
