/**
 * Sanitized Private Operator snapshot for MVP-5 (Stage 4.18-P2D).
 * READ ONLY — research summaries only.
 * No secrets, no API keys, no /data raw paths, no investment advice.
 * Markers: SANITIZED SNAPSHOT · READ ONLY · NOT INVESTMENT ADVICE ·
 * SYSTEM ISSUE preserved historically · prompt repair status
 */
import type { NexusSnapshot } from "../../types/nexusSnapshot";

export const SNAPSHOT_SOURCE =
  "SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE" as const;

export const p2dPrivateOperatorSnapshot: NexusSnapshot = {
  source: SNAPSHOT_SOURCE,
  uiMode: "private_operator_snapshot",

  latestBackendStage: "4.18-P2D",
  latestVerdict: "STAGE_4_18P2D_PASS",

  systemStatus: {
    mode: "Private Operator · Research-only",
    safetyLine: "No ARM / No Live Trading / Defensive ON",
    stageReadiness:
      "Stage 4.18-P2D PASS · prompt repair status · awaiting P2D-R1 runtime regression",
    currentGate: "4.18-P2D PASS · Stage 4.19 blocked",
    lastUpdate: "2026-07-13T08:00:00Z",
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
      "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false · routing_permanent_change_supported=false · prompt repair status · SYSTEM ISSUE preserved historically · needs_next_runtime_regression=true",
  },

  stageGate: {
    stageLabel: "4.18-P2D",
    verdict: "STAGE_4_18P2D_PASS",
    p2aStatus:
      "P2A PASS — eth_followup_confirmation_failed (prior)",
    p2bStatus:
      "P2B PASS — eth_followup_direction_changed (LONG/BUY → NONE/NONE)",
    p2cStatus:
      "P2C PASS — confirmation_prompt_too_strict (not market reversal); SYSTEM ISSUE preserved historically",
    p2dStatus:
      "P2D PASS — prompt repair status; previous_watch_context + direction collapse guard; next=P2D-R1 runtime regression",
    latestGate: "Stage 4.18-P2D · BTC graduation=3 · ETH graduation=0",
    note: "Do not start Stage 4.19. Next: P2D-R1 runtime regression (read-only).",
  },

  btcStatus: {
    symbol: "BTCUSDT",
    actualValidWatchCount: 3,
    actualGraduationCount: 3,
    statusLabel: "passed (actual-only graduation=3)",
    note: "P2-R1 Cerebras-first experiment produced actual-only BTC graduation=3",
  },

  ethStatus: {
    symbol: "ETHUSDT",
    actualValidWatchCount: 1,
    actualGraduationCount: 0,
    rootCause: "confirmation_prompt_too_strict",
    confirmationFailureReason: "confirmation_prompt_too_strict",
    ethDetail: "LONG/BUY → NONE/NONE without market reversal",
    statusLabel:
      "blocked (actual-only graduation=0 · previous failure confirmation_prompt_too_strict · prompt repair pending runtime)",
    note: "ETH valid_watch=1; previous failure=confirmation_prompt_too_strict; SYSTEM ISSUE preserved historically; prompt repair status added; needs P2D-R1 runtime regression · NOT MARKET REVERSAL",
  },

  providerRoutingStatus: {
    actualPrimary: "groq",
    shadowPrimary: "cerebras",
    btcExperimentChain: "cerebras,groq (P2-R1 experiment; not permanent)",
    ethRoutingUnchanged: true,
    routingPermanentChangeSupported: false,
    btcCerebrasFirstExperimentSupported: true,
    health: "ok (sanitized snapshot)",
    note: "BTC Cerebras-first experiment supported (default-off). Permanent Cerebras-first production routing is not supported.",
  },

  providerShadowStatus: {
    actualProvider: "groq",
    shadowProvider: "cerebras",
    divergence:
      "P2-R1: BTC actual Cerebras-first experiment; shadow excluded from graduation",
    comparable: true,
    notes:
      "Shadow excluded from paper / calibration / graduation / Stage 4.19. Graduation uses actual-only.",
    shadowExcludedFromPaper: true,
    shadowExcludedFromCalibration: true,
    shadowExcludedFromGraduation: true,
    mustNotAffectStage419: true,
    p1cSummary: "P1C pair-compare: shadow diagnostics only; not graduation input",
    p2DesignSummary:
      "P2 design PASS — Option 2 BTC Cerebras-first experiment (default-off; not permanent)",
    p2r1Summary:
      "P2-R1 BTC Cerebras-first — BTC graduation=3 actual-only; ETH=0; shadow excluded",
    p2bSummary:
      "P2B ETH confirmation — direction_changed LONG/BUY → NONE/NONE; no MAE/invalidation breach",
    p2cSummary:
      "P2C — confirmation_prompt_too_strict; market_valid=false; system_issue=true; permanent routing still unsupported",
    p2dSummary:
      "P2D — prompt repair status; previous_watch_context injected; direction collapse guard; awaiting P2D-R1; permanent routing still unsupported",
    actualOnlyGraduation: true,
  },

  paperLabStatus: {
    wouldEnterCount: 0,
    wouldSkipCount: 4,
    watchlistCount: 3,
    calibrationStatus: "actual-only",
    graduationStatus: "BTC passed (=3) · ETH blocked (=0) · Stage 4.19 blocked",
    btcGraduationCount: 3,
    ethGraduationCount: 0,
    btcPassed: true,
    ethBlocked: true,
    stage419Blocked: true,
    whyNotGraduated:
      "ETH actual graduation=0; previous failure=confirmation_prompt_too_strict; prompt repair awaiting P2D-R1 runtime regression; should_start_419=false",
    paperLoggerStatus: "read-only / append-only research (actual-only)",
    nextDiagnostic: "P2D-R1 runtime regression",
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
    nextStep: "P2D-R1 runtime regression",
  },

  ethConfirmationTimeline: {
    symbol: "ETHUSDT",
    confirmationFailed: true,
    failureReason: "confirmation_prompt_too_strict",
    ethDetail: "LONG/BUY → NONE/NONE without market reversal",
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
      label: "Watch tick",
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
      label: "Follow-up tick",
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
      "SYSTEM ISSUE preserved historically — not a real market reversal. P2C classified confirmation_prompt_too_strict. P2D added prompt repair status (previous_watch_context + direction collapse guard). Awaiting P2D-R1 runtime regression.",
    nextStep: "P2D-R1 runtime regression",
    recoveryRecommendation: "eth_followup_confirmation_prompt_review",
  },

  reports: [
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
    {
      id: "rpt-p2b",
      title: "Stage 4.18-P2B ETH Watchlist Confirmation Diagnostics",
      stageMarker: "4.18-P2B",
      verdict: "STAGE_4_18P2B_PASS",
      path: "docs/reports/STAGE_4_18P2B_ETH_WATCHLIST_CONFIRMATION_DIAGNOSTICS_REPORT.md",
      updatedAt: "2026-07-13T04:00:00Z",
    },
    {
      id: "rpt-p2a",
      title: "Stage 4.18-P2A ETH+BTC Graduation Alignment Diagnostics",
      stageMarker: "4.18-P2A",
      verdict: "STAGE_4_18P2A_PASS",
      path: "docs/reports/STAGE_4_18P2A_ETH_BTC_GRADUATION_ALIGNMENT_DIAGNOSTICS_REPORT.md",
      updatedAt: "2026-07-13T03:00:00Z",
    },
  ],
};
