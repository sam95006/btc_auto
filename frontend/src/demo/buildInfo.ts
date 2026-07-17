/**
 * Visible UI deploy marker (Product Transformation Phase 2).
 * READ ONLY · NOT INVESTMENT ADVICE · backend HOLD (in System Status)
 */
export const NEXUS_UI_BUILD_INFO = {
  uiVersion: "PT-2",
  uiStyle: "Decision Experience · Visual Intelligence",
  publicName: "NEXUS — Live Market Intelligence",
  latestCommit: "pending",
  backendState: "HOLD",
  stage419: "BLOCKED",
  /** Compact top-bar / footer label */
  displayLabel: "PT-2 · decision experience",
  buildMarker: "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE2_DECISION_EXPERIENCE",
  /** Retained so Phase 1 / MVP-22D / prior Live SoT checks still find the string. */
  phase1LegacyMarker: "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE1_MARKET_SCANNER",
  mvp22dLegacyMarker: "NEXUS_UI_MVP22D_ANOMALY_OUTCOME_RESEARCH",
  mvp22cLegacyMarker: "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR",
  mvp22bLegacyMarker: "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT",
  /** Retained so MVP-22A safety / prior Live SoT checks still find the string. */
  mvp22aLegacyMarker: "NEXUS_UI_MVP22A_LIVE_MARKET_DATA",
  /**
   * Compatibility string kept so sync_operator_ui / older verifiers still find a known marker.
   */
  syncCompatibilityMarker: "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60",
} as const;
