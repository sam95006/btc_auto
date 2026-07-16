import { FRESH_DELAYED_MS, FRESH_LIVE_MS } from "./freshness";
import { fundingRateToPct } from "./fundingConfig";
import { sharedOiHistory } from "./oiHistory";
import type {
  DerivativesFieldStatus,
  DerivativesMarketContext,
  LiveMarketPrice,
} from "./types";

export type EvidenceLabel = "supportive" | "neutral" | "conflicting" | "unavailable";

function fieldStatus(ageMs: number, hasAny: boolean): DerivativesFieldStatus {
  if (!hasAny) return "UNAVAILABLE";
  if (ageMs <= FRESH_LIVE_MS) return "LIVE";
  if (ageMs <= FRESH_DELAYED_MS) return "DELAYED";
  return "STALE";
}

export function toDerivativesContext(price: LiveMarketPrice | undefined): DerivativesMarketContext | undefined {
  if (!price) return undefined;
  const hasDeriv =
    price.openInterest != null ||
    price.openInterestValue != null ||
    price.fundingRate != null ||
    price.volume24h != null ||
    price.turnover24h != null;
  const oiSnap = sharedOiHistory.snapshot(price.symbol, Date.now());
  return {
    symbol: price.symbol,
    openInterest: price.openInterest,
    openInterestValue: price.openInterestValue,
    openInterestUnit: "COIN",
    openInterestValueUnit: "USDT",
    fundingRate: price.fundingRate,
    fundingRatePct: fundingRateToPct(price.fundingRate),
    nextFundingTime: price.nextFundingTime,
    volume24h: price.volume24h,
    volumeUnit: "COIN",
    turnover24h: price.turnover24h,
    turnoverUnit: "USDT",
    source: "BYBIT_MAINNET_LINEAR",
    exchangeTimestamp: price.exchangeTimestamp,
    receivedAt: price.receivedAt,
    status: fieldStatus(price.ageMs, hasDeriv),
    ...oiSnap,
  };
}

/**
 * Evidence labels for display only — NOT recommendation scoring (MVP-22B).
 * Transparent heuristics for operator confirmation.
 */
export function labelDerivativesEvidence(
  ctx: DerivativesMarketContext | undefined,
  recommendation: string,
): {
  oi: EvidenceLabel;
  funding: EvidenceLabel;
  volume: EvidenceLabel;
  note: string;
} {
  const note =
    "Market context shown for confirmation; not yet included in recommendation scoring.";
  if (!ctx || ctx.status === "UNAVAILABLE" || ctx.status === "STALE") {
    return { oi: "unavailable", funding: "unavailable", volume: "unavailable", note };
  }
  const rec = recommendation.toUpperCase();
  const wantLong = rec === "LONG" || rec === "HOLD" || rec === "WAIT" || rec === "MONITOR";
  const wantShort = rec === "SHORT";

  let oi: EvidenceLabel = "neutral";
  if (ctx.oiWindow.m5 === "collecting" || ctx.oiChange5mPct == null) oi = "unavailable";
  else if (Math.abs(ctx.oiChange5mPct) < 0.05) oi = "neutral";
  else if (wantShort) oi = ctx.oiChange5mPct > 0 ? "conflicting" : "supportive";
  else if (wantLong) oi = ctx.oiChange5mPct > 0 ? "supportive" : "conflicting";

  let funding: EvidenceLabel = "neutral";
  const fr = ctx.fundingRatePct;
  if (fr == null) funding = "unavailable";
  else if (Math.abs(fr) < 0.003) funding = "neutral";
  else if (wantLong) funding = fr < 0 ? "supportive" : "conflicting";
  else if (wantShort) funding = fr > 0 ? "supportive" : "conflicting";

  const volume: EvidenceLabel =
    ctx.turnover24h == null && ctx.volume24h == null ? "unavailable" : "neutral";

  return { oi, funding, volume, note };
}

export function formatCompactQty(n: number | undefined | null, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "Unavailable";
  if (Math.abs(n) >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
  return n.toFixed(digits);
}

export function formatOiChange(pct: number | null | undefined, window: "ready" | "collecting"): string {
  if (window === "collecting" || pct == null) return "Collecting";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}
