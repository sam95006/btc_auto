/**
 * Sanitized Private Operator snapshot for MVP-3 (Stage 4.18-P2B).
 * READ ONLY — research summaries only.
 * No secrets, no API keys, no /data raw paths, no investment advice.
 */
import type { NexusSnapshot } from "../../types/nexusSnapshot";

export const SNAPSHOT_SOURCE =
  "SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE" as const;

export const p2bPrivateOperatorSnapshot: NexusSnapshot = {
  source: SNAPSHOT_SOURCE,
  uiMode: "private_operator_snapshot",

  latestBackendStage: "4.18-P2B",
  latestVerdict: "STAGE_4_18P2B_PASS",

  systemStatus: {
    mode: "Private Operator · Research-only",
    safetyLine: "No ARM / No Live Trading / Defensive ON",
    stageReadiness: "Stage 4.18-P2B PASS · ETH confirmation failed (direction changed)",
    currentGate: "4.18-P2B PASS · Stage 4.19 blocked",
    lastUpdate: "2026-07-13T04:00:00Z",
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
      "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false · routing_permanent_change_supported=false · invalidation_breached=false · mae_breached=false",
  },

  stageGate: {
    stageLabel: "4.18-P2B",
    verdict: "STAGE_4_18P2B_PASS",
    p2aStatus:
      "P2A PASS — eth_followup_confirmation_failed (prior gate; refined by P2B)",
    p2bStatus:
      "P2B PASS — eth_followup_direction_changed (LONG/BUY → NONE/NONE); Stage 4.19 blocked; no permanent routing change",
    latestGate: "Stage 4.18-P2B · BTC graduation=3 · ETH graduation=0",
    note: "Do not start Stage 4.19. Next: P2C market context review (read-only).",
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
    rootCause: "eth_followup_confirmation_failed",
    confirmationFailureReason: "eth_followup_direction_changed",
    ethDetail: "LONG/BUY → NONE/NONE",
    statusLabel: "blocked (actual-only graduation=0 · confirmation failed)",
    note: "ETH valid_watch=1; follow-up hard_skip collapsed LONG/BUY → NONE/NONE; invalidation_breached=false; mae_breached=false",
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
      "P2B ETH confirmation — failureReason=eth_followup_direction_changed; no MAE/invalidation breach; Stage 4.19 blocked",
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
      "ETH actual graduation=0; failureReason=eth_followup_direction_changed; should_start_419=false",
    paperLoggerStatus: "read-only / append-only research (actual-only)",
    nextDiagnostic: "P2C market context review",
  },

  ethConfirmationTimeline: {
    symbol: "ETHUSDT",
    confirmationFailed: true,
    failureReason: "eth_followup_direction_changed",
    ethDetail: "LONG/BUY → NONE/NONE",
    invalidationBreached: false,
    maeBreached: false,
    confirmationFailureIsMarketValid: false,
    confirmationFailureIsSystemIssue: true,
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
      entryTrigger: "collapsed",
      invalidation: "not breached",
      mae: "not breached",
      invalidationBreached: false,
      maeBreached: false,
    },
    conclusion:
      "Confirmation failed: eth_followup_direction_changed — bias/side collapsed LONG/BUY → NONE/NONE under hard_skip (same provider). Not MAE or invalidation breach.",
    nextStep: "P2C market context review",
    recoveryRecommendation: "eth_followup_market_context_or_confirmation_review",
  },

  reports: [
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
    {
      id: "rpt-p2-r1",
      title: "Stage 4.18-P2-R1 BTC Cerebras-first Read-only Experiment",
      stageMarker: "4.18-P2-R1",
      verdict: "PARTIAL_BTC_ONLY",
      path: "docs/reports/STAGE_4_18P2_R1_BTC_CEREBRAS_FIRST_READ_ONLY_EXPERIMENT_REPORT.md",
      updatedAt: "2026-07-11T18:00:00Z",
    },
  ],
};
