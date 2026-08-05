"""Canonical public DTO registry for Member UI bindings."""
from __future__ import annotations

from dataclasses import dataclass

from backend.nexus_public_ui_trace.constants import ALLOWED_PUBLIC_FIELDS, SCHEMA


@dataclass(frozen=True)
class PublicDtoField:
    dto_name: str
    field_path: str  # dotted path relative to DTO root
    leaf_field: str


# Public intelligence + member-surface DTOs (field leaves must be allow-listed).
PUBLIC_DTO_FIELDS: tuple[PublicDtoField, ...] = (
    # MarketOverviewDto
    PublicDtoField("MarketOverviewDto", "market_state", "market_state"),
    PublicDtoField("MarketOverviewDto", "regime_label", "regime_label"),
    PublicDtoField("MarketOverviewDto", "symbol", "symbol"),
    PublicDtoField("MarketOverviewDto", "symbols", "symbols"),
    PublicDtoField("MarketOverviewDto", "data_freshness", "data_freshness"),
    PublicDtoField("MarketOverviewDto", "data_completeness", "data_completeness"),
    PublicDtoField("MarketOverviewDto", "freshness_state", "freshness_state"),
    PublicDtoField("MarketOverviewDto", "system_availability", "system_availability"),
    PublicDtoField("MarketOverviewDto", "as_of", "as_of"),
    PublicDtoField("MarketOverviewDto", "retrieved_at", "retrieved_at"),
    PublicDtoField("MarketOverviewDto", "stale_indicator", "stale_indicator"),
    PublicDtoField("MarketOverviewDto", "unavailable_indicator", "unavailable_indicator"),
    # DecisionSummaryDto / DecisionDetailDto
    PublicDtoField("DecisionSummaryDto", "decision_id", "decision_id"),
    PublicDtoField("DecisionSummaryDto", "symbol", "symbol"),
    PublicDtoField("DecisionSummaryDto", "decision_title", "decision_title"),
    PublicDtoField("DecisionSummaryDto", "decision_posture", "decision_posture"),
    PublicDtoField("DecisionSummaryDto", "decision_state", "decision_state"),
    PublicDtoField("DecisionSummaryDto", "confidence_band", "confidence_band"),
    PublicDtoField("DecisionSummaryDto", "confidence_calibration", "confidence_calibration"),
    PublicDtoField("DecisionSummaryDto", "thesis_status", "thesis_status"),
    PublicDtoField("DecisionSummaryDto", "thesis_horizon", "thesis_horizon"),
    PublicDtoField("DecisionSummaryDto", "freshness_state", "freshness_state"),
    PublicDtoField("DecisionSummaryDto", "citation_count", "citation_count"),
    PublicDtoField("DecisionSummaryDto", "count", "count"),
    PublicDtoField("DecisionSummaryDto", "as_of", "as_of"),
    PublicDtoField("DecisionSummaryDto", "stale_indicator", "stale_indicator"),
    PublicDtoField("DecisionDetailDto", "evidence_summaries", "evidence_summaries"),
    PublicDtoField("DecisionDetailDto", "contradicting_evidence", "contradicting_evidence"),
    PublicDtoField("DecisionDetailDto", "risk_alerts", "risk_alerts"),
    PublicDtoField("DecisionDetailDto", "outcome_status", "outcome_status"),
    PublicDtoField("DecisionDetailDto", "outcome_review_classification", "outcome_review_classification"),
    PublicDtoField("DecisionDetailDto", "review_note", "review_note"),
    PublicDtoField("DecisionDetailDto", "message", "message"),
    # EvidenceDto
    PublicDtoField("EvidenceDto", "evidence_summary", "evidence_summary"),
    PublicDtoField("EvidenceDto", "evidence_polarity", "evidence_polarity"),
    PublicDtoField("EvidenceDto", "evidence_freshness", "evidence_freshness"),
    PublicDtoField("EvidenceDto", "source_label", "source_label"),
    PublicDtoField("EvidenceDto", "as_of", "as_of"),
    PublicDtoField("EvidenceDto", "freshness_state", "freshness_state"),
    PublicDtoField("EvidenceDto", "stale_indicator", "stale_indicator"),
    PublicDtoField("EvidenceDto", "unavailable_indicator", "unavailable_indicator"),
    # RiskAlertDto
    PublicDtoField("RiskAlertDto", "risk_alert", "risk_alert"),
    PublicDtoField("RiskAlertDto", "alert_severity", "alert_severity"),
    PublicDtoField("RiskAlertDto", "alert_code", "alert_code"),
    PublicDtoField("RiskAlertDto", "alert_message", "alert_message"),
    PublicDtoField("RiskAlertDto", "status", "status"),
    PublicDtoField("RiskAlertDto", "count", "count"),
    # ThesisMonitorDto
    PublicDtoField("ThesisMonitorDto", "thesis_status", "thesis_status"),
    PublicDtoField("ThesisMonitorDto", "thesis_horizon", "thesis_horizon"),
    PublicDtoField("ThesisMonitorDto", "decision_id", "decision_id"),
    PublicDtoField("ThesisMonitorDto", "message", "message"),
    PublicDtoField("ThesisMonitorDto", "freshness_state", "freshness_state"),
    PublicDtoField("ThesisMonitorDto", "as_of", "as_of"),
    PublicDtoField("ThesisMonitorDto", "stale_indicator", "stale_indicator"),
    # NotificationDto / AlertDto
    PublicDtoField("NotificationDto", "alert_code", "alert_code"),
    PublicDtoField("NotificationDto", "alert_severity", "alert_severity"),
    PublicDtoField("NotificationDto", "alert_message", "alert_message"),
    PublicDtoField("NotificationDto", "decision_id", "decision_id"),
    PublicDtoField("NotificationDto", "as_of", "as_of"),
    PublicDtoField("NotificationDto", "freshness_state", "freshness_state"),
    PublicDtoField("NotificationDto", "stale_indicator", "stale_indicator"),
    # OutcomeReviewDto
    PublicDtoField("OutcomeReviewDto", "outcome_status", "outcome_status"),
    PublicDtoField("OutcomeReviewDto", "outcome_review_classification", "outcome_review_classification"),
    PublicDtoField("OutcomeReviewDto", "review_note", "review_note"),
    PublicDtoField("OutcomeReviewDto", "decision_id", "decision_id"),
    PublicDtoField("OutcomeReviewDto", "symbol", "symbol"),
    # MembershipDto
    PublicDtoField("MembershipDto", "tier_name", "tier_name"),
    PublicDtoField("MembershipDto", "tier_blurb", "tier_blurb"),
    PublicDtoField("MembershipDto", "entitlement_labels", "entitlement_labels"),
    PublicDtoField("MembershipDto", "billing_note", "billing_note"),
    # Account / privacy / notifications / NEX AI
    PublicDtoField("AccountDto", "display_name", "display_name"),
    PublicDtoField("AccountDto", "email_masked", "email_masked"),
    PublicDtoField("AccountDto", "locale", "locale"),
    PublicDtoField("AccountDto", "timezone", "timezone"),
    PublicDtoField("PrivacyDto", "consent_marketing", "consent_marketing"),
    PublicDtoField("PrivacyDto", "consent_analytics", "consent_analytics"),
    PublicDtoField("PrivacyDto", "consent_crash", "consent_crash"),
    PublicDtoField("AccountDeletionDto", "deletion_requested", "deletion_requested"),
    PublicDtoField("AccountDeletionDto", "export_requested", "export_requested"),
    PublicDtoField("NotificationSettingsDto", "notify_decision", "notify_decision"),
    PublicDtoField("NotificationSettingsDto", "notify_risk", "notify_risk"),
    PublicDtoField("NotificationSettingsDto", "notify_stale", "notify_stale"),
    PublicDtoField("NotificationSettingsDto", "notify_thesis", "notify_thesis"),
    PublicDtoField("NotificationSettingsDto", "notify_anomaly", "notify_anomaly"),
    PublicDtoField("NexAiDto", "nex_ai_availability", "nex_ai_availability"),
    PublicDtoField("NexAiDto", "nex_ai_disclaimer", "nex_ai_disclaimer"),
    PublicDtoField("NexAiDto", "system_availability", "system_availability"),
    # Envelope metadata usable by chips
    PublicDtoField("PublicEnvelopeDto", "schema_version", "schema_version"),
    PublicDtoField("PublicEnvelopeDto", "availability", "availability"),
    PublicDtoField("PublicEnvelopeDto", "environment", "environment"),
    PublicDtoField("PublicEnvelopeDto", "lineage_id", "lineage_id"),
    PublicDtoField("PublicEnvelopeDto", "published_at", "published_at"),
)


def dto_path(dto_name: str, field_path: str) -> str:
    return f"{dto_name}.{field_path}"


def all_dto_paths() -> frozenset[str]:
    return frozenset(dto_path(f.dto_name, f.field_path) for f in PUBLIC_DTO_FIELDS)


def leaf_fields() -> frozenset[str]:
    return frozenset(f.leaf_field for f in PUBLIC_DTO_FIELDS)


def assert_registry_allowlisted() -> None:
    unknown = leaf_fields() - ALLOWED_PUBLIC_FIELDS
    if unknown:
        raise AssertionError(f"DTO leaves not in ALLOWED_PUBLIC_FIELDS: {sorted(unknown)}")


def schema_version() -> str:
    return SCHEMA
