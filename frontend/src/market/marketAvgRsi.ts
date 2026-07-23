/**
 * Market average RSI contract.
 * Per-symbol rsi_14 exists on workbench indicators; no market-average backend yet.
 * Never invents or coerces missing→0.
 */

import { pendingMetric, type ParityMetric } from "./parityContracts";

export type AvgRsiValue = {
  avgRsi: number;
  period: number;
};

/**
 * Honest pending metric until a market-average RSI endpoint exists.
 */
export function getMarketAvgRsiMetric(): ParityMetric<AvgRsiValue> {
  return {
    ...pendingMetric<AvgRsiValue>(
      "市場平均 RSI",
      "markets.indicators",
      "無市場平均 RSI API · 標的層 rsi_14 見工作台 Structure 分頁",
    ),
    freshness: "更新時間未知",
  };
}

/** Probe helper reserved for future backend; currently always pending. */
export async function fetchMarketAvgRsiMetric(): Promise<ParityMetric<AvgRsiValue>> {
  return getMarketAvgRsiMetric();
}
