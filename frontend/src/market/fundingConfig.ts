/**
 * Funding display thresholds — single config (MVP-22B).
 * Display / evidence labeling only. NOT trading rules. NOT recommendation scoring.
 */
export const FUNDING_CONFIG = {
  /** Bybit fundingRate is a decimal; multiply by 100 → percent display. */
  rateToPctMultiplier: 100,
  /** Absolute fundingRatePct bands for bias labels */
  elevatedAbsPct: 0.01,
  extremeAbsPct: 0.05,
  neutralAbsPct: 0.003,
} as const;

export type FundingBias = "Positive" | "Neutral" | "Negative";
export type FundingBand =
  | "Low / Neutral"
  | "Elevated Positive"
  | "Extreme Positive"
  | "Elevated Negative"
  | "Extreme Negative"
  | "Unavailable";

/** Convert exchange decimal funding rate to percent number (0.0001 → 0.01). */
export function fundingRateToPct(rate: number | undefined | null): number | undefined {
  if (rate == null || !Number.isFinite(rate)) return undefined;
  return rate * FUNDING_CONFIG.rateToPctMultiplier;
}

export function formatFundingPct(rate: number | undefined | null): string {
  const pct = fundingRateToPct(rate);
  if (pct == null) return "Unavailable";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(4)}%`;
}

export function fundingBias(rate: number | undefined | null): FundingBias | "Unavailable" {
  const pct = fundingRateToPct(rate);
  if (pct == null) return "Unavailable";
  if (Math.abs(pct) <= FUNDING_CONFIG.neutralAbsPct) return "Neutral";
  return pct > 0 ? "Positive" : "Negative";
}

export function fundingBand(rate: number | undefined | null): FundingBand {
  const pct = fundingRateToPct(rate);
  if (pct == null) return "Unavailable";
  const abs = Math.abs(pct);
  if (abs <= FUNDING_CONFIG.neutralAbsPct) return "Low / Neutral";
  if (pct > 0) {
    return abs >= FUNDING_CONFIG.extremeAbsPct ? "Extreme Positive" : "Elevated Positive";
  }
  return abs >= FUNDING_CONFIG.extremeAbsPct ? "Extreme Negative" : "Elevated Negative";
}
