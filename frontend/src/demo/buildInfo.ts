/**
 * Visible UI deploy marker (Product Transformation Phase 1).
 * READ ONLY · NOT INVESTMENT ADVICE · backend HOLD
 */
export const NEXUS_UI_BUILD_INFO = {
  uiVersion: "PT-1",
  uiStyle: "Market Opportunity Intelligence",
  publicName: "NEXUS — Live Market Intelligence",
  latestCommit: "pending",
  backendState: "HOLD",
  stage419: "BLOCKED",
  /** Compact top-bar / footer label */
  displayLabel: "PT-1 · market scanner",
  buildMarker: "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE1_MARKET_SCANNER",
  /** Retained so MVP-22D / prior Live SoT checks still find the string. */
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
