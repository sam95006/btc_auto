/**
 * Sanitized Private Operator snapshot for MVP-7 (Stage 4.18-P2E).
 * READ ONLY — research summaries only.
 * No secrets, no API keys, no /data raw paths, no investment advice.
 */
import type { NexusSnapshot } from "../../types/nexusSnapshot";

export const SNAPSHOT_SOURCE =
  "SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE" as const;

export const p2ePrivateOperatorSnapshot: NexusSnapshot = {
  source: SNAPSHOT_SOURCE,
  uiMode: "private_operator_snapshot",

  latestBackendStage: "4.18-P2E",
  latestVerdict: "STAGE_4_18P2E_PASS",

  systemStatus: {
    mode: "Private Operator · Research-only",
    safetyLine: "No ARM / No Live Trading / Defensive ON",
    stageReadiness:
      "Stage 4.18-P2E PASS · ETH no-watch=sample_market_no_edge · not prompt over-conservative · Stage 4.19 blocked",
    currentGate: "4.18-P2E / P2F readiness · do_not_run_regression_now · Stage 4.19 blocked",
    lastUpdate: "2026-07-14T03:00:00Z",
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
      "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false · should_run_60m=false · wait_helper_fixed=true · ETH sample_market_no_edge",
  },

  stageGate: {
    stageLabel: "4.18-P2E",
    verdict: "STAGE_4_18P2E_PASS",
    p2aStatus: "P2A PASS — prior",
    p2bStatus: "P2B PASS — eth_followup_direction_changed",
    p2cStatus: "P2C PASS — confirmation_prompt_too_strict",
    p2dStatus: "P2D PASS — prompt repair on runtime",
    p2dR1Status: "P2D-R1 PARTIAL_NO_ETH_WATCH — technical PASS; repair not validated",
    p2eStatus:
      "P2E PASS — sample_market_no_edge; prompt_repair_over_conservative=false; wait for ETH watch reappearance",
    latestGate:
      "Stage 4.18-P2E · ETH decisions=5 soft_skip×3/hard_skip×2 · vw=0 · grad=0 · regression_readiness=false",
    note: "Do not start Stage 4.19. Do not run 60m. Next gate: P2F ETH Watch Reappearance Gate.",
  },

  btcStatus: {
    symbol: "BTCUSDT",
    actualValidWatchCount: 1,
    actualGraduationCount: 0,
    statusLabel: "partial (P2D-R1 last-tick watch context retained)",
    note: "BTC context from prior P2D-R1; not a Stage 4.19 substitute",
  },

  ethStatus: {
    symbol: "ETHUSDT",
    actualValidWatchCount: 0,
    actualGraduationCount: 0,
    rootCause: "sample_market_no_edge",
    confirmationFailureReason: "sample_market_no_edge",
    ethDetail:
      "ETH decision_count=5 · soft_skip×3 hard_skip×2 · conf 0.20_0.35×4 lt_0.20×1 · bias NONE×5 · side NONE×5 · watch/grad=0/0",
    statusLabel: "blocked (sample_market_no_edge — not prompt over-conservative)",
    note: "prompt_repair_over_conservative_suspected=false · needs_prompt_adjustment=false · needs_another_short_regression only when ETH watch conditions reappear",
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
    divergence: "P2E offline diagnostics; shadow excluded from graduation",
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
    p2eSummary:
      "P2E PASS — sample_market_no_edge; should_run_60m=false; wait helper fixed; no permanent routing",
    actualOnlyGraduation: true,
  },

  paperLabStatus: {
    wouldEnterCount: 0,
    wouldSkipCount: 5,
    watchlistCount: 0,
    calibrationStatus: "actual-only",
    graduationStatus:
      "BTC graduation=0 · ETH graduation=0 · ETH no-watch sample_market_no_edge · Stage 4.19 blocked",
    btcGraduationCount: 0,
    ethGraduationCount: 0,
    btcPassed: false,
    ethBlocked: true,
    stage419Blocked: true,
    whyNotGraduated:
      "ETH watch/graduation=0/0; actual_non_shadow_btc_eth_graduation_met=false; do not run 60m",
    paperLoggerStatus: "read-only / append-only research (actual-only)",
    nextDiagnostic: "P2F ETH Watch Reappearance Gate — wait for ETH watch conditions",
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
    nextStep: "P2F ETH Watch Reappearance Gate",
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
    nextGate: "P2F ETH Watch Reappearance Gate",
    nextRecommendation: "wait_for_eth_watch_conditions_reappear_no_60m",
  },

  ethConfirmationTimeline: {
    symbol: "ETHUSDT",
    confirmationFailed: true,
    failureReason: "confirmation_prompt_too_strict",
    ethDetail: "Historical P2C LONG/BUY → NONE/NONE (system issue) — not current P2E failure",
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
      "P2E: current ETH no-watch is sample_market_no_edge (not prompt over-conservative). Repair still awaits ETH watch reappearance.",
    nextStep: "P2F ETH Watch Reappearance Gate",
    recoveryRecommendation: "wait_for_eth_watch_conditions_reappear_no_60m",
  },

  reports: [
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
