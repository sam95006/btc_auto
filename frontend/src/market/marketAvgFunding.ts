/**
 * Market average funding — derived from real scanner candidate fundingRate values.
 * Never treats missing as 0.
 */

import { formatFundingPct, fundingBias, fundingRateToPct } from "./fundingConfig";
import { fetchScannerCandidates, type MarketCandidate } from "./scannerApi";
import { errorMetric, pendingMetric, type ParityMetric } from "./parityContracts";

export type AvgFundingValue = {
  avgRate: number;
  avgPct: number;
  display: string;
  bias: string;
};

function collectRates(candidates: MarketCandidate[]): number[] {
  const rates: number[] = [];
  for (const c of candidates) {
    if (c.fundingRate == null || !Number.isFinite(c.fundingRate)) continue;
    rates.push(c.fundingRate);
  }
  return rates;
}

export function computeAvgFunding(
  candidates: MarketCandidate[],
  freshness?: string | null,
): ParityMetric<AvgFundingValue> {
  const rates = collectRates(candidates);
  if (!rates.length) {
    return {
      ...pendingMetric<AvgFundingValue>("市場平均 Funding", "scanner.candidates"),
      freshness: freshness || "更新時間未知",
      coverageNote: "掃描候選尚無可用 fundingRate",
      status: "pending",
    };
  }
  const sum = rates.reduce((a, b) => a + b, 0);
  const avgRate = sum / rates.length;
  const avgPct = fundingRateToPct(avgRate);
  if (avgPct == null) {
    return pendingMetric<AvgFundingValue>("市場平均 Funding", "scanner.candidates");
  }
  return {
    status: "live",
    value: {
      avgRate,
      avgPct,
      display: formatFundingPct(avgRate),
      bias: String(fundingBias(avgRate)),
    },
    label: "市場平均 Funding",
    freshness: freshness || "更新時間未知",
    sampleCount: rates.length,
    coverageNote: `以 ${rates.length} 個有 Funding 的掃描候選計算（非全市場保證）`,
    error: null,
    source: "scanner.candidates",
  };
}

export async function fetchAvgFundingMetric(): Promise<ParityMetric<AvgFundingValue>> {
  try {
    const body = await fetchScannerCandidates(undefined, 40);
    return computeAvgFunding(body.candidates || [], body.freshness);
  } catch (e) {
    return errorMetric<AvgFundingValue>(
      "市場平均 Funding",
      "scanner.candidates",
      e instanceof Error ? e.message : "fetch_failed",
    );
  }
}
