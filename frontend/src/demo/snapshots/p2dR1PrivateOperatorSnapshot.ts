/**
 * Sanitized Private Operator snapshot for MVP-6 (Stage 4.18-P2D-R1).
 * READ ONLY — research summaries only.
 * No secrets, no API keys, no /data raw paths, no investment advice.
 */
import type { NexusSnapshot } from "../../types/nexusSnapshot";

export const SNAPSHOT_SOURCE =
  "SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE" as const;

export const p2dR1PrivateOperatorSnapshot: NexusSnapshot = {
  source: SNAPSHOT_SOURCE,
  uiMode: "private_operator_snapshot",

  latestBackendStage: "4.18-P2D-R1",
  latestVerdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",

  systemStatus: {
    mode: "Private Operator · Research-only",
    safetyLine: "No ARM / No Live Trading / Defensive ON",
    stageReadiness:
      "Stage 4.18-P2D-R1 PARTIAL · technical PASS · no ETH watch · repair not runtime-validated",
    currentGate: "4.18-P2D-R1 PARTIAL_NO_ETH_WATCH · Stage 4.19 blocked",
    lastUpdate: "2026-07-14T01:00:00Z",
    disclaimer: "Not Investment Advice",
  },

  safetyStatus: {
    orderAllowed: false,
    arm: false,
    production: false,
    stage419Readiness: false,
    shouldStart419: false,
    privateOperatorMode: true,
    defensiveOn: true,
    summary:
      "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false · technical_valid=true · ETH valid_watch=0 · repair effectiveness=false (sample insufficient)",
  },

  stageGate: {
    stageLabel: "4.18-P2D-R1",
    verdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
    p2aStatus: "P2A PASS — prior",
    p2bStatus: "P2B PASS — eth_followup_direction_changed",
    p2cStatus: "P2C PASS — confirmation_prompt_too_strict",
    p2dStatus: "P2D PASS — prompt repair added; awaiting runtime validation",
    p2dR1Status:
      "P2D-R1 PARTIAL_NO_ETH_WATCH — technical PASS; ETH valid_watch=0; repair not validated; Stage 4.19 blocked",
    latestGate:
      "Stage 4.18-P2D-R1 · tick=6 · effective=18 · BTC vw=1 last-tick · ETH vw=0 · graduations=0",
    note: "Do not start Stage 4.19. Next: P2E ETH no-watch diagnostics + wait helper robustness fix.",
  },

  btcStatus: {
    symbol: "BTCUSDT",
    actualValidWatchCount: 1,
    actualGraduationCount: 0,
    statusLabel: "partial (valid_watch=1 at last tick, no follow-up, graduation=0)",
    note: "BTC valid_watch=1 at last tick; no follow-up; BTC graduation=0",
  },

  ethStatus: {
    symbol: "ETHUSDT",
    actualValidWatchCount: 0,
    actualGraduationCount: 0,
    rootCause: "PARTIAL_NO_ETH_WATCH",
    confirmationFailureReason: "No ETH prior watch occurred in sample",
    ethDetail: "ETH valid_watch=0 · followup_cases=0 · repair not validated",
    statusLabel: "blocked (no ETH watch in P2D-R1 sample)",
    note: "prompt_repair_runtime_present=true but previous_watch_context_seen=false; eth_confirmation_prompt_repair_effective=false due sample insufficient",
  },

  providerRoutingStatus: {
    actualPrimary: "groq",
    shadowPrimary: "cerebras",
    btcExperimentChain: "cerebras,groq (P2D-R1 experiment; not permanent)",
    ethRoutingUnchanged: true,
    routingPermanentChangeSupported: false,
    btcCerebrasFirstExperimentSupported: true,
    health: "ok (sanitized snapshot)",
    note: "No permanent routing change. BTC Cerebras-first was experiment-only and flags reset.",
  },

  providerShadowStatus: {
    actualProvider: "groq",
    shadowProvider: "cerebras",
    divergence: "P2D-R1 actual-only experiment; shadow not used for graduation",
    comparable: true,
    notes: "Shadow excluded from paper / calibration / graduation / Stage 4.19.",
    shadowExcludedFromPaper: true,
    shadowExcludedFromCalibration: true,
    shadowExcludedFromGraduation: true,
    mustNotAffectStage419: true,
    p1cSummary: "P1C shadow diagnostics only",
    p2DesignSummary: "P2 design Option 2 experiment (default-off)",
    p2r1Summary: "P2-R1 prior BTC graduation=3 context (historical)",
    p2dSummary: "P2D prompt repair present before R1",
    p2dR1Summary:
      "P2D-R1 PARTIAL_NO_ETH_WATCH — technical PASS; no ETH watch; repair not validated; no permanent routing",
    actualOnlyGraduation: true,
  },

  paperLabStatus: {
    wouldEnterCount: 0,
    wouldSkipCount: 5,
    watchlistCount: 1,
    calibrationStatus: "actual-only",
    graduationStatus:
      "BTC graduation=0 · ETH graduation=0 · BTC last-tick watch · ETH no-watch · Stage 4.19 blocked",
    btcGraduationCount: 0,
    ethGraduationCount: 0,
    btcPassed: false,
    ethBlocked: true,
    stage419Blocked: true,
    whyNotGraduated:
      "actual_non_shadow_btc_eth_graduation_met=false; ETH valid_watch=0; BTC last-tick watch no follow-up",
    paperLoggerStatus: "read-only / append-only research (actual-only)",
    nextDiagnostic: "P2E ETH no-watch diagnostics + wait helper fix",
  },

  promptRepairStatus: {
    promptRepairAdded: true,
    previousWatchContextInjected: true,
    entryTriggerRecheckRequired: true,
    invalidationRecheckRequired: true,
    maeRecheckRequired: true,
    contextContinuityCheckRequired: true,
    directionCollapseGuardAdded: true,
    confidenceCollapseReasonRequired: true,
    staticExpectedFollowupBehavior: "continuation_watch_or_confirmation_pending",
    wouldPreventUnexplainedCollapse: true,
    needsNextRuntimeRegression: true,
    nextStep: "P2E ETH no-watch diagnostics + wait helper fix",
  },

  runtimeRegressionStatus: {
    technicalValid: true,
    tickCount: 6,
    effectiveDecisionCount: 18,
    parseErrorCount: 0,
    promptRepairRuntimePresent: true,
    previousWatchContextSeen: false,
    directionCollapseGuardSeen: false,
    ethValidWatchCount: 0,
    ethFollowupCasesCount: 0,
    ethGraduationCount: 0,
    ethConfirmationPromptRepairEffective: false,
    sampleInsufficientReason: "No ETH prior watch occurred in sample",
    btcValidWatchCount: 1,
    btcValidWatchNote: "last tick, no follow-up",
    btcGraduationCount: 0,
    actualNonShadowBtcEthGraduationMet: false,
    stage419Blocked: true,
    nextStep: "P2E ETH no-watch diagnostics + wait helper fix",
  },

  ethConfirmationTimeline: {
    symbol: "ETHUSDT",
    confirmationFailed: true,
    failureReason: "confirmation_prompt_too_strict",
    ethDetail: "LONG/BUY → NONE/NONE without market reversal (historical P2C)",
    invalidationBreached: false,
    maeBreached: false,
    confirmationFailureIsMarketValid: false,
    confirmationFailureIsSystemIssue: true,
    marketContextDelta: {
      priceChangePct: -0.127,
      regimeBefore: "trend",
      regimeAfter: "trend",
      trendStrengthBefore: 0.41,
      trendStrengthAfter: 0.64,
      dataQualityBefore: "ok",
      dataQualityAfter: "ok",
    },
    watch: {
      label: "Historical P2C watch",
      provider: "cerebras",
      intent: "watch",
      confidence: 0.55,
      directionalBias: "LONG",
      candidateSide: "BUY",
      entryTrigger: "present",
      invalidation: "present (not breached)",
      mae: "0.30 (cap passed)",
      invalidationBreached: false,
      maeBreached: false,
    },
    followup: {
      label: "Historical P2C follow-up",
      provider: "cerebras",
      intent: "hard_skip",
      confidence: 0.0,
      directionalBias: "NONE",
      candidateSide: "NONE",
      entryTrigger: "not rechecked",
      invalidation: "not breached",
      mae: "not breached",
      invalidationBreached: false,
      maeBreached: false,
    },
    conclusion:
      "P2D repair is present, but P2D-R1 sample had ETH valid_watch=0 so repair was not runtime-validated.",
    nextStep: "P2E ETH no-watch diagnostics + wait helper fix",
    recoveryRecommendation: "eth_no_watch_diagnostics_before_another_short_regression",
  },

  reports: [
    {
      id: "rpt-p2d-r1",
      title: "Stage 4.18-P2D-R1 ETH Follow-up Prompt Runtime Regression",
      stageMarker: "4.18-P2D-R1",
      verdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
      path: "docs/reports/STAGE_4_18P2D_R1_ETH_FOLLOWUP_PROMPT_RUNTIME_REGRESSION_REPORT.md",
      updatedAt: "2026-07-14T01:00:00Z",
    },
    {
      id: "rpt-p2d",
      title: "Stage 4.18-P2D ETH Follow-up Confirmation Prompt Review",
      stageMarker: "4.18-P2D",
      verdict: "STAGE_4_18P2D_PASS",
      path: "docs/reports/STAGE_4_18P2D_ETH_FOLLOWUP_CONFIRMATION_PROMPT_REVIEW_REPORT.md",
      updatedAt: "2026-07-13T08:00:00Z",
    },
    {
      id: "rpt-p2c",
      title: "Stage 4.18-P2C ETH Follow-up Market Context Review",
      stageMarker: "4.18-P2C",
      verdict: "STAGE_4_18P2C_PASS",
      path: "docs/reports/STAGE_4_18P2C_ETH_FOLLOWUP_MARKET_CONTEXT_REVIEW_REPORT.md",
      updatedAt: "2026-07-13T06:00:00Z",
    },
  ],
};
