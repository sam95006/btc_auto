import type {
  EvidenceItem,
  FleetStatus,
  MarketCard,
  MembershipTierInfo,
  PaperLabSummary,
  ProviderShadowSummary,
  ReflectionSummary,
  RiskEvidenceFlags,
  RoundTableSummary,
  SignalRow,
  SystemStatus,
} from "../types/nexus";

export const DEMO_SOURCE = "DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE";

const meta = { demo: true as const, source: DEMO_SOURCE };

export const demoSystemStatus: SystemStatus = {
  ...meta,
  mode: "Research-only",
  safetyLine: "No ARM / No Live Trading / Defensive ON",
  stageReadiness: "Stage 4.18-P2 design PASS; P2-R1 candidate",
  currentGate: "4.18-P2 / P2-R1 candidate",
  lastUpdate: "2026-07-10T18:00:00Z",
  disclaimer: "Not Investment Advice",
};

export const demoMarkets: MarketCard[] = [
  {
    ...meta,
    symbol: "BTCUSDT",
    price: 108450.2,
    change24hPct: -0.42,
    regime: "range",
    riskScore: 0.48,
    status: "observe",
    provider: "cerebras",
    confidence: 0.51,
    lastDecisionAt: "2026-07-10T17:55:00Z",
  },
  {
    ...meta,
    symbol: "ETHUSDT",
    price: 3120.5,
    change24hPct: 0.18,
    regime: "trend_up",
    riskScore: 0.41,
    status: "would_skip",
    provider: "cerebras",
    confidence: 0.58,
    lastDecisionAt: "2026-07-10T17:55:00Z",
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
    lastDecisionAt: "2026-07-10T17:55:00Z",
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
    lastDecisionAt: "2026-07-10T17:55:00Z",
  },
];

export const demoFleets: FleetStatus[] = demoMarkets.map((m) => ({
  ...meta,
  symbol: m.symbol,
  fleetId: `${m.symbol.replace("USDT", "")}_FLEET`,
  intent: m.status === "blocked" ? "hard_skip" : "soft_skip",
  confidence: m.confidence,
  watchState: m.status === "blocked" ? "hard_skip" : "soft_skip",
  mae: 0.012,
  entryTrigger: "await confirmation candle",
  invalidation: "break of structure against thesis",
  provider: m.provider,
  graduationStatus: "not_graduated",
}));

export const demoRoundTable: RoundTableSummary = {
  ...meta,
  consensus: "Observe only — no live trade path in research mode.",
  disagreement: "Trend AI sees mild upside; Risk AI flags elevated MAE on PEPE.",
  whyNotTradeNow: "Order path disabled; Stage 4.19 not ready; defensive mode ON.",
  confirmationNeeded: "Actual non-shadow BTC + ETH graduation > 0",
  roles: [
    { ...meta, role: "Trend AI", stance: "mild constructive", note: "Range with upside bias on ETH" },
    { ...meta, role: "Risk AI", stance: "defensive", note: "Keep size at zero; no ARM" },
    { ...meta, role: "News AI", stance: "neutral", note: "No high-impact catalyst in demo window" },
    { ...meta, role: "Reflection AI", stance: "caution", note: "Prior soft_skip patterns on BTC Groq path" },
  ],
};

export const demoSignals: SignalRow[] = [
  {
    ...meta,
    id: "sig-btc-1",
    symbol: "BTCUSDT",
    status: "observe",
    reason: "No edge after soft_skip cluster",
    risk: "medium",
    invalidation: "loss of range support",
    mae: 0.01,
    confidence: 0.51,
    dataQuality: "good",
    provider: "cerebras",
    evidenceId: "ev-1",
  },
  {
    ...meta,
    id: "sig-eth-1",
    symbol: "ETHUSDT",
    status: "watch",
    reason: "Structure building; not confirmed",
    risk: "medium-low",
    invalidation: "failed breakout",
    mae: 0.015,
    confidence: 0.58,
    dataQuality: "good",
    provider: "cerebras",
    evidenceId: "ev-2",
  },
];

export const demoEvidence: EvidenceItem[] = [
  {
    ...meta,
    id: "ev-1",
    symbol: "BTCUSDT",
    decision: "soft_skip",
    confidence: 0.51,
    riskScore: 0.48,
    reason: "Insufficient edge vs MAE",
    dataQuality: "good",
    skipReason: "no_edge",
    timestamp: "2026-07-10T17:55:00Z",
    provider: "cerebras",
    stageMarker: "4.18-P2",
    reportLink: "docs/reports/STAGE_4_18P2_PROVIDER_ROUTING_DESIGN_GATE_REPORT.md",
  },
];

export const demoRiskFlags: RiskEvidenceFlags = {
  ...meta,
  orderAllowed: false,
  mock: false,
  arm: false,
  production: false,
  paperExecution: false,
  validatorStatus: "PASS (demo)",
  calibrationStatus: "actual-only pending",
  graduationStatus: "0 / blocked for Stage 4.19",
  providerHealth: "ok (demo)",
  resetStatus: "flags default-off",
  safetyLogSummary: "No order / ARM / production path in UI",
};

export const demoReflection: ReflectionSummary = {
  ...meta,
  mistakes: ["Over-weighting soft_skip as inactivity"],
  repeatedErrors: ["Quota collision misread as skill gap (fixed in P1B)"],
  confidencePenalty: "none applied in demo",
  sizeAdjustment: "n/a (no live size)",
  behaviorChange: "Prefer Cerebras-first BTC experiment design only",
  nextPatchRecommendation: "Operator-approved P2-R1 read-only soak",
  applied: false,
};

export const demoProviderShadow: ProviderShadowSummary = {
  ...meta,
  actualProvider: "groq",
  shadowProvider: "cerebras",
  divergence: "shadow valid_watch higher on clean sample (P1C)",
  comparable: true,
  notes: "Shadow excluded from paper/calibration/graduation/Stage 4.19",
  shadowExcludedFromPaper: true,
  shadowExcludedFromCalibration: true,
  shadowExcludedFromGraduation: true,
  mustNotAffectStage419: true,
};

export const demoPaperLab: PaperLabSummary = {
  ...meta,
  wouldEnterCount: 0,
  wouldSkipCount: 4,
  watchlistCount: 1,
  calibrationStatus: "actual-only",
  graduationStatus: "0",
  whyNotGraduated: "No confirmed follow-up in demo window",
  paperLoggerStatus: "read-only / append-only research",
};

export const demoMembershipTiers: MembershipTierInfo[] = [
  { ...meta, tier: "Free", label: "Free", summary: "Overview + basic cards", lockedSurfaces: ["Fleet Center", "Evidence Vault"] },
  { ...meta, tier: "Standard", label: "Standard", summary: "Multi-symbol + alerts", lockedSurfaces: ["Round Table full"] },
  { ...meta, tier: "Pro", label: "Pro", summary: "Round table + paper lab", lockedSurfaces: ["Provider Shadow"] },
  { ...meta, tier: "Elite", label: "Elite", summary: "Shadow + exports", lockedSurfaces: ["Team workflow"] },
  { ...meta, tier: "Team", label: "Team", summary: "Reviewer workflow", lockedSurfaces: ["Enterprise SSO"] },
  { ...meta, tier: "Enterprise", label: "Enterprise", summary: "Governance + audit", lockedSurfaces: [] },
];
