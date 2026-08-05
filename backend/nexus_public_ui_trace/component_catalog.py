"""Member UI component inventory — every card/table/chart/gauge/chip/notification/decision_summary."""
from __future__ import annotations

from dataclasses import dataclass

from backend.nexus_public_ui_trace.constants import COMPONENT_KINDS


@dataclass(frozen=True)
class UiComponent:
    component_id: str
    page: str
    kind: str
    label: str
    required_in_live: bool = True


def _c(component_id: str, page: str, kind: str, label: str) -> UiComponent:
    if kind not in COMPONENT_KINDS:
        raise ValueError(f"unknown kind: {kind}")
    return UiComponent(component_id=component_id, page=page, kind=kind, label=label)


# Exhaustive public Member Platform inventory (PUB-D page set).
UI_COMPONENT_CATALOG: tuple[UiComponent, ...] = (
    # Home
    _c("home.hero_decision_summary", "Home", "decision_summary", "Home hero Decision summary"),
    _c("home.market_context_card", "Home", "card", "Home market context card"),
    _c("home.freshness_chip", "Home", "chip", "Home freshness chip"),
    _c("home.confidence_gauge", "Home", "gauge", "Home confidence gauge"),
    _c("home.risk_open_chip", "Home", "chip", "Home open-risk chip"),
    _c("home.alert_notification", "Home", "notification", "Home alert notification"),
    _c("home.regime_chart", "Home", "chart", "Home regime spark chart"),
    # Market Overview
    _c("market.overview_btc_card", "Market Overview", "card", "BTC market context card"),
    _c("market.overview_eth_card", "Market Overview", "card", "ETH market context card"),
    _c("market.freshness_card", "Market Overview", "card", "Feed freshness card"),
    _c("market.availability_card", "Market Overview", "card", "System availability card"),
    _c("market.symbols_table", "Market Overview", "table", "Symbols table"),
    _c("market.regime_chip", "Market Overview", "chip", "Regime label chip"),
    _c("market.freshness_gauge", "Market Overview", "gauge", "Freshness gauge"),
    _c("market.completeness_chart", "Market Overview", "chart", "Completeness chart"),
    # Decision Feed
    _c("decisions.feed_table", "Decision Feed", "table", "Decision feed table"),
    _c("decisions.summary_card", "Decision Feed", "decision_summary", "Decision summary card"),
    _c("decisions.posture_chip", "Decision Feed", "chip", "Posture chip"),
    _c("decisions.confidence_gauge", "Decision Feed", "gauge", "Confidence gauge"),
    _c("decisions.freshness_chip", "Decision Feed", "chip", "Feed freshness chip"),
    _c("decisions.posture_chart", "Decision Feed", "chart", "Posture distribution chart"),
    # Decision Detail
    _c("detail.decision_summary", "Decision Detail", "decision_summary", "Decision detail summary"),
    _c("detail.thesis_card", "Decision Detail", "card", "Thesis card"),
    _c("detail.context_card", "Decision Detail", "card", "Context snapshot card"),
    _c("detail.evidence_table", "Decision Detail", "table", "Evidence table"),
    _c("detail.counter_evidence_table", "Decision Detail", "table", "Counter-evidence table"),
    _c("detail.risk_table", "Decision Detail", "table", "Risk conditions table"),
    _c("detail.confidence_gauge", "Decision Detail", "gauge", "Detail confidence gauge"),
    _c("detail.freshness_chip", "Decision Detail", "chip", "Detail freshness chip"),
    _c("detail.outcome_card", "Decision Detail", "card", "Outcome status card"),
    _c("detail.calibration_chart", "Decision Detail", "chart", "Calibration chart"),
    # Evidence
    _c("evidence.list_table", "Evidence", "table", "Evidence list table"),
    _c("evidence.summary_card", "Evidence", "card", "Evidence summary card"),
    _c("evidence.polarity_chip", "Evidence", "chip", "Polarity chip"),
    _c("evidence.freshness_chip", "Evidence", "chip", "Evidence freshness chip"),
    _c("evidence.polarity_chart", "Evidence", "chart", "Polarity mix chart"),
    # Counter Evidence
    _c("counter.list_table", "Counter Evidence", "table", "Counter-evidence table"),
    _c("counter.summary_card", "Counter Evidence", "card", "Counter-evidence summary card"),
    _c("counter.polarity_chip", "Counter Evidence", "chip", "Counter polarity chip"),
    _c("counter.freshness_chip", "Counter Evidence", "chip", "Counter freshness chip"),
    # Risk Conditions
    _c("risk.conditions_table", "Risk Conditions", "table", "Risk conditions table"),
    _c("risk.open_gauge", "Risk Conditions", "gauge", "Open risk gauge"),
    _c("risk.severity_chip", "Risk Conditions", "chip", "Severity chip"),
    _c("risk.alert_notification", "Risk Conditions", "notification", "Risk alert notification"),
    _c("risk.severity_chart", "Risk Conditions", "chart", "Severity distribution chart"),
    # Thesis Monitor
    _c("thesis.monitor_table", "Thesis Monitor", "table", "Thesis monitor table"),
    _c("thesis.status_chip", "Thesis Monitor", "chip", "Thesis status chip"),
    _c("thesis.drift_card", "Thesis Monitor", "card", "Thesis drift card"),
    _c("thesis.freshness_chip", "Thesis Monitor", "chip", "Thesis freshness chip"),
    _c("thesis.status_chart", "Thesis Monitor", "chart", "Thesis status chart"),
    # Alerts
    _c("alerts.notification_list", "Alerts", "notification", "Alerts notification list"),
    _c("alerts.severity_chip", "Alerts", "chip", "Alert severity chip"),
    _c("alerts.kind_table", "Alerts", "table", "Alerts kind table"),
    _c("alerts.count_gauge", "Alerts", "gauge", "Open alerts gauge"),
    # Decision Memory
    _c("memory.decision_table", "Decision Memory", "table", "Decision memory table"),
    _c("memory.summary_card", "Decision Memory", "decision_summary", "Memory Decision summary"),
    _c("memory.freshness_chip", "Decision Memory", "chip", "Memory freshness chip"),
    _c("memory.timeline_chart", "Decision Memory", "chart", "Memory timeline chart"),
    # Outcome Review
    _c("outcome.review_table", "Outcome Review", "table", "Outcome review table"),
    _c("outcome.class_chip", "Outcome Review", "chip", "Outcome class chip"),
    _c("outcome.review_card", "Outcome Review", "card", "Outcome review card"),
    _c("outcome.class_chart", "Outcome Review", "chart", "Outcome class chart"),
    # NEX AI
    _c("nexai.availability_card", "NEX AI Conversation", "card", "NEX AI availability card"),
    _c("nexai.disclaimer_chip", "NEX AI Conversation", "chip", "NEX AI disclaimer chip"),
    _c("nexai.status_gauge", "NEX AI Conversation", "gauge", "NEX AI availability gauge"),
    # Membership
    _c("membership.tier_card", "Membership", "card", "Membership tier card"),
    _c("membership.entitlement_chip", "Membership", "chip", "Entitlement chip"),
    _c("membership.billing_note_card", "Membership", "card", "Billing note card"),
    # Account
    _c("account.profile_card", "Account", "card", "Account profile card"),
    _c("account.locale_chip", "Account", "chip", "Locale chip"),
    # Privacy
    _c("privacy.consent_table", "Privacy", "table", "Consent table"),
    _c("privacy.consent_chip", "Privacy", "chip", "Consent chip"),
    # Account Deletion
    _c("deletion.request_card", "Account Deletion", "card", "Deletion request card"),
    _c("deletion.export_chip", "Account Deletion", "chip", "Export requested chip"),
    # Notification Settings
    _c("notify.settings_table", "Notification Settings", "table", "Notification settings table"),
    _c("notify.decision_chip", "Notification Settings", "chip", "Notify decision chip"),
    _c("notify.risk_chip", "Notification Settings", "chip", "Notify risk chip"),
    _c("notify.stale_chip", "Notification Settings", "chip", "Notify stale chip"),
)


def catalog_by_id() -> dict[str, UiComponent]:
    out = {c.component_id: c for c in UI_COMPONENT_CATALOG}
    if len(out) != len(UI_COMPONENT_CATALOG):
        raise AssertionError("duplicate component_id in catalog")
    return out


def required_kinds_present() -> bool:
    kinds = {c.kind for c in UI_COMPONENT_CATALOG}
    return COMPONENT_KINDS.issubset(kinds)


def pages_covered() -> frozenset[str]:
    return frozenset(c.page for c in UI_COMPONENT_CATALOG)
