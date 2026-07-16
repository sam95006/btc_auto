/**
 * Visible UI deploy marker (MVP-22B Derivatives Context).
 * READ ONLY · NOT INVESTMENT ADVICE · backend HOLD
 */
export const NEXUS_UI_BUILD_INFO = {
  uiVersion: "MVP-22B",
  uiStyle: "Live Market Intelligence",
  publicName: "NEXUS — Live Market Intelligence",
  latestCommit: "56066e8",
  backendState: "HOLD",
  stage419: "BLOCKED",
  /** Compact top-bar / footer label */
  displayLabel: "MVP-22B · derivatives context",
  buildMarker: "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT",
  /** Retained so MVP-22A safety / prior Live SoT checks still find the string. */
  mvp22aLegacyMarker: "NEXUS_UI_MVP22A_LIVE_MARKET_DATA",
  /**
   * Compatibility string kept so sync_operator_ui / older verifiers still find a known marker.
   * Do not remove without updating tools/deploy/sync_operator_ui_into_zeabur_stage3.py.
   */
  syncCompatibilityMarker: "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60",
} as const;
