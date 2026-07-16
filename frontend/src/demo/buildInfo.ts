/**
 * Visible UI deploy marker (MVP-22A Live Market Data).
 * READ ONLY · NOT INVESTMENT ADVICE · backend HOLD
 */
export const NEXUS_UI_BUILD_INFO = {
  uiVersion: "MVP-22A",
  uiStyle: "Live Market Intelligence",
  publicName: "NEXUS — Live Market Intelligence",
  latestCommit: "9aa4ffc",
  backendState: "HOLD",
  stage419: "BLOCKED",
  /** Compact top-bar / footer label */
  displayLabel: "MVP-22A · live market",
  buildMarker: "NEXUS_UI_MVP22A_LIVE_MARKET_DATA",
  /**
   * Compatibility string kept so sync_operator_ui / older verifiers still find a known marker.
   * Do not remove without updating tools/deploy/sync_operator_ui_into_zeabur_stage3.py.
   */
  syncCompatibilityMarker: "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60",
} as const;
