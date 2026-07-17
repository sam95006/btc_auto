/**
 * Visible UI deploy marker (MVP-22D Anomaly Outcome Research).
 * READ ONLY · NOT INVESTMENT ADVICE · backend HOLD
 */
export const NEXUS_UI_BUILD_INFO = {
  uiVersion: "MVP-22D",
  uiStyle: "Live Market Intelligence",
  publicName: "NEXUS — Live Market Intelligence",
  latestCommit: "00a0075",
  backendState: "HOLD",
  stage419: "BLOCKED",
  /** Compact top-bar / footer label */
  displayLabel: "MVP-22D · outcome research",
  buildMarker: "NEXUS_UI_MVP22D_ANOMALY_OUTCOME_RESEARCH",
  mvp22cLegacyMarker: "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR",
  mvp22bLegacyMarker: "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT",
  /** Retained so MVP-22A safety / prior Live SoT checks still find the string. */
  mvp22aLegacyMarker: "NEXUS_UI_MVP22A_LIVE_MARKET_DATA",
  /**
   * Compatibility string kept so sync_operator_ui / older verifiers still find a known marker.
   */
  syncCompatibilityMarker: "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60",
} as const;
