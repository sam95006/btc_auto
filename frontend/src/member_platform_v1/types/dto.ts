/**
 * Member Platform V1 — public DTOs for UI.
 * Designed for Mock Adapter → future Zeabur Public Read-only API.
 * Never includes private wallet, keys, positions, or execution controls.
 */
export type MembershipTier = "starter" | "advanced" | "professional" | "enterprise";

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
  riskNote?: string;
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
  whyInteresting: string[];
  risks: string[];
  invalidation: string[];
  sparkline: number[];
  /** Advanced — gated by tier */
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
  timeLabel: string;
  read: boolean;
}

export interface PlanDto {
  id: MembershipTier;
  name: string;
  tagline: string;
  priceLabel: string;
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
