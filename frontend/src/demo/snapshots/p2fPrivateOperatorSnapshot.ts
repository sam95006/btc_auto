/**
 * Sanitized Private Operator snapshot for MVP-8 (Stage 4.18-P2F).
 * READ ONLY — research summaries only.
 * No secrets, no API keys, no /data raw paths, no investment advice.
 */
import type { NexusSnapshot } from "../../types/nexusSnapshot";

export const SNAPSHOT_SOURCE =
  "SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE" as const;

export const p2fPrivateOperatorSnapshot: NexusSnapshot = {
  source: SNAPSHOT_SOURCE,
  uiMode: "private_operator_snapshot",

  latestBackendStage: "4.18-P2F",
  latestVerdict: "STAGE_4_18P2F_PASS",

  systemStatus: {
    mode: "Private Operator · Research-only",
    safetyLine: "No ARM / No Live Trading / Defensive ON",
    stageReadiness:
      "Stage 4.18-P2F PASS · regression_readiness=false · do_not_run_regression_now · Stage 4.19 blocked",
    currentGate: "4.18-P2F watch reappearance · wait_for_eth_watch_conditions_reappear_no_60m",
    lastUpdate: "2026-07-14T03:40:00Z",
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
      "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false · should_run_60m=false · wait_helper=PASS · do_not_run_regression_now=true",
  },

  stageGate: {
    stageLabel: "4.18-P2F",
    verdict: "STAGE_4_18P2F_PASS",
    p2aStatus: "P2A PASS — prior BTC graduation evidence",
    p2bStatus: "P2B PASS — eth_followup_direction_changed",
    p2cStatus: "P2C PASS — confirmation_prompt_too_strict",
    p2dStatus: "P2D PASS — prompt repair on runtime",
    p2dR1Status: "P2D-R1 PARTIAL_NO_ETH_WATCH",
    p2eStatus: "P2E PASS — sample_market_no_edge",
    p2fStatus:
      "P2F PASS — regression_readiness=false; do_not_run_regression_now; wait helper PASS",
    latestGate:
      "Stage 4.18-P2F · ETH watch conditions incomplete · no 30m/60m · Stage 4.19 blocked",
    note: "Do not start Stage 4.19. Wait for ETH watch conditions before any short regression.",
  },

  btcStatus: {
    symbol: "BTCUSDT",
    actualValidWatchCount: 1,
    actualGraduationCount: 0,
    statusLabel: "prior evidence exists (historical graduation=3); latest regression grad=0",
    note: "BTC prior actual graduation evidence exists; not a Stage 4.19 substitute alone",
  },

  ethStatus: {
    symbol: "ETHUSDT",
    actualValidWatchCount: 0,
    actualGraduationCount: 0,
    rootCause: "sample_market_no_edge",
    confirmationFailureReason: "ETH watch conditions not met",
    ethDetail:
      "has_eth_watch_or_valid_watch=false · bias/side/conf/trigger/inval/mae=false · context_quality_ok=true · regime_not_unknown=true",
    statusLabel: "blocked (watch reappearance gate not ready)",
    note: "regression_readiness=false · do_not_run_regression_now=true · operator_approved_short_regression_may_be_justified=false",
  },

  providerRoutingStatus: {
    actualPrimary: "groq",
    shadowPrimary: "cerebras",
    btcExperimentChain: "prior experiment only (not permanent)",
    ethRoutingUnchanged: true,
    routingPermanentChangeSupported: false,
    btcCerebrasFirstExperimentSupported: true,
    health: "ok (sanitized snapshot)",
    note: "No permanent routing change.",
  },

  providerShadowStatus: {
    actualProvider: "groq",
    shadowProvider: "cerebras",
    divergence: "P2F offline gate; shadow excluded from graduation",
    comparable: true,
    notes: "Shadow excluded from paper / calibration / graduation / Stage 4.19.",
    shadowExcludedFromPaper: true,
    shadowExcludedFromCalibration: true,
    shadowExcludedFromGraduation: true,
    mustNotAffectStage419: true,
    p1cSummary: "P1C shadow diagnostics only",
    p2DesignSummary: "P2 design Option 2 experiment (default-off)",
    p2r1Summary: "P2-R1 prior BTC graduation context (historical)",
    p2dSummary: "P2D prompt repair present on runtime",
    p2dR1Summary: "P2D-R1 PARTIAL_NO_ETH_WATCH",
    p2eSummary: "P2E PASS — sample_market_no_edge",
    p2fSummary:
      "P2F PASS — regression_readiness=false; do_not_run_now; wait helper PASS; no permanent routing",
    actualOnlyGraduation: true,
  },

  paperLabStatus: {
    wouldEnterCount: 0,
    wouldSkipCount: 5,
    watchlistCount: 0,
    calibrationStatus: "actual-only",
    graduationStatus:
      "BTC latest grad=0 · ETH grad=0 · watch gate not ready · Stage 4.19 blocked",
    btcGraduationCount: 0,
    ethGraduationCount: 0,
    btcPassed: false,
    ethBlocked: true,
    stage419Blocked: true,
    whyNotGraduated:
      "ETH watch reappearance conditions incomplete; do not run 30m/60m; Stage 4.19 blocked",
    paperLoggerStatus: "read-only / append-only research (actual-only)",
    nextDiagnostic:
      "Next condition before regression: ETH watch/valid_watch + bias/side + conf>=0.45 + trigger + invalidation + MAE cap + quality/regime",
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
    nextStep: "wait_for_eth_watch_conditions_reappear_no_60m",
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
    sampleInsufficientReason: "sample_market_no_edge — No ETH prior watch in P2D-R1",
    btcValidWatchCount: 1,
    btcValidWatchNote: "last tick, no follow-up",
    btcGraduationCount: 0,
    actualNonShadowBtcEthGraduationMet: false,
    stage419Blocked: true,
    nextStep: "wait_for_eth_watch_conditions_reappear_no_60m",
  },

  regressionReadinessStatus: {
    readiness: false,
    reason: "ETH watch conditions not present",
    noWatchRootCause: "sample_market_no_edge",
    promptRepairOverConservativeSuspected: false,
    needsPromptAdjustment: false,
    shouldRun60m: false,
    waitHelperFixed: true,
    ethWatchConditionsPresent: false,
    stage419Blocked: true,
    nextGate: "P2F ETH Watch Reappearance Gate (closed)",
    nextRecommendation: "wait_for_eth_watch_conditions_reappear_no_60m",
  },

  watchReappearanceGateStatus: {
    regressionReadiness: false,
    doNotRunRegressionNow: true,
    operatorApprovedShortRegressionMayBeJustified: false,
    conditions: {
      hasEthWatchOrValidWatch: false,
      hasLongBuyBias: false,
      confidenceNearReference: false,
      entryTriggerPresent: false,
      invalidationPresent: false,
      maeCapPassed: false,
      contextQualityOk: true,
      regimeNotUnknown: true,
    },
    shouldRun60m: false,
    waitHelperRobustnessStatus: "PASS",
    stage419Blocked: true,
    nextRecommendation: "wait_for_eth_watch_conditions_reappear_no_60m",
  },

  reportIndex: [
    {
      stage: "4.18-P2D",
      verdict: "STAGE_4_18P2D_PASS",
      oneLineConclusion: "Prompt repair added (previous_watch_context + collapse guards)",
      reportPath: "docs/reports/STAGE_4_18P2D_ETH_FOLLOWUP_CONFIRMATION_PROMPT_REVIEW_REPORT.md",
      nextAction: "Needs runtime validation on ETH watch/follow-up",
    },
    {
      stage: "4.18-P2D-R1",
      verdict: "STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH",
      oneLineConclusion: "Technical PASS but no ETH watch — repair not validated",
      reportPath: "docs/reports/STAGE_4_18P2D_R1_ETH_FOLLOWUP_PROMPT_RUNTIME_REGRESSION_REPORT.md",
      nextAction: "Diagnose ETH no-watch (done in P2E)",
    },
    {
      stage: "4.18-P2E",
      verdict: "STAGE_4_18P2E_PASS",
      oneLineConclusion: "sample_market_no_edge — not prompt over-conservative; wait helper fixed",
      reportPath:
        "docs/reports/STAGE_4_18P2E_ETH_NO_WATCH_DIAGNOSTICS_AND_WAIT_HELPER_FIX_REPORT.md",
      nextAction: "Define ETH watch reappearance gate",
    },
    {
      stage: "4.18-P2F",
      verdict: "STAGE_4_18P2F_PASS",
      oneLineConclusion: "regression_readiness=false — do not run; wait for ETH watch conditions",
      reportPath: "docs/reports/STAGE_4_18P2F_ETH_WATCH_REAPPEARANCE_GATE_REPORT.md",
      nextAction: "wait_for_eth_watch_conditions_reappear_no_60m",
    },
  ],

  ethConfirmationTimeline: {
    symbol: "ETHUSDT",
    confirmationFailed: true,
    failureReason: "confirmation_prompt_too_strict",
    ethDetail: "Historical P2C LONG/BUY → NONE/NONE (system issue)",
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
      "P2F gate closed: wait for ETH watch conditions before any short regression. No 60m. Stage 4.19 blocked.",
    nextStep: "wait_for_eth_watch_conditions_reappear_no_60m",
    recoveryRecommendation: "wait_for_eth_watch_conditions_reappear_no_60m",
  },

  reports: [
    {
      id: "rpt-p2f",
      title: "Stage 4.18-P2F ETH Watch Reappearance Gate",
      stageMarker: "4.18-P2F",
      verdict: "STAGE_4_18P2F_PASS",
      path: "docs/reports/STAGE_4_18P2F_ETH_WATCH_REAPPEARANCE_GATE_REPORT.md",
      updatedAt: "2026-07-14T03:40:00Z",
    },
    {
      id: "rpt-p2e",
      title: "Stage 4.18-P2E ETH No-Watch Diagnostics and Wait Helper Fix",
      stageMarker: "4.18-P2E",
      verdict: "STAGE_4_18P2E_PASS",
      path: "docs/reports/STAGE_4_18P2E_ETH_NO_WATCH_DIAGNOSTICS_AND_WAIT_HELPER_FIX_REPORT.md",
      updatedAt: "2026-07-14T03:00:00Z",
    },
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
  ],
};
