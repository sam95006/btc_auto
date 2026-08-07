/**
 * V18.2.7 LIVE / freshness data-truth mapping for public Actual Panel surfaces.
 * Prevents: stale_as_live · fixture_as_live · unavailable_as_zero · global_live_overclaim.
 */

export type FreshnessTone = "live" | "degraded" | "delayed" | "stale" | "collecting" | "unavailable";

export type FreshnessDisplay = {
  raw: string;
  label: string;
  tone: FreshnessTone;
  /** True when a LIVE claim would overstate freshness. */
  global_live_overclaim: boolean;
  stale_as_live: boolean;
  fixture_as_live: boolean;
  unavailable_as_zero: boolean;
};

const FIXTURE_MARKERS = /FIXTURE|DEMO|MOCK|SAMPLE/i;

export type FreshnessContext = {
  wsConnected?: boolean | null;
  lastError?: string | null;
  source?: string | null;
  valueSource?: string | null;
  /** When eligible/confirmed is 0, do not present plain LIVE as global trust. */
  confirmedCandidates?: number | null;
};

export function mapMarketFreshnessDisplay(
  rawIn: string | null | undefined,
  ctx: FreshnessContext = {},
): FreshnessDisplay {
  const raw = (rawIn || "").trim();
  const upper = raw.toUpperCase();
  const sourceBlob = `${ctx.source || ""} ${ctx.valueSource || ""}`;
  const fixture = FIXTURE_MARKERS.test(sourceBlob) || FIXTURE_MARKERS.test(upper);

  let tone: FreshnessTone = "unavailable";
  let label = "更新時間未知";
  let staleAsLive = false;
  let fixtureAsLive = false;
  let overclaim = false;

  if (!raw || upper === "UNAVAILABLE" || upper === "—" || upper === "UNKNOWN") {
    return {
      raw: raw || "UNAVAILABLE",
      label: "資料不可用",
      tone: "unavailable",
      global_live_overclaim: false,
      stale_as_live: false,
      fixture_as_live: false,
      unavailable_as_zero: false,
    };
  }

  if (upper === "STALE") {
    tone = "stale";
    label = "資料過期";
  } else if (upper === "DELAYED") {
    tone = "delayed";
    label = "延遲";
  } else if (upper === "COLLECTING") {
    tone = "collecting";
    label = "資料累積中";
  } else if (upper === "DEGRADED" || upper === "LIVE_PARTIAL_DEGRADED") {
    tone = "degraded";
    label = "部分即時／資料降級";
  } else if (upper === "LIVE" || upper === "FRESH") {
    if (fixture) {
      tone = "degraded";
      label = "示範資料（非即時）";
      fixtureAsLive = true;
      overclaim = true;
    } else if (ctx.lastError || ctx.wsConnected === false) {
      tone = "degraded";
      label = "部分即時／資料降級";
      overclaim = true;
    } else if (ctx.confirmedCandidates === 0) {
      tone = "degraded";
      label = "部分即時／資料降級";
      overclaim = true;
    } else {
      tone = "live";
      label = "即時";
    }
  } else {
    // Unknown token — never upgrade to LIVE
    tone = "degraded";
    label = raw;
  }

  // Guard: never present STALE/DELAYED as LIVE (caller misuse)
  if ((upper === "STALE" || upper === "DELAYED") && label === "即時") {
    staleAsLive = true;
    label = upper === "STALE" ? "資料過期" : "延遲";
    tone = upper === "STALE" ? "stale" : "delayed";
  }

  return {
    raw,
    label,
    tone,
    global_live_overclaim: overclaim,
    stale_as_live: staleAsLive,
    fixture_as_live: fixtureAsLive,
    unavailable_as_zero: false,
  };
}

/** Founder funnel stage definitions (labels only — do not mix listing vs validated counts). */
export const FUNNEL_METRIC_DEFINITIONS = [
  {
    key: "discovery",
    label: "全市場發現",
    definition: "交易所可觀察 linear 上市／廣度列舉數（sectors.breadthMarketCount）",
  },
  {
    key: "data_valid",
    label: "資料有效",
    definition: "通過基礎欄位與流動性門檻、可納入掃描的標的",
  },
  {
    key: "monitoring",
    label: "即時監控",
    definition: "執行期深度追蹤池（scanner.status.symbolCount，≠ 全市場上市數）",
  },
  {
    key: "safety_review",
    label: "安全審查",
    definition: "風險／過熱／資料品質閘門審查中的候選",
  },
  {
    key: "eligible",
    label: "Eligible",
    definition: "通過安全條件的 confirmedCandidates（可顯示為機會）",
  },
  {
    key: "candidate",
    label: "Candidate",
    definition: "做多／做空觀察候選（未必 Eligible；不可視為可執行建議）",
  },
] as const;

/**
 * When eligible==0, tradable/top opportunity cards must be 0.
 * Watch-only rows do not count toward this metric.
 */
export function eligibleZeroFalseOpportunityCount(args: {
  eligible: number | null | undefined;
  renderedTradableOpportunityCount: number;
}): number {
  const elig = args.eligible;
  if (elig == null) return 0;
  if (Number(elig) !== 0) return 0;
  return Math.max(0, args.renderedTradableOpportunityCount);
}
