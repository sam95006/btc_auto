/**
 * Sanitized Private Operator snapshot for MVP-2.
 * READ ONLY — research summaries only.
 * No secrets, no API keys, no /data raw paths, no investment advice.
 */
import type { NexusSnapshot } from "../../types/nexusSnapshot";

export const SNAPSHOT_SOURCE =
  "SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE" as const;

export const p2aPrivateOperatorSnapshot: NexusSnapshot = {
  source: SNAPSHOT_SOURCE,
  uiMode: "private_operator_snapshot",

  latestBackendStage: "4.18-P2A",
  latestVerdict: "STAGE_4_18P2A_PASS",

  systemStatus: {
    mode: "Private Operator · Research-only",
    safetyLine: "No ARM / No Live Trading / Defensive ON",
    stageReadiness: "Stage 4.18-P2A PASS · ETH confirmation diagnostics gated",
    currentGate: "4.18-P2A PASS · Stage 4.19 blocked",
    lastUpdate: "2026-07-13T03:00:00Z",
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
      "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false · routing_permanent_change_supported=false",
  },

  stageGate: {
    stageLabel: "4.18-P2A",
    verdict: "STAGE_4_18P2A_PASS",
    p2aStatus:
      "P2A PASS — eth_followup_confirmation_failed; Stage 4.19 blocked; no permanent routing change",
    latestGate: "Stage 4.18-P2A · BTC graduation=3 · ETH graduation=0",
    note: "Do not start Stage 4.19. Next: P2B ETH confirmation diagnostics (read-only).",
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
    statusLabel: "blocked (actual-only graduation=0)",
    note: "ETH had 1 valid_watch; follow-up confirmation failed — Stage 4.19 blocked",
  },

  providerRoutingStatus: {
    actualPrimary: "groq",
    shadowPrimary: "cerebras",
    btcExperimentChain: "cerebras,groq (P2-R1 experiment; not permanent)",
    ethRoutingUnchanged: true,
    routingPermanentChangeSupported: false,
    health: "ok (sanitized snapshot)",
    note: "Permanent Cerebras-first production routing is not supported. Experiment-only.",
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
      "ETH actual graduation=0; root cause=eth_followup_confirmation_failed; should_start_419=false",
    paperLoggerStatus: "read-only / append-only research (actual-only)",
    nextDiagnostic: "P2B ETH confirmation diagnostics",
  },

  reports: [
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
    {
      id: "rpt-p2-design",
      title: "Stage 4.18-P2 Provider Routing Design Gate",
      stageMarker: "4.18-P2",
      verdict: "design PASS · experiment-only routing",
      path: "docs/reports/STAGE_4_18P2_PROVIDER_ROUTING_DESIGN_GATE_REPORT.md",
      updatedAt: "2026-07-10T12:00:00Z",
    },
  ],
};
