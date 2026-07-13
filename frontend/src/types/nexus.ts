/** Shared NEXUS / EATI UI types — MVP-1 Private Operator Dashboard (read-only). */

export type SignalStatus =
  | "observe"
  | "building"
  | "watch"
  | "valid_watch"
  | "confirmed"
  | "overheated"
  | "blocked_by_risk"
  | "would_enter"
  | "would_skip"
  | "soft_skip"
  | "hard_skip"
  | "blocked";

export type MembershipTier =
  | "Free"
  | "Standard"
  | "Pro"
  | "Elite"
  | "Team"
  | "Enterprise";

export interface DemoMeta {
  demo: boolean;
  source: string;
}

export interface MarketCard extends DemoMeta {
  symbol: string;
  price: number;
  change24hPct: number;
  regime: string;
  riskScore: number;
  status: SignalStatus;
  provider: string;
  confidence: number;
  lastDecisionAt: string;
}

export interface FleetStatus extends DemoMeta {
  symbol: string;
  fleetId: string;
  intent: string;
  confidence: number;
  watchState: "valid_watch" | "soft_skip" | "hard_skip" | "observe";
  mae: number;
  entryTrigger: string;
  invalidation: string;
  provider: string;
  graduationStatus: string;
}

export interface RoundTableRole extends DemoMeta {
  role: string;
  stance: string;
  note: string;
}

export interface RoundTableSummary extends DemoMeta {
  consensus: string;
  disagreement: string;
  whyNotTradeNow: string;
  confirmationNeeded: string;
  roles: RoundTableRole[];
}

export interface SignalRow extends DemoMeta {
  id: string;
  symbol: string;
  status: SignalStatus;
  reason: string;
  risk: string;
  invalidation: string;
  mae: number;
  confidence: number;
  dataQuality: string;
  provider: string;
  evidenceId: string;
}

export interface EvidenceItem extends DemoMeta {
  id: string;
  symbol: string;
  decision: string;
  confidence: number;
  riskScore: number;
  reason: string;
  dataQuality: string;
  skipReason: string;
  timestamp: string;
  provider: string;
  stageMarker: string;
  reportLink: string;
}

export interface RiskEvidenceFlags extends DemoMeta {
  orderAllowed: false;
  mock: false;
  arm: false;
  production: false;
  paperExecution: false;
  stage419Readiness: false;
  shouldStart419: false;
  validatorStatus: string;
  calibrationStatus: string;
  graduationStatus: string;
  providerHealth: string;
  resetStatus: string;
  safetyLogSummary: string;
}

export interface ReflectionSummary extends DemoMeta {
  mistakes: string[];
  repeatedErrors: string[];
  confidencePenalty: string;
  sizeAdjustment: string;
  behaviorChange: string;
  nextPatchRecommendation: string;
  applied: boolean;
}

export interface ProviderShadowSummary extends DemoMeta {
  actualProvider: string;
  shadowProvider: string;
  divergence: string;
  comparable: boolean;
  notes: string;
  shadowExcludedFromPaper: true;
  shadowExcludedFromCalibration: true;
  shadowExcludedFromGraduation: true;
  mustNotAffectStage419: true;
  p1cSummary: string;
  p2DesignSummary: string;
  p2r1Summary: string;
}

export interface PaperLabSummary extends DemoMeta {
  wouldEnterCount: number;
  wouldSkipCount: number;
  watchlistCount: number;
  calibrationStatus: string;
  graduationStatus: string;
  btcGraduationCount: number;
  ethGraduationCount: number;
  stage419Blocked: true;
  whyNotGraduated: string;
  paperLoggerStatus: string;
}

export interface MembershipTierInfo extends DemoMeta {
  tier: MembershipTier;
  label: string;
  summary: string;
  lockedSurfaces: string[];
  /** Future Public SaaS placeholder — not a live product. */
  productBoundary: "Future only / Not implemented / No billing";
}

export interface SystemStatus extends DemoMeta {
  mode: string;
  safetyLine: string;
  stageReadiness: string;
  currentGate: string;
  lastUpdate: string;
  disclaimer: string;
}

/** Stage gate panel for Private Operator Overview. */
export interface StageGateStatus extends DemoMeta {
  stageLabel: string;
  verdict: string;
  p2aStatus: string;
  latestGate: string;
  note: string;
}

/** Provider health / routing experiment summary (read-only). */
export interface ProviderStatusSummary extends DemoMeta {
  actualPrimary: string;
  shadowPrimary: string;
  btcExperimentChain: string;
  ethRoutingUnchanged: true;
  health: string;
  note: string;
}

/** Latest research report metadata (links are repo paths, not live APIs). */
export interface LatestReportMeta extends DemoMeta {
  id: string;
  title: string;
  stageMarker: string;
  verdict: string;
  path: string;
  updatedAt: string;
}

/** Actual-only graduation summary (shadow excluded). */
export interface GraduationStatusSummary extends DemoMeta {
  btcGraduationCount: number;
  ethGraduationCount: number;
  shadowExcludedFromGraduation: true;
  actualOnly: true;
  stage419Readiness: false;
  shouldStart419: false;
  whyBlocked: string;
}

/** Safety flags for Private Operator Safety Status card. */
export interface SafetyStatusSummary extends DemoMeta {
  orderAllowed: false;
  arm: false;
  production: false;
  stage419Readiness: false;
  shouldStart419: false;
  privateOperatorMode: true;
  defensiveOn: true;
  summary: string;
}

/** Private Operator Mode chrome — not a public SaaS session. */
export interface PrivateOperatorMode extends DemoMeta {
  enabled: true;
  label: string;
  audience: string;
  publicSaas: "Future only / Not implemented / No billing";
  readOnly: true;
}
