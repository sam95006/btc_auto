import type {
  EvidenceItem,
  FleetStatus,
  GraduationStatusSummary,
  LatestReportMeta,
  MarketCard,
  MembershipTierInfo,
  PaperLabSummary,
  PrivateOperatorMode,
  ProviderShadowSummary,
  ProviderStatusSummary,
  ReflectionSummary,
  RiskEvidenceFlags,
  RoundTableSummary,
  SafetyStatusSummary,
  SignalRow,
  StageGateStatus,
  SystemStatus,
} from "../types/nexus";

export const DEMO_SOURCE = "DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE";

const meta = { demo: true as const, source: DEMO_SOURCE };

export const demoSystemStatus: SystemStatus = {
  ...meta,
  mode: "Private Operator · Research-only",
  safetyLine: "No ARM / No Live Trading / Defensive ON",
  stageReadiness: "Stage 4.18-P2-R1 PARTIAL_BTC_ONLY",
  currentGate: "4.18-P2A PASS · ETH follow-up gated",
  lastUpdate: "2026-07-11T18:00:00Z",
  disclaimer: "Not Investment Advice",
};

export const demoPrivateOperatorMode: PrivateOperatorMode = {
  ...meta,
  enabled: true,
  label: "Private Operator Mode ON",
  audience: "Internal operators / researchers only",
  publicSaas: "Future only / Not implemented / No billing",
  readOnly: true,
};

export const demoStageGateStatus: StageGateStatus = {
  ...meta,
  stageLabel: "4.18-P2-R1",
  verdict: "PARTIAL_BTC_ONLY",
  p2aStatus: "P2A PASS — eth_followup_confirmation_failed; Stage 4.19 blocked",
  latestGate: "Stage 4.18-P2-R1 · ETH graduation still 0",
  note: "Do not start Stage 4.19. No permanent Cerebras-first production routing.",
};

export const demoProviderStatus: ProviderStatusSummary = {
  ...meta,
  actualPrimary: "groq",
  shadowPrimary: "cerebras",
  btcExperimentChain: "cerebras,groq (P2-R1 experiment; reset after run)",
  ethRoutingUnchanged: true,
  health: "ok (demo)",
  note: "Shadow excluded from paper / calibration / graduation / Stage 4.19",
};

export const demoLatestReports: LatestReportMeta[] = [
  {
    ...meta,
    id: "rpt-p2-r1",
    title: "Stage 4.18-P2-R1 BTC Cerebras-first Read-only Experiment",
    stageMarker: "4.18-P2-R1",
    verdict: "PARTIAL_BTC_ONLY",
    path: "docs/reports/STAGE_4_18P2_R1_BTC_CEREBRAS_FIRST_READ_ONLY_EXPERIMENT_REPORT.md",
    updatedAt: "2026-07-11T18:00:00Z",
  },
  {
    ...meta,
    id: "rpt-p2-design",
    title: "Stage 4.18-P2 Provider Routing Design Gate",
    stageMarker: "4.18-P2",
    verdict: "design PASS · P2-R1 PARTIAL_BTC_ONLY · P2A PASS",
    path: "docs/reports/STAGE_4_18P2_PROVIDER_ROUTING_DESIGN_GATE_REPORT.md",
    updatedAt: "2026-07-10T12:00:00Z",
  },
];

export const demoGraduationStatus: GraduationStatusSummary = {
  ...meta,
  btcGraduationCount: 3,
  ethGraduationCount: 0,
  shadowExcludedFromGraduation: true,
  actualOnly: true,
  stage419Readiness: false,
  shouldStart419: false,
  whyBlocked: "ETH actual graduation = 0; Stage 4.19 requires BTC + ETH actual non-shadow graduation > 0",
};

export const demoSafetyStatus: SafetyStatusSummary = {
  ...meta,
  orderAllowed: false,
  arm: false,
  production: false,
  stage419Readiness: false,
  shouldStart419: false,
  privateOperatorMode: true,
  defensiveOn: true,
  summary: "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false",
};

export const demoMarkets: MarketCard[] = [
  {
    ...meta,
    symbol: "BTCUSDT",
    price: 108450.2,
    change24hPct: -0.42,
    regime: "range",
    riskScore: 0.48,
    status: "valid_watch",
    provider: "cerebras",
    confidence: 0.62,
    lastDecisionAt: "2026-07-11T17:55:00Z",
  },
  {
    ...meta,
    symbol: "ETHUSDT",
    price: 3120.5,
    change24hPct: 0.18,
    regime: "trend_up",
    riskScore: 0.41,
    status: "would_skip",
    provider: "groq",
    confidence: 0.58,
    lastDecisionAt: "2026-07-11T17:55:00Z",
  },
  {
    ...meta,
    symbol: "SOLUSDT",
    price: 148.2,
    change24hPct: 1.05,
    regime: "trend_up",
    riskScore: 0.55,
    status: "observe",
    provider: "groq",
    confidence: 0.44,
    lastDecisionAt: "2026-07-11T17:55:00Z",
  },
  {
    ...meta,
    symbol: "PEPEUSDT",
    price: 0.00000912,
    change24hPct: -2.1,
    regime: "volatile",
    riskScore: 0.72,
    status: "blocked",
    provider: "groq",
    confidence: 0.33,
    lastDecisionAt: "2026-07-11T17:55:00Z",
  },
];

export const demoFleets: FleetStatus[] = demoMarkets.map((m) => ({
  ...meta,
  symbol: m.symbol,
  fleetId: `${m.symbol.replace("USDT", "")}_FLEET`,
  intent: m.status === "blocked" ? "hard_skip" : m.status === "valid_watch" ? "valid_watch" : "soft_skip",
  confidence: m.confidence,
  watchState:
    m.status === "blocked"
      ? "hard_skip"
      : m.status === "valid_watch"
        ? "valid_watch"
        : "soft_skip",
  mae: 0.012,
  entryTrigger: "await confirmation candle",
  invalidation: "break of structure against thesis",
  provider: m.provider,
  graduationStatus:
    m.symbol === "BTCUSDT"
      ? "btc_graduation=3 (actual-only)"
      : m.symbol === "ETHUSDT"
        ? "eth_graduation=0"
        : "not_graduated",
}));

export const demoRoundTable: RoundTableSummary = {
  ...meta,
  consensus: "Private Operator Mode — observe only; P2-R1 PARTIAL_BTC_ONLY.",
  disagreement: "BTC actual graduation advanced; ETH still at 0.",
  whyNotTradeNow: "order_allowed=false; ARM=false; production=false; Stage 4.19 blocked.",
  confirmationNeeded: "Actual non-shadow ETH graduation > 0 + operator approval before any 4.19 discussion",
  roles: [
    { ...meta, role: "Trend AI", stance: "mild constructive", note: "BTC Cerebras-first path produced valid_watch×3 (demo)" },
    { ...meta, role: "Risk AI", stance: "defensive", note: "Keep size at zero; no ARM; should_start_419=false" },
    { ...meta, role: "News AI", stance: "neutral", note: "No high-impact catalyst in demo window" },
    { ...meta, role: "Reflection AI", stance: "caution", note: "P2A: ETH confirmation failed; do not permanentize routing" },
  ],
};

export const demoSignals: SignalRow[] = [
  {
    ...meta,
    id: "sig-btc-1",
    symbol: "BTCUSDT",
    status: "valid_watch",
    reason: "P2-R1 actual Cerebras-first valid_watch (demo sample)",
    risk: "medium",
    invalidation: "loss of range support",
    mae: 0.01,
    confidence: 0.62,
    dataQuality: "good",
    provider: "cerebras",
    evidenceId: "ev-1",
  },
  {
    ...meta,
    id: "sig-eth-1",
    symbol: "ETHUSDT",
    status: "watch",
    reason: "Structure building; no actual graduation yet",
    risk: "medium-low",
    invalidation: "failed breakout",
    mae: 0.015,
    confidence: 0.58,
    dataQuality: "good",
    provider: "groq",
    evidenceId: "ev-2",
  },
];

export const demoEvidence: EvidenceItem[] = [
  {
    ...meta,
    id: "ev-1",
    symbol: "BTCUSDT",
    decision: "valid_watch",
    confidence: 0.62,
    riskScore: 0.48,
    reason: "P2-R1 actual-only BTC graduation path (demo)",
    dataQuality: "good",
    skipReason: "n/a",
    timestamp: "2026-07-11T17:55:00Z",
    provider: "cerebras",
    stageMarker: "4.18-P2-R1",
    reportLink: "docs/reports/STAGE_4_18P2_R1_BTC_CEREBRAS_FIRST_READ_ONLY_EXPERIMENT_REPORT.md",
  },
  {
    ...meta,
    id: "ev-2",
    symbol: "ETHUSDT",
    decision: "soft_skip",
    confidence: 0.58,
    riskScore: 0.41,
    reason: "ETH graduation remains 0 — Stage 4.19 blocked",
    dataQuality: "good",
    skipReason: "no_graduation",
    timestamp: "2026-07-11T17:55:00Z",
    provider: "groq",
    stageMarker: "4.18-P2-R1",
    reportLink: "docs/reports/STAGE_4_18P2_R1_BTC_CEREBRAS_FIRST_READ_ONLY_EXPERIMENT_REPORT.md",
  },
];

export const demoRiskFlags: RiskEvidenceFlags = {
  ...meta,
  orderAllowed: false,
  mock: false,
  arm: false,
  production: false,
  paperExecution: false,
  stage419Readiness: false,
  shouldStart419: false,
  validatorStatus: "PASS (demo)",
  calibrationStatus: "actual-only · BTC=3 ETH=0",
  graduationStatus: "BTC=3 ETH=0 · Stage 4.19 blocked",
  providerHealth: "ok (demo)",
  resetStatus: "experiment flags reset after P2-R1",
  safetyLogSummary:
    "order_allowed=false · ARM=false · production=false · stage_419_readiness=false · should_start_419=false",
};

export const demoReflection: ReflectionSummary = {
  ...meta,
  mistakes: ["Treating BTC-only graduation as Stage 4.19 readiness"],
  repeatedErrors: ["Quota collision misread as skill gap (fixed in P1B)"],
  confidencePenalty: "none applied in demo",
  sizeAdjustment: "n/a (no live size)",
  behaviorChange: "Keep Cerebras-first as experiment-only until ETH also graduates",
  nextPatchRecommendation: "ETH watchlist follow-up diagnostics (read-only) — not 60m / not 4.19",
  applied: false,
};

export const demoProviderShadow: ProviderShadowSummary = {
  ...meta,
  actualProvider: "groq",
  shadowProvider: "cerebras",
  divergence: "P1C: shadow valid_watch higher on clean sample; P2-R1: BTC actual Cerebras-first",
  comparable: true,
  notes: "Shadow excluded from paper / calibration / graduation / Stage 4.19. Graduation uses actual-only.",
  shadowExcludedFromPaper: true,
  shadowExcludedFromCalibration: true,
  shadowExcludedFromGraduation: true,
  mustNotAffectStage419: true,
  p1cSummary: "P1C pair-compare: shadow diagnostics only; not graduation input",
  p2DesignSummary: "P2 design PASS — Option 2 BTC Cerebras-first experiment (default-off)",
  p2r1Summary: "P2-R1 PARTIAL_BTC_ONLY — BTC graduation=3 actual-only; ETH=0; shadow excluded",
};

export const demoPaperLab: PaperLabSummary = {
  ...meta,
  wouldEnterCount: 0,
  wouldSkipCount: 4,
  watchlistCount: 3,
  calibrationStatus: "actual-only",
  graduationStatus: "BTC=3 · ETH=0 · Stage 4.19 blocked",
  btcGraduationCount: 3,
  ethGraduationCount: 0,
  stage419Blocked: true,
  whyNotGraduated: "ETH actual graduation = 0; shadow excluded; should_start_419=false",
  paperLoggerStatus: "read-only / append-only research (actual-only)",
};

const FUTURE_BOUNDARY = "Future only / Not implemented / No billing" as const;

export const demoMembershipTiers: MembershipTierInfo[] = [
  {
    ...meta,
    tier: "Free",
    label: "Free",
    summary: "Future Public SaaS — overview stubs",
    lockedSurfaces: ["Fleet Center", "Evidence Vault"],
    productBoundary: FUTURE_BOUNDARY,
  },
  {
    ...meta,
    tier: "Standard",
    label: "Standard",
    summary: "Future Public SaaS — multi-symbol stubs",
    lockedSurfaces: ["Round Table full"],
    productBoundary: FUTURE_BOUNDARY,
  },
  {
    ...meta,
    tier: "Pro",
    label: "Pro",
    summary: "Future Public SaaS — paper lab stubs",
    lockedSurfaces: ["Provider Shadow"],
    productBoundary: FUTURE_BOUNDARY,
  },
  {
    ...meta,
    tier: "Elite",
    label: "Elite",
    summary: "Future Public SaaS — shadow + export stubs",
    lockedSurfaces: ["Team workflow"],
    productBoundary: FUTURE_BOUNDARY,
  },
  {
    ...meta,
    tier: "Team",
    label: "Team",
    summary: "Future Public SaaS — reviewer workflow stubs",
    lockedSurfaces: ["Enterprise SSO"],
    productBoundary: FUTURE_BOUNDARY,
  },
  {
    ...meta,
    tier: "Enterprise",
    label: "Enterprise",
    summary: "Future Public SaaS — governance stubs",
    lockedSurfaces: [],
    productBoundary: FUTURE_BOUNDARY,
  },
];
