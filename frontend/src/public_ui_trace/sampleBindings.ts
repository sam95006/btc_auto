/**
 * Static mapping sample mirrored from backend LIVE bindings.
 * Full inventory is verified by tools/public_v1/run_ui_data_traceability_gate.py.
 */

import type { UiDtoBinding } from "./contract";

/** Representative LIVE bindings — every kind represented. */
export const SAMPLE_LIVE_BINDINGS: UiDtoBinding[] = [
  {
    componentId: "home.hero_decision_summary",
    page: "Home",
    kind: "decision_summary",
    mode: "LIVE",
    dtoPath: "DecisionSummaryDto.decision_posture",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
  {
    componentId: "market.symbols_table",
    page: "Market Overview",
    kind: "table",
    mode: "LIVE",
    dtoPath: "MarketOverviewDto.symbols",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
  {
    componentId: "decisions.posture_chart",
    page: "Decision Feed",
    kind: "chart",
    mode: "LIVE",
    dtoPath: "DecisionSummaryDto.decision_posture",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
  {
    componentId: "detail.confidence_gauge",
    page: "Decision Detail",
    kind: "gauge",
    mode: "LIVE",
    dtoPath: "DecisionSummaryDto.confidence_band",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
  {
    componentId: "evidence.polarity_chip",
    page: "Evidence",
    kind: "chip",
    mode: "LIVE",
    dtoPath: "EvidenceDto.evidence_polarity",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
  {
    componentId: "alerts.notification_list",
    page: "Alerts",
    kind: "notification",
    mode: "LIVE",
    dtoPath: "NotificationDto.alert_message",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
  {
    componentId: "market.overview_btc_card",
    page: "Market Overview",
    kind: "card",
    mode: "LIVE",
    dtoPath: "MarketOverviewDto.market_state",
    valueSource: "LIVE",
    freshnessState: "FRESH",
    staleIndicatorPresent: false,
    unavailableIndicatorPresent: false,
  },
];
