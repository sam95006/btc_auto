/** Shared NEXUS / EATI UI types — MVP-0 read-only shell. */

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
}

export interface PaperLabSummary extends DemoMeta {
  wouldEnterCount: number;
  wouldSkipCount: number;
  watchlistCount: number;
  calibrationStatus: string;
  graduationStatus: string;
  whyNotGraduated: string;
  paperLoggerStatus: string;
}

export interface MembershipTierInfo extends DemoMeta {
  tier: MembershipTier;
  label: string;
  summary: string;
  lockedSurfaces: string[];
}

export interface SystemStatus extends DemoMeta {
  mode: string;
  safetyLine: string;
  stageReadiness: string;
  currentGate: string;
  lastUpdate: string;
  disclaimer: string;
}
