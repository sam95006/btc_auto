import type { FeatureKey, MembershipTier } from "../types/dto";

const TIER_RANK: Record<MembershipTier, number> = {
  starter: 1,
  advanced: 2,
  professional: 3,
  enterprise: 4,
};

const FEATURE_MIN: Record<FeatureKey, MembershipTier> = {
  full_ranking: "advanced",
  why_reasons: "advanced",
  watchlist: "advanced",
  risk_alerts: "advanced",
  evidence: "professional",
  derivatives: "professional",
  liquidity: "professional",
  signal_history: "professional",
  team: "enterprise",
  api_export: "enterprise",
};

export function canAccess(tier: MembershipTier, feature: FeatureKey): boolean {
  return TIER_RANK[tier] >= TIER_RANK[FEATURE_MIN[feature]];
}

export function minTierFor(feature: FeatureKey): MembershipTier {
  return FEATURE_MIN[feature];
}

export const TIER_LABELS: Record<MembershipTier, string> = {
  starter: "入門版",
  advanced: "進階版",
  professional: "專業版",
  enterprise: "企業版",
};

export const BIAS_LABELS = {
  bullish: "市場偏多",
  bearish: "市場偏空",
  neutral: "方向不明",
} as const;

export const ADVICE_LABELS = {
  watch_closely: "可留意",
  observing: "觀察中",
  wait: "先不要急",
} as const;

export const RISK_LABELS = {
  low: "低",
  medium: "中",
  high: "高",
} as const;
