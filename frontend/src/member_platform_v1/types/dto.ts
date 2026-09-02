/**
 * Member Platform — public DTOs for UI.
 * Product DTOs retained for static product configuration.
 * Never includes wallet, keys, positions, or execution controls.
 */
// Canonical Personal subscription plans (aligned with backend nexus_platform /
// nexus_billing). Enterprise is a SEPARATE product, not the top Personal tier, but
// remains a valid entitlement code. View Mode (SIMPLE/STANDARD/PRO) is independent
// and NEVER grants authorization — see NexusExperience.
export type MembershipTier = "free" | "starter" | "pro" | "advanced" | "enterprise";

export type MarketBias = "bullish" | "bearish" | "neutral";
export type ActionAdvice = "watch_closely" | "observing" | "wait";
export type RiskLevel = "low" | "medium" | "high";

export interface MemberSession {
  id: string;
  email: string;
  displayName: string;
  accountType: "individual" | "enterprise";
  tier: MembershipTier;
}

export interface MarketOverviewDto {
  bias: MarketBias;
  biasLabel: string;
  advice: ActionAdvice;
  adviceLabel: string;
  risk: RiskLevel;
  riskLabel: string;
  summary: string;
  updatedAt: string;
  /** Plain-language one-liners for dashboard */
  biasDetail?: string;
  actionDetail?: string;
  riskDetail?: string;
}

export interface MarketHighlightDto {
  id: string;
  title: string;
  body: string;
  tone: "info" | "positive" | "caution";
}

export interface MarketRankingRowDto {
  symbol: string;
  name: string;
  price: number;
  change24hPct: number;
  bias: MarketBias;
  biasLabel: string;
  advice: ActionAdvice;
  adviceLabel: string;
  score: number | null;
  beginnerReason: string;
  risk: RiskLevel;
  riskLabel: string;
  riskNote?: string;
  sparkline?: number[];
  lastChangeLabel?: string;
}

export interface SignalChangeDto {
  id: string;
  symbol: string;
  fromLabel: string;
  toLabel: string;
  timeLabel: string;
}

export interface AssetDetailDto {
  symbol: string;
  name: string;
  price: number;
  change24hPct: number;
  bias: MarketBias;
  biasLabel: string;
  advice: ActionAdvice;
  adviceLabel: string;
  score: number | null;
  risk: RiskLevel;
  riskLabel: string;
  whyInteresting: string[];
  risks: string[];
  invalidation: string[];
  sparkline: number[];
  candles?: Array<{ o: number; h: number; l: number; c: number; v?: number }>;
  evidence?: {
    supporting: string[];
    contradicting: string[];
  };
  derivatives?: {
    fundingLabel: string;
    oiLabel: string;
    note: string;
  };
  liquidity?: {
    spreadLabel: string;
    depthLabel: string;
    note: string;
  };
  signalHistory?: Array<{
    id: string;
    timeLabel: string;
    summary: string;
  }>;
}

export interface AlertDto {
  id: string;
  symbol?: string;
  title: string;
  body: string;
  severity: "info" | "caution" | "high";
  category: "priority" | "market" | "risk" | "watchlist";
  timeLabel: string;
  read: boolean;
}

export interface PlanDto {
  id: MembershipTier;
  name: string;
  tagline: string;
  priceLabel: string;
  audience: string;
  dailyValue: string;
  features: string[];
  highlighted?: boolean;
}

export interface MembershipStatusDto {
  tier: MembershipTier;
  tierName: string;
  renewLabel: string;
  seatsLabel?: string;
}

export interface DashboardDto {
  overview: MarketOverviewDto;
  topAssets: MarketRankingRowDto[];
  highlights: MarketHighlightDto[];
  riskAlerts: AlertDto[];
  watchlistPreview: MarketRankingRowDto[];
  membership: MembershipStatusDto;
  signalChanges: SignalChangeDto[];
  plainLanguage: {
    happening: string;
    whyStrong: string;
    avoid: string;
    topRisk: string;
  };
  pulse: {
    marketCapLabel: string;
    breadthBullPct: number;
    breadthBearPct: number;
    tickers: Array<{ symbol: string; price: number; change24hPct: number }>;
    trend: number[];
  };
}

export type FeatureKey =
  | "full_ranking"
  | "why_reasons"
  | "watchlist"
  | "risk_alerts"
  | "evidence"
  | "derivatives"
  | "liquidity"
  | "signal_history"
  | "team"
  | "api_export";
