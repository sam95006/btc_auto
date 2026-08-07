/**
 * Layered market metrics — never mix discovery count with runtime-validated count.
 * Founder funnel: 全市場發現 → 資料有效 → 即時監控 → 安全審查 → Eligible → Candidate
 */

export type MarketMetricDef = {
  metric_name: string;
  label_zh: string;
  definition: string;
  source: string;
  current_value: number | null | undefined;
  freshness?: string | null;
};

export function buildMarketMetricFunnel(input: {
  breadthMarketCount?: number | null;
  dataValidCount?: number | null;
  deepScanCount?: number | null;
  symbolCount?: number | null;
  highRiskCandidates?: number | null;
  confirmedCandidates?: number | null;
  longCandidates?: number | null;
  shortCandidates?: number | null;
  freshness?: string | null;
  runtimeObservable?: number | null;
}): MarketMetricDef[] {
  const watchPool =
    (input.longCandidates ?? 0) + (input.shortCandidates ?? 0) || undefined;
  return [
    {
      metric_name: "market_discovery",
      label_zh: "全市場發現",
      definition: "交易所公開可列舉的 linear 市場總數（廣度層，未全部即時訂閱）",
      source: "GET /api/market/sectors/status → breadthMarketCount",
      current_value: input.breadthMarketCount,
      freshness: input.freshness,
    },
    {
      metric_name: "data_valid",
      label_zh: "資料有效",
      definition: "通過基礎欄位與流動性門檻、可納入掃描的標的（≠ 上市總數）",
      source: "scanner.universe.eligible_before_limit / sectors.validMarketCount",
      current_value: input.dataValidCount ?? input.deepScanCount ?? input.symbolCount,
      freshness: input.freshness,
    },
    {
      metric_name: "runtime_observable",
      label_zh: "即時監控",
      definition: "當前 Runtime／Scanner 實際訂閱或觀測中的合約快照（scanner.symbolCount）",
      source: "scanner.status.symbolCount",
      current_value: input.runtimeObservable ?? input.symbolCount,
      freshness: input.freshness,
    },
    {
      metric_name: "safety_review",
      label_zh: "安全審查",
      definition: "風險／過熱／資料品質閘門審查中或阻擋的候選",
      source: "scanner.status.highRiskCandidates",
      current_value: input.highRiskCandidates,
      freshness: input.freshness,
    },
    {
      metric_name: "eligible",
      label_zh: "Eligible",
      definition: "通過確認／安全閘門的合格市場機會（confirmedCandidates）",
      source: "scanner.status.confirmedCandidates",
      current_value: input.confirmedCandidates,
      freshness: input.freshness,
    },
    {
      metric_name: "candidate",
      label_zh: "Candidate",
      definition: "未通過合格閘門、僅供觀察的 LONG/SHORT 池（不可視為交易建議）",
      source: "longCandidates + shortCandidates",
      current_value: watchPool,
      freshness: input.freshness,
    },
  ];
}

/** Map scanner freshness to member-facing trust label (no LIVE overclaim when degraded). */
export function memberDataTrustLabel(input: {
  scannerFreshness?: string | null;
  confirmedCandidates?: number | null;
  highRiskCandidates?: number | null;
  wsConnected?: boolean | null;
  lastError?: string | null;
}): { code: string; label_zh: string; global_live_overclaim: boolean } {
  const fresh = String(input.scannerFreshness || "").toUpperCase();
  const eligible = input.confirmedCandidates ?? null;
  if (fresh === "STALE") {
    return { code: "STALE", label_zh: "過期", global_live_overclaim: false };
  }
  if (fresh === "DELAYED") {
    return { code: "DELAYED", label_zh: "延遲", global_live_overclaim: false };
  }
  if (fresh === "DEGRADED" || fresh === "LIVE_PARTIAL_DEGRADED") {
    return {
      code: "LIVE_PARTIAL_DEGRADED",
      label_zh: "部分即時／資料降級",
      global_live_overclaim: false,
    };
  }
  if (
    fresh === "LIVE" &&
    (eligible === 0 || input.lastError || input.wsConnected === false)
  ) {
    return {
      code: "LIVE_PARTIAL_DEGRADED",
      label_zh: "部分即時／資料降級",
      global_live_overclaim: true,
    };
  }
  if (fresh === "LIVE") {
    return { code: "LIVE", label_zh: "即時", global_live_overclaim: false };
  }
  if (!fresh || fresh === "—" || fresh === "UNKNOWN" || fresh === "UNAVAILABLE") {
    return { code: "UNAVAILABLE", label_zh: "資料狀態未知", global_live_overclaim: false };
  }
  return { code: fresh, label_zh: fresh, global_live_overclaim: false };
}
