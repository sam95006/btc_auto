/**
 * Market average RSI — derived from per-symbol indicators endpoint.
 * Fetches rsi_14 for key symbols and computes an honest average.
 * Never invents or coerces missing→0.
 */

import { errorMetric, pendingMetric, type ParityMetric } from "./parityContracts";

export type AvgRsiValue = {
  avgRsi: number;
  period: number;
};

const PROBE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];

type IndicatorResponse = {
  ok: boolean;
  symbol: string;
  indicators?: { rsi_14?: number | null };
  barCount?: number;
};

async function fetchSymbolRsi(symbol: string): Promise<number | null> {
  try {
    const res = await fetch(
      `/api/nexus/markets/${encodeURIComponent(symbol)}/indicators?interval=5m&limit=60`,
      { cache: "no-store", headers: { Accept: "application/json" } },
    );
    if (!res.ok) return null;
    const body = (await res.json()) as IndicatorResponse;
    if (!body.ok) return null;
    const val = body.indicators?.rsi_14;
    if (val == null || !Number.isFinite(val)) return null;
    return val;
  } catch {
    return null;
  }
}

/**
 * Honest pending metric for sync callers — no data yet.
 */
export function getMarketAvgRsiMetric(): ParityMetric<AvgRsiValue> {
  return {
    ...pendingMetric<AvgRsiValue>(
      "市場平均 RSI",
      "markets.indicators",
      "載入中 · 自 BTC/ETH/SOL 指標導出",
    ),
    freshness: "載入中…",
  };
}

export async function fetchMarketAvgRsiMetric(): Promise<ParityMetric<AvgRsiValue>> {
  try {
    const results = await Promise.all(PROBE_SYMBOLS.map(fetchSymbolRsi));
    const valid = results.filter((v): v is number => v != null);

    if (!valid.length) {
      return {
        ...pendingMetric<AvgRsiValue>(
          "市場平均 RSI",
          "markets.indicators",
          "指標端點無可用 rsi_14 · 標的層見工作台 Structure 分頁",
        ),
        freshness: new Date().toLocaleTimeString(),
      };
    }

    const avg = valid.reduce((a, b) => a + b, 0) / valid.length;
    return {
      status: "live",
      value: { avgRsi: Math.round(avg * 10) / 10, period: 14 },
      label: "市場平均 RSI",
      freshness: new Date().toLocaleTimeString(),
      sampleCount: valid.length,
      coverageNote: `以 ${valid.length}/${PROBE_SYMBOLS.length} 個主要標的 5m rsi_14 計算（非全市場）`,
      error: null,
      source: "markets.indicators",
    };
  } catch (e) {
    return errorMetric<AvgRsiValue>(
      "市場平均 RSI",
      "markets.indicators",
      e instanceof Error ? e.message : "fetch_failed",
    );
  }
}
