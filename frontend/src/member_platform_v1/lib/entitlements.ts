import type { MembershipTier } from "../types/dto";

/**
 * NEXUS-EXPERIENCE-1B.1: there is NO client-side tier-rank authorization. The
 * backend is the sole entitlement authority (per-capability states from
 * /api/v1/personal/catalog and the member's effective plan). The former
 * TIER_RANK / FEATURE_MIN / canAccess() rank system was removed — the frontend
 * must never decide access from a plan rank.
 *
 * TIER_LABELS are canonical, display-only fallbacks (zh-TW). Prefer the localized
 * plan_* keys via useExperience().t() where a locale context is available.
 */
export const TIER_LABELS: Record<MembershipTier, string> = {
  free: "免費版",
  starter: "入門版",
  pro: "專業版",
  advanced: "進階版",
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
